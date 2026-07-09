"""
run_all_personas.py — Run all primary personas and display full transcripts.
Run from c:\\Muru_Workspace (parent of pay_restore_demo):

    python "pay_restore_demo/Agent Sim/run_all_personas.py"

Options:
    --personas 1 3 5    run specific persona numbers only
    --skip-reset        skip DB reset between personas (faster, less isolated)
"""

import asyncio
import sys
import os
import io
import argparse
import traceback as _tb
import subprocess

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
os.environ.setdefault("ADK_DISABLE_PROGRESSIVE_SSE_STREAMING", "1")

_this_dir    = os.path.dirname(os.path.abspath(__file__))
_project_dir = os.path.dirname(_this_dir)
_workspace   = os.path.dirname(_project_dir)
sys.path.insert(0, _workspace)

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
# PRIMARY PERSONA SCRIPTS
# =============================================================================

PERSONAS = [
    {
        "num":     1,
        "name":    "Alex 20001 — Primary happy path",
        "desc":    "SUSPENDED | Team | 9mo | card 4242 EXPIRED | 5d suspended | waiver PASS | upgrade Business 3mo",
        "account": 20001,
        "turns": [
            (1, "Our team account is suspended — our payment method expired and AutoPay failed. "
                "Before we pay, I need you to confirm that our recent projects weren't wiped. "
                "If our data is safe, I want to pay with our new Visa to get it restored right away "
                "and waive any late fees. Also upgrade us to the Business plan for the next 3 months. "
                "Account 20001."),
            (2, "The new card number is 4111 1111 1111 4321. Go ahead and restore it."),
            (3, "Yes, upgrade to Business."),
        ],
    },
    {
        "num":     2,
        "name":    "Jordan 20002 — Waiver FAIL Rule A",
        "desc":    "SUSPENDED | Team | 2mo (< 6mo threshold) | card 8831 valid | waiver DENIED | $25 late fee",
        "account": 20002,
        "turns": [
            (1, "Our team account is suspended and I need to get it restored. Account 20002."),
            (2, "Yes, charge my card on file and restore it."),
        ],
    },
    {
        "num":     3,
        "name":    "Sam 20003 — Data AT RISK",
        "desc":    "SUSPENDED | Business | 14mo | card 5517 EXPIRED | 35d suspended (> 30d retention) | waiver PASS",
        "account": 20003,
        "turns": [
            (1, "Our business account is suspended and I need to restore it. Account 20003."),
            (2, "I understand the risk. I want to proceed with the restore."),
            (3, "New card number is 4111 1111 1111 9988. Yes, go ahead."),
        ],
    },
    {
        "num":     4,
        "name":    "Riley 20004 — Waiver FAIL Rule C",
        "desc":    "SUSPENDED | Individual | 7mo | card 2290 EXPIRED | 10d | waiver used 90d ago (Rule C FAILS)",
        "account": 20004,
        "turns": [
            (1, "I need to restore my account. Account 20004."),
            (2, "New card is 4111 1111 1111 5678."),
            (3, "Yes, go ahead and charge it."),
        ],
    },
    {
        "num":     5,
        "name":    "Avery 20010 — Enterprise restore",
        "desc":    "SUSPENDED | Enterprise | 30mo | card 3388 EXPIRED | 8d | $399 | 35 projects | waiver PASS",
        "account": 20010,
        "turns": [
            (1, "Our enterprise account is suspended. I need it restored urgently. Account 20010."),
            (2, "Please use new card 5500 0055 5555 4321 and restore us now."),
        ],
    },
    {
        "num":     6,
        "name":    "Casey 20006 — Active account plan upgrade",
        "desc":    "ACTIVE | Team | 8mo | $0 balance | Team -> Business upgrade",
        "account": 20006,
        "turns": [
            (1, "I'd like to upgrade my plan. Account 20006."),
            (2, "I want to upgrade to Business."),
            (3, "Yes, confirm the upgrade."),
        ],
    },
    {
        "num":     7,
        "name":    "Drew 20007 — Downgrade BLOCKED (seat count)",
        "desc":    "ACTIVE | Business | 25 seats | Team max=10 | T9 eligible=False -> human escalation",
        "account": 20007,
        "turns": [
            (1, "I want to downgrade my plan. Account 20007."),
            (2, "Downgrade to Team plan."),
        ],
    },
    {
        "num":     8,
        "name":    "Parker 20011 — CANCELED win-back",
        "desc":    "CANCELED | Team | 1.5mo | no restore -> win-back routing to sales team",
        "account": 20011,
        "turns": [
            (1, "Hi, I'd like to reactivate my account. Account 20011."),
            (2, "Yes, I'd like to explore your current plans."),
        ],
    },
    {
        "num":     9,
        "name":    "Morgan 20005 — Waiver FAIL Rule B",
        "desc":    "SUSPENDED | Team | 18mo | card 6644 valid | AutoPay OFF | waiver DENIED | $25 late fee",
        "account": 20005,
        "turns": [
            (1, "Our account is suspended and I need it restored. Account 20005."),
            (2, "Yes, charge my card on file and restore it."),
        ],
    },
    {
        "num":     10,
        "name":    "Quinn 20008 — Clean downgrade (seat check PASS)",
        "desc":    "ACTIVE | Business | 5 seats (≤ 10 Team max) | storage 500->100 GB | downgrade executes",
        "account": 20008,
        "turns": [
            (1, "I want to downgrade my plan. Account 20008."),
            (2, "Downgrade to Team plan."),
            (3, "Yes, confirm the downgrade."),
        ],
    },
    {
        "num":     11,
        "name":    "Jamie 20009 — Waiver FAIL Rule A boundary",
        "desc":    "SUSPENDED | Business | 6.0mo (NOT > 6mo) | card 9955 EXPIRED | 20d | $50 fee applies",
        "account": 20009,
        "turns": [
            (1, "Our business account is suspended. Account 20009. Need to restore it."),
            (2, "New card 4111 1111 1111 7777. Yes, restore it."),
        ],
    },
    {
        "num":     12,
        "name":    "Taylor 20012 — SA1 Diagnostic, Storage Culprit",
        "desc":    "ACTIVE | Team | 11mo | storage 95/100 GB (95%) | Slack healthy | SA1 fan-out → storage finding",
        "account": 20012,
        "turns": [
            (1, "Account 20012 -- something feels off lately. Projects are loading slowly and a few uploads just failed. Not sure what's going on."),
            (2, "Ah, that makes sense. What are my options?"),
        ],
    },
    {
        "num":     13,
        "name":    "Blake 20013 — SA1 Diagnostic, Integration Culprit",
        "desc":    "ACTIVE | Business | 16mo | storage 45/500 GB (9%) | GitHub auth_failure (5x) | SA1 fan-out → integration finding",
        "account": 20013,
        "turns": [
            (1, "Account 20013 -- things just don't feel right. My team says changes aren't showing up in projects, like it's not syncing. I don't know if it's a billing thing or what."),
            (2, "Yes, please walk me through how to fix the GitHub connection."),
        ],
    },
]

