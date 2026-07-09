"""
run_personas.py -- Run all 15 persona scripts sequentially.
Resets the DB before each persona. Prints a PASS/FAIL summary at the end.

Run from c:\\Muru_Workspace:
    python "pay_restore_demo/Agent Sim/run_personas.py"
"""

import asyncio
import sys
import os
import io
import traceback as _tb
import importlib
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

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

SEP  = "=" * 72
SEP2 = "-" * 72

# ---------------------------------------------------------------------------
# All 11 personas
# ---------------------------------------------------------------------------
PERSONAS = [
    {
        "id": 1,
        "label": "Alex 20001 — Primary happy path (SUSPENDED, card expired, waiver PASS, Business upgrade 3mo)",
        "account_id": 20001,
        "turns": [
            "Our team account is suspended -- our payment method expired and AutoPay failed. "
            "Before we pay, I need you to confirm that our recent projects weren't wiped. "
            "If our data is safe, I want to pay with our new Visa to get it restored right away "
            "and waive any late fees. Also upgrade us to the Business plan for the next 3 months. "
            "Account 20001.",
            "The new card number is 4111 1111 1111 4321. Go ahead and restore it.",
            "Yes, upgrade to Business.",
        ],
        "expect": [
            "data SAFE (5d), 12 projects",
            "T3: $49 charged to new card 4321",
            "T4: waiver PASS (9mo, autopay ON)",
            "T5: ACTIVE",
            "T9/T6: Business upgrade, 3mo, revert date",
        ],
    },
    {
        "id": 2,
        "label": "Jordan 20002 — Waiver FAIL Rule A (2mo < 6mo threshold)",
        "account_id": 20002,
        "turns": [
            "Our team account is suspended and I need to get it restored. Account 20002.",
            "Yes, charge my card on file and restore it.",
        ],
        "expect": [
            "data SAFE, card 8831 valid → offer card on file",
            "T4: FAIL Rule A (2mo not > 6mo), $25 late fee",
            "T3: $49 + $25 = balance charged",
            "T5: ACTIVE",
        ],
    },
    {
        "id": 3,
        "label": "Sam 20003 — Data AT RISK (35 days > 30-day retention)",
        "account_id": 20003,
        "turns": [
            "Our business account is suspended and I need to restore it. Account 20003.",
            "I understand the risk. I want to proceed with the restore.",
            "New card number is 4111 1111 1111 9988. Yes, go ahead.",
        ],
        "expect": [
            "Turn 1: AT RISK warning, two paths, HARD STOP",
            "Turn 2: at_risk_proceeding=1, ask for new card (5517 expired)",
            "Turn 3: $129 charged to 9988, waiver PASS (14mo), ACTIVE, NO 'projects intact'",
        ],
    },
    {
        "id": 4,
        "label": "Riley 20004 — Waiver FAIL Rule C (prior waiver 90 days ago)",
        "account_id": 20004,
        "turns": [
            "I need to restore my account. Account 20004.",
            "New card is 4111 1111 1111 5678.",
            "Yes, go ahead and charge it.",
        ],
        "expect": [
            "data SAFE (10d), card 2290 expired",
            "T4: FAIL Rule C (waiver 90d ago within 12mo window), $10 late fee (Individual plan)",
            "T3: $10 charged to new card 5678",
            "T5: ACTIVE",
        ],
    },
    {
        "id": 5,
        "label": "Avery 20010 — Enterprise top tier perfect restore",
        "account_id": 20010,
        "turns": [
            "Our enterprise account is suspended. I need it restored. Account 20010.",
            "Please use new card 5500 0055 5555 4321 and restore us now.",
        ],
        "expect": [
            "data SAFE (8d), 35 projects, card 3388 expired",
            "T4: waiver PASS (30mo, autopay ON), $399 charged to 4321, ACTIVE",
        ],
    },
    {
        "id": 6,
        "label": "Casey 20006 — ACTIVE account standalone plan upgrade",
        "account_id": 20006,
        "turns": [
            "I'd like to upgrade my plan. Account 20006.",
            "I want to upgrade to Business.",
            "Yes, confirm the upgrade.",
        ],
        "expect": [
            "ACTIVE, no restore flow",
            "DA4: T9 eligible, upgrade Team → Business",
            "T6: permanent upgrade (no duration)",
            "T8: receipt sent",
        ],
    },
    {
        "id": 7,
        "label": "Drew 20007 — ACTIVE downgrade BLOCKED (25 seats > 10 max on Team)",
        "account_id": 20007,
        "turns": [
            "I want to downgrade my plan. Account 20007.",
            "Downgrade to Team plan.",
        ],
        "expect": [
            "ACTIVE, DA4 T9: seat_count_ok=False (25 > 10), eligible=False",
            "HARD STOP → human escalation (T6 never called)",
        ],
    },
    {
        "id": 8,
        "label": "Parker 20011 — CANCELED account win-back",
        "account_id": 20011,
        "turns": [
            "Hi, I'd like to reactivate my account. Account 20011.",
            "Yes, I'd like to explore your current plans.",
        ],
        "expect": [
            "CANCELED → win-back script",
            "Route to human sales team",
            "No DA2/DA3/DA4 called",
        ],
    },
    {
        "id": 9,
        "label": "Morgan 20005 — Waiver FAIL Rule B (autopay OFF)",
        "account_id": 20005,
        "turns": [
            "Our account is suspended and I need it restored. Account 20005.",
            "Yes, charge my card on file and restore it.",
        ],
        "expect": [
            "data SAFE (3d), card 6644 valid → offer card on file",
            "T4: FAIL Rule B (autopay OFF), $25 late fee",
            "T3: $49 + $25 charged to 6644",
            "T5: ACTIVE",
        ],
    },
    {
        "id": 10,
        "label": "Quinn 20008 — ACTIVE clean downgrade (5 seats ≤ 10 max on Team)",
        "account_id": 20008,
        "turns": [
            "I want to downgrade my plan. Account 20008.",
            "Downgrade to Team plan.",
            "Yes, confirm the downgrade.",
        ],
        "expect": [
            "ACTIVE, DA4 T9: seat_count_ok=True (5 ≤ 10)",
            "Storage reduction warning (500 GB → 100 GB, informational)",
            "T6: downgrade to Team (permanent)",
            "T8: receipt sent",
        ],
    },
    {
        "id": 11,
        "label": "Jamie 20009 — Waiver FAIL Rule A boundary (exactly 6.0mo, not > 6)",
        "account_id": 20009,
        "turns": [
            "I need to restore my account. Account 20009.",
            "New card number is 4111 1111 1111 7777. Yes, go ahead.",
        ],
        "expect": [
            "data SAFE (20d), card 9955 expired",
            "T4: FAIL Rule A (6.0mo is NOT strictly > 6mo), $50 late fee (Business plan)",
            "T3: $129 + $50 charged to 7777",
            "T5: ACTIVE",
        ],
    },
    {
        "id": 12,
        "label": "Taylor 20012 — SA1 diagnostic: storage culprit (95/100 GB near-limit)",
        "account_id": 20012,
        "turns": [
            "Account 20012 -- something feels off lately. Projects are loading slowly and a few uploads just failed. Not sure what's going on.",
            "Ah, that makes sense. What are my options?",
        ],
        "expect": [
            "ACTIVE — no restore flow",
            "Ambiguous complaint → routes to SA1_DiagnosticSupervisor",
            "SA1 fan-out: DA1 + DA5 (T11: 95/100 GB, near_limit=True) + DA6 (T12: Slack healthy) in parallel",
            "SA1 synthesis: PRIMARY_FINDING=storage, culprit identified",
            "Turn 2: upgrade to Business (500 GB) presented as resolution",
        ],
    },
    {
        "id": 13,
        "label": "Blake 20013 — SA1 diagnostic: integration culprit (GitHub auth_failure, 5 failures)",
        "account_id": 20013,
        "turns": [
            "Account 20013 -- things just don't feel right. My team says changes aren't showing up in projects, like it's not syncing. I don't know if it's a billing thing or what.",
            "Yes, please walk me through how to fix the GitHub connection.",
        ],
        "expect": [
            "ACTIVE — no restore flow",
            "Ambiguous complaint → routes to SA1_DiagnosticSupervisor",
            "SA1 fan-out: DA1 + DA5 (T11: 45/500 GB = 9%, healthy) + DA6 (T12: GitHub auth_failure, 5 failures, action_required=True) in parallel",
            "SA1 synthesis: PRIMARY_FINDING=integration, culprit identified — NOT billing",
            "Turn 2: GitHub reconnect steps presented",
        ],
    },
    {
        "id": 14,
        "label": "Priya 20014 — ACTIVE manual payer, $0 balance, card update request",
        "account_id": 20014,
        "turns": [
            "I need help with my account. 20014. Can you tell me my balance.",
            "I want to make a payment but with a new card. Before that, can you confirm what's the card on file?",
        ],
        "expect": [
            "ACTIVE, balance $0, autopay OFF (manual payer)",
            "Turn 1: 'Your account is all paid up — no balance due.'",
            "Turn 2: confirms card on file (6691) AND addresses new card intent — offers card update for future billing",
            "No DA2 called, no T3 charge (balance = $0)",
        ],
    },
    {
        "id": 15,
        "label": "Dana 20015 — ACTIVE manual payer, $49 balance due, payment with new card",
        "account_id": 20015,
        "turns": [
            "Account 20015. I have an invoice I need to pay.",
            "Yes, charge my card on file.",
        ],
        "expect": [
            "ACTIVE, balance $49, autopay OFF (manual payer)",
            "Turn 1: invoice of $49 surfaced, card 7722 valid → offer card on file",
            "Turn 2: consent → DA2 STATE 4 (T3: $49 charged to 7722, T8 receipt sent)",
            "No fee waiver (Rule B — autopay OFF). No restore (ACTIVE account).",
        ],
    },
]

