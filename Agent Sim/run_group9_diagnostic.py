"""
run_group9_diagnostic.py — Group 9: SA1 Diagnostic Supervisor (Scenarios SD01–SD04)
Uses LLM-as-judge (gemini-2.5-flash) for semantic PASS/FAIL grading.

Tests the SA1_DiagnosticSupervisor parallel fan-out pattern and single-intent bypass.
Uses diagnostic demo accounts 20012 (Taylor — storage near limit) and 20013 (Blake — GitHub auth failure).
Both accounts are ACTIVE — no billing or restore issues.

Run from c:\\Muru_Workspace:
    python "pay_restore_demo/Agent Sim/run_group9_diagnostic.py"
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
# Group 9 scenarios — SA1 Diagnostic Supervisor
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "G9-SD01",
        "title": "Ambiguous complaint — storage is culprit (Taylor 20012)",
        "desc": (
            "Account 20012 (Taylor, Brightline, Team plan, ACTIVE). "
            "T11: 95/100 GB used (95%) — near_limit=True. T12: Slack integration healthy. "
            "Customer: 'Account 20012 — something feels off lately. Projects are loading slowly "
            "and a few uploads just failed. Not sure what's going on.' "
            "Agent must route to SA1_DiagnosticSupervisor (ambiguous multi-dimensional complaint). "
            "SA1 fans out DA1 + DA5_StorageAgent + DA6_IntegrationAgent in parallel. "
            "SA1 synthesises: PRIMARY_FINDING=storage (HIGH), integration=healthy, account=healthy. "
            "Agent explains storage near-limit (95/100 GB) as the cause of upload failures. "
            "Turn 2: 'Ah, that makes sense. What are my options?' "
            "Agent presents upgrade path (Business = 500 GB) or archiving old files. "
            "PASS = agent identified storage as the root cause (95/100 GB) and offered options. "
            "FAIL = agent blamed billing, integration, or gave a generic 'contact support' response."
        ),
        "db_mod": None,
        "turns": [
            "Account 20012 — something feels off lately. Projects are loading slowly and a few "
            "uploads just failed. Not sure what's going on.",
            "Ah, that makes sense. What are my options?",
        ],
    },
    {
        "id": "G9-SD02",
        "title": "Ambiguous complaint — integration is culprit (Blake 20013)",
        "desc": (
            "Account 20013 (Blake, Nexus Digital, Business plan, ACTIVE). "
            "T11: 45/500 GB (9%) — storage healthy. T12: GitHub auth_failure, 5 auth failures, "
            "last sync 3 days ago, action_required=True. "
            "Customer: 'Account 20013 — things just don't feel right. My team says changes aren't "
            "showing up in projects, like it's not syncing. I don't know if it's a billing thing or what.' "
            "Agent must route to SA1_DiagnosticSupervisor. "
            "SA1 fans out all 3 agents in parallel. "
            "SA1 synthesises: PRIMARY_FINDING=integration (HIGH), storage=healthy, account=healthy. "
            "Agent confirms it's NOT billing — GitHub auth failure (5 auth failures recorded). "
            "Turn 2: 'Yes, please walk me through how to fix the GitHub connection.' "
            "Agent provides reconnect steps to fix the integration in Orbit Settings → Integrations. "
            "PASS = agent identified GitHub auth failure (with 5 failures) as the root cause "
            "AND provided some actionable reconnect steps in Turn 2. "
            "FAIL = agent blamed storage or billing, said all systems are healthy, or gave no fix steps."
        ),
        "db_mod": None,
        "turns": [
            "Account 20013 — things just don't feel right. My team says changes aren't showing "
            "up in projects, like it's not syncing. I don't know if it's a billing thing or what.",
            "Yes, please walk me through how to fix the GitHub connection.",
        ],
    },
    {
        "id": "G9-SD03",
        "title": "Single-intent storage query — SA1 NOT invoked (Taylor 20012)",
        "desc": (
            "Account 20012 (Taylor, Team plan, ACTIVE). "
            "Customer asks: 'Account 20012 — how much storage am I using right now?' "
            "This is a single-dimension storage question — root_agent must route DIRECTLY to "
            "DA5_StorageAgent (T11), bypassing SA1_DiagnosticSupervisor entirely. "
            "T11: 95/100 GB, near_limit=True. "
            "Agent reports the storage usage numbers (95 GB of 100 GB, or 95%). "
            "Additional context or recommendations are allowed — only the numbers and SA1 routing matter. "
            "PASS = agent reported correct storage usage (95 GB of 100 GB, or 95%) AND did not invoke SA1. "
            "FAIL = agent invoked SA1, or reported wrong numbers, or said storage was healthy."
        ),
        "db_mod": None,
        "turns": [
            "Account 20012 — how much storage am I using right now?",
        ],
    },
    {
        "id": "G9-SD04",
        "title": "Single-intent integration query — SA1 NOT invoked (Blake 20013)",
        "desc": (
            "Account 20013 (Blake, Business plan, ACTIVE). "
            "Customer asks: 'Account 20013 — is our GitHub integration working? It feels like "
            "it stopped syncing.' "
            "Single-dimension integration question — root_agent must route DIRECTLY to "
            "DA6_IntegrationAgent (T12), bypassing SA1. "
            "T12: GitHub auth_failure, 5 auth failures, last sync 3 days ago, action_required=True. "
            "Agent reports the GitHub integration issue directly. "
            "PASS = agent reported GitHub auth failure (5 failures, last sync 3 days ago) without SA1. "
            "FAIL = agent invoked SA1, or reported integration as healthy."
        ),
        "db_mod": None,
        "turns": [
            "Account 20013 — is our GitHub integration working? It feels like it stopped syncing.",
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
    print("GROUP 9 — SA1 Diagnostic Supervisor (Scenarios SD01–SD04)")
    print("Grading: LLM-as-judge (gemini-2.5-flash)")
    print("Accounts: 20012 Taylor (storage) · 20013 Blake (integration)")
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
    print("SUMMARY — Group 9  (LLM-as-judge)")
    print(SEP)
    for sc_id, title, status, verdict in results:
        sym = {"PASS": "✓", "FAIL": "✗", "ERROR": "!!"}.get(status, "?")
        print(f"  {sc_id:<10} {sym} {status:<6}  {title}")
        print(f"             {verdict}")
    passed_count = sum(1 for _, _, s, _ in results if s == "PASS")
    print(f"\n  {passed_count}/{len(SCENARIOS)} passing\n{SEP}\n")


if __name__ == "__main__":
    asyncio.run(main())