SEP  = "=" * 72
SEP2 = "-" * 72


def reset_db():
    """Reset the DB to a clean state before each persona."""
    result = subprocess.run(
        [sys.executable, "pay_restore_demo/agents_tools_db/z_reset_world.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=_workspace,
    )
    if result.returncode != 0:
        print(f"  !! DB RESET FAILED:\n{result.stderr[:400]}")
        return False
    return True


_KEY_TOOLS = {
    "T1_GetAccount", "T2_CheckDataRetention", "T3_ProcessPayment",
    "T4_CheckFeeWaiver", "T5_RestoreAccount", "T6_ChangePlan", "T9_ValidatePlanChange",
}


def extract_events(event, turn_num, tools_log):
    agent_text = ""
    if not event.content or not event.content.parts:
        return agent_text
    for part in event.content.parts:
        if hasattr(part, "function_call") and part.function_call:
            fc = part.function_call
            args = dict(fc.args) if fc.args else {}
            display_args = {
                k: (str(v)[:80] + "...") if isinstance(v, str) and len(str(v)) > 80 else v
                for k, v in args.items()
            }
            marker = " **" if fc.name in _KEY_TOOLS else ""
            tools_log.append(f"  Turn {turn_num}  {fc.name}({display_args}){marker}")
        if event.is_final_response() and hasattr(part, "text") and part.text:
            agent_text += part.text
    return agent_text


async def run_persona(persona, skip_reset=False):
    num     = persona["num"]
    name    = persona["name"]
    desc    = persona["desc"]
    turns   = persona["turns"]
    acct_id = persona["account"]
    app_name = f"pay_restore_test_p{num}"
    user_id  = f"test_{acct_id}"

    print(f"\n{SEP}")
    print(f"PERSONA {num}: {name}")
    print(f"  {desc}")
    print(SEP)

    if not skip_reset:
        print("  Resetting DB...", end=" ", flush=True)
        ok = reset_db()
        print("OK" if ok else "FAILED")
        if not ok:
            return {"persona": num, "name": name, "status": "DB_RESET_FAIL", "turns": []}

    session_service = InMemorySessionService()
    runner = Runner(agent=root_agent, app_name=app_name, session_service=session_service)
    session = await session_service.create_session(app_name=app_name, user_id=user_id)

    tools_log = []
    convo_log = []
    errors    = []

    for turn_num, user_text in turns:
        print(f"\n{SEP2}")
        print(f"TURN {turn_num} — USER:")
        print(f"  {user_text}")
        print(SEP2)

        msg = types.Content(role="user", parts=[types.Part(text=user_text)])
        agent_response = ""

        try:
            async for event in runner.run_async(
                user_id=user_id,
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
        print(f"\nTURN {turn_num} — AGENT:")
        print(agent_text)

    print(f"\n{SEP2}")
    print(f"TOOLS CALLED (Persona {num})  — ** = key decision point")
    print(SEP2)
    if tools_log:
        for entry in tools_log:
            print(entry)
    else:
        print("  (none recorded)")

    if errors:
        print(f"\nERRORS:")
        for e in errors:
            print(f"  {e}")

    status = "ERROR" if errors else "COMPLETE"
    return {"persona": num, "name": name, "status": status, "turns": convo_log}


async def main():
    parser = argparse.ArgumentParser(description="Run primary personas with full transcripts")
    parser.add_argument("--personas", nargs="+", type=int, help="Persona numbers to run (default: all)")
    parser.add_argument("--skip-reset", action="store_true", help="Skip DB reset between personas")
    args = parser.parse_args()

    target = args.personas or [p["num"] for p in PERSONAS]
    selected = [p for p in PERSONAS if p["num"] in target]

    print(f"\nRunning {len(selected)} persona(s): {[p['num'] for p in selected]}")
    print("DB reset between personas:", "NO (--skip-reset)" if args.skip_reset else "YES")

    results = []
    for persona in selected:
        result = await run_persona(persona, skip_reset=args.skip_reset)
        results.append(result)

    # ─── Final summary ────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("FINAL SUMMARY")
    print(SEP)
    for r in results:
        print(f"  Persona {r['persona']:2d}: {r['status']:12s}  {r['name']}")

    print(f"\nDone. {len(results)} persona(s) run.")


if __name__ == "__main__":
    asyncio.run(main())
