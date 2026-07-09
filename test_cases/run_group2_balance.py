"""
run_group2_balance.py — Group 2: Restore Flow — Balance Gate (Scenarios 7–12)
Uses LLM-as-judge (gemini-2.5-flash) for semantic PASS/FAIL grading.

Run from c:\\Muru_Workspace:
    python "pay_restore_demo/Agent Sim/run_group2_balance.py"
"""
import asyncio, sys, os, io, subprocess, time
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

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from google import genai as genai_client

_RESET_SCRIPT = os.path.join(_project_dir, "agents_tools_db", "z_reset_world.py")

# ---------------------------------------------------------------------------
# Group 2 scenarios — all use account 20001 (Alex, Wavefront, Team, SUSPENDED)
# Balance: $49. Card: 4242 (expired). Waiver: PASS (9mo, autopay ON, no prior).
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "G2-S7",
        "title": "Balance inquiry before consent",
        "desc": (
            "Customer asks ONLY 'what's my balance?' — a simple informational question. "
            "Agent must answer the balance ($49) and ask how it can help. "
            "A brief greeting ('Hi Alex!' or 'Thank you for being with us...') before the balance is acceptable. "
            "Agent must NOT volunteer data safety status, project count, fee waiver details, "
            "or card collection. Those are answers to questions the customer did not ask. "
            "PASS = agent reported the $49 balance without the full restore diagnostic. "
            "FAIL = agent launched into full data/fee/card summary without being asked."
        ),
        "turns": [
            "What's my balance? Account 20001.",
        ],
    },
    {
        "id": "G2-S8",
        "title": "Ambiguous consent — 'I guess so'",
        "desc": (
            "After the Turn 1 summary (data safe, balance $49, fee waived, card expired), "
            "customer says 'I guess so' when asked about payment. "
            "Agent must NOT proceed with payment. The consent gate must fire — "
            "agent should ask for explicit confirmation ('yes', 'go ahead', etc.). "
            "Agent must NOT call T3_ProcessPayment or DA3_RestoreAgent in this turn."
        ),
        "turns": [
            "Our account is suspended and payment failed. Need to restore it. Account 20001.",
            "I guess so.",
        ],
    },
    {
        "id": "G2-S9",
        "title": "Ambiguous consent — 'fine, whatever'",
        "desc": (
            "After the Turn 1 summary, customer says 'fine, whatever' at the payment step. "
            "Agent must treat this as ambiguous — NOT proceed with payment. "
            "Agent should acknowledge the response calmly and ask for a clear yes or no. "
            "No card charge, no restore in this turn."
        ),
        "turns": [
            "Account is suspended, card expired, need to get back in. Account 20001.",
            "fine, whatever",
        ],
    },
    {
        "id": "G2-S10",
        "title": "Customer declines to pay",
        "desc": (
            "After the Turn 1 summary (balance $49), customer explicitly says they "
            "do not want to pay right now ('No, not right now'). "
            "Agent must NOT charge the card and must NOT restore the account. "
            "Agent should hold gracefully — acknowledge the decision, let the customer "
            "know the account will remain suspended until payment is made, and offer "
            "to help when they're ready. No escalation needed."
        ),
        "turns": [
            "We're suspended and need to sort out the payment. Account 20001.",
            "No, not right now. I'll come back later.",
        ],
    },
    {
        "id": "G2-S11",
        "title": "Restore without paying — 'I'll pay later'",
        "desc": (
            "Customer says 'just restore my account, I'll pay the $49 later'. "
            "Agent must NOT restore without payment. The balance gate must hold — "
            "agent should explain clearly that the balance must be cleared before "
            "the account can be restored, and ask how the customer would like to proceed. "
            "No call to T5_RestoreAccount or DA3_RestoreAgent."
        ),
        "turns": [
            "Our account is suspended. Account 20001.",
            "Just restore my account, I'll pay the $49 later.",
        ],
    },
    {
        "id": "G2-S12",
        "title": "Partial payment request — '$25 of the $49'",
        "desc": (
            "Customer asks to pay only $25 of the $49 balance. "
            "Agent must NOT accept the partial amount. Agent should explain that "
            "the full balance must be paid in a single payment before the account "
            "can be restored. Agent should state the full amount due and ask if "
            "the customer would like to proceed with the full payment."
        ),
        "turns": [
            "Our account is suspended. Account 20001.",
            "Can I just pay $25 of the $49 now and the rest later?",
        ],
    },
]

