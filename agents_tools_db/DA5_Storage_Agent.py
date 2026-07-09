"""
DA5_Storage_Agent.py  --  da5_storage_agent
============================================

AGENT TIER: Domain Agent (DA5_Storage)
----------------------------------------
Owns the storage boundary. Checks how much storage an account is consuming
relative to its plan limit and returns a structured health result.

Called by:
    - root_agent  : when customer asks a single-intent storage question
    - SA1         : as part of the parallel diagnostic fan-out

TOOLS AVAILABLE:
    T11_CheckStorage -- Returns used_gb, plan_gb, used_pct, near_limit, headroom_gb.
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

from .T11_CheckStorage import T11_CheckStorage
from .log_setup        import get_logger

_log = get_logger("da5_storage")
_SEP = "-" * 64

DB_PATH = os.path.join(os.path.dirname(__file__), "orbit.db")
conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None, timeout=30.0)
conn.execute("PRAGMA journal_mode=WAL")


def create_db_tool(func, tool_name, description):
    bound = functools.partial(func, conn)
    bound.__name__ = tool_name
    bound.__doc__  = description
    return FunctionTool(bound)


t11_tool = create_db_tool(
    T11_CheckStorage,
    "T11_CheckStorage",
    "Returns current storage consumption for an account vs its plan limit. "
    "Returns: storage_used_gb, plan_storage_gb, used_pct (0-100), "
    "near_limit (True if used_pct >= 90), headroom_gb, plan_name. "
    "Input: account_id (integer).",
)


# ── Step log callbacks ─────────────────────────────────────────────────────
def _before_tool(tool: BaseTool, args: dict[str, Any], tool_context: CallbackContext):
    req = str(args)[:120].replace("\n", " ")
    print(f"\n{_SEP}")
    print(f"  DA5 -> {tool.name}")
    print(f"  REQ: {req}...")
    print(_SEP)
    _log.debug(f"CALL  tool={tool.name}  args={req[:80]}")
    return None


def _after_tool(tool: BaseTool, args: dict[str, Any], tool_context: CallbackContext, tool_response: Any):
    resp = str(tool_response)[:160].replace("\n", " ")
    print(f"\n{_SEP}")
    print(f"  DA5 <- {tool.name}")
    print(f"  RSP: {resp}...")
    print(_SEP)
    _log.debug(f"RESP  tool={tool.name}  rsp={resp[:80]}")
    return None


da5_storage_agent = Agent(
    name="DA5_StorageAgent",
    model="gemini-3.5-flash",
    planner=BuiltInPlanner(thinking_config=genai_types.ThinkingConfig(thinking_budget=0)),
    tools=[t11_tool],
    before_tool_callback=_before_tool,
    after_tool_callback=_after_tool,
    instruction="""
You are the Storage Specialist for the Orbit SaaS platform.

YOUR ROLE:
    Check an account's current storage consumption against its plan limit.
    Called by root_agent (single-intent query) or SA1 (diagnostic fan-out).
    Execute once and return a clean, structured result.

================================================================================
STATE 1: IDENTIFY TASK
================================================================================
ENTRY GUARD:
    - account_id must be present in the message.
    - If missing: return "STORAGE_ERROR: No account_id provided."

THE JOB:
    Extract account_id. Task is always STORAGE_CHECK.

TRANSITION GUARD:
    → STATE 2

================================================================================
STATE 2: STORAGE CHECK
================================================================================
ENTRY GUARD:
    - account_id confirmed from STATE 1.

THE JOB:
    Call T11_CheckStorage(account_id).

PRE-TOOL GUARD:
    - account_id is numeric.

POST-TOOL GUARD:
    - If T11 returns error: return "STORAGE_ERROR: Could not check storage for account [id]."
      STOP.
    - Proceed to TRANSITION GUARD.

TRANSITION GUARD:
    near_limit=False →
        Return: "Storage check complete for account [id]. Using [used_gb] GB of
                 [plan_gb] GB ([used_pct]%) on the [plan_name] plan.
                 [headroom_gb] GB remaining. Storage is HEALTHY — no action needed."

    near_limit=True →
        Return: "Storage check complete for account [id]. NEAR LIMIT: using [used_gb] GB
                 of [plan_gb] GB ([used_pct]%) on the [plan_name] plan.
                 Only [headroom_gb] GB remaining. This is likely causing upload failures
                 and slow project loading. ACTION REQUIRED: upgrade to a higher plan or
                 archive old projects to free space."

    STOP.

================================================================================
GLOBAL GUARDRAILS
================================================================================
    1. Never call T11 more than once per invocation.
    2. Return exactly one result block — no preamble, no closing question.
    3. Never make plan upgrade recommendations that name a specific plan price.
       Let root_agent handle pricing details.
    4. Never infer storage health from any source other than T11's output.
"""
)
