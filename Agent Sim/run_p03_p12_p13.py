"""
run_p03_p12_p13.py — Retry P03 (Sam, AT RISK) and run new P12 (Taylor) + P13 (Blake).
Run from c:\\Muru_Workspace:
    python "pay_restore_demo/Agent Sim/run_p03_p12_p13.py"
"""
import asyncio, sys, os, io, time, subprocess
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

SCENARIOS = [
    {
        "id": "P03",
        "name": "Sam 20003 — Data AT RISK (35d > 30d), waiver PASS, no 'projects intact'",
        "turns": [
            "Our business account is suspended and I need to restore it. Account 20003.",
            "I understand the risk. I want to proceed with the restore.",
            "New card number is 4111 1111 1111 9988. Yes, go ahead.",
        ],
        "checks": ["dashboard", "active", "waived"],
    },
    {
        "id": "P12",
        "name": "Taylor 20012 — SA1 diagnostic: storage culprit (95/100 GB)",
        "turns": [
            "Account 20012 -- something feels off lately. Projects are loading slowly and a few uploads just failed. Not sure what's going on.",
            "Ah, that makes sense. What are my options?",
        ],
        "checks": ["storage", "95", "upload"],
    },
    {
        "id": "P13",
        "name": "Blake 20013 — SA1 diagnostic: integration culprit (GitHub auth_failure)",
        "turns": [
            "Account 20013 -- things just don't feel right. My team says changes aren't showing up in projects, like it's not syncing. I don't know if it's a billing thing or what.",
            "Yes, please walk me through how to fix the GitHub connection.",
        ],
        "checks": ["github", "auth", "reconnect"],
    },
]

_RESET_SCRIPT = os.path.join(_project_dir, "agents_tools_db", "z_reset_world.py")
_KEY_TOOLS = {
    "T1_GetAccount", "T2_CheckDataRetention", "T3_ProcessPayment",
    "T4_CheckFeeWaiver", "T5_RestoreAccount", "T6_ChangePlan",
    "T9_ValidatePlanChange", "T0_SetSessionState", "T11_CheckStorage",
    "T12_CheckIntegration",
}
SEP = "=" * 72


def reset_db():
    result = subprocess.run([sys.executable, _RESET_SCRIPT], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  !! DB reset failed: {result.stderr[-200:]}")
        return False
    return True


async def run_scenario(root_agent, scenario):
    sid = scenario["id"]
    checks = [c.lower() for c in scenario["checks"]]
    session_service = InMemorySessionService()
    runner = Runner(agent=root_agent, app_name="tgt", session_service=session_service)
    session = await session_service.create_session(app_name="tgt", user_id=f"u_{sid}")

    responses = []
    tools_log = []
    error = None

    for turn_num, user_text in enumerate(scenario["turns"], 1):
        msg = types.Content(role="user", parts=[types.Part(text=user_text)])
        agent_text = ""
        try:
            async for event in runner.run_async(user_id=f"u_{sid}", session_id=session.id, new_message=msg):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, "function_call") and part.function_call:
                            fc = part.function_call
                            marker = " **" if fc.name in _KEY_TOOLS else ""
                            tools_log.append(f"  Turn {turn_num}  {fc.name}{marker}")
                        if event.is_final_response() and getattr(part, "text", None):
                            agent_text += part.text
        except Exception as e:
            error = f"Turn {turn_num}: {type(e).__name__}: {e}"
            break
        responses.append((turn_num, user_text, agent_text.strip()))

    combined = " ".join(r[2].lower() for r in responses)
    missing = [c for c in checks if c not in combined]
    if error:
        status = "ERROR"
    elif missing:
        status = "FAIL"
    else:
        status = "PASS"

    return status, responses, tools_log, missing, error


async def main():
    from pay_restore_demo import root_agent

    print(f"\n{SEP}")
    print("TARGETED RUN — P03 (retry) + P12 + P13 (new SA1 diagnostic personas)")
    print(SEP)

    results = []
    for i, sc in enumerate(SCENARIOS, 1):
        print(f"\n[{i}/3] {sc['id']}  {sc['name']}")
        print("  Resetting DB... ", end="", flush=True)
        if not reset_db():
            results.append((sc["id"], "DB_RESET_FAILED", [], [], [], None))
            continue
        print("OK")

        t0 = time.time()
        status, responses, tools_log, missing, error = await run_scenario(root_agent, sc)
        elapsed = time.time() - t0

        sym = {"PASS": "✓", "FAIL": "✗", "ERROR": "!!"}.get(status, "?")
        print(f"  {sym} {status}  ({elapsed:.1f}s)")
        if missing:
            print(f"  Missing checks: {missing}")
        if error:
            print(f"  Error: {error}")

        for turn_num, user_text, agent_text in responses:
            print(f"\n  [Turn {turn_num}]")
            print(f"  USER : {user_text[:120]}")
            print(f"  AGENT: {agent_text[:600]}{'...' if len(agent_text) > 600 else ''}")

        print(f"\n  Tools ({len(tools_log)} calls):")
        for entry in tools_log:
            print(f" {entry}")

        results.append((sc["id"], status, responses, tools_log, missing, error))

    print(f"\n\n{SEP}")
    print("SUMMARY")
    print(SEP)
    for sc_id, status, *_ in results:
        sym = {"PASS": "✓", "FAIL": "✗", "ERROR": "!!", "DB_RESET_FAILED": "!!"}.get(status, "?")
        print(f"  {sc_id:<6}  {sym} {status}")
    print(f"\n{SEP}\n")


if __name__ == "__main__":
    asyncio.run(main())
