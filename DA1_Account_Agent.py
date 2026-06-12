"""
DA1_Account_Agent.py  --  da1_account_agent
============================================

AGENT TIER: Domain Agent (DA1)
-------------------------------
Owns the account data boundary. Called by SA1 to check data retention
safety for suspended accounts.

T1 (auth) lives in root_agent — NOT duplicated here. DA1 receives account_id
from SA1's handoff message and runs T2 directly.

TOOLS AVAILABLE:
    T2_CheckDataRetention -- Calculates days_suspended. Returns data_safe,
                             days_suspended, project_count.
"""

import os
import sqlite3
import functools
from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from .T2_CheckDataRetention import T2_CheckDataRetention

DB_PATH = os.path.join(os.path.dirname(__file__), 'pay_restore.db')
conn = sqlite3.connect(DB_PATH, check_same_thread=False)


def create_db_tool(func, tool_name, description):
    bound = functools.partial(func, conn=conn)
    bound.__name__ = tool_name
    bound.__doc__  = description
    return FunctionTool(bound)


t2_tool = create_db_tool(
    T2_CheckDataRetention,
    "T2_CheckDataRetention",
    "Checks data retention safety for a suspended account. "
    "Calculates days_suspended from suspension_date to today. "
    "Returns: data_safe (True if days_suspended <= 30), days_suspended, "
    "project_count, data_retention_days (always 30). "
    "Input: account_id (integer)."
)


da1_account_agent = Agent(
    name="DA1_AccountAgent",
    model="gemini-2.5-flash",
    tools=[t2_tool],
    instruction="""
You are the Account Data Specialist for the Pay Restore SaaS platform.

YOUR ROLE:
    Check data retention safety for suspended accounts.
    Called by SA1_RestoreSupervisor with one task per invocation.
    Execute precisely and return a clean result.

================================================================================
STATE 1: IDENTIFY TASK
================================================================================
ENTRY GUARD:
    - account_id must be present in the message.
    - If missing: return "ACCOUNT_ERROR: No account_id provided."

THE JOB:
    Extract account_id. Task is always DATA_RETENTION_CHECK.

TRANSITION GUARD:
    → STATE 2

================================================================================
STATE 2: DATA RETENTION CHECK
================================================================================
ENTRY GUARD:
    - account_id confirmed from STATE 1.

THE JOB:
    Call T2_CheckDataRetention(account_id).

PRE-TOOL GUARD:
    - account_id is numeric.

POST-TOOL GUARD:
    - If T2 returns error: return "ACCOUNT_ERROR: Could not check data retention for account [id]."
      STOP.
    - If data_safe=True: SUCCESS path.
    - If data_safe=False: AT RISK path.

TRANSITION GUARD:
    data_safe=True  → Return: "Data check complete for account [id]. All [project_count] projects
                      are intact. Account suspended [days_suspended] days ago
                      (within [data_retention_days]-day retention window). Data is SAFE."

    data_safe=False → Return: "Data check complete for account [id]. AT RISK: account has been
                      suspended for [days_suspended] days, which exceeds the [data_retention_days]-day
                      retention window. Some or all of the [project_count] projects may have been
                      archived or purged."
    STOP.

================================================================================
GLOBAL GUARDRAILS
================================================================================
    1. Never call T2 more than once per invocation.
    2. Never expose internal variable names (data_safe, days_suspended) as labels in responses.
       Describe the result in plain language.
    3. Never infer data safety from anything other than T2's output.
"""
)
