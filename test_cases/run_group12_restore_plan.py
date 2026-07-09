"""
run_group12_restore_plan.py — Group 12: Plan Changes During Restore + Routing Edge Cases (S76–S83)
Uses LLM-as-judge (gemini-2.5-flash) for semantic PASS/FAIL grading.

Tests plan change routing during suspended-account restore flows (ROW 1/2 dispatch),
plus routing edge cases: active account restore attempt, cancel on suspended account,
balance-only on suspended account.

Run from c:\\Muru_Workspace:
    python "pay_restore_demo/Agent Sim/run_group12_restore_plan.py"
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
# Group 12 scenarios — Plan Changes During Restore + Routing Edge Cases
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "G12-S76",
        "title": "Upgrade requested in Turn 1 — customer skips it in Turn 3",
        "desc": (
            "Account 20001 (Alex, Team plan, SUSPENDED, card expired 4242). "
            "Turn 1: 'Account 20001 — we're suspended. Restore us and upgrade to Business.' "
            "Turn 2: New card 4111 1111 1111 4321, consent to pay. "
            "Turn 3: 'Actually, skip the upgrade — just the restore is fine.' "
            "Agent must restore (payment + DA3) in Turn 2, then in Turn 3 NOT execute the plan change. "
            "PASS = restore completed, plan upgrade skipped after customer declines in Turn 3. "
            "FAIL = agent executed the Business upgrade despite customer cancelling it."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended. Restore us and upgrade to Business.",
            "New card: 4111 1111 1111 4321. Go ahead and restore.",
            "Actually, skip the upgrade — just the restore is fine.",
        ],
    },
    {
        "id": "G12-S77",
        "title": "Customer changes target plan between Turn 1 and Turn 3",
        "desc": (
            "Account 20001 (Alex, Team plan, SUSPENDED, card expired 4242). "
            "Turn 1: 'Account 20001 — restore us and upgrade to Business.' "
            "Turn 2: New card 4111 1111 1111 4321, consent to restore. "
            "Turn 3: 'Actually, upgrade us to Enterprise instead of Business.' "
            "Agent must upgrade to Enterprise (not Business) in Turn 3. "
            "PASS = agent upgraded to Enterprise ($399/mo, 2 TB, 100 users) not Business. "
            "FAIL = agent upgraded to Business or refused to change the plan mid-flow."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — restore us and upgrade to Business.",
            "New card: 4111 1111 1111 4321. Go ahead and restore.",
            "Actually, upgrade us to Enterprise instead of Business.",
        ],
    },
    {
        "id": "G12-S78",
        "title": "Customer requests downgrade post-restore (suspended → downgrade after payment)",
        "desc": (
            "Account 20001 (Alex, Team plan, SUSPENDED, card expired 4242). "
            "Turn 1: 'Account 20001 — restore us and downgrade to Individual after.' "
            "Turn 2: New card 4111 1111 1111 4321, consent. "
            "Turn 3: 'Yes, downgrade to Individual.' "
            "Agent must restore in Turn 2, then route downgrade to DA4 in Turn 3. "
            "T9: eligible=True, direction=downgrade, 8 seats > 1 max → seat_count_ok=False → HARD STOP. "
            "PASS = agent blocked the downgrade due to seat count (8 seats > 1 max on Individual) "
            "and offered escalation. FAIL = agent executed the downgrade despite seat violation."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — restore us and downgrade to Individual after.",
            "New card: 4111 1111 1111 4321. Go ahead and restore.",
            "Yes, downgrade to Individual.",
        ],
    },
    {
        "id": "G12-S79",
        "title": "Downgrade post-restore blocked by seat count — escalation",
        "desc": (
            "Account 20010 (Avery, Enterprise plan, SUSPENDED, 45 seats, card expired 3388). "
            "Turn 1: 'Account 20010 — restore us and downgrade to Business afterwards.' "
            "Turn 2: New card 4111 1111 1111 9999, consent. "
            "Turn 3: 'Yes, downgrade to Business.' "
            "T9: 45 seats > 30 max on Business → seat_count_ok=False → HARD STOP. "
            "PASS = agent blocked the Business downgrade (45 seats > 30 max) and offered escalation. "
            "FAIL = agent executed the downgrade despite seat count violation."
        ),
        "db_mod": None,
        "turns": [
            "Account 20010 — restore us and downgrade to Business afterwards.",
            "New card: 4111 1111 1111 9999. Go ahead and restore.",
            "Yes, downgrade to Business.",
        ],
    },
    {
        "id": "G12-S80",
        "title": "Active account tries to enter restore flow",
        "desc": (
            "Account 20006 (Casey, Driftwood, Team plan, ACTIVE). "
            "Turn 1: 'Account 20006 — I want to restore my account.' "
            "T1 returns ACTIVE status. Agent must NOT enter restore/payment flow. "
            "Expected: EXPLICITLY tell the customer their account is already active, "
            "so no restore is needed. A generic 'what can I help you with?' without "
            "addressing the restore request is NOT sufficient. "
            "PASS = agent told the customer their account is already active (no restore needed) "
            "and offered alternative help (billing, plan changes, etc.). "
            "FAIL = agent entered restore/payment flow OR only gave a generic greeting without "
            "addressing the active status relative to the restore request."
        ),
        "db_mod": None,
        "turns": [
            "Account 20006 — I want to restore my account.",
        ],
    },
    {
        "id": "G12-S81",
        "title": "Customer says 'I want to cancel' on a SUSPENDED account",
        "desc": (
            "Account 20001 (Alex, Wavefront, Team plan, SUSPENDED). "
            "Turn 1: 'Account 20001 — we're suspended and honestly I just want to cancel.' "
            "Agent must NOT attempt restore, payment, or DA3. "
            "Expected: acknowledge request, route to support team for cancellation processing. "
            "PASS = agent acknowledged cancellation request and routed to human team. Did not restore. "
            "FAIL = agent entered restore flow or tried to collect payment for a cancellation."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended and honestly I just want to cancel.",
        ],
    },
    {
        "id": "G12-S82",
        "title": "Balance-only inquiry on suspended account — no full diagnostic",
        "desc": (
            "Account 20001 (Alex, Wavefront, Team plan, SUSPENDED, $49 balance). "
            "Turn 1: 'Account 20001 — what's my balance?' "
            "Agent must answer balance ($49) without launching full data/fee/card diagnostic. "
            "A brief greeting is acceptable. T7 or DA2 balance check only. "
            "PASS = agent reported the $49 balance without full restore diagnostic (no data safety "
            "status, no project count, no card collection prompt). "
            "FAIL = agent launched full Turn 1 restore diagnostic including data/fee/card details."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — what's my balance?",
        ],
    },
    {
        "id": "G12-S83",
        "title": "CANCELED account asks about billing — win-back, no billing actions",
        "desc": (
            "Account 20011 (Parker, Helix Systems, CANCELED, Team plan). "
            "Turn 1: 'Account 20011 — I have a question about my last invoice.' "
            "T1 returns CANCELED. Agent must NOT route to DA2 or attempt any billing action. "
            "Expected: acknowledge account is closed, no billing actions available; pivot to win-back. "
            "PASS = agent confirmed account is closed and no billing actions are available on a closed "
            "account, without calling DA2 or entering payment flow. "
            "FAIL = agent attempted a billing lookup or payment action on a canceled account."
        ),
        "db_mod": None,
        "turns": [
            "Account 20011 — I have a question about my last invoice.",
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
    print("GROUP 12 — Plan Changes During Restore + Routing Edge Cases (S76–S83)")
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
    print("SUMMARY — Group 12  (LLM-as-judge)")
    print(SEP)
    for sc_id, title, status, verdict in results:
        sym = {"PASS": "✓", "FAIL": "✗", "ERROR": "!!"}.get(status, "?")
        print(f"  {sc_id:<12} {sym} {status:<6}  {title}")
        print(f"               {verdict}")
    passed_count = sum(1 for _, _, s, _ in results if s == "PASS")
    print(f"\n  {passed_count}/{len(SCENARIOS)} passing\n{SEP}\n")


if __name__ == "__main__":
    asyncio.run(main())
