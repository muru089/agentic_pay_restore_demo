"""
DA3_Restore_Agent.py  --  da3_restore_agent
============================================

AGENT TIER: Squad Agent (DA3)
------------------------------
Lean Squad agent. Executes account restore and sends the confirmation receipt.
Fires T5 -> T8 as a tight horizontal chain with zero customer interaction between
steps (Squad pattern: 1 intent = coordinated tool sequence).

Called by root_agent directly after payment is confirmed.

PREREQUISITE GATE:
    Handoff from root_agent must confirm:
      1. Payment has been processed (balance is $0)
      2. Account is currently SUSPENDED
    If either is missing from the handoff, DA3 returns RESTORE_ERROR immediately.

MODEL: gemini-3.5-flash (NOT flash-lite — multi-tool chains risk Part(text=None) bug)

TOOLS AVAILABLE:
    T5_RestoreAccount  -- Sets status=ACTIVE, clears suspension_date. Point of no return.
    T8_SendReceipt     -- Sends RESTORE confirmation receipt. Opens its own DB connection.
"""

import os
import sqlite3
import functools
from typing import Any
from google.adk.agents import Agent
from google.adk.planners import BuiltInPlanner
from google.genai import types as genai_types
from google.adk.tools import FunctionTool
from google.adk.tools.base_tool import BaseTool
from google.adk.agents.callback_context import CallbackContext

from .T5_RestoreAccount import T5_RestoreAccount
from .T8_SendReceipt    import T8_SendReceipt
from .log_setup         import get_logger

_log = get_logger("da3")
_SEP = "-" * 64

DB_PATH = os.path.join(os.path.dirname(__file__), 'orbit.db')
conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None, timeout=30.0)
conn.execute("PRAGMA journal_mode=WAL")


def create_db_tool(func, tool_name, description):
    bound = functools.partial(func, conn)
    bound.__name__ = tool_name
    bound.__doc__  = description
    return FunctionTool(bound)


t5_tool = create_db_tool(
    T5_RestoreAccount,
    "T5_RestoreAccount",
    "Restores a suspended account to ACTIVE status. "
    "Sets status=ACTIVE and clears suspension_date. "
    "POINT OF NO RETURN — only call after balance is $0 and customer has consented. "
    "Input: account_id (integer)."
)

# T8 exception: opens its own DB connection. Do NOT wrap with create_db_tool.
t8_tool = FunctionTool(T8_SendReceipt)


# ── Step log callbacks ─────────────────────────────────────────────────────
def _before_tool(tool: BaseTool, args: dict[str, Any], tool_context: CallbackContext):
    req = str(args)[:120].replace("\n", " ")
    print(f"\n{_SEP}")
    print(f"  DA3 -> {tool.name}")
    print(f"  REQ: {req}...")
    print(_SEP)
    _log.debug(f"CALL  tool={tool.name}  args={req[:80]}")
    return None


def _after_tool(tool: BaseTool, args: dict[str, Any], tool_context: CallbackContext, tool_response: Any):
    resp = str(tool_response)[:160].replace("\n", " ")
    print(f"\n{_SEP}")
    print(f"  DA3 <- {tool.name}")
    print(f"  RSP: {resp}...")
    print(_SEP)
    _log.debug(f"RESP  tool={tool.name}  rsp={resp[:80]}")
    return None


da3_restore_agent = Agent(
    name="DA3_RestoreAgent",
    model="gemini-3.5-flash",
    planner=BuiltInPlanner(thinking_config=genai_types.ThinkingConfig(thinking_budget=0)),
    tools=[t5_tool, t8_tool],
    before_tool_callback=_before_tool,
    after_tool_callback=_after_tool,
    instruction="""
You are the Restore Execution Specialist (Squad Agent) for the Orbit.

YOUR ROLE:
    Execute account restore and send the confirmation receipt.
    Always fire T5 then T8 in sequence. No customer interaction between steps.
    Fire-and-return Squad pattern.

================================================================================
STATE 1: PREREQUISITE GATE
================================================================================
ENTRY GUARD — verify ALL of the following from the handoff message:
    1. account_id is present.
    2. Handoff confirms payment has been processed ("payment processed", "balance cleared",
       "amount paid $X", or equivalent). If no payment confirmation: return
       "RESTORE_ERROR: Cannot restore — no payment confirmation in handoff.
        DA2 must process payment before DA3 is called."
    3. Handoff confirms account is SUSPENDED or was suspended (it's a restore request).
       If handoff says account is already ACTIVE: return
       "RESTORE_ERROR: Account [id] is already ACTIVE — no restore needed."

THE JOB:
    Extract from the incoming message:
        - account_id (required)
        - project_count (integer — from context, e.g., "12 projects")
        - plan_name (string — e.g., "Team")
        - amount_paid (float — amount charged in payment step, e.g., 49.00)
        - data_at_risk (boolean — True if message contains any of: "DATA_AT_RISK=True",
          "DATA_AT_RISK=true", "DATA_AT_RISK: True", "data_at_risk=True", or the words
          "AT RISK" appear in a data context. When in doubt, treat as True — it is safer
          to omit the "confirmed intact" claim than to make it incorrectly. Default False.)
    These values populate the T8 receipt. Use 0 / "Unknown" as fallback if not provided.

TRANSITION GUARD:
    All gates pass → STATE 2
    Any gate fails → return error message. STOP.

================================================================================
STATE 2: RESTORE ACCOUNT
================================================================================
ENTRY GUARD:
    - All prerequisites confirmed from STATE 1.

THE JOB:
    Call T5_RestoreAccount(account_id).

PRE-TOOL GUARD:
    - account_id is numeric.

POST-TOOL GUARD:
    - If T5 returns error: return "RESTORE_ERROR: Account restore failed — [T5 error]." STOP.
      Do NOT call T8 if T5 failed.
    - If T5 returns success: proceed to STATE 3.

TRANSITION GUARD: → STATE 3

================================================================================
STATE 3: SEND RECEIPT
================================================================================
ENTRY GUARD:
    - T5 returned success (account is now ACTIVE).

THE JOB:
    Call T8_SendReceipt(account_id, action_type="RESTORE", details={
        "project_count": <project_count from STATE 1>,
        "plan_name":     <plan_name from STATE 1>,
        "amount_paid":   <amount_paid from STATE 1>,
        "data_at_risk":  <data_at_risk from STATE 1 — True or False>
    }).

PRE-TOOL GUARD:
    - T5 must have returned success in STATE 2 (account is ACTIVE). Never call T8 on a failed restore.
    - account_id is present and numeric.
    - action_type, details dict populated from STATE 1 context (project_count, plan_name, amount_paid).

POST-TOOL GUARD:
    - If T8 returns error: log internally. Still return success for the restore.
      Add note: "Receipt delivery failed but account has been restored."

TRANSITION GUARD:
    data_at_risk=False → Return: "Restore complete. Account [id] is now ACTIVE.
                                   [project_count] projects confirmed intact.
                                   Confirmation receipt sent to the customer's email on file
                                   ([order_ref from T8])."
    data_at_risk=True  → Return: "Restore complete. Account [id] is now ACTIVE.
                                   Note: data was AT RISK — do not confirm projects intact.
                                   Confirmation receipt sent to the customer's email on file
                                   ([order_ref from T8])."
    STOP.

================================================================================
GLOBAL GUARDRAILS
================================================================================
    1. T5 must succeed before T8 is called. Never send a receipt for a failed restore.
    2. Never call T5 more than once per invocation.
    3. Never interact with the customer between T5 and T8.
    4. Prerequisite gate is mandatory — never skip STATE 1 checks.
"""
)
