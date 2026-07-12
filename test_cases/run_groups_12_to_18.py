"""
run_groups_12_to_18.py — Master runner for Groups 12–18 (S76–S134)
Runs each group as a subprocess sequentially, streams output to terminal,
and prints a combined scoreboard at the end.

Run from c:\\Muru_Workspace:
    python "pay_restore_demo/Agent Sim/run_groups_12_to_18.py"
"""
import subprocess, sys, os, re, time, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_this_dir    = os.path.dirname(os.path.abspath(__file__))
_project_dir = os.path.dirname(_this_dir)
_workspace   = os.path.dirname(_project_dir)

GROUPS = [
    ("G12", "run_group12_restore_plan.py",     "Plan Changes During Restore + Routing Edge Cases",  8),
    ("G13", "run_group13_conversation.py",     "Conversation Dynamics",                             8),
    ("G14", "run_group14_tone.py",             "Warm Close & Tone",                                 6),
    ("G15", "run_group15_sa1_extended.py",     "SA1 Extended Diagnostics",                         10),
    ("G16", "run_group16_safety_ext.py",       "Safety Extended",                                   9),
    ("G17", "run_group17_escalation_state.py", "Escalation + Persistent State",                    10),
    ("G18", "run_group18_rag_routing.py",      "RAG Edge Cases + Routing Gaps",                     8),
]

SEP  = "=" * 70
HASH = "#" * 70

_PASS_RE = re.compile(r"^\s+(\w+-\w+)\s+[✓✗!!]+\s+(PASS|FAIL|ERROR)", re.UNICODE)
_TOTAL_RE = re.compile(r"(\d+)/(\d+) passing")


def run_group(script_name: str) -> tuple[list[tuple], int, int]:
    """Run a group script as subprocess, stream output, return (results, passed, total)."""
    script_path = os.path.join(_this_dir, script_name)
    proc = subprocess.Popen(
        [sys.executable, script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=_workspace,
    )

    lines = []
    passed = total = 0
    for line in proc.stdout:
        print(line, end="", flush=True)
        lines.append(line)

        # capture final passing count from SUMMARY line
        m = _TOTAL_RE.search(line)
        if m:
            passed = int(m.group(1))
            total  = int(m.group(2))

    proc.wait()
    return lines, passed, total


def main():
    grand_pass = grand_total = 0
    group_scores = []
    master_start = time.time()

    for tag, script, label, expected in GROUPS:
        print(f"\n\n{HASH}")
        print(f"STARTING {tag} — {label}")
        print(HASH)
        g_start = time.time()

        lines, passed, total = run_group(script)
        elapsed = time.time() - g_start

        if total == 0:
            total = expected  # fallback if parse failed
        grand_pass  += passed
        grand_total += total
        group_scores.append((tag, label, passed, total, elapsed))
        print(f"\n  {tag} complete — {passed}/{total} in {elapsed/60:.1f} min")

    # ── Master scoreboard ──────────────────────────────────────────────────
    master_elapsed = time.time() - master_start
    print(f"\n\n{HASH}")
    print("MASTER SCOREBOARD — Groups 12–18")
    print(HASH)
    for tag, label, passed, total, elapsed in group_scores:
        bar = "✓" if passed == total else ("~" if passed >= total * 0.8 else "✗")
        print(f"  {tag:<4}  {passed}/{total:<4}  {bar}  {label}  ({elapsed/60:.1f}m)")
    print(f"\n  TOTAL: {grand_pass}/{grand_total}  ({master_elapsed/60:.1f} min total)")
    print(HASH)


if __name__ == "__main__":
    main()
