"""
run_group5_retention.py — Group 5: Data Retention — Edge Cases (Scenarios 29–35)
Uses LLM-as-judge (gemini-2.5-flash) for semantic PASS/FAIL grading.

Run from c:\\Muru_Workspace:
    python "pay_restore_demo/Agent Sim/run_group5_retention.py"
"""
import asyncio, sys, os, io, time, datetime
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

today = datetime.date.today()

def date_offset(days):
    return (today - datetime.timedelta(days=days)).isoformat()

# ---------------------------------------------------------------------------
# Group 5 scenarios — Data Retention Edge Cases
# All DB mods use account 20003 (Sam, Business plan, $129, card 5517 expired,
# 28 projects, data_retention_days=30, normally 35 days suspended).
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "G5-S29",
        "title": "Suspended exactly 30 days — boundary (data SAFE per T2 rule)",
        "desc": (
            "Account 20003 (Sam, Business plan). DB modified: suspension_date = today - 30 days. "
            "T2 rule: days_suspended <= 30 → data SAFE. 30 == 30 satisfies the rule — data is safe. "
            "Agent must NOT present the AT RISK warning. "
            "Agent should confirm data is safe. Note: since the account is SUSPENDED, it is expected "
            "and acceptable for the agent to also include balance and card info (full diagnostic). "
            "The sole pass/fail criterion is whether data is correctly reported as SAFE at 30 days. "
            "PASS = agent confirmed data is safe (30 days is within the retention window). "
            "Agent may include additional balance/card context — this does not cause a FAIL. "
            "FAIL = agent incorrectly flagged data as AT RISK for a 30-day suspension."
        ),
        "db_mod": {
            "sql": f"UPDATE customer_accounts SET suspension_date='{date_offset(30)}' WHERE account_id=20003",
        },
        "turns": [
            "Account 20003 — we've been suspended for exactly a month. Is our data still safe?",
        ],
    },
    {
        "id": "G5-S30",
        "title": "Suspended 29 days — clearly SAFE",
        "desc": (
            "Account 20003 (Sam, Business plan). DB modified: suspension_date = today - 29 days. "
            "T2: 29 days <= 30 → data SAFE. "
            "Agent must confirm data is safe and proceed with normal restore flow. "
            "PASS = agent confirmed data is SAFE (any phrasing) and did NOT present an AT RISK "
            "warning. Mentioning project count is a bonus but not required for PASS. "
            "FAIL = agent flagged data as AT RISK, or stated suspension is over 30 days."
        ),
        "db_mod": {
            "sql": f"UPDATE customer_accounts SET suspension_date='{date_offset(29)}' WHERE account_id=20003",
        },
        "turns": [
            "Account 20003 — we've been suspended. Is our data safe? We need to restore urgently.",
        ],
    },
    {
        "id": "G5-S31",
        "title": "Suspended 31 days — AT RISK (just over threshold)",
        "desc": (
            "Account 20003 (Sam, Business plan). DB modified: suspension_date = today - 31 days. "
            "T2: 31 days > 30 → data AT RISK. "
            "Agent must present the AT RISK warning and the two paths: "
            "(A) proceed and check project dashboard, (B) connect to data recovery team. "
            "HARD STOP — agent must NOT proceed to payment in this turn. "
            "PASS = agent presented AT RISK warning with both paths and stopped. "
            "FAIL = agent said data is safe, or skipped the warning and proceeded to payment."
        ),
        "db_mod": {
            "sql": f"UPDATE customer_accounts SET suspension_date='{date_offset(31)}' WHERE account_id=20003",
        },
        "turns": [
            "Account 20003 — we need to restore. How long have we been suspended? Is our data there?",
        ],
    },
    {
        "id": "G5-S32",
        "title": "AT RISK step — customer asks project count without claiming they're safe",
        "desc": (
            "Account 20003 (Sam, 35 days suspended, AT RISK). "
            "Turn 1: restore intent → AT RISK warning presented with two paths. "
            "Turn 2: 'How many projects do we have in the account?' "
            "Agent must state the project count (28) but must NOT say the projects are safe or intact. "
            "The data retention status is uncertain — agent can confirm the count from T2 data "
            "but must not make claims about whether they are all accessible. "
            "PASS = agent stated project count (28) without claiming they are all safe or intact. "
            "FAIL = agent said '28 projects are intact/safe' on the AT RISK path."
        ),
        "db_mod": None,
        "turns": [
            "Account 20003 — we've been suspended for a long time. Is our data safe? Need to restore.",
            "How many projects do we have in the account?",
        ],
    },
    {
        "id": "G5-S33",
        "title": "AT RISK step — customer asks to skip the warning",
        "desc": (
            "Account 20003 (Sam, 35 days suspended, AT RISK). "
            "Turn 1: restore intent → AT RISK warning with two paths. "
            "Turn 2: 'Just skip the data warning and restore it.' "
            "Agent must NOT skip the warning. The two paths must be re-presented or maintained. "
            "Customer must explicitly choose Path A (proceed) or Path B (data team) before payment. "
            "PASS = agent declined to skip the warning, maintained the two-path choice. "
            "FAIL = agent accepted 'skip it' and proceeded directly to payment."
        ),
        "db_mod": None,
        "turns": [
            "Account 20003 — we're suspended. I need to get back in immediately.",
            "Just skip the data warning and restore the account.",
        ],
    },
    {
        "id": "G5-S34",
        "title": "After AT RISK restore — customer asks if projects are back",
        "desc": (
            "Account 20003 (Sam, 35 days suspended, AT RISK, card 5517 expired, $129 balance). "
            "Full restore flow: Turn 1 AT RISK warning, Turn 2 proceed, Turn 3 card + consent. "
            "After restore completes: Turn 4 'Are all our 28 projects back?' "
            "Agent must NOT confirm all projects are intact — data was AT RISK. "
            "Instead agent should direct customer to check the project dashboard. "
            "PASS = agent did NOT confirm projects are intact, directed to project dashboard. "
            "FAIL = agent said 'all 28 projects confirmed intact' or similar after AT RISK restore."
        ),
        "db_mod": None,
        "turns": [
            "Account 20003 — we've been suspended. Need to restore. Is our data still there?",
            "I understand the risk. I want to proceed with the restore.",
            "New card: 4111 1111 1111 9988. Yes, go ahead and charge it.",
            "Are all our 28 projects back?",
        ],
    },
    {
        "id": "G5-S35",
        "title": "Customer dismisses data risk — agent still presents both paths then proceeds",
        "desc": (
            "Account 20003 (Sam, 35 days suspended, AT RISK, card 5517 expired, $129 balance). "
            "Turn 1: 'I don't care about the data, just restore the account.' "
            "Even though customer dismissed the risk, agent must still present the AT RISK warning "
            "and both paths — the warning is mandatory. "
            "Turn 2: 'Go ahead, restore it.' → agent sets at_risk_proceeding=1, asks for card. "
            "Turn 3: card + 'yes' → payment + restore completes without 'projects intact' claim. "
            "PASS = agent presented the AT RISK warning in Turn 1 despite dismissal, then completed restore. "
            "FAIL = agent skipped the warning and went directly to payment, or failed to complete restore."
        ),
        "db_mod": None,
        "turns": [
            "Account 20003 — I don't care about the data, just restore the account now.",
            "Go ahead, restore it.",
            "New card: 4111 1111 1111 9988. Yes, charge it.",
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
    print("GROUP 5 — Data Retention: Edge Cases (Scenarios 29–35)")
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
    print("SUMMARY — Group 5  (LLM-as-judge)")
    print(SEP)
    for sc_id, title, status, verdict in results:
        sym = {"PASS": "✓", "FAIL": "✗", "ERROR": "!!"}.get(status, "?")
        print(f"  {sc_id:<8} {sym} {status:<6}  {title}")
        print(f"           {verdict}")
    passed_count = sum(1 for _, _, s, _ in results if s == "PASS")
    print(f"\n  {passed_count}/{len(SCENARIOS)} passing\n{SEP}\n")


if __name__ == "__main__":
    asyncio.run(main())
