"""
run_group17_escalation_state.py — Group 17: Escalation + Persistent State (S117–S126)
Uses LLM-as-judge (gemini-2.5-flash) for semantic PASS/FAIL grading.

Escalation scenarios (Part B 77-82): human handoff patterns, stuck loop, handoff
context, resume after escalation offered. Persistent State scenarios (Part B 101-104):
T0 state correctness, fresh session re-run, post-resolve no re-entry, ROW 3 warm close.

Run from c:\\Muru_Workspace:
    python "pay_restore_demo/Agent Sim/run_group17_escalation_state.py"
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
    # ── Escalation scenarios ──────────────────────────────────────────────────
    {
        "id": "G17-S117",
        "title": "Customer asks for human mid-restore — graceful handoff with context",
        "desc": (
            "Account 20001 (Alex, Team plan, SUSPENDED, card expired 4242). "
            "Turn 1: Standard restore request — agent runs ROW 7 diagnostic. "
            "Turn 2: 'Actually, can I just speak to a person?' "
            "Agent must offer human escalation gracefully — not argue or dismiss. "
            "PASS = agent offered escalation warmly with a brief context summary "
            "(name, plan, issue) so the human agent has context. "
            "FAIL = agent refused to escalate or continued the payment flow without "
            "acknowledging the escalation request."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended, need help with restore.",
            "Actually, can I just speak to a person?",
        ],
    },
    {
        "id": "G17-S118",
        "title": "Customer dismisses VA — 'this isn't helping, just transfer me'",
        "desc": (
            "Account 20001 (Alex, Team plan, SUSPENDED). "
            "Turn 1: 'Account 20001 — we're suspended.' "
            "Turn 2: 'This isn't helping, just transfer me.' "
            "Agent must not argue or re-pitch the VA. Offer escalation gracefully. "
            "PASS = agent offered escalation without argument, without re-pitching itself, "
            "and with a brief context note for the human agent. "
            "FAIL = agent argued ('let me try again'), ignored the request, or dismissed it."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended.",
            "This isn't helping, just transfer me.",
        ],
    },
    {
        "id": "G17-S119",
        "title": "After escalation offered, customer resumes — agent picks up where it left off",
        "desc": (
            "Account 20001 (Alex, Team plan, SUSPENDED). "
            "Turn 1: Standard restore request. "
            "Turn 2: 'Can I speak to a person?' → agent offers escalation. "
            "Turn 3: 'Actually, let's just keep going — I'll deal with it here.' "
            "Agent must resume the restore flow from where it left off "
            "(card situation, not restart from Turn 1 diagnostic). "
            "PASS = agent resumed the restore flow appropriately without re-running the "
            "full ROW 7 diagnostic from scratch. "
            "FAIL = agent re-ran the full diagnostic from scratch or refused to resume."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended and need to restore.",
            "Can I speak to a person instead?",
            "Actually, let's just keep going — I'll deal with it here.",
        ],
    },
    {
        "id": "G17-S120",
        "title": "Stuck loop — customer won't confirm or decline consent → escalation offered",
        "desc": (
            "Account 20001 (Alex, SUSPENDED, card expired). "
            "Turn 1: Full restore request. "
            "Turn 2: Agent presents card situation. Customer: 'I don't know, maybe.' "
            "Turn 3: Agent re-prompts for consent. Customer: 'I'm not sure yet.' "
            "After two non-consents, agent should offer escalation rather than looping. "
            "PASS = after two unclear responses, agent offered escalation as an option "
            "(connect with specialist, call back, etc.) rather than asking a third time. "
            "FAIL = agent asked a third consent question without offering any alternative path."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended. Need to restore.",
            "I don't know, maybe.",
            "I'm not sure yet.",
        ],
    },
    {
        "id": "G17-S121",
        "title": "Billing dispute beyond pending balance — routes to specialist",
        "desc": (
            "Account 20001 (Alex, SUSPENDED, $49 pending). "
            "Turn 1: 'Account 20001 — I also want to dispute a $200 charge from 3 months ago.' "
            "The pending balance ($49) is within VA scope. The old charge dispute is NOT. "
            "Agent must handle the restore flow for the current balance AND acknowledge the "
            "old dispute is outside what the VA can resolve, routing to specialist. "
            "PASS = agent distinguished between the current $49 (VA scope) and the historical "
            "dispute (specialist scope), and offered to connect for the dispute. "
            "FAIL = agent ignored the dispute entirely or tried to process the old charge."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended. I also want to dispute a $200 charge from 3 months ago.",
        ],
    },
    {
        "id": "G17-S122",
        "title": "Data AT RISK — customer explicitly requests data recovery specialist",
        "desc": (
            "Account 20003 (Sam, Business, SUSPENDED 35 days — AT RISK). "
            "Turn 1: 'Account 20003 — we need to restore. Is our data safe?' "
            "AT RISK warning presented. Two paths offered. "
            "Turn 2: 'I want to speak to your data recovery team.' "
            "Agent must route to data recovery specialist — not proceed with payment. "
            "PASS = agent routed to data recovery team, did not enter payment flow. "
            "FAIL = agent collected payment or proceeded with restore despite escalation request."
        ),
        "db_mod": None,
        "turns": [
            "Account 20003 — we need to restore. Is our data safe?",
            "I want to speak to your data recovery team.",
        ],
    },
    # ── Persistent State scenarios ─────────────────────────────────────────────
    {
        "id": "G17-S123",
        "title": "ROW 7 T0 write — state persists correctly before Turn 2",
        "desc": (
            "Account 20001 (Alex, SUSPENDED, 12 projects, data_safe=True). "
            "Turn 1: Full restore request → ROW 7 fires (data_checked=0). "
            "T0_SetSessionState must write: data_checked=1, data_safe=1, "
            "days_suspended=5, project_count=12. "
            "Turn 2: New card + consent → ROW 6 fires using stored state (not re-running T2). "
            "PASS = in Turn 2 the agent processed payment and restore correctly using session "
            "state from Turn 1, without calling T2 or re-checking data again in Turn 2. "
            "FAIL = agent re-ran the data retention check (T2) in Turn 2, or lost Turn 1 context."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended. Check our data and restore us.",
            "New card: 4111 1111 1111 4321. Yes, go ahead.",
        ],
    },
    {
        "id": "G17-S124",
        "title": "Post-resolve follow-up — no restore re-entry",
        "desc": (
            "Account 20001 (Alex, SUSPENDED, card expired). "
            "Turn 1: Restore request. "
            "Turn 2: New card + consent → payment + restore complete (restore_complete=1). "
            "Turn 3: 'What is my new monthly cost?' "
            "ROW 3 (ALL DONE) fires — agent answers from context, does NOT re-enter restore flow. "
            "PASS = agent answered the monthly cost question from context (Team $49 or Business) "
            "without re-running any restore steps or re-entering ROW 7. "
            "FAIL = agent re-ran data check, re-requested payment, or showed any confusion about "
            "the already-completed restore."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended and need to restore.",
            "New card: 4111 1111 1111 4321. Yes, go ahead and restore.",
            "What is my new monthly cost?",
        ],
    },
    {
        "id": "G17-S125",
        "title": "ROW 3 warm close — fires after plan_executed=1",
        "desc": (
            "Account 20001 (Alex, SUSPENDED, full 3-turn happy path: restore + Business upgrade). "
            "Turn 1: Restore + Business upgrade request. "
            "Turn 2: New card + consent. "
            "Turn 3: 'Yes, upgrade to Business.' "
            "Turn 4: 'Are we done?' "
            "ROW 3 must fire: plan_executed=1, restore_complete=1 → warm close, no further actions. "
            "PASS = agent responded warmly to Turn 4 confirming everything is complete, "
            "without running any additional tools or re-checking state. "
            "FAIL = agent re-ran any tool or re-entered any restore/plan step in Turn 4."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — restore us and upgrade to Business.",
            "New card: 4111 1111 1111 4321. Yes, go ahead.",
            "Yes, upgrade to Business.",
            "Are we done?",
        ],
    },
    {
        "id": "G17-S126",
        "title": "Suspended account asks only about plan pricing — note suspend first",
        "desc": (
            "Account 20001 (Alex, Team plan, SUSPENDED). "
            "Turn 1: 'Account 20001 — how much is the Business plan and what's included?' "
            "No restore intent. Agent must note account is suspended and suggest restoring first, "
            "but can still answer the pricing question (plan changes only take effect post-restore). "
            "PASS = agent answered the Business plan pricing AND noted the account is suspended, "
            "suggesting the customer restore first before the plan change takes effect. "
            "FAIL = agent launched full restore flow ignoring the pricing question, "
            "or answered pricing without mentioning the suspended status."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — how much is the Business plan and what's included?",
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
    print("GROUP 17 — Escalation + Persistent State (Scenarios S117–S126)")
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
    print("SUMMARY — Group 17  (LLM-as-judge)")
    print(SEP)
    for sc_id, title, status, verdict in results:
        sym = {"PASS": "✓", "FAIL": "✗", "ERROR": "!!"}.get(status, "?")
        print(f"  {sc_id:<12} {sym} {status:<6}  {title}")
        print(f"               {verdict}")
    passed_count = sum(1 for _, _, s, _ in results if s == "PASS")
    print(f"\n  {passed_count}/{len(SCENARIOS)} passing\n{SEP}\n")


if __name__ == "__main__":
    asyncio.run(main())