_RESET_SCRIPT = os.path.join(_project_dir, "agents_tools_db", "z_reset_world.py")
_KEY_TOOLS = {
    "T1_GetAccount", "T2_CheckDataRetention", "T3_ProcessPayment",
    "T4_CheckFeeWaiver", "T5_RestoreAccount", "T6_ChangePlan",
    "T9_ValidatePlanChange", "T0_SetSessionState",
}


def reset_db():
    result = subprocess.run(
        [sys.executable, _RESET_SCRIPT],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  !! DB reset failed: {result.stderr[-200:]}")
        return False
    return True


def extract_events(event, turn_num, tools_log):
    agent_text = ""
    if not event.content or not event.content.parts:
        return agent_text
    for part in event.content.parts:
        if hasattr(part, "function_call") and part.function_call:
            fc = part.function_call
            args = dict(fc.args) if fc.args else {}
            display_args = {
                k: (str(v)[:60] + "...") if isinstance(v, str) and len(str(v)) > 60 else v
                for k, v in args.items()
            }
            marker = " **" if fc.name in _KEY_TOOLS else ""
            tools_log.append(f"  Turn {turn_num}  {fc.name}({display_args}){marker}")
        if event.is_final_response() and hasattr(part, "text") and part.text:
            agent_text += part.text
    return agent_text


async def run_persona(root_agent, persona):
    app_name = f"pay_restore_test"
    user_id  = f"test_{persona['account_id']}"

    session_service = InMemorySessionService()
    runner = Runner(agent=root_agent, app_name=app_name, session_service=session_service)
    session = await session_service.create_session(app_name=app_name, user_id=user_id)

    tools_log  = []
    convo_log  = []
    errors     = []

    for turn_num, user_text in enumerate(persona["turns"], 1):
        msg = types.Content(role="user", parts=[types.Part(text=user_text)])
        agent_response = ""
        try:
            async for event in runner.run_async(
                user_id=user_id, session_id=session.id, new_message=msg
            ):
                chunk = extract_events(event, turn_num, tools_log)
                if chunk:
                    agent_response += chunk
        except Exception as e:
            err = f"Turn {turn_num}: {type(e).__name__}: {e}"
            errors.append(err)
            break
        convo_log.append((turn_num, user_text, agent_response.strip() or "(no text)"))

    return convo_log, tools_log, errors


async def main():
    # Import root_agent once (shared across all personas)
    from pay_restore_demo import root_agent

    results = []

    for persona in PERSONAS:
        pid = persona["id"]
        print(f"\n{SEP}")
        print(f"PERSONA {pid}: {persona['label']}")
        print(SEP)

        print("  Resetting DB...", end=" ", flush=True)
        if not reset_db():
            results.append((pid, persona["label"], "DB_RESET_FAILED", [], [], []))
            continue
        print("OK")

        print(f"  Running {len(persona['turns'])} turns...")
        try:
            convo_log, tools_log, errors = await run_persona(root_agent, persona)
        except Exception as e:
            _tb.print_exc()
            results.append((pid, persona["label"], "EXCEPTION", [], [], [str(e)]))
            continue

        # Print conversation
        for turn_num, user_text, agent_text in convo_log:
            print(f"\n  [Turn {turn_num}]")
            print(f"  USER : {user_text[:120]}")
            print(f"  AGENT: {agent_text[:500]}")

        # Print key tool calls
        print(f"\n  Tool calls ({len(tools_log)} total):")
        for entry in tools_log:
            print(f" {entry}")

        if errors:
            print(f"\n  ERRORS: {errors}")

        status = "ERRORS" if errors else "DONE"
        results.append((pid, persona["label"], status, convo_log, tools_log, errors))

    # Summary
    print(f"\n\n{SEP}")
    print("SUMMARY")
    print(SEP)
    for pid, label, status, convo_log, tools_log, errors in results:
        err_str = f"  !! {errors[0]}" if errors else ""
        print(f"  P{pid:02d}  {status:8s}  {label[:70]}{err_str}")

    print(f"\n{SEP}\n")


if __name__ == "__main__":
    asyncio.run(main())
