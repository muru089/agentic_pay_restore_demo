"""
run_group4_waiver.py — Group 4: Fee Waiver — Boundary & Edge Cases (Scenarios 21–28)
Uses LLM-as-judge (gemini-2.5-flash) for semantic PASS/FAIL grading.

Run from c:\\Muru_Workspace:
    python "pay_restore_demo/Agent Sim/run_group4_waiver.py"
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
# Group 4 scenarios — Fee Waiver Boundary & Edge Cases
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "G4-S21",
        "title": "Tenure exactly 6.0 months — FAIL Rule A (strictly > 6 required)",
        "desc": (
            "Account 20009 (Jamie, Business plan, SUSPENDED, tenure=6.0 months exactly, autopay=ON, "
            "no prior waiver). The fee waiver requires tenure STRICTLY GREATER THAN 6 months. "
            "6.0 months is NOT strictly greater than 6 — Rule A fails. "
            "Agent must state the late fee of $50 applies (Business plan late fee) and explain "
            "that the account does not meet the 6-month minimum (it is exactly 6 months). "
            "Note: agent may also show data safety and card info alongside the fee result — this "
            "is acceptable and expected for suspended accounts running the full diagnostic. "
            "The sole pass/fail criterion is whether the fee waiver decision is correct: "
            "PASS = agent correctly denied the waiver, citing the 6-month minimum rule, "
            "and stated the $50 late fee. Additional context (data check, card prompt) is fine. "
            "FAIL = agent granted the waiver for a 6.0-month account."
        ),
        "db_mod": None,
        "turns": [
            "Account 20009 — we've been suspended for about 20 days. Can I get the late fee waived? "
            "I've had AutoPay on the whole time.",
            "New card number is 4111 1111 1111 7777. Go ahead and pay.",
        ],
    },
    {
        "id": "G4-S22",
        "title": "Tenure > 6 months — PASS Rule A",
        "desc": (
            "Account 20001 (Alex, Team plan, SUSPENDED, tenure=9.0 months, autopay=ON, no prior waiver). "
            "All 3 waiver rules pass: tenure 9mo > 6mo (Rule A), autopay ON (Rule B), no prior waiver (Rule C). "
            "Agent must confirm the late fee is WAIVED and state the reason. "
            "PASS = agent granted the fee waiver and completed the restore. "
            "FAIL = agent denied the waiver for an eligible account."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended, AutoPay failed on our expired card. "
            "Please restore and waive the late fee. New card: 4111 1111 1111 4321. Go ahead.",
        ],
    },
    {
        "id": "G4-S23",
        "title": "AutoPay OFF — FAIL Rule B (long tenure does not override)",
        "desc": (
            "Account 20005 (Morgan, Team plan, SUSPENDED, tenure=18 months, autopay=OFF, no prior waiver). "
            "Rule B fails because AutoPay was not enabled. Tenure of 18 months satisfies Rule A. "
            "No prior waiver satisfies Rule C. But Rule B (autopay=OFF) blocks the waiver. "
            "A $25 late fee applies (Team plan). Long tenure is noted but does NOT override autopay rule. "
            "Agent must explain autopay was not enabled, NOT make exceptions for long tenure. "
            "PASS = agent denied waiver citing AutoPay was not enabled, stated $25 fee. "
            "FAIL = agent granted waiver citing long tenure, or failed to mention autopay."
        ),
        "db_mod": None,
        "turns": [
            "This is account 20005. We've been suspended for a few days. I've been a customer for "
            "18 months — can you waive the late fee? I need to restore our account.",
            "Use the card on file. Yes, restore it.",
        ],
    },
    {
        "id": "G4-S24",
        "title": "Last waiver exactly 12 months ago — PASS Rule C",
        "desc": (
            "Account 20004 (Riley, Individual plan, SUSPENDED, tenure=7 months, autopay=ON). "
            "DB modified: last_waiver_date set to 366 days ago (older than 12 months). "
            "Rule C requires no prior waiver in the last 12 months. "
            "A waiver from 366 days ago IS older than 12 months — Rule C passes. "
            "All 3 rules should pass: tenure 7mo > 6mo (A), autopay ON (B), waiver > 12mo ago (C). "
            "Agent must GRANT the waiver. "
            "PASS = agent granted waiver and completed restore. "
            "FAIL = agent incorrectly denied waiver for account with 366-day-old prior waiver."
        ),
        "db_mod": {
            "sql": f"UPDATE customer_accounts SET last_waiver_date='{date_offset(366)}', waivers_used_12m=0 WHERE account_id=20004",
        },
        "turns": [
            "Account 20004, we're suspended. Card expired, I have a new one. "
            "Please waive the late fee if possible — it's been over a year since we last needed one.",
            f"New card: 4111 1111 1111 5555. Yes, go ahead.",
        ],
    },
    {
        "id": "G4-S25",
        "title": "Last waiver 11 months 29 days ago — FAIL Rule C",
        "desc": (
            "Account 20004 (Riley, Individual plan, SUSPENDED, tenure=7 months, autopay=ON). "
            "DB modified: last_waiver_date set to 359 days ago (within 12 months). "
            "Rule C fails because the prior waiver was only 359 days ago (less than 12 months). "
            "A $10 late fee applies (Individual plan late fee). "
            "Agent must DENY the waiver and explain the prior waiver is too recent. "
            "Note: agent may also show data safety and card info alongside the fee result — this "
            "is acceptable and expected for suspended accounts running the full diagnostic. "
            "The sole pass/fail criterion is whether the fee waiver decision is correct: "
            "PASS = agent denied waiver citing recent prior waiver (within 12-month window). "
            "Additional context (data check, card prompt) is fine. "
            "FAIL = agent granted waiver despite the recent prior waiver."
        ),
        "db_mod": {
            "sql": f"UPDATE customer_accounts SET last_waiver_date='{date_offset(359)}', waivers_used_12m=1 WHERE account_id=20004",
        },
        "turns": [
            "Account 20004, suspended, card expired. Can we get the late fee waived?",
            "New card: 4111 1111 1111 5555. Go ahead.",
        ],
    },
    {
        "id": "G4-S26",
        "title": "All 3 waiver rules fail simultaneously",
        "desc": (
            "Account 20002 (Jordan, Team plan, SUSPENDED, tenure=2 months, autopay=OFF). "
            "DB modified: last_waiver_date set to 30 days ago. "
            "All 3 rules fail: tenure 2mo ≤ 6mo (Rule A), autopay=OFF (Rule B), "
            "waiver 30 days ago (Rule C). "
            "Agent must explain that a $25 late fee applies. "
            "Ideally mentions at least the primary reason (Rule A — account too new). "
            "PASS = agent stated the late fee applies and gave at least one reason for denial. "
            "FAIL = agent granted the waiver despite all 3 rules failing."
        ),
        "db_mod": {
            "sql": f"UPDATE customer_accounts SET last_waiver_date='{date_offset(30)}', waivers_used_12m=1 WHERE account_id=20002",
        },
        "turns": [
            "Account 20002, we're suspended. Please restore our account and waive the late fee.",
            "Use the card on file. Yes, go ahead.",
        ],
    },
    {
        "id": "G4-S27",
        "title": "Customer insists waiver despite denial — agent holds firm",
        "desc": (
            "Account 20002 (Jordan, Team plan, tenure=2 months, FAIL Rule A). "
            "After restore completes with $25 fee, customer insists the fee should be waived. "
            "Agent must hold firm — explain the reason clearly, do not capitulate, "
            "do not offer to 're-check' or grant a courtesy waiver not supported by the rules. "
            "PASS = agent politely but firmly maintained the waiver denial with a clear reason, "
            "without re-running T4 or overriding the policy. "
            "FAIL = agent agreed to waive the fee or offered to 'try again'."
        ),
        "db_mod": None,
        "turns": [
            "Account 20002. We're suspended — restore it and waive the fee.",
            "Use the card on file. Yes, go ahead and restore.",
            "I still think you should waive that fee. We've been a loyal customer.",
        ],
    },
    {
        "id": "G4-S28",
        "title": "Customer asks to check waiver eligibility again after denial",
        "desc": (
            "Account 20002 (Jordan, Team plan, tenure=2 months, FAIL Rule A). "
            "After restore completes with $25 fee, customer asks agent to 'check again' "
            "claiming there might be an error. "
            "Agent should confirm the result stands without re-querying T4 unnecessarily. "
            "Agent may explain the rule clearly but should not call the fee waiver tool again "
            "just because the customer asked nicely. "
            "PASS = agent confirmed the fee denial is correct, gave the reason, without re-running eligibility check. "
            "FAIL = agent agreed to re-run the check or reversed the decision."
        ),
        "db_mod": None,
        "turns": [
            "Account 20002. Suspended — restore it.",
            "Use the card on file. Yes, restore it.",
            "Actually, can you check the waiver eligibility again? I think there might be an error.",
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
    print("GROUP 4 — Fee Waiver: Boundary & Edge Cases (Scenarios 21–28)")
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
    print("SUMMARY — Group 4  (LLM-as-judge)")
    print(SEP)
    for sc_id, title, status, verdict in results:
        sym = {"PASS": "✓", "FAIL": "✗", "ERROR": "!!"}.get(status, "?")
        print(f"  {sc_id:<8} {sym} {status:<6}  {title}")
        print(f"           {verdict}")
    passed_count = sum(1 for _, _, s, _ in results if s == "PASS")
    print(f"\n  {passed_count}/{len(SCENARIOS)} passing\n{SEP}\n")


if __name__ == "__main__":
    asyncio.run(main())
