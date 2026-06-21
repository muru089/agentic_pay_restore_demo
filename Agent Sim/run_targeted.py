"""
run_targeted.py — Re-run only the 5 failing scenarios with latest code.
Run from c:\\Muru_Workspace:
    python "pay_restore_demo/Agent Sim/run_targeted.py"
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

from pay_restore_demo import root_agent
from pay_restore_demo.agents_tools_db.z_reset_world import reset_world
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

SCENARIOS = [
    {   "id": "S02", "name": "Avery 20010 — Enterprise restore (2-turn)",
        "turns": [
            "Our enterprise account is suspended. I need it restored. Account 20010.",
            "Please use new card 5500 0055 5555 4321 and restore us now.",
        ],
        "checks": ["active", "waived"],
    },
    {   "id": "S04", "name": "Riley 20004 — waiver FAIL Rule C",
        "turns": [
            "I need to restore my account. Account 20004.",
            "New card is 4111 1111 1111 5678.",
            "Yes, go ahead and charge it.",
        ],
        "checks": ["late fee", "10"],
    },
    {   "id": "S07a", "name": "Sam 20003 — data AT RISK, customer proceeds",
        "turns": [
            "Our business account is suspended and I need to restore it. Account 20003.",
            "I understand the risk. I want to proceed with the restore.",
            "New card number is 4111 1111 1111 9988. Yes, go ahead.",
        ],
        "checks": ["dashboard", "active"],
    },
    {   "id": "S15", "name": "RAG — temporary upgrade policy question",
        "turns": [
            "Can I upgrade to Enterprise for just 2 months and then go back automatically?",
        ],
        "checks": ["revert", "period"],
    },
    {   "id": "S17", "name": "RAG — GDPR DPA (not in KB)",
        "turns": [
            "Does Orbit have a GDPR Data Processing Agreement I can sign? "
            "We need a DPA before our legal team approves the purchase.",
        ],
        "checks": ["support@orbit.io"],
    },
]

SEP = "=" * 70

async def run_one(scenario, session_service, runner):
    sid = scenario["id"]
    checks = [c.lower() for c in scenario["checks"]]
    session = await session_service.create_session(app_name="tgt", user_id=f"u_{sid}")
    responses = []
    for i, user_text in enumerate(scenario["turns"], 1):
        msg = types.Content(role="user", parts=[types.Part(text=user_text)])
        agent_text = ""
        try:
            async for event in runner.run_async(user_id=f"u_{sid}", session_id=session.id, new_message=msg):
                if event.is_final_response() and event.content and event.content.parts:
                    for part in event.content.parts:
                        if getattr(part, "text", None):
                            agent_text += part.text
        except Exception as e:
            return {"id": sid, "status": "ERROR", "note": str(e)[:80], "responses": responses}
        responses.append((i, user_text, agent_text.strip()))
    combined = " ".join(r[2].lower() for r in responses)
    missing = [c for c in checks if c not in combined]
    status = "PASS" if not missing else "FAIL"
    return {"id": sid, "status": status, "missing": missing, "responses": responses}

async def main():
    print(f"\n{SEP}\nTARGETED RE-RUN — 5 SCENARIOS\n{SEP}\n")
    results = []
    for i, sc in enumerate(SCENARIOS, 1):
        print(f"[{i}/5] {sc['id']}  {sc['name']}")
        print("       Resetting DB... ", end="", flush=True)
        reset_world()
        print("done")
        ss = InMemorySessionService()
        runner = Runner(agent=root_agent, app_name="tgt", session_service=ss)
        t0 = time.time()
        r = await run_one(sc, ss, runner)
        elapsed = time.time() - t0
        sym = {"PASS": "✓", "FAIL": "✗", "ERROR": "!!"}.get(r["status"], "?")
        print(f"       {sym} {r['status']}  ({elapsed:.1f}s)")
        if r.get("missing"): print(f"       Missing: {r['missing']}")
        for turn_num, user_text, agent_text in r.get("responses", []):
            print(f"       U{turn_num}: {user_text[:80]}...")
            print(f"       A{turn_num}: {agent_text[:300]}{'...' if len(agent_text)>300 else ''}")
        print()
        results.append(r)
    print(f"\n{SEP}\nSUMMARY\n{SEP}")
    for r in results:
        sym = {"PASS": "✓", "FAIL": "✗", "ERROR": "!!"}.get(r["status"], "?")
        flag = f"  [missing: {r['missing']}]" if r.get("missing") else ""
        print(f"{r['id']:<6} {sym} {r['status']}{flag}")
    passed = sum(1 for r in results if r["status"] == "PASS")
    print(f"\n{passed}/5 passing\n")

if __name__ == "__main__":
    asyncio.run(main())
