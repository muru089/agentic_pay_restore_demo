"""
run_group1_auth.py — Group 1: Authentication & Account State (scenarios 1–6)
Uses LLM-as-judge (gemini-2.5-flash) for semantic PASS/FAIL grading.

Run from c:\\Muru_Workspace:
    python "pay_restore_demo/Agent Sim/run_group1_auth.py"
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

SCENARIOS = [
    {
        "id": "G1-S1",
        "title": "No account ID in opening message",
        "desc": (
            "Customer opens without any account ID. "
            "Agent must ask for the 5-digit account ID before doing anything else. "
            "Agent must NOT look up any account, mention any balance, or take any action."
        ),
        "turns": [
            "Hi, my account is suspended and I need to restore it. Can you help?",
        ],
    },
    {
        "id": "G1-S2",
        "title": "Account ID in wrong format — name and company given",
        "desc": (
            "Customer provides their name and then company name instead of an account ID. "
            "Agent must reject both non-numeric attempts and consistently ask for "
            "the 5-digit numeric account ID. Agent must NOT look up any account."
        ),
        "turns": [
            "My name is Alex and my account is suspended. Can you look me up?",
            "My company is Wavefront.",
        ],
    },
    {
        "id": "G1-S3",
        "title": "Account ID that doesn't exist in DB",
        "desc": (
            "Customer provides account ID 99999 which does not exist. "
            "Agent must inform the customer the account was not found and ask them "
            "to double-check or try again. Agent must NOT proceed with any restore flow."
        ),
        "turns": [
            "Please restore my account. Account 99999.",
        ],
    },
    {
        "id": "G1-S4",
        "title": "Account ID provided mid-sentence",
        "desc": (
            "Customer embeds account 20001 in the middle of their sentence. "
            "Agent must correctly extract the ID and proceed with the full Turn 1 "
            "diagnostic summary: data safety status (12 projects intact), "
            "balance ($49), fee waiver result (waived), and card situation "
            "(card 4242 expired → prompt for new card). "
            "Agent must NOT ask for the account ID again."
        ),
        "turns": [
            "Can you check account 20001 please — we've been suspended.",
        ],
    },
    {
        "id": "G1-S5",
        "title": "Customer switches account ID mid-conversation",
        "desc": (
            "Customer starts with account 20001 (Alex, Wavefront, SUSPENDED, 9 months). "
            "In Turn 2, customer switches to account 20005 (Morgan, Crestline, SUSPENDED, 18 months). "
            "The key test is account switching: agent must call T1 for 20005, drop the 20001 context, "
            "and respond with Morgan's account details including the 18-month tenure greeting. "
            "PASS = agent correctly identified 20005 belongs to Morgan at Crestline (or similar) "
            "and used an 18-month tenure acknowledgment ('Thank you for being with us for 18 months'). "
            "FAIL = agent continued referring to Alex or Wavefront in Turn 2, or refused to switch accounts."
        ),
        "turns": [
            "Account 20001 — we're suspended and need help restoring.",
            "Actually, can you check account 20005 instead? That's the right one.",
        ],
    },
    {
        "id": "G1-S6",
        "title": "Customer asks 'what account am I on?' before providing one",
        "desc": (
            "Customer asks about their account without providing an ID. "
            "Agent must ask for the 5-digit account ID before doing anything. "
            "Agent must NOT guess, look up any account, or provide account information."
        ),
        "turns": [
            "What account am I on?",
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
    runner = Runner(agent=root_agent, app_name="g1", session_service=session_service)
    session = await session_service.create_session(app_name="g1", user_id=f"u_{sid}")

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
    """Evaluate scenario outcome using gemini-2.5-flash as semantic judge."""
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
    print("GROUP 1 — Authentication & Account State (Scenarios 1–6)")
    print("Grading: LLM-as-judge (gemini-2.5-flash)")
    print(SEP)

    results = []

    for i, sc in enumerate(SCENARIOS, 1):
        print(f"\n{SEP2}")
        print(f"[{i}/6] {sc['id']} — {sc['title']}")
        print(SEP2)

        reset_db()
        t0 = time.time()
        responses, error = await run_scenario(root_agent, sc)
        run_elapsed = time.time() - t0

        # Print full transcript
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
    print("SUMMARY — Group 1  (LLM-as-judge)")
    print(SEP)
    for sc_id, title, status, verdict in results:
        sym = {"PASS": "✓", "FAIL": "✗", "ERROR": "!!"}.get(status, "?")
        print(f"  {sc_id:<8} {sym} {status:<6}  {title}")
        print(f"           {verdict}")
    passed_count = sum(1 for _, _, s, _ in results if s == "PASS")
    print(f"\n  {passed_count}/6 passing\n{SEP}\n")


if __name__ == "__main__":
    asyncio.run(main())
