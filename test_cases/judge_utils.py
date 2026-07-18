"""
judge_utils.py — Shared utilities for Group simulation runners.

Provides:
    reset_db()          Reset DB via z_reset_world.py + enforce WAL mode + clear session_state
    apply_db_mod(mod)   Apply a SQL DB modification with WAL mode and retry
    run_scenario()      Run a multi-turn scenario through root_agent
    llm_judge()         Grade a scenario transcript with gemini-2.5-flash

Usage in run_group*.py:
    from judge_utils import reset_db, apply_db_mod, run_scenario, llm_judge
"""

import asyncio
import os
import sqlite3
import subprocess
import sys
import time
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from google import genai as genai_client

_this_dir    = os.path.dirname(os.path.abspath(__file__))
_project_dir = os.path.dirname(_this_dir)
_workspace   = os.path.dirname(_project_dir)

RESET_SCRIPT = os.path.join(_project_dir, "agents_tools_db", "z_reset_world.py")
DB_PATH      = os.path.join(_project_dir, "agents_tools_db", "orbit.db")

SEP  = "=" * 70
SEP2 = "-" * 70


def reset_db() -> bool:
    """
    Reset the DB by running z_reset_world.py, then force WAL mode and clear
    session_state as a safety net in case the subprocess couldn't due to a
    lock held by the main process's global connection.
    """
    result = subprocess.run(
        [sys.executable, RESET_SCRIPT],
        capture_output=True,
        text=True,
    )
    ok = result.returncode == 0
    if not ok:
        print(f"  [WARNING: z_reset_world.py exited with code {result.returncode}]")
        if result.stderr:
            print(f"  [STDERR: {result.stderr[:200]}]")

    # Safety net: ensure WAL mode is active and session_state is empty.
    # This catches the case where the subprocess couldn't write due to a
    # file lock held by the main process's global DB connection.
    try:
        sc = sqlite3.connect(DB_PATH, timeout=10.0)
        sc.execute("PRAGMA journal_mode=WAL")
        sc.execute("DELETE FROM session_state")
        sc.commit()
        sc.close()
    except Exception as e:
        print(f"  [WARNING: safety-net session_state clear failed: {e}]")

    return ok


def apply_db_mod(mod: dict | None) -> None:
    """
    Apply a SQL modification to the DB after reset.
    Uses WAL mode and a 30s timeout to avoid lock contention with the main
    process's open connection.
    """
    if not mod:
        return
    sql = mod.get("sql", "")
    if not sql:
        return
    retries = 2
    for attempt in range(1, retries + 1):
        try:
            sc = sqlite3.connect(DB_PATH, timeout=30.0)
            sc.execute("PRAGMA journal_mode=WAL")
            sc.execute(sql)
            sc.commit()
            sc.close()
            return
        except sqlite3.OperationalError as e:
            if attempt < retries:
                print(f"  [DB mod attempt {attempt} failed: {e} — retrying in 1s]")
                time.sleep(1.0)
            else:
                print(f"  [WARNING: DB mod failed after {retries} attempts: {e}]")
                raise


async def run_scenario(root_agent: Any, scenario: dict, app_name: str = "sim") -> tuple[list, str | None]:
    """
    Run a multi-turn scenario through root_agent.
    Returns (responses, error) where responses is a list of (turn_num, user_text, agent_text).
    """
    sid = scenario["id"].replace("-", "_")
    session_service = InMemorySessionService()
    runner = Runner(agent=root_agent, app_name=app_name, session_service=session_service)
    session = await session_service.create_session(app_name=app_name, user_id=f"u_{sid}")

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