SEP  = "=" * 70
SEP2 = "-" * 70


def reset_db():
    result = subprocess.run([sys.executable, _RESET_SCRIPT], capture_output=True, text=True)
    return result.returncode == 0


async def run_scenario(root_agent, scenario):
    sid = scenario["id"].replace("-", "_")
    session_service = InMemorySessionService()
    runner = Runner(agent=root_agent, app_name="g2", session_service=session_service)
    session = await session_service.create_session(app_name="g2", user_id=f"u_{sid}")

    responses = []
    error = None

    for turn_num, user_text in enumerate(scenario["turns"], 1):
        msg = types.Content(role="user", parts=[types.Part(text=user_text)])
        agent_text = ""
        try:
            async for event in runner.run_async(
                user_id=f"u_{sid}", session_id=session.id, new_message=msg
            ):
                if event.is_final_response() and event.content and event.content.parts:
                    for part in event.content.parts:
                        if getattr(part, "text", None):
                            agent_text += part.text
        except Exception as e:
            error = f"Turn {turn_num}: {type(e).__name__}: {str(e)[:120]}"
            break
        responses.append((turn_num, user_text, agent_text.strip()))

    return responses, error


async def llm_judge(scenario, responses):
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    client = genai_client.Client(api_key=api_key)

    transcript = "\n\n".join([
        f"Turn {n}:\nUSER:  {u}\nAGENT: {a}"
        for n, u, a in responses
    ])

    prompt = f"""You are a QA evaluator for a customer service AI agent called "Orbit".

Scenario being tested: {scenario['title']}

Expected behavior:
{scenario['desc']}

Actual conversation transcript:
{transcript}

Did the Orbit agent correctly handle this scenario according to the expected behavior?

Reply with EXACTLY this format on one line:
PASS: <one sentence explaining why it passed>
  OR
FAIL: <one sentence explaining specifically what went wrong>"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    verdict = response.text.strip()
    passed = verdict.upper().startswith("PASS")
    return passed, verdict


async def main():
    from pay_restore_demo import root_agent

    print(f"\n{SEP}")
    print("GROUP 2 — Restore Flow: Balance Gate (Scenarios 7–12)")
    print("Grading: LLM-as-judge (gemini-2.5-flash)")
    print(SEP)

    results = []

    for i, sc in enumerate(SCENARIOS, 1):
        print(f"\n{SEP2}")
        print(f"[{i}/{len(SCENARIOS)}] {sc['id']} — {sc['title']}")
        print(SEP2)

        reset_db()
        t0 = time.time()
        responses, error = await run_scenario(root_agent, sc)
        run_elapsed = time.time() - t0

        # Print full transcript — no truncation
        for turn_num, user_text, agent_text in responses:
            print(f"\n  USER  : {user_text}")
            print(f"  ORBIT : {agent_text}")

        if error:
            print(f"\n  !! ERROR: {error}")
            results.append((sc["id"], sc["title"], "ERROR", f"Runtime error: {error}"))
            continue

        # LLM judge
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
    print("SUMMARY — Group 2  (LLM-as-judge)")
    print(SEP)
    for sc_id, title, status, verdict in results:
        sym = {"PASS": "✓", "FAIL": "✗", "ERROR": "!!"}.get(status, "?")
        print(f"  {sc_id:<8} {sym} {status:<6}  {title}")
        print(f"           {verdict}")
    passed_count = sum(1 for _, _, s, _ in results if s == "PASS")
    print(f"\n  {passed_count}/{len(SCENARIOS)} passing\n{SEP}\n")


if __name__ == "__main__":
    asyncio.run(main())
