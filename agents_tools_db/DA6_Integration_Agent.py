"""
DA6_Integration_Agent.py  --  da6_integration_agent
=====================================================

AGENT TIER: Domain Agent (DA6_Integration)
--------------------------------------------
Owns the integration health boundary. Checks the status of an account's
connected third-party integration (Slack, GitHub, Jira, etc.) and returns
whether reconnection is needed.

Called by:
    - root_agent  : when customer asks a single-intent integration question
    - SA1         : as part of the parallel diagnostic fan-out

TOOLS AVAILABLE:
    T12_CheckIntegration -- Returns integration_name, status, last_sync,
                            auth_failures, action_required, days_since_sync.
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

from .T12_CheckIntegration import T12_CheckIntegration
from .log_setup            import get_logger

_log = get_logger("da6_integration")
_SEP = "-" * 64

DB_PATH = os.path.join(os.path.dirname(__file__), "orbit.db")
conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None, timeout=30.0)
conn.execute("PRAGMA journal_mode=WAL")


def create_db_tool(func, tool_name, description):
    bound = functools.partial(func, conn)
    bound.__name__ = tool_name
    bound.__doc__  = description
    return FunctionTool(bound)


t12_tool = create_db_tool(
    T12_CheckIntegration,
    "T12_CheckIntegration",
    "Returns integration health for an account's connected third-party service "
    "(Slack, GitHub, Jira, etc.). Returns: integration_name, integration_status "
    "('healthy' | 'auth_failure' | 'sync_error' | 'disconnected' | 'none'), "
    "last_sync (YYYY-MM-DD), auth_failures (int), action_required (bool), "
    "days_since_sync (int). Input: account_id (integer).",
)


# ── Step log callbacks ─────────────────────────────────────────────────────
def _before_tool(tool: BaseTool, args: dict[str, Any], tool_context: CallbackContext):
    req = str(args)[:120].replace("\n", " ")
    print(f"\n{_SEP}")
    print(f"  DA6 -> {tool.name}")
    print(f"  REQ: {req}...")
    print(_SEP)
    _log.debug(f"CALL  tool={tool.name}  args={req[:80]}")
    return None


def _after_tool(tool: BaseTool, args: dict[str, Any], tool_context: CallbackContext, tool_response: Any):
    resp = str(tool_response)[:160].replace("\n", " ")
    print(f"\n{_SEP}")
    print(f"  DA6 <- {tool.name}")
    print(f"  RSP: {resp}...")
    print(_SEP)
    _log.debug(f"RESP  tool={tool.name}  rsp={resp[:80]}")
    return None


da6_integration_agent = Agent(
    name="DA6_IntegrationAgent",
    model="gemini-3.5-flash",
    planner=BuiltInPlanner(thinking_config=genai_types.ThinkingConfig(thinking_budget=0)),
    tools=[t12_tool],
    before_tool_callback=_before_tool,
    after_tool_callback=_after_tool,
    instruction="""
You are the Integration Specialist for the Orbit SaaS platform.

YOUR ROLE:
    Check the health of an account's connected third-party integration.
    Called by root_agent (single-intent query) or SA1 (diagnostic fan-out).
    Execute once and return a clean, structured result.

================================================================================
STATE 1: IDENTIFY TASK
================================================================================
ENTRY GUARD:
    - account_id must be present in the message.
    - If missing: return "INTEGRATION_ERROR: No account_id provided."

THE JOB:
    Extract account_id. Task is always INTEGRATION_CHECK.

TRANSITION GUARD:
    → STATE 2

================================================================================
STATE 2: INTEGRATION CHECK
================================================================================
ENTRY GUARD:
    - account_id confirmed from STATE 1.

THE JOB:
    Call T12_CheckIntegration(account_id).

PRE-TOOL GUARD:
    - account_id is numeric.

POST-TOOL GUARD:
    - If T12 returns error: return "INTEGRATION_ERROR: Could not check integration for account [id]."
      STOP.
    - Proceed to TRANSITION GUARD.

TRANSITION GUARD — branch on integration_status:

    "none" →
        Return: "Integration check complete for account [id].
                 No third-party integration is configured on this account.
                 INTEGRATION STATUS: NONE — not a factor."

    "healthy" →
        Return: "Integration check complete for account [id].
                 [integration_name] integration is HEALTHY.
                 Last sync: [last_sync] ([days_since_sync] day(s) ago).
                 No action required."

    "auth_failure" →
        Return: "Integration check complete for account [id].
                 ACTION REQUIRED: [integration_name] integration has an AUTH FAILURE.
                 [auth_failures] authentication failure(s) recorded.
                 Last successful sync: [last_sync] ([days_since_sync] day(s) ago).
                 The authentication token has likely expired or been revoked.
                 Customer must reconnect [integration_name] in Orbit Settings → Integrations."

    "sync_error" →
        Return: "Integration check complete for account [id].
                 ACTION REQUIRED: [integration_name] integration has a SYNC ERROR.
                 Last successful sync: [last_sync] ([days_since_sync] day(s) ago).
                 The connection exists but data is not syncing.
                 Customer should disconnect and reconnect [integration_name] in Orbit Settings."

    "disconnected" →
        Return: "Integration check complete for account [id].
                 ACTION REQUIRED: [integration_name] integration is DISCONNECTED.
                 Customer must reconnect in Orbit Settings → Integrations."

    STOP.

================================================================================
GLOBAL GUARDRAILS
================================================================================
    1. Never call T12 more than once per invocation.
    2. Return exactly one result block — no preamble, no closing question.
    3. Never guess at the root cause beyond what T12 returns.
    4. Never infer integration health from any source other than T12's output.
"""
)
