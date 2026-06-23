"""
run_group3_cards.py — Group 3: Restore Flow — Card Handling (Scenarios 13–20)
Uses LLM-as-judge (gemini-2.5-flash) for semantic PASS/FAIL grading.

Run from c:\\Muru_Workspace:
    python "pay_restore_demo/Agent Sim/run_group3_cards.py"
"""
import asyncio, sys, os, io, time
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

from google.genai import types

_RESET_SCRIPT = os.path.join(_project_dir, "agents_tools_db", "z_reset_world.py")
_DB_PATH      = os.path.join(_project_dir, "agents_tools_db", "orbit.db")

# ---------------------------------------------------------------------------
# Group 3 scenarios — Card Handling
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "G3-S13",
        "title": "Valid card on file — agent offers it, no new card prompt",
        "desc": (
            "Account 20002 (Jordan, Team plan, SUSPENDED). Card 8831 is VALID (card_expired=0). "
            "Turn 1: restore intent. Agent runs ROW 7, presents data check + balance ($49) + fee result. "
            "Para 3 MUST offer the card on file: 'Would you like to pay with your card on file ending in 8831?' "
            "Agent must NOT ask the customer to provide a new card or emit __CARD_FORM__. "
            "Turn 2: 'Use the card on file. Go ahead.' → agent charges card on file, restores. "
            "PASS = agent offered existing card in Turn 1 response and completed restore in Turn 2."
        ),
        "db_mod": None,
        "turns": [
            "Account 20002, our team is suspended and we need to restore access immediately.",
            "Yes, use the card on file. Go ahead and restore it.",
        ],
    },
    {
        "id": "G3-S14",
        "title": "Expired card — agent proactively prompts for new card",
        "desc": (
            "Account 20001 (Alex, Team plan, SUSPENDED). Card 4242 is EXPIRED (card_expired=1). "
            "After ROW 7 runs (data check + balance + fee), Para 3 must say the card is expired "
            "and ask for new card details — it must NOT offer the expired card as a payment option. "
            "Expected response includes: card 'expired', prompt for new card details, and __CARD_FORM__. "
            "PASS = agent mentioned card is expired and asked for new card details (NOT offered the expired card)."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001, we're suspended. We need to restore our account — is our data safe?",
        ],
    },
    {
        "id": "G3-S15",
        "title": "No card on file — asks for card without referencing 'card on file'",
        "desc": (
            "Account 20001 (Alex, SUSPENDED), but card_last4 has been set to NULL in the DB. "
            "Agent must ask for card details WITHOUT saying 'your card on file' (there is none). "
            "Expected: 'No payment method on file. Please provide your card details.' "
            "PASS = agent requested card details without referencing any existing card on file."
        ),
        "db_mod": {
            "sql": "UPDATE customer_accounts SET card_last4=NULL, card_expired=0 WHERE account_id=20001",
        },
        "turns": [
            "Account 20001, we're suspended. We need to restore. Is our data safe?",
        ],
    },
    {
        "id": "G3-S16",
        "title": "15-digit card number — agent asks for 16 digits",
        "desc": (
            "Account 20002 (Jordan, SUSPENDED, valid card 8831). "
            "Turn 1: restore intent → ROW 7 runs, agent presents summary and asks about card. "
            "Turn 2: customer provides a 15-digit number '4111 1111 1111 111'. "
            "Agent must recognize this is not a complete 16-digit card number and ask the customer "
            "to provide a valid 16-digit card number. "
            "PASS = agent rejected the 15-digit input and asked for a complete 16-digit card number. "
            "FAIL = agent accepted the partial number and proceeded with payment."
        ),
        "db_mod": None,
        "turns": [
            "Account 20002, we're suspended, need to restore please.",
            "4111 1111 1111 111",
        ],
    },
    {
        "id": "G3-S17",
        "title": "16-digit card with no Luhn — agent accepts and proceeds",
        "desc": (
            "Account 20002 (Jordan, SUSPENDED, valid card 8831). "
            "Turn 1: restore intent → data + billing check summary. "
            "Turn 2: customer provides '4111 1111 1111 1113' — a 16-digit number. "
            "Agent validation in text mode (MODE B) checks only: exactly 16 digits, "
            "no 4+ consecutive zeros, not all-identical digits. Luhn is NOT checked in "
            "text mode — Luhn validation is handled client-side in orbit_chat.html only. "
            "Agent must accept '4111 1111 1111 1113' as a valid input (passes all three rules), "
            "extract last 4 digits (1113), and proceed with payment. "
            "PASS = agent accepted the 16-digit number, extracted last 4 (1113), and attempted payment. "
            "FAIL = agent rejected the number as invalid or asked the customer to re-check it."
        ),
        "db_mod": None,
        "turns": [
            "Account 20002, our team is suspended. We need to get back in.",
            "4111 1111 1111 1113",
        ],
    },
    {
        "id": "G3-S18",
        "title": "Card number provided in chunks across two turns",
        "desc": (
            "Account 20002 (Jordan, SUSPENDED, valid card 8831). "
            "Turn 1: restore intent → ROW 7 summary + card prompt. "
            "Turn 2: customer provides only 8 digits: '4111 1111'. "
            "Agent should NOT proceed with an incomplete card — must ask for the full 16-digit number. "
            "Turn 3: customer provides '1111 4321' (the rest) — still not a full 16 digits in one message. "
            "PASS = agent asked for the complete card number in Turn 2 (did not try to process partial). "
            "The agent should not combine partial numbers across turns."
        ),
        "db_mod": None,
        "turns": [
            "Account 20002, we're suspended and need to restore urgently.",
            "4111 1111",
            "1111 4321",
        ],
    },
    {
        "id": "G3-S19",
        "title": "Customer says 'use same card' when card is expired",
        "desc": (
            "Account 20001 (Alex, SUSPENDED). Card 4242 is EXPIRED. "
            "Turn 1: ROW 7 runs → agent presents summary. Para 3 says card is expired, asks for new card. "
            "Turn 2: Customer says 'Just use the same card on file, it should still work.' "
            "Agent must explain that the card on file (ending in 4242) is expired and cannot be charged — "
            "a new card is required. Agent must NOT attempt to charge the expired card. "
            "PASS = agent clearly explained the card is expired and asked for new card details."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001, we're suspended. Please restore our account and check our data.",
            "Just use the same card on file, it should still work.",
        ],
    },
    {
        "id": "G3-S20",
        "title": "Customer asks what card is on file — last 4 only",
        "desc": (
            "Account 20001 (Alex). Customer asks what card is on file. "
            "Agent must state the last 4 digits ('ending in 4242') only. "
            "Agent must NOT reveal the full card number, expiry date, or any additional card details. "
            "PASS = agent stated only the last 4 digits without revealing any other card information. "
            "FAIL = agent revealed more than the last 4 digits, or stated no card is on file."
        ),
        "db_mod": None,
        "turns": [
            "What card do you have on file for account 20001?",
        ],
    },
]

