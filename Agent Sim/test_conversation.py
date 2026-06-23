"""
test_conversation.py -- Orbit Demo: Automated Conversation Test
======================================================================
Tests the multi-agent restore flow via ADK Runner.
Run from c:\\Muru_Workspace (parent of pay_restore_demo):

    python "pay_restore_demo/Agent Sim/test_conversation.py"

Select a persona below by uncommenting its TURNS + USER_ID block.
Currently ACTIVE: Persona 1 -- Alex (20001), primary demo happy path.
"""

import asyncio
import sys
import os
import io
import traceback as _tb

# Force UTF-8 output on Windows (avoids cp1252 crashes on unicode chars)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Disable experimental progressive SSE streaming -- it produces Part(text=None)
# events after multi-tool chains, causing agent_tool.py to return '' instead of
# the agent's actual text response.
os.environ.setdefault("ADK_DISABLE_PROGRESSIVE_SSE_STREAMING", "1")

# File is at pay_restore_demo/Agent Sim/test_conversation.py
# Two levels up = c:\Muru_Workspace (where pay_restore_demo package lives)
_this_dir    = os.path.dirname(os.path.abspath(__file__))   # .../Agent Sim
_project_dir = os.path.dirname(_this_dir)                    # .../pay_restore_demo
_workspace   = os.path.dirname(_project_dir)                 # .../Muru_Workspace
sys.path.insert(0, _workspace)

