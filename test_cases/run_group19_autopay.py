"""
run_group19_autopay.py — Group 19: AutoPay Management (Scenarios G19-S01 to G19-S06)
Uses LLM-as-judge (gemini-2.5-flash) for semantic PASS/FAIL grading.

Tests T13_UpdateAutoPay across active and suspended accounts.
Key coverage:
  - Enable/disable AutoPay on ACTIVE accounts
  - Enable AutoPay on SUSPENDED account where it changes waiver outcome (Morgan 18mo)
  - Enable AutoPay on SUSPENDED account where waiver is still denied (Jordan 2mo — Rule A)
  - AutoPay status inquiry (no toggle)
  - AutoPay request without account ID (guardrail)

Run from c:\\Muru_Workspace:
    python "pay_restore_demo/test_cases/run_group19_autopay.py"
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
# Group 19 scenarios — AutoPay Management
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "G19-S01",
        "title": "Enable AutoPay — ACTIVE account (Dana 20015, AutoPay OFF)",
        "desc": (
            "Account 20015 (Dana, Ironforge, Team, ACTIVE, AutoPay OFF). "
            "Turn 1: 'Account 20015 — please enable AutoPay for me.' "
            "T13_UpdateAutoPay called with enabled=1. "
            "Expected: agent confirms AutoPay is now enabled. "
            "Mention that future invoices will be charged automatically. "
            "No payment processing — this is a settings change only. "
            "PASS = agent confirmed AutoPay enabled and mentioned automatic billing going forward. "
            "FAIL = agent refused, called a payment tool, or failed to confirm the change."
        ),
        "db_mod": None,
        "turns": [
            "Account 20015 — please enable AutoPay for me.",
        ],
    },
    {
        "id": "G19-S02",
        "title": "Disable AutoPay — ACTIVE account (Casey 20006, AutoPay ON)",
        "desc": (
            "Account 20006 (Casey, Driftwood, Team, ACTIVE, AutoPay ON). "
            "Turn 1: 'Account 20006 — turn off AutoPay, I want to pay manually.' "
            "T13_UpdateAutoPay called with enabled=0. "
            "Expected: agent confirms AutoPay is now disabled. "
            "Agent should note that manual payers may lose waiver eligibility if a payment is missed "
            "(Rule B: AutoPay must be enabled). No payment processing. "
            "PASS = agent confirmed AutoPay disabled and mentioned the waiver eligibility impact. "
            "FAIL = agent refused, required consent, or processed a payment."
        ),
        "db_mod": None,
        "turns": [
            "Account 20006 — turn off AutoPay, I want to pay manually.",
        ],
    },
    {
        "id": "G19-S03",
        "title": "Enable AutoPay on SUSPENDED account — waiver still denied (Jordan 20002, 2mo)",
        "desc": (
            "Account 20002 (Jordan, Sprinto, Team, SUSPENDED, AutoPay OFF, 2.0 months tenure, balance $49). "
            "Jordan asks to enable AutoPay BEFORE paying, hoping it helps with the fee. "
            "Turn 1: 'Account 20002 — before I pay, can I enable AutoPay first?' "
            "T13_UpdateAutoPay called with enabled=1. "
            "Agent must NOT promise the waiver — must say 'may qualify' since it depends on T4 re-check. "
            "Agent should then resume the restore flow (data check, fee preview, card situation). "
            "Turn 2: 'Yes, go ahead and charge my card on file.' "
            "T4 re-checks: Rule A fails (2mo < 6mo threshold). Waiver denied. "
            "T3 charges $49 + $25 = $74. DA3 restores. "
            "PASS = agent enabled AutoPay without promising the waiver, then charged $74 total (not $49), "
            "completed the restore, and did NOT claim the waiver was granted. "
            "FAIL = agent promised the waiver would be granted, or charged only $49, or refused to enable AutoPay."
        ),
        "db_mod": None,
        "turns": [
            "Account 20002 — before I pay, can I enable AutoPay first?",
            "Yes, go ahead and charge my card on file.",
        ],
    },
    {
        "id": "G19-S04",
        "title": "Enable AutoPay on SUSPENDED account — waiver NOW passes (Morgan 20005, 18mo)",
        "desc": (
            "Account 20005 (Morgan, Crestline, Team, SUSPENDED, AutoPay OFF, 18mo tenure, balance $49). "
            "Morgan previously failed waiver only on Rule B (AutoPay OFF). "
            "After enabling AutoPay, Rule B passes → all 3 rules pass → waiver granted. "
            "Turn 1: 'Account 20005. Can I enable AutoPay? I read it helps with the late fee.' "
            "T13_UpdateAutoPay called with enabled=1. "
            "Agent should: confirm AutoPay enabled, note the fee will be re-evaluated, "
            "then present the Turn 1 diagnostic (data check result, balance, fee preview, card situation). "
            "Turn 2: 'Yes, go ahead and charge my card on file ending in 6644.' "
            "T4 re-checks with AutoPay now ON: Rule A pass (18mo > 6mo), Rule B NOW pass, Rule C pass. "
            "Waiver granted. T3 charges $49 only (no late fee). DA3 restores. "
            "PASS = agent confirmed waiver was granted (fee waived) and charged only $49, account restored. "
            "FAIL = agent charged $74 (applied the fee despite AutoPay now being ON), "
            "or refused to enable AutoPay, or claimed waiver before T4 ran."
        ),
        "db_mod": None,
        "turns": [
            "Account 20005. Can I enable AutoPay? I read it helps with the late fee.",
            "Yes, go ahead and charge my card on file ending in 6644.",
        ],
    },
    {
        "id": "G19-S05",
        "title": "AutoPay status inquiry — active account (not a toggle request)",
        "desc": (
            "Account 20006 (Casey, Driftwood, Team, ACTIVE, AutoPay ON). "
            "Customer asks about their current AutoPay status — not asking to change it. "
            "Turn 1: 'Account 20006 — is AutoPay turned on for my account?' "
            "Agent should answer from T1 data (T1 returns autopay_active). "
            "T13 must NOT be called — this is an inquiry, not a toggle request. "
            "Expected: 'Yes, AutoPay is currently enabled on your account.' "
            "No changes made. No payment processing. "
            "PASS = agent correctly reported AutoPay status (ON for 20006) without calling T13. "
            "FAIL = agent called T13 (changed the setting) or gave wrong status."
        ),
        "db_mod": None,
        "turns": [
            "Account 20006 — is AutoPay turned on for my account?",
        ],
    },
    {
        "id": "G19-S06",
        "title": "AutoPay enable request with no account ID — auth gate fires",
        "desc": (
            "Customer asks to enable AutoPay but provides no account ID. "
            "Turn 1: 'I want to enable AutoPay on my account.' "
            "Auth gate must fire before any tools are called. "
            "T1_GetAccount must NOT be called. T13 must NOT be called. "
            "Expected response: ask for the 5-digit account ID. "
            "Example: 'To get started, please share your 5-digit account ID.' "
            "PASS = agent asked for the account ID and did not process the request. "
            "FAIL = agent called T13 without an account ID, or asked for name/email instead of ID."
        ),
        "db_mod": None,
        "turns": [
            "I want to enable AutoPay on my account.",
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
    print("GROUP 19 — AutoPay Management (Scenarios G19-S01 to G19-S06)")
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
    print("SUMMARY — Group 19  (LLM-as-judge)")
    print(SEP)
    for sc_id, title, status, verdict in results:
        sym = {"PASS": "✓", "FAIL": "✗", "ERROR": "!!"}.get(status, "?")
        print(f"  {sc_id:<12} {sym} {status:<6}  {title}")
        print(f"               {verdict}")
    passed_count = sum(1 for _, _, s, _ in results if s == "PASS")
    print(f"\n  {passed_count}/{len(SCENARIOS)} passing\n{SEP}\n")


if __name__ == "__main__":
    asyncio.run(main())
