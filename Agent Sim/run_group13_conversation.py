"""
run_group13_conversation.py — Group 13: Conversation Dynamics (S84–S91)
Uses LLM-as-judge (gemini-2.5-flash) for semantic PASS/FAIL grading.

Tests how the agent handles varied conversational patterns: compressed intent,
terse messages, topic changes mid-restore, wrong ordering, info already provided,
and natural topic pivots.

Run from c:\\Muru_Workspace:
    python "pay_restore_demo/Agent Sim/run_group13_conversation.py"
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
# Group 13 scenarios — Conversation Dynamics
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "G13-S84",
        "title": "All info in one turn — card + consent + plan in opening message",
        "desc": (
            "Account 20001 (Alex, Team plan, SUSPENDED, card expired 4242). "
            "Turn 1: Customer provides everything upfront — account ID, new card, consent, plan upgrade. "
            "'Account 20001 — we're suspended. New card is 4111 1111 1111 4321. "
            "Go ahead, restore us and upgrade to Business for 3 months.' "
            "Agent must process payment ($49, new card last4=4321), restore account, "
            "and upgrade to Business for 3 months — all from this single turn. "
            "PASS = agent completed payment + restore + Business upgrade in Turn 1 without asking "
            "for info already provided. Receipt sent. "
            "FAIL = agent asked for the card number again or ignored the plan change request."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended. New card is 4111 1111 1111 4321. "
            "Go ahead, restore us and upgrade to Business for 3 months.",
        ],
    },
    {
        "id": "G13-S85",
        "title": "Terse message — minimal utterance with clear intent",
        "desc": (
            "Account 20001 (Alex, Team plan, SUSPENDED, card expired 4242). "
            "Turn 1: '20001. restore. now.' "
            "Agent must process the terse message: call T1, enter restore flow. "
            "Should not demand elaboration — extracts intent from minimal input. "
            "PASS = agent acknowledged the suspended account and began the restore flow "
            "(data check, card situation) without asking the customer to rephrase. "
            "FAIL = agent asked the customer to restate their request more clearly."
        ),
        "db_mod": None,
        "turns": [
            "20001. restore. now.",
        ],
    },
    {
        "id": "G13-S86",
        "title": "Wrong order — upgrade requested before restore",
        "desc": (
            "Account 20001 (Alex, Team plan, SUSPENDED, card expired 4242). "
            "Turn 1: 'Account 20001 — upgrade us to Business first, then restore.' "
            "Agent must follow correct flow order: restore before plan change. "
            "Expected: agent notes it will handle the restore first, then the upgrade, "
            "and begins the restore diagnostic. "
            "PASS = agent correctly sequenced restore before upgrade and proceeded with "
            "the data check / card situation in Turn 1. "
            "FAIL = agent attempted the upgrade before the account was restored."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — upgrade us to Business first, then restore.",
        ],
    },
    {
        "id": "G13-S87",
        "title": "Topic change mid-restore — customer asks plan question during restore flow",
        "desc": (
            "Account 20001 (Alex, Team plan, SUSPENDED). "
            "Turn 1: 'Account 20001 — we're suspended, need to restore. Card on file.' "
            "Agent runs Turn 1 diagnostic (data check, balance, fee preview). "
            "Turn 2: 'Wait — before I pay, what's included in the Business plan?' "
            "Agent answers the plan question from knowledge (T10 or inline), "
            "then offers to resume the restore. "
            "PASS = agent answered the Business plan question correctly and offered to "
            "continue with the restore. "
            "FAIL = agent ignored the plan question or abandoned the restore context."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended, need to restore. Card on file, just restore it.",
            "Wait — before I pay, what's included in the Business plan? How does it compare to Team?",
        ],
    },
    {
        "id": "G13-S88",
        "title": "Customer asks 'what did you just do?' after restore — no tool names",
        "desc": (
            "Account 20001 (Alex, Team plan, SUSPENDED, card expired 4242). "
            "Turn 1: Full restore request with new card. "
            "Turn 2: New card + consent. "
            "Turn 3: 'What did you just do exactly?' "
            "Agent must summarise actions in natural language. "
            "Must NOT expose tool names (T3, T5, DA3, etc.) or internal identifiers. "
            "PASS = agent described what was done (payment processed, account restored, "
            "receipt sent) in plain language without mentioning any tool or function names. "
            "FAIL = agent mentioned T3, T5, DA3, or any other internal tool or system name."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended. Card expired. Need to restore.",
            "New card: 4111 1111 1111 4321. Yes, go ahead and restore.",
            "What did you just do exactly?",
        ],
    },
    {
        "id": "G13-S89",
        "title": "Customer uses informal language throughout — agent matches register",
        "desc": (
            "Account 20001 (Alex, Team plan, SUSPENDED, card expired 4242). "
            "Turn 1: 'hey account 20001, we're totally locked out, what's the deal?' "
            "Agent should acknowledge in a friendly, accessible tone — not stiff or corporate. "
            "Should not use 'Kindly note', 'Please be advised', or overly formal language. "
            "PASS = agent responded in a warm, conversational tone that matches the casual register. "
            "The response should feel like a text conversation, not a formal letter. "
            "FAIL = agent used corporate filler language or responded with excessive formality."
        ),
        "db_mod": None,
        "turns": [
            "hey account 20001, we're totally locked out, what's the deal?",
        ],
    },
    {
        "id": "G13-S90",
        "title": "Customer asks 'how long will this take?' — realistic expectation given",
        "desc": (
            "Account 20001 (Alex, Team plan, SUSPENDED). "
            "Turn 1: 'Account 20001 — we're suspended. How long will it take to get restored?' "
            "Agent should give a realistic expectation: restoration is immediate once payment clears. "
            "PASS = agent confirmed that restoration is immediate/instant once payment is processed, "
            "and began the restore process or asked for the next step. "
            "FAIL = agent gave a vague timeline ('1-3 business days') or refused to estimate."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended. How long will it take to get restored?",
        ],
    },
    {
        "id": "G13-S91",
        "title": "Customer provides info in chunks — card number in two messages",
        "desc": (
            "Account 20001 (Alex, Team plan, SUSPENDED, card expired 4242). "
            "Turn 1: Full restore request. "
            "Turn 2: Agent asks for card details. Customer replies: '4111 1111'. "
            "Agent must recognize this is incomplete (only 8 digits) and ask for the full 16. "
            "PASS = agent correctly identified the partial card number and asked for the full 16 digits. "
            "FAIL = agent accepted the 8-digit partial as a valid card number."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended and need to restore. Card is expired.",
            "4111 1111",
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
    print("GROUP 13 — Conversation Dynamics (Scenarios S84–S91)")
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
    print("SUMMARY — Group 13  (LLM-as-judge)")
    print(SEP)
    for sc_id, title, status, verdict in results:
        sym = {"PASS": "✓", "FAIL": "✗", "ERROR": "!!"}.get(status, "?")
        print(f"  {sc_id:<12} {sym} {status:<6}  {title}")
        print(f"               {verdict}")
    passed_count = sum(1 for _, _, s, _ in results if s == "PASS")
    print(f"\n  {passed_count}/{len(SCENARIOS)} passing\n{SEP}\n")


if __name__ == "__main__":
    asyncio.run(main())
