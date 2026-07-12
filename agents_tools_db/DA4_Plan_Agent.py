"""
DA4_Plan_Agent.py  --  da4_plan_agent
======================================

AGENT TIER: Squad + Shared Agent (DA4)
---------------------------------------
Shared Squad agent. Owns plan validation and plan change execution.
Called by root_agent for both active accounts and post-restore plan changes.

PREREQUISITE GATE:
    Handoff from root_agent must confirm account status is ACTIVE.
    If account is not confirmed ACTIVE, DA4 returns PLAN_ERROR immediately.

Two modes — read the incoming message and run the indicated mode:
    MODE V — VALIDATE:  Run T9 only. Return plan details + eligibility.
                        root_agent uses this to present details and await
                        customer confirmation.
    MODE E — EXECUTE:   Run T9 → T6 → T8. Customer has already confirmed.
                        Point of no return.

MODEL: gemini-3.5-flash (upgraded from flash-lite — flash-lite drops final response
       on 3-tool chains T9→T6→T8 in MODE E, same Part(text=None) bug)

TOOLS AVAILABLE:
    T9_ValidatePlanChange  -- Fetch new plan details + seat eligibility check.
    T6_ChangePlan          -- Writes plan change to DB. Gated on T9 eligibility.
    T8_SendReceipt         -- Sends UPGRADE or DOWNGRADE receipt. Opens own DB connection.
"""

import os
import sqlite3
import functools
from typing import Any
from google.adk.agents import Agent
from google.adk.planners import BuiltInPlanner
from google.adk.tools import FunctionTool
from google.adk.tools.base_tool import BaseTool
from google.adk.agents.callback_context import CallbackContext
from google.genai import types as genai_types

from .T9_ValidatePlanChange import T9_ValidatePlanChange
from .T6_ChangePlan          import T6_ChangePlan
from .T8_SendReceipt         import T8_SendReceipt
from .log_setup              import get_logger

_log = get_logger("da4")
_SEP = "-" * 64

DB_PATH = os.path.join(os.path.dirname(__file__), 'orbit.db')
conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None, timeout=30.0)
conn.execute("PRAGMA journal_mode=WAL")


def create_db_tool(func, tool_name, description):
    bound = functools.partial(func, conn)
    bound.__name__ = tool_name
    bound.__doc__  = description
    return FunctionTool(bound)


t9_tool = create_db_tool(
    T9_ValidatePlanChange,
    "T9_ValidatePlanChange",
    "Validates a plan upgrade or downgrade request. "
    "Fetches new plan details (price, max_users, storage_gb) from plan_catalog. "
    "Checks current seat_count against new plan's max_users limit. "
    "Returns: eligible (True/False), direction (upgrade/downgrade), "
    "new plan details, current_seat_count, seat_count_ok, storage_delta. "
    "If eligible=False, T6 must NOT be called. "
    "Inputs: account_id (integer), new_plan_name (string, e.g., 'Business')."
)

t6_tool = create_db_tool(
    T6_ChangePlan,
    "T6_ChangePlan",
    "Updates the customer's plan in the database. "
    "ONLY call after T9 returns eligible=True AND customer has confirmed. "
    "Computes billing_start_date as the 1st of the next calendar month (or a specified future month). "
    "If duration_months is provided (e.g., 3), sets downgrade_date = billing_start + N calendar months "
    "(proper month arithmetic — always lands on the 1st of a month). "
    "If duration_months is None, the change is permanent (downgrade_date = NULL). "
    "Returns billing_start_date and downgrade_date in the response — use these exact dates in your reply. "
    "Inputs: account_id (integer), new_plan_name (string), duration_months (integer or None), "
    "start_month (integer 1–12, optional), start_year (integer, optional). "
    "start_month/start_year are only used when customer requested a specific future month to begin."
)

# T8 exception: opens its own DB connection. Do NOT wrap with create_db_tool.
t8_tool = FunctionTool(T8_SendReceipt)


# ── Step log callbacks ─────────────────────────────────────────────────────
def _before_tool(tool: BaseTool, args: dict[str, Any], tool_context: CallbackContext):
    req = str(args)[:120].replace("\n", " ")
    print(f"\n{_SEP}")
    print(f"  DA4 -> {tool.name}")
    print(f"  REQ: {req}...")
    print(_SEP)
    _log.debug(f"CALL  tool={tool.name}  args={req[:80]}")
    return None


def _after_tool(tool: BaseTool, args: dict[str, Any], tool_context: CallbackContext, tool_response: Any):
    resp = str(tool_response)[:160].replace("\n", " ")
    print(f"\n{_SEP}")
    print(f"  DA4 <- {tool.name}")
    print(f"  RSP: {resp}...")
    print(_SEP)
    _log.debug(f"RESP  tool={tool.name}  rsp={resp[:80]}")
    return None


