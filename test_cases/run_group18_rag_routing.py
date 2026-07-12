"""
run_group18_rag_routing.py — Group 18: RAG Edge Cases + Routing Gaps (S127–S134)
Uses LLM-as-judge (gemini-2.5-flash) for semantic PASS/FAIL grading.

Covers the remaining uncovered secondary scenarios: RAG multi-part questions (56-57),
conversation dynamics gaps (85, 87, 88), and routing edge cases not in G12 (98-100).

Run from c:\\Muru_Workspace:
    python "pay_restore_demo/Agent Sim/run_group18_rag_routing.py"
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

SCENARIOS = [
    # ── RAG edge cases ────────────────────────────────────────────────────────
    {
        "id": "G18-S127",
        "title": "RAG multi-part question — both parts answered from knowledge base",
        "desc": (
            "No account ID. "
            "Turn 1: 'What's included in the Team plan, and how long is data kept after "
            "an account is suspended?' "
            "Both parts are covered in knowledge base (plans_pricing.html, data_retention.html). "
            "Agent must call T10 and answer both from retrieved content — not from training data. "
            "PASS = agent answered both questions accurately: "
            "Team plan ($49/mo, 10 users, 100 GB) AND 30-day data retention window after suspension. "
            "FAIL = agent answered only one part, or answered from training data without T10 call."
        ),
        "db_mod": None,
        "turns": [
            "What's included in the Team plan, and how long is data kept after an account is suspended?",
        ],
    },
    {
        "id": "G18-S128",
        "title": "RAG question then account-specific question — agent switches tools correctly",
        "desc": (
            "Account 20001 (Alex, SUSPENDED). "
            "Turn 1: 'How does AutoPay work, and does enabling it affect fee waiver eligibility?' "
            "Turn 2: 'Account 20001 — what's my current balance?' "
            "Agent must: Turn 1 → T10 (RAG, policy question). "
            "Turn 2 → T1 + T7 (account-specific lookup). "
            "PASS = Turn 1 answered from knowledge base (T10), Turn 2 reported the "
            "account balance ($49) from account tools — agent switched correctly. "
            "FAIL = agent answered the policy question from training data, or failed to "
            "switch to account lookup for Turn 2."
        ),
        "db_mod": None,
        "turns": [
            "How does AutoPay work, and does having it enabled affect my fee waiver eligibility?",
            "Account 20001 — what's my current balance?",
        ],
    },
    # ── Conversation dynamics gaps ────────────────────────────────────────────
    {
        "id": "G18-S129",
        "title": "Customer changes mind on plan after confirming — DA4 not yet called",
        "desc": (
            "Account 20001 (Alex, SUSPENDED, card expired). "
            "Turn 1: Restore + Business upgrade request. "
            "Turn 2: New card + consent to restore → payment + restore complete. "
            "DA4 MODE V presented Business plan details. "
            "Turn 3: 'Wait — actually make it Enterprise instead of Business.' "
            "DA4 not yet called with T6 (plan_executed=0). "
            "Agent must accept the change and upgrade to Enterprise instead. "
            "PASS = agent upgraded to Enterprise (not Business), confirming $399/mo. "
            "FAIL = agent refused to change or upgraded to Business despite the request."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — restore us and upgrade to Business.",
            "New card: 4111 1111 1111 4321. Yes, go ahead and restore.",
            "Wait — actually make it Enterprise instead of Business.",
        ],
    },
    {
        "id": "G18-S130",
        "title": "Customer sends empty / nearly-empty message — agent re-prompts gently",
        "desc": (
            "Account 20001 (Alex, SUSPENDED, card expired). "
            "Turn 1: Restore request → agent presents card situation. "
            "Turn 2: Customer sends just '...' (near-empty). "
            "Agent must not crash, error, or make assumptions. "
            "Should gently re-prompt for card details. "
            "PASS = agent responded gracefully to the near-empty message, gently asking "
            "for the card details needed to proceed. "
            "FAIL = agent errored, assumed consent, or ignored the empty message."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended and need to restore.",
            "...",
        ],
    },
    {
        "id": "G18-S131",
        "title": "Very long message with irrelevant content — agent extracts relevant parts",
        "desc": (
            "Account 20001 (Alex, SUSPENDED). "
            "Turn 1: Customer sends a long message with both the key request and irrelevant filler. "
            "'Hey, account 20001 here. I was just reading about your new dashboard features, "
            "and also I wanted to mention our team loved the old export tool, anyway enough about "
            "that — we're suspended and we need to get restored asap, card expired. "
            "Also unrelated but have you tried the new UI? Anyway, restore us please.' "
            "Agent must extract the core intent (suspended, restore, card expired) and proceed. "
            "PASS = agent identified the suspension + expired card and began the restore flow "
            "without getting confused by the irrelevant content. "
            "FAIL = agent commented on the dashboard features, got confused, or missed the restore intent."
        ),
        "db_mod": None,
        "turns": [
            "Hey, account 20001 here. I was just reading about your new dashboard features, "
            "and also I wanted to mention our team loved the old export tool, anyway enough about "
            "that — we're suspended and we need to get restored asap, card expired. "
            "Also unrelated but have you tried the new UI? Anyway, restore us please.",
        ],
    },
    # ── Routing edge cases not in G12 ─────────────────────────────────────────
    {
        "id": "G18-S132",
        "title": "Out-of-scope: app not loading — routes to support email",
        "desc": (
            "No account ID. "
            "Turn 1: 'My Orbit app keeps crashing when I try to open a project.' "
            "This is technical support — outside the VA's scope. "
            "Agent must route to support@orbit.io and not attempt to troubleshoot. "
            "PASS = agent declined to troubleshoot and directed the customer to "
            "support@orbit.io (or equivalent support channel). "
            "FAIL = agent attempted to troubleshoot the app crash or gave generic debugging steps."
        ),
        "db_mod": None,
        "turns": [
            "My Orbit app keeps crashing when I try to open a project.",
        ],
    },
    {
        "id": "G18-S133",
        "title": "Out-of-scope: refund request for old charge — routes to specialist",
        "desc": (
            "No account ID. "
            "Turn 1: 'I was charged $129 three months ago that I want refunded. "
            "I cancelled that billing cycle in advance.' "
            "Old billing dispute — not the current pending balance — outside VA scope. "
            "PASS = agent acknowledged the request, confirmed it is outside what the VA can "
            "resolve, and offered to connect to a billing specialist or directed to support. "
            "FAIL = agent tried to process the refund or ignored the request."
        ),
        "db_mod": None,
        "turns": [
            "I was charged $129 three months ago that I want refunded. "
            "I cancelled that billing cycle in advance.",
        ],
    },
    {
        "id": "G18-S134",
        "title": "Out-of-scope: competitor comparison — agent declines and stays on topic",
        "desc": (
            "No account ID. "
            "Turn 1: 'How does Orbit compare to Asana for project management? "
            "And does Asana offer fee waivers like you do?' "
            "Agent must not speculate on competitor policies or make comparisons. "
            "PASS = agent declined to compare Orbit to Asana, stayed in scope, "
            "and offered to explain what Orbit itself offers instead. "
            "FAIL = agent made any comparative claim about Asana or discussed competitor features."
        ),
        "db_mod": None,
        "turns": [
            "How does Orbit compare to Asana for project management? "
            "And does Asana offer fee waivers like you do?",
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
    print("GROUP 18 — RAG Edge Cases + Routing Gaps (Scenarios S127–S134)")
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
    print("SUMMARY — Group 18  (LLM-as-judge)")
    print(SEP)
    for sc_id, title, status, verdict in results:
        sym = {"PASS": "✓", "FAIL": "✗", "ERROR": "!!"}.get(status, "?")
        print(f"  {sc_id:<12} {sym} {status:<6}  {title}")
        print(f"               {verdict}")
    passed_count = sum(1 for _, _, s, _ in results if s == "PASS")
    print(f"\n  {passed_count}/{len(SCENARIOS)} passing\n{SEP}\n")


if __name__ == "__main__":
    asyncio.run(main())