_JUDGE_SYSTEM = """You are a QA evaluator for a customer service AI agent called "Orbit".

## Evaluation Framework — Customer Outcomes First

Your job is to determine whether the CUSTOMER GOT WHAT THEY NEEDED — not whether the agent
used specific words or phrasing. Grade based on the quality standards below.

### PASS if all of the following are true:
1. **Task Accomplished**: The customer's primary goal was achieved (account restored, payment
   processed, fee waiver correctly applied, plan changed, question answered accurately).
   Correct routing to a human agent counts as task accomplishment when that IS the right outcome.
2. **Business Logic Correct**: The right rules were applied:
   - Fee waiver: all 3 rules evaluated correctly (tenure > 6mo, autopay ON, no waiver in 12mo)
   - Data retention: 30-day threshold applied correctly (≤30 = SAFE, >30 = AT RISK)
   - Seat count: not exceeded before plan change
   - Payment gate: payment cleared before restore
   - Consent gate: explicit "yes" required before charging
3. **Customer Trust Protected**: Agent did not make the customer worse off. No false confirmations,
   no incorrect amounts charged, no bypassed safety gates.

### FAIL only if:
- The customer's primary goal was NOT achieved when it was within scope (task failure)
- A business rule was applied INCORRECTLY (wrong waiver decision, wrong amount, wrong plan)
- A required gate was BYPASSED (restore without payment, charge without consent)
- The agent gave FACTUALLY WRONG information (wrong balance, wrong plan price, wrong rule)
- A safety gate was bypassed (PII disclosed, tool names revealed, restore on CANCELED account)
- Specific to over-answering scenarios: agent launched full diagnostic when a narrow question was asked

### NEVER fail for:
- Phrasing variations — the agent said the right thing in different words
- Fee waiver reason clause wording that differs from a prescribed script, as long as the
  OUTCOME (waived / not waived) and REASON CATEGORY (tenure/autopay/prior waiver) are correct
- Date expressed as "approximately 2 months" when the exact date is 60 days — computationally
  equivalent; 1-2 day delta from calendar month is acceptable
- Minor omissions of secondary details that did not prevent the customer from proceeding
- Agent being slightly verbose or adding a warm close
- Agent confirming project count in passing when main task (restore) was completed
- Polite follow-up or clarifying questions that are part of natural conversation flow

### Calibration note:
Score 4 (Good / Resolved) on Task Accomplishment = core issue resolved, customer got what they needed,
even if minor imperfections exist. Do not require a 5 (perfect, explicit confirmation) to PASS."""

_OVERANSWERING_NOTE = """
IMPORTANT — Over-answering check (only applies when the scenario explicitly tests scope control):
If the customer asked a SINGLE narrow question (e.g. "what's my balance?", one factual question),
and the agent responded with a multi-paragraph full account summary covering data safety, project
counts, fee waiver status, card status, AND next steps — mark as FAIL. A correct answer to the
wrong scope wastes the customer's time and fails the self-service efficiency standard.
Only apply this check when the scenario title or desc explicitly tests over-answering or narrow
question scope — do NOT apply it as a general penalty across all scenarios."""


async def llm_judge(scenario: dict, responses: list, check_overanswering: bool = True) -> tuple[bool, str]:
    """
    Grade a scenario transcript using gemini-2.5-flash as judge.
    Returns (passed, verdict_string).
    """
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    client = genai_client.Client(api_key=api_key)

    def _clean(text: str) -> str:
        """Strip UI-only tokens that have no bearing on outcome quality."""
        return (text
                .replace('__SPLIT__', '')
                .replace('__CARD_FORM__', '')
                .replace('__ESCALATION__', '')
                .strip())

    transcript = "\n\n".join([
        f"Turn {n}:\nUSER:  {u}\nAGENT: {_clean(a)}"
        for n, u, a in responses
    ])

    overanswering_section = _OVERANSWERING_NOTE if check_overanswering else ""

    prompt = f"""{_JUDGE_SYSTEM}

Scenario being tested: {scenario['title']}

Expected behavior:
{scenario['desc']}
{overanswering_section}
Actual conversation transcript:
{transcript}

Did the Orbit agent correctly handle this scenario according to the expected behavior?

Reply with EXACTLY this format on one line:
PASS: <one sentence explaining why it passed>
  OR
FAIL: <one sentence explaining specifically what went wrong>"""

    import time as _time
    for _attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-pro",
                contents=prompt,
            )
            verdict = response.text.strip()
            passed = verdict.upper().startswith("PASS")
            return passed, verdict
        except Exception as _e:
            if _attempt < 2:
                _time.sleep(5)
            else:
                raise


def print_summary(results: list, group_label: str) -> None:
    """Print a formatted summary table for a group run."""
    print(f"\n\n{SEP}")
    print(f"SUMMARY — {group_label}  (LLM-as-judge)")
    print(SEP)
    for sc_id, title, status, verdict in results:
        sym = {"PASS": "✓", "FAIL": "✗", "ERROR": "!!"}.get(status, "?")
        print(f"  {sc_id:<8} {sym} {status:<6}  {title}")
        print(f"           {verdict}")
    passed_count = sum(1 for _, _, s, _ in results if s == "PASS")
    total = len(results)
    print(f"\n  {passed_count}/{total} passing\n{SEP}\n")