SEP  = "=" * 70
SEP2 = "-" * 70

sys.path.insert(0, _this_dir)
from judge_utils import reset_db, apply_db_mod, run_scenario, llm_judge


async def main():
    from pay_restore_demo import root_agent

    print(f"\n{SEP}")
    print("GROUP 3 — Restore Flow: Card Handling (Scenarios 13–20)")
    print("Grading: LLM-as-judge (gemini-2.5-flash)")
    print(SEP)

    results = []

    for i, sc in enumerate(SCENARIOS, 1):
        print(f"\n{SEP2}")
        print(f"[{i}/{len(SCENARIOS)}] {sc['id']} — {sc['title']}")
        print(SEP2)

        reset_db()
        if sc.get("db_mod"):
            apply_db_mod(sc["db_mod"])
            print(f"  [DB mod applied: {sc['db_mod']['sql'][:80]}]")

        t0 = time.time()
        responses, error = await run_scenario(root_agent, sc)
        run_elapsed = time.time() - t0

        for turn_num, user_text, agent_text in responses:
            print(f"\n  USER  : {user_text}")
            print(f"  ORBIT : {agent_text}")

        if error:
            print(f"\n  !! ERROR: {error}")
            results.append((sc["id"], sc["title"], "ERROR", f"Runtime error: {error}"))
            continue

        print(f"\n  [Judging... ", end="", flush=True)
        j0 = time.time()
        passed, verdict = await llm_judge(sc, responses)
        judge_elapsed = time.time() - j0
        print(f"{judge_elapsed:.1f}s]")

        sym = "✓" if passed else "✗"
        status = "PASS" if passed else "FAIL"
        print(f"  {sym} {status}  ({run_elapsed:.1f}s run + {judge_elapsed:.1f}s judge)")
        print(f"  Judge: {verdict}")

        results.append((sc["id"], sc["title"], status, verdict))

    print(f"\n\n{SEP}")
    print("SUMMARY — Group 3  (LLM-as-judge)")
    print(SEP)
    for sc_id, title, status, verdict in results:
        sym = {"PASS": "✓", "FAIL": "✗", "ERROR": "!!"}.get(status, "?")
        print(f"  {sc_id:<8} {sym} {status:<6}  {title}")
        print(f"           {verdict}")
    passed_count = sum(1 for _, _, s, _ in results if s == "PASS")
    print(f"\n  {passed_count}/{len(SCENARIOS)} passing\n{SEP}\n")


if __name__ == "__main__":
    asyncio.run(main())