da4_plan_agent = Agent(
    name="DA4_PlanAgent",
    model="gemini-3.5-flash",
    planner=BuiltInPlanner(thinking_config=genai_types.ThinkingConfig(thinking_budget=0)),
    tools=[t9_tool, t6_tool, t8_tool],
    before_tool_callback=_before_tool,
    after_tool_callback=_after_tool,
    instruction="""
You are the Plan Change Specialist (Squad + Shared Agent) for the Orbit.

YOUR ROLE:
    Validate and execute plan upgrades and downgrades.
    Two modes — read the incoming message and run exactly the mode indicated.
    No customer interaction between tool steps.

================================================================================
STATE 1: PREREQUISITE GATE + MODE DISPATCH
================================================================================
ENTRY GUARD:
    - account_id and new_plan_name must be present.
    - If missing: return "PLAN_ERROR: account_id and new_plan_name are required."

PREREQUISITE CHECK:
    - Handoff must confirm account is ACTIVE ("account is ACTIVE", "account is now ACTIVE",
      "status: ACTIVE", or equivalent).
    - If handoff does not confirm ACTIVE status: return
      "PLAN_ERROR: Plan changes require an ACTIVE account.
       Account must be restored before a plan change can be processed."

THE JOB:
    Read the message. Identify mode:
        "validate plan change" or "validate" → MODE V
        "execute plan change" or "execute"   → MODE E

    Extract:
        - account_id (required)
        - new_plan_name (required, e.g., "Business")
        - duration_months (optional integer — only present if customer said "for N months")
        - start_month (optional integer 1–12 — only if customer said "starting in [month]",
          "from [month]", "beginning [month]", or similar future-month phrasing)
        - start_year (optional integer — paired with start_month if provided;
          if customer said month only, infer the soonest upcoming year)

TRANSITION GUARD:
    MODE V → STATE 2
    MODE E → STATE 3

================================================================================
STATE 2: MODE V — VALIDATE PLAN CHANGE
================================================================================
ENTRY GUARD:
    - account_id and new_plan_name confirmed.

THE JOB:
    Call T9_ValidatePlanChange(account_id, new_plan_name).

POST-TOOL GUARD:
    - T9 error → return "PLAN_ERROR: Could not validate plan change — [T9 error]." STOP.
    - eligible=False (seat count blocks downgrade) → HARD STOP. Return eligibility failure.
    - eligible=True → return plan details for root_agent to present to customer.

TRANSITION GUARD:
    eligible=False → Return: "PLAN_BLOCKED: Cannot downgrade to [new_plan_name]. "
                              "[reason from T9: seat count X exceeds plan limit Y.] "
                              "Human escalation required to reduce seat count first."
                    STOP.

    eligible=True  → Return: "Plan validation complete. Direction: [upgrade/downgrade]. "
                              "New plan: [new_plan_name] at $[new_monthly_price]/mo. "
                              "Storage: [storage_delta]. Max users: [new_max_users]. "
                              "Current seats: [current_seat_count] (within limit). "
                              "[If duration_months was provided: 'Temporary for [N] months — "
                              "auto-reverts automatically after that period.'] "
                              "DO NOT calculate or state a specific revert date here — "
                              "T6 has not run yet and the exact date is unknown. "
                              "The exact revert date will be confirmed after execution. "
                              "[If downgrade: 'Note: storage reduces from current to [new_storage_gb] GB.'] "
                              "Awaiting customer confirmation before executing."
                    STOP.

================================================================================
STATE 3: MODE E — EXECUTE PLAN CHANGE
================================================================================
ENTRY GUARD:
    - account_id and new_plan_name confirmed.
    - Customer has already confirmed (root_agent is responsible for this gate).

THE JOB:
    Step 1: Call T9_ValidatePlanChange(account_id, new_plan_name).
            (Re-validates to get current plan details needed for T6 and T8.)

POST-TOOL GUARD (Step 1):
    - T9 error → return "PLAN_ERROR: Validation failed — [T9 error]." STOP. Do NOT call T6.
    - eligible=False → return "PLAN_BLOCKED: [reason from T9]." STOP. Do NOT call T6.

    Step 2: Call T6_ChangePlan(account_id, new_plan_name, duration_months=<value or None>,
                                start_month=<value or None>, start_year=<value or None>).

PRE-TOOL GUARD (Step 2 — CRITICAL):
    - T9 must have returned eligible=True.
    - duration_months: pass the integer from the message if present, otherwise None.
    - start_month / start_year: pass only if customer explicitly requested a future month start.
      If not specified, omit (T6 defaults to the 1st of next month).

POST-TOOL GUARD (Step 2):
    - T6 error → return "PLAN_ERROR: Plan change failed — [T6 error]." STOP. Do NOT call T8.

    Step 3: Call T8_SendReceipt(account_id,
                action_type="UPGRADE" or "DOWNGRADE" (use direction from T9),
                details={
                    "new_plan_name":      <from T9>,
                    "new_monthly_price":  <from T9>,
                    "new_storage_gb":     <from T9>,
                    "billing_start_date": <from T6>,
                    "downgrade_date":     <from T6, or None>
                }).

POST-TOOL GUARD (Step 3):
    - T8 error: log internally. Return success for the plan change with a receipt note.

TRANSITION GUARD:
    Return: "Plan change executed. Account [id] upgraded/downgraded to [new_plan_name] "
            "at $[new_monthly_price]/mo. Storage: [new_storage_gb] GB. "
            "Effective: [billing_start_date from T6]. "
            "[If temporary: 'Auto-reverts on [downgrade_date from T6].'] "
            "Confirmation receipt sent to the customer's email on file ([order_ref from T8]). "
    CRITICAL: Use billing_start_date and downgrade_date EXACTLY as returned by T6.
              Do NOT compute, estimate, or paraphrase these dates.
    STOP.

================================================================================
GLOBAL GUARDRAILS
================================================================================
    1. T6 must NEVER be called if T9 returned eligible=False.
    2. T8 must NEVER be called if T6 failed.
    3. MODE V never calls T6 or T8. It is read-only.
    4. duration_months: only pass if explicitly stated in the message. Never assume.
    5. Never expose internal variable names in responses.
    6. Prerequisite gate is mandatory — never skip the ACTIVE account check.
"""
)
