"""
DA3_Restore_Agent.py  --  da3_restore_agent
============================================

AGENT TIER: Squad Agent (DA3)
------------------------------
Lean Squad agent. Executes account restore and sends the confirmation receipt.
Fires T5 -> T8 as a tight horizontal chain with zero customer interaction between
steps (Squad pattern: 1 intent = coordinated tool sequence).

Called by SA1_RestoreSupervisor only after balance is $0 and customer has consented.
Never called by root_agent directly.

MODEL: gemini-2.5-flash (NOT flash-lite — multi-tool chains risk Part(text=None) bug)

TOOLS AVAILABLE:
    T5_RestoreAccount  -- Sets status=ACTIVE, clears suspension_date. Point of no return.
    T8_SendReceipt     -- Sends RESTORE confirmation receipt. Opens its own DB connection.
"""

import os
import sqlite3
import functools
from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from .T5_RestoreAccount import T5_RestoreAccount
from .T8_SendReceipt    import T8_SendReceipt

DB_PATH = os.path.join(os.path.dirname(__file__), 'pay_restore.db')
conn = sqlite3.connect(DB_PATH, check_same_thread=False)


def create_db_tool(func, tool_name, description):
    bound = functools.partial(func, conn=conn)
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


da3_restore_agent = Agent(
    name="DA3_RestoreAgent",
    model="gemini-2.5-flash",
    tools=[t5_tool, t8_tool],
    instruction="""
You are the Restore Execution Specialist (Squad Agent) for the Pay Restore SaaS platform.

YOUR ROLE:
    Execute account restore and send the confirmation receipt.
    Always fire T5 then T8 in sequence. No customer interaction between steps.
    Fire-and-return Squad pattern.

================================================================================
STATE 1: VALIDATE INPUTS
================================================================================
ENTRY GUARD:
    - account_id must be present in the message.
    - If missing: return "RESTORE_ERROR: No account_id provided."

THE JOB:
    Extract from the incoming message:
        - account_id (required)
        - project_count (integer — from SA1's context, e.g., "12 projects")
        - plan_name (string — e.g., "Team")
        - amount_paid (float — amount charged in payment step, e.g., 49.00)
        - data_at_risk (boolean — True if message contains "DATA_AT_RISK=True", else False)
    These values populate the T8 receipt. Use 0 / "Unknown" as fallback if not provided.

TRANSITION GUARD: → STATE 2

================================================================================
STATE 2: RESTORE ACCOUNT
================================================================================
ENTRY GUARD:
    - account_id confirmed from STATE 1.
    - SA1 has confirmed balance is $0 and customer has consented before calling DA3.

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
        "amount_paid":   <amount_paid from STATE 1>
    }).

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
"""
)
