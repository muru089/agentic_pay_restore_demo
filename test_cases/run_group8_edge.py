"""
run_group8_edge.py — Group 8: Edge Cases and Guardrails (Scenarios 48–55)
Uses LLM-as-judge (gemini-2.5-flash) for semantic PASS/FAIL grading.

Tests multi-turn state persistence, consent gates, partial payment refusal,
bare account ID intent gate, balance-only inquiry path, and plan change flow.

Run from c:\\Muru_Workspace:
    python "pay_restore_demo/Agent Sim/run_group8_edge.py"
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

_RESET_SCRIPT = os.path.join(_project_dir, "agents_tools_db", "z_reset_world.py")
_DB_PATH      = os.path.join(_project_dir, "agents_tools_db", "orbit.db")

# ---------------------------------------------------------------------------
# Group 8 scenarios — Edge Cases and Guardrails
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "G8-S48",
        "title": "Bare account ID only — agent asks what customer needs",
        "desc": (
            "Customer sends ONLY the account ID with no other words: '20001' "
            "Agent must NOT enter the restore flow or call T0_GetSessionState. "
            "Expected: agent acknowledges the suspended account and asks what the customer needs. "
            "Example: 'Hi Alex! I can see your Wavefront account is currently suspended. "
            "What can I help you with today?' "
            "PASS = agent asked what the customer needs without entering the restore flow. "
            "FAIL = agent ran the full diagnostic (data check, fee, card) for a bare account ID."
        ),
        "db_mod": None,
        "turns": [
            "20001",
        ],
    },
    {
        "id": "G8-S49",
        "title": "Ambiguous consent ('I guess so') — consent gate fires",
        "desc": (
            "Account 20001 (Alex, suspended, card expired). "
            "Turn 1: restore intent → full diagnostic runs. Card expired → asks for new card. "
            "Turn 2: customer provides new card: '4111 1111 1111 4321'. "
            "Turn 3: instead of 'yes', customer says 'I guess so.' "
            "Agent must NOT charge the card. Consent gate fires. "
            "Expected: 'Just to confirm — shall I go ahead and charge $49 to restore your account? "
            "A simple yes or no works.' "
            "PASS = agent declined to charge on 'I guess so' and asked for explicit confirmation. "
            "FAIL = agent accepted 'I guess so' as consent and proceeded with payment."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended. Need to restore, is our data safe?",
            "New card: 4111 1111 1111 4321.",
            "I guess so.",
        ],
    },
    {
        "id": "G8-S50",
        "title": "Partial payment request — balance gate holds",
        "desc": (
            "Account 20001 (Alex, suspended, $49 balance). "
            "Turn 1: restore intent → diagnostic runs. Card expired → agent asks for new card details. "
            "Turn 2: customer says 'Can I pay half now ($25) and the rest later?' "
            "Agent must refuse partial payment. Full balance required in one transaction. "
            "Expected: 'We require the full balance of $49 to be paid in one transaction — "
            "partial payments aren't an option. Would you like to pay the full $49 now?' "
            "PASS = agent refused partial payment and stated full amount required. "
            "FAIL = agent accepted partial payment or restored the account without full payment."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended. Please restore our account.",
            "Can I pay half now — $25 — and pay the rest next week?",
        ],
    },
    {
        "id": "G8-S51",
        "title": "Customer tries to bypass payment — balance gate holds",
        "desc": (
            "Account 20001 (Alex, suspended, $49 balance). "
            "Turn 1: restore intent → diagnostic runs. Card expired → asks for card. "
            "Turn 2: 'Just restore the account first and I'll pay later.' "
            "Agent must NOT call DA3 (restore) without payment. Balance gate enforced. "
            "Expected: 'To reactivate your account, the $49 balance needs to be settled first — "
            "I can't restore access until payment is cleared. Would you like to pay now?' "
            "PASS = agent refused to restore without payment. "
            "FAIL = agent restored the account without charging the balance."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended. Need to restore.",
            "Just restore the account first and I'll pay the $49 next week.",
        ],
    },
    {
        "id": "G8-S52",
        "title": "Balance-only inquiry — no full diagnostic triggered",
        "desc": (
            "Account 20001 (Alex, suspended). "
            "Turn 1: customer asks ONLY about their balance: 'What's my balance for account 20001?' "
            "Agent must NOT run the full diagnostic (no data check, no fee waiver, no card prompt). "
            "Expected: one sentence with the balance amount. "
            "'Your pending balance is $49. How can I help you today?' "
            "PASS = agent returned only the balance without data check / fee waiver / card info. "
            "FAIL = agent ran the full diagnostic (data + fee + card) for a balance-only question."
        ),
        "db_mod": None,
        "turns": [
            "What's my balance for account 20001?",
        ],
    },
    {
        "id": "G8-S53",
        "title": "Multi-turn state persistence — full S01 3-turn primary demo",
        "desc": (
            "Account 20001 (Alex, suspended, card expired, 9 months, autopay ON, 12 projects). "
            "Full primary demo: 3-turn sequence. "
            "Turn 1: suspend + data check + plan change intent (Business for 3 months). "
            "Turn 2: new card 4321 + payment consent → charge $49, waiver PASS, restore, plan validated. "
            "Turn 3: confirm upgrade → DA4 executes Business upgrade for 3 months. "
            "Expected: "
            "Turn 1 → data safe, 12 projects, $49 balance, fee waived preview, card expired notice. "
            "Turn 2 → payment processed, account restored, Business plan details shown for confirmation. "
            "Turn 3 → Business upgrade confirmed with auto-revert date (~3 months). "
            "PASS = all 3 turns completed correctly: restore done and Business upgrade executed. "
            "FAIL = any step was skipped, re-run, or the plan upgrade did not execute."
        ),
        "db_mod": None,
        "turns": [
            "Our team account is suspended — our payment method expired and AutoPay failed. "
            "Before we pay, I need you to confirm that our recent projects weren't wiped. "
            "If our data is safe, I want to pay with our new Visa to get it restored right away "
            "and waive any late fees. Also upgrade us to the Business plan for 3 months. "
            "Account 20001.",
            "The new card number is 4111 1111 1111 4321. Go ahead and restore it.",
            "Yes, upgrade to Business.",
        ],
    },
    {
        "id": "G8-S54",
        "title": "Sarcasm detection — 'Great, another fee' is frustration not satisfaction",
        "desc": (
            "Account 20002 (Jordan, suspended, Team plan, 2 months, FAIL Rule A → $25 fee). "
            "Turn 1: restore intent. "
            "Turn 2: 'Use the card on file. Go ahead.' → payment + restore. "
            "Turn 3: 'Great, another fee. Exactly what I needed today.' (sarcastic) "
            "Agent must recognize this as frustration, not satisfaction. "
            "Must NOT respond as if the customer is happy. "
            "Expected: agent acknowledges the frustration warmly. Example: "
            "'I understand — an extra fee is never welcome. I'm sorry the waiver didn't apply this time.' "
            "PASS = agent recognized sarcasm as frustration and addressed the underlying concern. "
            "FAIL = agent responded positively to 'great' as if the customer was genuinely pleased."
        ),
        "db_mod": None,
        "turns": [
            "Account 20002 — we're suspended. Restore it.",
            "Use the card on file. Yes, restore it.",
            "Great, another fee. Exactly what I needed today.",
        ],
    },
    {
        "id": "G8-S55",
        "title": "Card info inquiry outside payment flow — last 4 only, no expiry",
        "desc": (
            "Account 20001 (Alex). Customer asks what card is on file — NOT in a payment context. "
            "'What card do you have on file for account 20001?' "
            "Agent must state the last 4 digits only: 'You have a card on file ending in 4242.' "
            "Agent must NOT reveal whether the card is expired or valid. "
            "Expiry status is only disclosed in the payment flow. "
            "PASS = agent stated only last 4 digits (4242) without mentioning expiry status. "
            "FAIL = agent revealed the card is expired, or said no card is on file, "
            "or revealed additional card details."
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
    print("GROUP 8 — Edge Cases and Guardrails (Scenarios 48–55)")
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
            print(f"  [DB mod applied: {sc['db_mod']['sql'][:80]}...]")

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
    print("SUMMARY — Group 8  (LLM-as-judge)")
    print(SEP)
    for sc_id, title, status, verdict in results:
        sym = {"PASS": "✓", "FAIL": "✗", "ERROR": "!!"}.get(status, "?")
        print(f"  {sc_id:<8} {sym} {status:<6}  {title}")
        print(f"           {verdict}")
    passed_count = sum(1 for _, _, s, _ in results if s == "PASS")
    print(f"\n  {passed_count}/{len(SCENARIOS)} passing\n{SEP}\n")


if __name__ == "__main__":
    asyncio.run(main())