# Load .env from pay_restore_demo/ (same place adk web reads it)
_env_path = os.path.join(_project_dir, ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

from pay_restore_demo import root_agent

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# =============================================================================
# PERSONA SCRIPTS -- select ONE active scenario by uncommenting TURNS + USER_ID
# =============================================================================

# ---------------------------------------------------------------------------
# PERSONA 1 (ACTIVE): Alex (20001) -- Primary Demo Happy Path
# ---------------------------------------------------------------------------
# Status: SUSPENDED | Tenure: 9mo | Plan: Team | Card: 4242 (EXPIRED)
# Suspension: 5 days ago -> data SAFE (within 30-day window)
# Autopay: ON | Prior waiver: None -> waiver PASS (Rules A+B+C all pass)
# 3-turn flow:
#   Turn 1: multi-intent opening (restore + data check + new card + waiver + upgrade)
#   Turn 2: provide new card number + confirm payment consent
#   Turn 3: confirm Business plan upgrade for 3 months
# Expected tool chain:
#   T1 -> DA1/T2 + DA2/T7 -> DA2/T3(new card 4321) -> DA2/T4 -> DA3/T5+T8
#   -> DA4/T9 (validate) -> [turn 3] -> DA4/T9+T6+T8
# ---------------------------------------------------------------------------
# TURNS = [
#     (1, "Our team account is suspended -- our payment method expired and AutoPay failed. "
#         "Before we pay, I need you to confirm that our recent projects weren't wiped. "
#         "If our data is safe, I want to pay with our new Visa to get it restored right away "
#         "and waive any late fees. Also upgrade us to the Business plan for the next 3 months. "
#         "Account 20001."),
#     (2, "The new card number is 4111 1111 1111 4321. Go ahead and restore it."),
#     (3, "Yes, upgrade to Business."),
# ]
# APP_NAME = "pay_restore_test"
# USER_ID  = "test_20001"

# ---------------------------------------------------------------------------
# PERSONA 2: Jordan (20002) -- Waiver FAIL Rule A (new customer)
# ---------------------------------------------------------------------------
# Status: SUSPENDED | Tenure: 2mo | Plan: Team | Card: 8831 (valid)
# Suspension: 5 days ago -> data SAFE
# Autopay: OFF | Prior waiver: None
# Waiver result: FAIL -- tenure_months (2.0) is NOT > 6 months
# 2-turn flow:
#   Turn 1: restore request
#   Turn 2: confirm payment consent (card on file)
# Expected: waiver DENIED, $25 late fee (Team plan), restore completes
# ---------------------------------------------------------------------------
# TURNS = [
#     (1, "Our team account is suspended and I need to get it restored. Account 20002."),
#     (2, "Yes, charge my card on file and restore it."),
# ]
# APP_NAME = "pay_restore_test"
# USER_ID  = "test_20002"

# ---------------------------------------------------------------------------
# PERSONA 3: Sam (20003) -- Data AT RISK (35 days suspended)
# ---------------------------------------------------------------------------
# Status: SUSPENDED | Tenure: 14mo | Plan: Business | Card: 5517 (EXPIRED)
# Suspension: 35 days ago -> data AT RISK (exceeds 30-day retention window)
# Autopay: ON | Prior waiver: None -> waiver would PASS (but AT RISK soft stop fires first)
# 3-turn flow:
#   Turn 1: restore request -> SA1 issues AT RISK notice + presents two paths, HARD STOP
#   Turn 2: customer chooses to proceed despite risk -> card_expired=True -> asks for new card
#   Turn 3: provide new card + consent -> payment -> fee waiver -> restore
# Note: no plan change requested -- STATE 7 skipped
# ---------------------------------------------------------------------------
# TURNS = [
#     (1, "Our business account is suspended and I need to restore it. Account 20003."),
#     (2, "I understand the risk. I want to proceed with the restore."),
#     (3, "New card number is 4111 1111 1111 9988. Yes, go ahead."),
# ]
# APP_NAME = "pay_restore_test"
# USER_ID  = "test_20003"

# ---------------------------------------------------------------------------
# PERSONA 4: Riley (20004) -- Waiver FAIL Rule C (prior waiver used 3mo ago)
# ---------------------------------------------------------------------------
# Status: SUSPENDED | Tenure: 7mo | Plan: Individual | Card: 2290 (EXPIRED)
# Suspension: 10 days ago -> data SAFE
# Autopay: ON | Prior waiver: 90 days ago (within 12mo) -> Rule C FAILS
# Waiver result: FAIL -- waiver used 90 days ago, within 12-month window
# Rules A (7mo > 6mo) and B (autopay ON) both pass; Rule C blocks
# ---------------------------------------------------------------------------
# TURNS = [
#     (1, "I need to restore my account. Account 20004."),
#     (2, "New card is 4111 1111 1111 5678."),
#     (3, "Yes, go ahead and charge it."),
# ]
# APP_NAME = "pay_restore_test"
# USER_ID  = "test_20004"

# ---------------------------------------------------------------------------
# PERSONA 5: Avery (20010) -- Enterprise, Top Tier Perfect Restore
# ---------------------------------------------------------------------------
# Status: SUSPENDED | Tenure: 30mo | Plan: Enterprise | Card: 3388 (EXPIRED)
# Suspension: 8 days ago -> data SAFE (35 projects)
# Autopay: ON | Prior waiver: None -> waiver PASS
# Balance: $399 | 45 seats | 35 projects
# ---------------------------------------------------------------------------
# TURNS = [
#     (1, "Our enterprise account is suspended. I need it restored. Account 20010."),
#     (2, "Please use new card 5500 0055 5555 4321 and restore us now."),
# ]
# APP_NAME = "pay_restore_test"
# USER_ID  = "test_20010"

# ---------------------------------------------------------------------------
# PERSONA 6 (ACTIVE account): Casey (20006) -- Standalone Plan Upgrade
# ---------------------------------------------------------------------------
# Status: ACTIVE | Plan: Team | Balance: $0
# Requesting upgrade to Business plan (active account -- root_agent routes to DA4 directly)
# ---------------------------------------------------------------------------
# TURNS = [
#     (1, "I'd like to upgrade my plan. Account 20006."),
#     (2, "I want to upgrade to Business."),
#     (3, "Yes, confirm the upgrade."),
# ]
# APP_NAME = "pay_restore_test"
# USER_ID  = "test_20006"

# ---------------------------------------------------------------------------
# PERSONA 7 (ACTIVE account): Drew (20007) -- Downgrade BLOCKED (seat count)
# ---------------------------------------------------------------------------
# Status: ACTIVE | Plan: Business | Seats: 25 | Wants to downgrade to Team (max 10)
# T9 returns seat_count_ok=False -> eligible=False -> PLAN_BLOCKED -> human escalation
# ---------------------------------------------------------------------------
# TURNS = [
#     (1, "I want to downgrade my plan. Account 20007."),
#     (2, "Downgrade to Team plan."),
# ]
# APP_NAME = "pay_restore_test"
# USER_ID  = "test_20007"

# ---------------------------------------------------------------------------
# PERSONA 8: Parker (20011) -- CANCELED account win-back
# ---------------------------------------------------------------------------
# Status: CANCELED -> root_agent issues win-back script, routes to human sales
# ---------------------------------------------------------------------------
# TURNS = [
#     (1, "Hi, I'd like to reactivate my account. Account 20011."),
#     (2, "Yes, I'd like to explore your current plans."),
# ]
# APP_NAME = "pay_restore_test"
# USER_ID  = "test_20011"

# ---------------------------------------------------------------------------
# PERSONA 9: Morgan (20005) -- Waiver FAIL Rule B (autopay OFF)
# ---------------------------------------------------------------------------
# Status: SUSPENDED | Tenure: 18mo | Plan: Team | Card: 6644 (valid)
# Suspension: 3 days ago -> data SAFE (11 projects)
# Autopay: OFF | Prior waiver: None
# Waiver result: FAIL Rule B -- AutoPay was not enabled. Rule A (18mo > 6) passes.
# Valid card on file (autopay OFF, card was never charged). 2-turn flow.
# Expected: $49 balance + $25 late fee disclosed upfront. Restore completes.
# ---------------------------------------------------------------------------
# TURNS = [
#     (1, "Our account is suspended and I need it restored. Account 20005."),
#     (2, "Yes, charge my card on file and restore it."),
# ]
# APP_NAME = "pay_restore_test"
# USER_ID  = "test_20005"

# ---------------------------------------------------------------------------
# PERSONA 10 (ACTIVE account): Quinn (20008) -- Clean Downgrade (seat check PASS)
# ---------------------------------------------------------------------------
# Status: ACTIVE | Plan: Business | Seats: 5 | Wants to downgrade to Team (max 10)
# T9: seat_count_ok=True (5 <= 10) -> eligible=True -> storage reduction warning
# Storage: 500 GB -> 100 GB (informational, not blocking). Downgrade executes.
# ---------------------------------------------------------------------------
# TURNS = [
#     (1, "I want to downgrade my plan. Account 20008."),
#     (2, "Downgrade to Team plan."),
#     (3, "Yes, confirm the downgrade."),
# ]
# APP_NAME = "pay_restore_test"
# USER_ID  = "test_20008"

# ---------------------------------------------------------------------------
# PERSONA 11: Jamie (20009) -- Waiver FAIL Rule A Boundary (exactly 6.0 months)
# ---------------------------------------------------------------------------
# Status: SUSPENDED | Tenure: 6.0mo | Plan: Business | Card: 9955 (EXPIRED)
# Suspension: 20 days ago -> data SAFE (18 projects)
# Autopay: ON | Prior waiver: None
# Waiver result: FAIL Rule A -- 6.0mo is NOT strictly > 6mo (boundary edge case)
# Expired card -> Turn 1 asks for new card. Turn 2: card + consent -> restore.
# Expected: $129 balance + $50 late fee disclosed upfront. Restore completes.
# ---------------------------------------------------------------------------
TURNS = [
    (1, "Our business account is suspended and I need to restore it. Account 20003."),
    (2, "I understand the risk. I want to proceed with the restore."),
    (3, "New card number is 4111 1111 1111 9988. Yes, go ahead."),
]
APP_NAME = "pay_restore_test"
USER_ID  = "test_20003"

SEP = "=" * 70

# Tools to highlight in the summary (key decision points)
_KEY_TOOLS = {
    "T1_GetAccount",
    "T2_CheckDataRetention",
    "T3_ProcessPayment",
    "T4_CheckFeeWaiver",
    "T5_RestoreAccount",
    "T6_ChangePlan",
    "T9_ValidatePlanChange",
}


def extract_events(event, turn_num, tools_log):
    """Parse a single ADK event for tool calls and final text."""
    agent_text = ""

    if not event.content or not event.content.parts:
        return agent_text

    for part in event.content.parts:
        # Tool call (agent -> tool)
        if hasattr(part, "function_call") and part.function_call:
            fc = part.function_call
            args = dict(fc.args) if fc.args else {}
            # Truncate large args (transcripts) to keep log readable
            display_args = {
                k: (str(v)[:80] + "...") if isinstance(v, str) and len(str(v)) > 80 else v
                for k, v in args.items()
            }
            marker = " **" if fc.name in _KEY_TOOLS else ""
            tools_log.append(f"  Turn {turn_num}  {fc.name}({display_args}){marker}")

        # Final text response
        if event.is_final_response() and hasattr(part, "text") and part.text:
            agent_text += part.text

    return agent_text


async def run_test():
    session_service = InMemorySessionService()
    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    session = await session_service.create_session(app_name=APP_NAME, user_id=USER_ID)

    tools_log = []   # ordered list of all tool calls
    convo_log = []   # (turn_num, user_text, agent_text) for clean replay
    errors    = []   # any exceptions

    for turn_num, user_text in TURNS:
        print(f"\n{SEP}")
        print(f"TURN {turn_num} -> USER: {user_text}")
        print(SEP)

        msg = types.Content(role="user", parts=[types.Part(text=user_text)])
        agent_response = ""

        try:
            async for event in runner.run_async(
                user_id=USER_ID,
                session_id=session.id,
                new_message=msg,
            ):
                chunk = extract_events(event, turn_num, tools_log)
                if chunk:
                    agent_response += chunk

        except Exception as e:
            err = f"Turn {turn_num}: {type(e).__name__}: {e}"
            errors.append(err)
            print(f"  !! ERROR: {err}")
            _tb.print_exc()
            break

        agent_text = agent_response.strip() or "(no text response)"
        convo_log.append((turn_num, user_text, agent_text))
        print(f"\nTURN {turn_num} -> AGENT:\n{agent_text}")

    # -----------------------------------------------------------------------
    # Clean conversation replay
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("CONVERSATION REPLAY")
    print(SEP)
    for turn_num, user_text, agent_text in convo_log:
        print(f"\n[Turn {turn_num}]")
        print(f"USER : {user_text}")
        print(f"AGENT: {agent_text}")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("SUMMARY -- TOOLS CALLED")
    print(SEP)
    print(f"\nTotal tool calls: {len(tools_log)}  (** = key decision point)")
    if tools_log:
        for entry in tools_log:
            print(entry)
    else:
        print("  (none recorded)")

    print(f"\nErrors / Exceptions:")
    if errors:
        for e in errors:
            print(f"  {e}")
    else:
        print("  None")

    # -----------------------------------------------------------------------
    # DB Verification -- show account state after the run
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("DB VERIFICATION")
    print(SEP)
    try:
        import sqlite3 as _sqlite3
        import re as _re

        _db_path = os.path.join(_project_dir, "agents_tools_db", "orbit.db")
        _db  = _sqlite3.connect(_db_path)
        _cur = _db.cursor()

        # Extract account_id from first TURNS message
        _match = _re.search(r'\b(2000\d|2001[0-3])\b', TURNS[0][1])
        _acct  = int(_match.group(1)) if _match else None

        if _acct:
            print(f"\nAccount {_acct} post-run state:")
            _cur.execute("""
                SELECT account_id, first_name, company_name, plan_name, status,
                       pending_balance, card_last4, card_expired,
                       suspension_date, downgrade_date, seat_count, project_count
                FROM customer_accounts WHERE account_id = ?
            """, (_acct,))
            _row = _cur.fetchone()
            if _row:
                _cols = [
                    "account_id", "first_name", "company_name", "plan_name", "status",
                    "pending_balance", "card_last4", "card_expired",
                    "suspension_date", "downgrade_date", "seat_count", "project_count"
                ]
                for _c, _v in zip(_cols, _row):
                    print(f"  {_c:18s}: {_v}")
            else:
                print(f"  Account {_acct} not found in DB.")

            # Show receipt log if receipts table exists
            _cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='receipts'"
            )
            if _cur.fetchone():
                print(f"\nReceipts for account {_acct}:")
                _cur.execute("""
                    SELECT order_ref, action_type, created_at
                    FROM receipts WHERE account_id = ?
                    ORDER BY created_at DESC LIMIT 5
                """, (_acct,))
                _rcpts = _cur.fetchall()
                if _rcpts:
                    for _r in _rcpts:
                        print(f"  {_r[0]}  {_r[1]:12s}  {_r[2]}")
                else:
                    print("  (none)")

        _db.close()

    except Exception as _e:
        print(f"  DB check failed: {_e}")

    print(f"\n{SEP}\n")


if __name__ == "__main__":
    asyncio.run(run_test())
