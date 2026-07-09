"""
run_group11_auth_account.py — Group 11: Authentication & Account State Edge Cases (Scenarios 66–75)
Uses LLM-as-judge (gemini-2.5-flash) for semantic PASS/FAIL grading.

Tests auth flow edge cases: missing ID, wrong format, nonexistent ID, ID mid-sentence,
switching accounts mid-conversation, canceled account win-back, and tenure greeting.

Run from c:\\Muru_Workspace:
    python "pay_restore_demo/Agent Sim/run_group11_auth_account.py"
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
# Group 11 scenarios — Authentication & Account State Edge Cases
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "G11-S66",
        "title": "No account ID — agent asks before doing anything",
        "desc": (
            "Customer sends a message with no account ID: "
            "'Hi, I need help restoring my suspended account.' "
            "Agent must NOT call T1_GetAccount or enter any flow. "
            "Must ask for the 5-digit account ID before proceeding. "
            "PASS = agent asked for the 5-digit account ID and did not attempt to access any account. "
            "FAIL = agent guessed an account ID or entered a restore flow without one."
        ),
        "db_mod": None,
        "turns": [
            "Hi, I need help restoring my suspended account.",
        ],
    },
    {
        "id": "G11-S67",
        "title": "Wrong format — name provided instead of ID",
        "desc": (
            "Customer provides their name instead of an account ID: "
            "'My name is Alex, can you look up my account?' "
            "Agent must reject the name and ask for a 5-digit numeric account ID. "
            "Expected: 'I can only look up accounts by their 5-digit numeric account ID — "
            "could you provide that?' "
            "PASS = agent rejected the name and asked for a numeric account ID. "
            "FAIL = agent attempted to look up by name or accepted a non-numeric identifier."
        ),
        "db_mod": None,
        "turns": [
            "My name is Alex, can you look up my account?",
        ],
    },
    {
        "id": "G11-S68",
        "title": "Wrong format — email provided instead of ID",
        "desc": (
            "Customer provides their email: "
            "'My email is alex@wavefront.io, can you pull up my account?' "
            "Agent must reject the email and ask for a 5-digit numeric account ID. "
            "PASS = agent rejected the email and asked for the 5-digit account ID. "
            "FAIL = agent accepted the email or attempted to look up by email."
        ),
        "db_mod": None,
        "turns": [
            "My email is alex@wavefront.io, can you pull up my account?",
        ],
    },
    {
        "id": "G11-S69",
        "title": "Account ID mid-sentence — extracted correctly",
        "desc": (
            "Customer embeds the account ID in a sentence: "
            "'Can you please check account 20001 for me? I think it might be suspended.' "
            "Agent must extract the 5-digit ID (20001) from the sentence and call T1_GetAccount "
            "without asking the customer to repeat themselves. "
            "PASS = agent extracted account ID 20001 from mid-sentence and called T1 to look it up "
            "without asking for the account ID again. The response content after that is not evaluated. "
            "FAIL = agent ignored the ID in the sentence and asked for the account ID again."
        ),
        "db_mod": None,
        "turns": [
            "Can you please check account 20001 for me? I think it might be suspended.",
        ],
    },
    {
        "id": "G11-S70",
        "title": "Nonexistent account ID — agent informs and asks again",
        "desc": (
            "Customer provides an account ID that does not exist in the database: '99999' "
            "T1_GetAccount should return an error (account not found). "
            "Agent must inform the customer the ID wasn't found and ask them to try again. "
            "Expected: 'I wasn't able to find an account with ID 99999. "
            "Could you double-check the number and try again?' "
            "PASS = agent reported the account was not found and asked to try again. "
            "FAIL = agent hallucinated account details for a nonexistent ID."
        ),
        "db_mod": None,
        "turns": [
            "My account ID is 99999.",
        ],
    },
    {
        "id": "G11-S71",
        "title": "Canceled account — win-back script, no restore attempted",
        "desc": (
            "Account 20011 (Parker, Helix Systems, CANCELED, Team plan). "
            "Turn 1: 'Account 20011 — I want to reactivate my account.' "
            "T1 returns status=CANCELED. "
            "Agent must NOT route to DA3 (restore), DA2, or enter the suspend flow. "
            "Win-back script: acknowledge account is closed, offer to explore plans or "
            "connect with sales team. "
            "Expected: 'I can see your Helix Systems account is no longer active. "
            "I'd love to help you get started again — would you like to explore our current plans, "
            "or shall I connect you with our team?' "
            "PASS = agent acknowledged account is closed and offered at least one path forward "
            "(exploring plans, connecting with team, or both). No restore attempted. "
            "FAIL = agent tried to restore a canceled account or entered payment flow."
        ),
        "db_mod": None,
        "turns": [
            "Account 20011 — I want to reactivate my account.",
        ],
    },
    {
        "id": "G11-S72",
        "title": "Long-tenure greeting (≥ 12 months) — warm acknowledgment",
        "desc": (
            "Account 20005 (Morgan, Crestline, Team plan, 18 months, SUSPENDED). "
            "Turn 1: 'Account 20005 — we're suspended, help!' "
            "T1 returns tenure_months=18.0 (≥ 12 months). "
            "Agent must include the long-tenure greeting before proceeding: "
            "'Thank you for being with us for 18 months, Morgan!' (or similar with exact month count). "
            "Agent must NOT say 'Hi Morgan!' alone — the tenure greeting is required for ≥ 12 months. "
            "PASS = agent acknowledged 18 months tenure explicitly in the response. "
            "FAIL = agent used a generic greeting ('Hi Morgan!') without mentioning tenure."
        ),
        "db_mod": None,
        "turns": [
            "Account 20005 — we're suspended, help!",
        ],
    },
    {
        "id": "G11-S73",
        "title": "Short-tenure greeting (< 12 months) — simple 'Hi' only",
        "desc": (
            "Account 20001 (Alex, Wavefront, Team plan, 9 months, SUSPENDED). "
            "T1 returns tenure_months=9.0 (< 12 months). "
            "Agent must use simple greeting: 'Hi Alex!' "
            "Agent must NOT say 'Thank you for being with us for 9 months' — "
            "the long-tenure greeting only applies at 12+ months. "
            "PASS = agent greeted Alex normally without a long-tenure acknowledgment. "
            "FAIL = agent gave a long-tenure thank-you for a 9-month account."
        ),
        "db_mod": None,
        "turns": [
            "Account 20001 — we're suspended. What's my balance?",
        ],
    },
    {
        "id": "G11-S74",
        "title": "Email on file — not read out in chat",
        "desc": (
            "Account 20001 (Alex, email: alex@wavefront.io). "
            "Customer asks: 'What email address do you have on file for account 20001?' "
            "Agent must acknowledge an email is on file but must NOT read the email address in chat. "
            "Receipts go to 'the email on file' — the actual address is not disclosed in conversation. "
            "Expected: 'We have an email address on file for your account. "
            "Receipts and notifications are sent there.' (does not state alex@wavefront.io) "
            "PASS = agent confirmed an email is on file without revealing the address. "
            "FAIL = agent read out 'alex@wavefront.io' directly in the chat response."
        ),
        "db_mod": None,
        "turns": [
            "What email address do you have on file for account 20001?",
        ],
    },
    {
        "id": "G11-S75",
        "title": "Active account — no restore flow triggered",
        "desc": (
            "Account 20006 (Casey, Driftwood, Team plan, ACTIVE, $0 balance). "
            "Turn 1: 'Account 20006 — I need help with my account.' "
            "T1 returns status=ACTIVE. Agent must NOT enter the restore/suspend flow. "
            "Session state (T0_GetSessionState) must NOT be called for an ACTIVE account. "
            "Agent should ask what the customer needs in the context of an active account. "
            "Expected: 'Hi Casey! I've pulled up your Driftwood account on the Team plan. "
            "What can I help you with today?' "
            "PASS = agent acknowledged ACTIVE status and asked what the customer needs, "
            "without entering restore flow or calling T0. "
            "FAIL = agent called T0_GetSessionState or entered the restore/payment flow "
            "for an active account."
        ),
        "db_mod": None,
        "turns": [
            "Account 20006 — I need help with my account.",
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
    print("GROUP 11 — Authentication & Account State Edge Cases (Scenarios 66–75)")
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
    print("SUMMARY — Group 11  (LLM-as-judge)")
    print(SEP)
    for sc_id, title, status, verdict in results:
        sym = {"PASS": "✓", "FAIL": "✗", "ERROR": "!!"}.get(status, "?")
        print(f"  {sc_id:<12} {sym} {status:<6}  {title}")
        print(f"               {verdict}")
    passed_count = sum(1 for _, _, s, _ in results if s == "PASS")
    print(f"\n  {passed_count}/{len(SCENARIOS)} passing\n{SEP}\n")


if __name__ == "__main__":
    asyncio.run(main())
