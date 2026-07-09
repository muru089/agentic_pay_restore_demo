"""
run_group14_tone.py — Group 14: Warm Close & Tone (S92–S97)
Uses LLM-as-judge (gemini-2.5-flash) for semantic PASS/FAIL grading.

Tests tone-related behaviors: warm close after resolution, empathy before
bad news, corporate filler absence, AT RISK measured tone, tenure greeting
accuracy, and escalation framing.

Run from c:\\Muru_Workspace:
    python "pay_restore_demo/Agent Sim/run_group14_tone.py"
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
# Group 14 scenarios — Warm Close & Tone
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "G14-S92",
        "title": "Warm close after full resolution (restore + upgrade)",
        "desc": (
            "Account 20001 (Alex, Team plan, SUSPENDED, card expired 4242). "
            "Full 3-turn S01 happy path: Turn 1 restore request, Turn 2 new card + consent, "
            "Turn 3 Business upgrade confirmed. "
            "After Turn 3 completes, the agent's final response must end with a genuine warm close — "
            "not abruptly stopping after the receipt line. "
            "PASS = agent's final response included a warm closing statement "
            "(e.g., 'Enjoy the upgrade', 'Great to have you back', 'Let us know if you need anything'). "
            "FAIL = agent ended with just the receipt confirmation and stopped abruptly with no close."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended. Card expired. Restore us and upgrade to Business for 3 months.",
            "New card: 4111 1111 1111 4321. Go ahead.",
            "Yes, upgrade to Business.",
        ],
    },
    {
        "id": "G14-S93",
        "title": "Waiver denied — empathy before the dollar amount",
        "desc": (
            "Account 20002 (Jordan, Team plan, SUSPENDED, valid card 8831, 2 months tenure). "
            "Turn 1: 'Account 20002 — restore us and please waive the late fee.' "
            "Turn 2: 'Use the card on file, go ahead.' "
            "Waiver fails Rule A (2 months < 6 month minimum). $25 late fee applies. "
            "Agent must acknowledge the outcome empathetically BEFORE stating the fee amount. "
            "PASS = agent delivered the waiver denial with acknowledgment/empathy before stating '$25'. "
            "The response must not lead with the dollar amount as the first thing. "
            "FAIL = agent led with 'A late fee of $25 applies' with no empathetic acknowledgment."
        ),
        "db_mod": None,
        "turns": [
            "Account 20002 — restore us and please waive the late fee.",
            "Use the card on file, go ahead.",
        ],
    },
    {
        "id": "G14-S94",
        "title": "AT RISK tone — measured, not minimising the risk",
        "desc": (
            "Account 20003 (Sam, Business plan, SUSPENDED 35 days, card expired 5517). "
            "Turn 1: 'Account 20003 — we need to restore. Is our data safe?' "
            "Data is AT RISK (35 days > 30-day retention window). "
            "Agent must present the AT RISK warning in a measured tone — clear, not alarming, "
            "but NOT minimising ('it might be fine') or rushing the customer. "
            "Agent must offer two clear paths (proceed vs. data recovery team). "
            "PASS = agent presented the AT RISK situation clearly and empathetically, "
            "offered two paths, and gave the customer space to decide. "
            "FAIL = agent minimised the risk ('your data is probably fine'), rushed the customer, "
            "or did not offer both paths."
        ),
        "db_mod": None,
        "turns": [
            "Account 20003 — we need to restore. Is our data safe?",
        ],
    },
    {
        "id": "G14-S95",
        "title": "No corporate filler — 'I apologize for the inconvenience' absent",
        "desc": (
            "Account 20001 (Alex, Team plan, SUSPENDED). "
            "Turn 1: 'Account 20001 — we're suspended and I'm frustrated. Just fix it.' "
            "Agent must handle the frustrated tone without using corporate filler phrases. "
            "Phrases to avoid: 'I apologize for the inconvenience', 'Kindly note', "
            "'Please be advised', 'I understand your frustration' (hollow), "
            "'Thank you for your patience'. "
            "PASS = agent responded empathetically and efficiently WITHOUT any of the above "
            "corporate filler phrases. Tone is direct and helpful. "
            "FAIL = agent used any of the flagged corporate filler phrases in the response."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended and I'm frustrated. Just fix it.",
        ],
    },
    {
        "id": "G14-S96",
        "title": "Blocking escalation framed positively — seat count block",
        "desc": (
            "Account 20007 (Drew, Lumen Co, Business plan, ACTIVE, 25 seats). "
            "Turn 1: 'Account 20007 — we want to downgrade to Team to save money.' "
            "T9: 25 seats > 10 max → seat_count_ok=False → HARD STOP. "
            "Agent must frame the escalation as the right path forward — helpful, not a failure. "
            "Expected tone: 'Your team has 25 active seats, which is above the Team plan's 10-seat "
            "limit. Our support team can help you review which seats are active and deactivate any "
            "you no longer need — then we can process the downgrade.' "
            "PASS = agent framed the escalation warmly and constructively, explaining the next step. "
            "FAIL = agent said 'I can't do that' without offering any path forward."
        ),
        "db_mod": None,
        "turns": [
            "Account 20007 — we want to downgrade to Team to save money.",
        ],
    },
    {
        "id": "G14-S97",
        "title": "Financial distress — payment discussion paused, warm escalation",
        "desc": (
            "Account 20001 (Alex, Team plan, SUSPENDED). "
            "Turn 1: 'Account 20001 — we're suspended. We need to restore but honestly "
            "we might lose the business if we can't afford this right now.' "
            "Financial hardship signal detected. Agent must NOT proceed with payment collection. "
            "Must acknowledge the situation empathetically and offer escalation to account team. "
            "PASS = agent paused payment discussion, acknowledged the difficulty, and offered "
            "to connect to the account team or a specialist who can work through options. "
            "FAIL = agent ignored the distress signal and proceeded to ask for card details."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended. We need to restore but honestly we might lose "
            "the business if we can't afford this right now.",
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
    print("GROUP 14 — Warm Close & Tone (Scenarios S92–S97)")
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
    print("SUMMARY — Group 14  (LLM-as-judge)")
    print(SEP)
    for sc_id, title, status, verdict in results:
        sym = {"PASS": "✓", "FAIL": "✗", "ERROR": "!!"}.get(status, "?")
        print(f"  {sc_id:<12} {sym} {status:<6}  {title}")
        print(f"               {verdict}")
    passed_count = sum(1 for _, _, s, _ in results if s == "PASS")
    print(f"\n  {passed_count}/{len(SCENARIOS)} passing\n{SEP}\n")


if __name__ == "__main__":
    asyncio.run(main())
