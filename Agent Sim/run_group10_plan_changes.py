"""
run_group10_plan_changes.py — Group 10: Plan Changes — Active Accounts (Scenarios 56–65)
Uses LLM-as-judge (gemini-2.5-flash) for semantic PASS/FAIL grading.

Tests DA4_PlanAgent (validate → execute), seat limit enforcement, downgrade blocking,
same-plan detection, temporary duration, and highest/lowest plan edge cases.
All accounts are ACTIVE — no restore flow involved.

Run from c:\\Muru_Workspace:
    python "pay_restore_demo/Agent Sim/run_group10_plan_changes.py"
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
# Group 10 scenarios — Plan Changes (Active Accounts)
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "G10-S56",
        "title": "Clean upgrade — Team → Business (Casey 20006)",
        "desc": (
            "Account 20006 (Casey, Driftwood, Team plan, ACTIVE, 5 seats). "
            "Turn 1: 'Account 20006 — I want to upgrade to Business.' "
            "T9: eligible=True, direction=upgrade, 5 seats < 30 max → seat_count_ok=True. "
            "Agent presents new plan details: $129/mo, 500 GB, up to 30 users. "
            "Turn 2: 'Yes, go ahead with the upgrade.' "
            "T6: upgrades to Business (no duration = permanent). T8: receipt sent. "
            "PASS = agent upgraded to Business, confirmed price ($129) and storage (500 GB). "
            "FAIL = agent denied the upgrade or gave wrong plan details."
        ),
        "db_mod": None,
        "turns": [
            "Account 20006 — I want to upgrade to Business.",
            "Yes, go ahead with the upgrade.",
        ],
    },
    {
        "id": "G10-S57",
        "title": "Downgrade BLOCKED by seat count (Drew 20007)",
        "desc": (
            "Account 20007 (Drew, Lumen Co, Business plan, ACTIVE, 25 seats). "
            "Turn 1: 'Account 20007, we want to downgrade to the Team plan to save costs.' "
            "T9: seat_count_ok=False (25 seats > 10 max on Team). eligible=False → HARD STOP. "
            "Agent must explain the seat limit is exceeded and escalate. "
            "Expected: 'Your team has 25 active seats, which exceeds the Team plan's 10-seat limit. "
            "I'll connect you with our support team to deactivate seats before downgrading.' "
            "T6 must NEVER be called. "
            "PASS = agent blocked the downgrade and explained the seat count issue (25 > 10). "
            "FAIL = agent executed the downgrade despite the seat count violation."
        ),
        "db_mod": None,
        "turns": [
            "Account 20007, we want to downgrade to the Team plan to save costs.",
        ],
    },
    {
        "id": "G10-S58",
        "title": "Clean downgrade — Business → Team (Quinn 20008)",
        "desc": (
            "Account 20008 (Quinn, Pathfinder, Business plan, ACTIVE, 5 seats). "
            "Turn 1: 'Account 20008. We want to move down to the Team plan — we don't need Business anymore.' "
            "T9: seat_count_ok=True (5 seats ≤ 10 max). direction=downgrade. "
            "Agent must present storage reduction warning (500 GB → 100 GB, informational only). "
            "Turn 2: 'Yes, proceed with the downgrade.' "
            "T6: downgrades to Team (no duration = permanent). T8: receipt sent. "
            "PASS = agent warned about storage reduction (500 → 100 GB) and completed the downgrade. "
            "FAIL = agent blocked the downgrade despite seats being within limit, or skipped warning."
        ),
        "db_mod": None,
        "turns": [
            "Account 20008. We want to move down to the Team plan — we don't need Business anymore.",
            "Yes, proceed with the downgrade.",
        ],
    },
    {
        "id": "G10-S59",
        "title": "Upgrade without naming plan — agent asks which plan",
        "desc": (
            "Account 20006 (Casey, Driftwood, Team plan, ACTIVE). "
            "Turn 1: 'Account 20006 — I want to upgrade.' (no plan named) "
            "Agent must NOT guess a plan. Must acknowledge current plan (Team) and ask which "
            "direction: Business at $129/mo (30 users) or Enterprise at $399/mo (100 users). "
            "Agent presents only valid upgrade options (not Individual, not Team). "
            "PASS = agent asked which plan and presented at least Business and Enterprise as options. "
            "FAIL = agent assumed a plan without asking, or presented plans in wrong direction."
        ),
        "db_mod": None,
        "turns": [
            "Account 20006 — I want to upgrade.",
        ],
    },
    {
        "id": "G10-S60",
        "title": "Temporary upgrade with duration — auto-revert date confirmed",
        "desc": (
            "Account 20006 (Casey, Driftwood, Team plan, ACTIVE, 5 seats). "
            "Turn 1: 'Account 20006 — upgrade us to Business for 2 months.' "
            "T9: eligible=True. DA4 presents plan details including the 2-month duration. "
            "Turn 2: 'Yes, go ahead.' "
            "T6: upgrades to Business with duration_months=2 → downgrade_date stored. "
            "The system calculates revert date as 2 × 30 = 60 days from today (not strict calendar months). "
            "Agent must confirm the auto-revert date (~60 days from today). "
            "PASS = agent confirmed Business upgrade with a temporary duration and an auto-revert date "
            "(a date 60 days from today is correct; 1-2 days difference from exact calendar months is acceptable). "
            "FAIL = agent made the upgrade permanent (no revert date), or refused the temporary upgrade."
        ),
        "db_mod": None,
        "turns": [
            "Account 20006 — upgrade us to Business for 2 months.",
            "Yes, go ahead.",
        ],
    },
    {
        "id": "G10-S61",
        "title": "Already on highest plan — Enterprise upgrade request",
        "desc": (
            "Account 20010 (Avery, Stratos, Enterprise plan — but make it ACTIVE for this test). "
            "DB modified: set status=ACTIVE, suspension_date=NULL, pending_balance=0. "
            "Turn 1: 'Account 20010 — can we upgrade to a higher tier?' "
            "T9 or agent logic: Enterprise is the highest plan — no upgrade available. "
            "Agent must explain they are already on the top tier (Enterprise). "
            "PASS = agent explained Enterprise is the highest plan and no upgrade is available. "
            "FAIL = agent attempted to upgrade past Enterprise or gave wrong information."
        ),
        "db_mod": {
            "sql": "UPDATE customer_accounts SET status='ACTIVE', suspension_date=NULL, pending_balance=0 WHERE account_id=20010",
        },
        "turns": [
            "Account 20010 — can we upgrade to a higher tier?",
        ],
    },
    {
        "id": "G10-S62",
        "title": "Already on lowest plan — Individual downgrade request",
        "desc": (
            "Account 20004 (Riley, Nomad Labs, Individual plan). "
            "DB modified: set status=ACTIVE, suspension_date=NULL, pending_balance=0. "
            "Turn 1: 'Account 20004 — I want to downgrade to a lower plan.' "
            "Individual is the lowest plan — no downgrade available. "
            "Agent must explain they are already on the lowest tier. "
            "PASS = agent explained Individual is the lowest plan and no downgrade is available. "
            "FAIL = agent attempted to downgrade below Individual or gave wrong information."
        ),
        "db_mod": {
            "sql": "UPDATE customer_accounts SET status='ACTIVE', suspension_date=NULL, pending_balance=0 WHERE account_id=20004",
        },
        "turns": [
            "Account 20004 — I want to downgrade to a lower plan.",
        ],
    },
    {
        "id": "G10-S63",
        "title": "Boundary seat count — exactly at new plan limit (10 seats → Team)",
        "desc": (
            "Account 20008 (Quinn, Business plan, ACTIVE). "
            "DB modified: set seat_count=10. "
            "T9: seat_count=10, Team plan max_users=10 → seat_count_ok=True (10 ≤ 10). "
            "Downgrade to Team should proceed — boundary case. "
            "Turn 1: 'Account 20008 — downgrade us to Team.' "
            "Turn 2: 'Yes, downgrade.' "
            "PASS = agent allowed the downgrade (10 seats ≤ 10 max Team limit). "
            "FAIL = agent blocked the downgrade claiming seats exceed the limit (10 is NOT over 10)."
        ),
        "db_mod": {
            "sql": "UPDATE customer_accounts SET seat_count=10 WHERE account_id=20008",
        },
        "turns": [
            "Account 20008 — downgrade us to Team.",
            "Yes, downgrade.",
        ],
    },
    {
        "id": "G10-S64",
        "title": "Same plan request — no change needed",
        "desc": (
            "Account 20006 (Casey, Driftwood, Team plan, ACTIVE). "
            "Turn 1: 'Account 20006 — can you switch us to the Team plan?' (already on Team) "
            "Agent must recognize no change is needed. "
            "Expected: something like 'You're already on the Team plan — no change is needed. "
            "Were you looking to upgrade or downgrade instead?' "
            "PASS = agent noted the account is already on Team and did not execute any plan change. "
            "FAIL = agent attempted to 'change' to the same plan or confirmed an unnecessary change."
        ),
        "db_mod": None,
        "turns": [
            "Account 20006 — can you switch us to the Team plan?",
        ],
    },
    {
        "id": "G10-S65",
        "title": "Customer cancels upgrade after validation — before T6",
        "desc": (
            "Account 20006 (Casey, Driftwood, Team plan, ACTIVE). "
            "Turn 1: 'Account 20006 — upgrade me to Business.' "
            "DA4 validates, presents plan details, awaits confirmation. "
            "Turn 2: 'Wait, actually I don't want to do this right now.' "
            "Agent must NOT call T6 (ChangePlan). Upgrade cancelled. "
            "Expected: 'No problem — no changes have been made. Your account remains on the "
            "Team plan. Is there anything else I can help you with?' "
            "PASS = agent cancelled the upgrade without executing T6, confirmed no change made. "
            "FAIL = agent executed the upgrade despite the customer cancelling."
        ),
        "db_mod": None,
        "turns": [
            "Account 20006 — upgrade me to Business.",
            "Wait, actually I don't want to do this right now.",
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
    print("GROUP 10 — Plan Changes: Active Accounts (Scenarios 56–65)")
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
    print("SUMMARY — Group 10  (LLM-as-judge)")
    print(SEP)
    for sc_id, title, status, verdict in results:
        sym = {"PASS": "✓", "FAIL": "✗", "ERROR": "!!"}.get(status, "?")
        print(f"  {sc_id:<10} {sym} {status:<6}  {title}")
        print(f"             {verdict}")
    passed_count = sum(1 for _, _, s, _ in results if s == "PASS")
    print(f"\n  {passed_count}/{len(SCENARIOS)} passing\n{SEP}\n")


if __name__ == "__main__":
    asyncio.run(main())
