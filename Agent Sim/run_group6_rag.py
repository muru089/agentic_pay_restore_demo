"""
run_group6_rag.py — Group 6: RAG Knowledge Questions (Scenarios 36–41)
Uses LLM-as-judge (gemini-2.5-flash) for semantic PASS/FAIL grading.

Scenarios test T10_SearchKnowledge retrieval and graceful fallback behavior.
No account ID is required for these scenarios — they are general policy/FAQ questions.

Run from c:\\Muru_Workspace:
    python "pay_restore_demo/Agent Sim/run_group6_rag.py"
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
# Group 6 scenarios — RAG Knowledge Questions
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "G6-S36",
        "title": "Plan features question — Business vs Team comparison",
        "desc": (
            "Customer asks: 'What's included in the Business plan and how does it compare to Team?' "
            "Agent must call T10_SearchKnowledge and answer from retrieved content only. "
            "Expected answer: Business plan — $129/mo, up to 30 users, 500 GB storage. "
            "Team plan — $49/mo, up to 10 users, 100 GB storage. "
            "Agent must not fabricate features not in the knowledge base. "
            "PASS = agent accurately described both plans with correct seats and storage. "
            "FAIL = agent fabricated wrong pricing/features or did not answer from retrieved content."
        ),
        "db_mod": None,
        "turns": [
            "What's included in the Business plan and how does it compare to Team?",
        ],
    },
    {
        "id": "G6-S37",
        "title": "Fee waiver eligibility — 3-rule explanation",
        "desc": (
            "Customer asks: 'How does the late fee waiver work? What do I need to qualify?' "
            "Agent must call T10_SearchKnowledge and answer from retrieved content. "
            "Expected: all 3 conditions explained — (1) tenure > 6 months, "
            "(2) AutoPay must be enabled, (3) no prior waiver used in the past 12 months. "
            "All three conditions must be present in the response. "
            "PASS = agent explained all 3 waiver conditions accurately. "
            "FAIL = agent omitted any of the 3 conditions or gave wrong eligibility criteria."
        ),
        "db_mod": None,
        "turns": [
            "How does the late fee waiver work? What do I need to qualify?",
        ],
    },
    {
        "id": "G6-S38",
        "title": "Data retention — 30-day suspension window",
        "desc": (
            "Customer asks: 'What happens to my data if my account is suspended for over a month?' "
            "Agent must call T10_SearchKnowledge. "
            "Expected: agent explains the 30-day data retention window. "
            "Data is preserved for up to 30 days of suspension. "
            "After 30 days, data may be archived or purged. "
            "Agent must cite 30 days as the threshold — not a different number. "
            "PASS = agent correctly stated the 30-day retention window. "
            "FAIL = agent fabricated a different timeframe or omitted the risk after 30 days."
        ),
        "db_mod": None,
        "turns": [
            "What happens to my data if my account is suspended for over a month?",
        ],
    },
    {
        "id": "G6-S39",
        "title": "Temporary upgrade — duration and auto-revert",
        "desc": (
            "Customer asks: 'Can I upgrade to Enterprise for just 2 months and then go back to "
            "Business automatically?' "
            "Agent must call T10_SearchKnowledge. "
            "Expected: agent confirms temporary upgrades are supported. Customer specifies a duration. "
            "Plan auto-reverts after the specified period. Agent confirms the auto-revert feature. "
            "PASS = agent confirmed temporary upgrades with auto-revert are possible. "
            "FAIL = agent said temporary upgrades are not supported, or did not confirm auto-revert."
        ),
        "db_mod": None,
        "turns": [
            "Can I upgrade to Enterprise for just 2 months and then go back to Business automatically?",
        ],
    },
    {
        "id": "G6-S40",
        "title": "Out-of-knowledge-base — GDPR DPA question (graceful fallback)",
        "desc": (
            "Customer asks: 'Does Orbit have a GDPR Data Processing Agreement I can sign? "
            "We need a DPA before our legal team approves the purchase.' "
            "Agent calls T10_SearchKnowledge. GDPR/DPA is not covered in any help center page. "
            "T10 should return [LOW_CONFIDENCE] or [NO_MATCH]. "
            "Agent must use graceful fallback — do NOT fabricate an answer. "
            "Required response: 'That's not something I have clear details on — I wouldn't want to "
            "guess on that. For the most accurate answer, our support team at support@orbit.io is "
            "the best resource.' "
            "PASS = agent used graceful fallback and did not fabricate a DPA answer. "
            "FAIL = agent fabricated a DPA policy or hallucinated an answer not from T10."
        ),
        "db_mod": None,
        "turns": [
            "Does Orbit have a GDPR Data Processing Agreement I can sign? "
            "We need a DPA before our legal team approves the purchase.",
        ],
    },
    {
        "id": "G6-S41",
        "title": "Cancellation policy — what happens after canceling",
        "desc": (
            "Customer asks: 'If we cancel our account, how long do we have to export our data?' "
            "Agent calls T10_SearchKnowledge. "
            "Expected: agent retrieves cancellation.html content. "
            "Answer should include: data export is recommended before cancellation, "
            "and 30-day post-cancel retention window. "
            "PASS = agent mentioned 30-day post-cancel data retention and export recommendation. "
            "FAIL = agent fabricated different retention rules or did not recommend export first."
        ),
        "db_mod": None,
        "turns": [
            "If we cancel our account, how long do we have to export our data?",
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
    print("GROUP 6 — RAG Knowledge Questions (Scenarios 36–41)")
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
    print("SUMMARY — Group 6  (LLM-as-judge)")
    print(SEP)
    for sc_id, title, status, verdict in results:
        sym = {"PASS": "✓", "FAIL": "✗", "ERROR": "!!"}.get(status, "?")
        print(f"  {sc_id:<8} {sym} {status:<6}  {title}")
        print(f"           {verdict}")
    passed_count = sum(1 for _, _, s, _ in results if s == "PASS")
    print(f"\n  {passed_count}/{len(SCENARIOS)} passing\n{SEP}\n")


if __name__ == "__main__":
    asyncio.run(main())
