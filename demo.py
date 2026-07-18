"""
demo.py — Orbit Pay Restore Demo Launcher
==========================================
Run this once before your interview. It:
  1. Resets the database (Day 1 state, all 15 accounts)
  2. Starts the ADK agent backend on port 8000
  3. Starts a static file server on port 3000 (serves all demo HTML)
  4. Opens the chat UI in your browser

Run from c:\\Muru_Workspace:
    python pay_restore_demo/demo.py

Then open any of these in your browser:
    http://127.0.0.1:3000/orbit_chat.html          ← Chat UI
    http://127.0.0.1:3000/Project Files/architecture.html  ← Architecture diagrams
    http://127.0.0.1:3000/knowledge_base/html/index.html   ← Help Center

Links between pages work correctly — "Chat with Orbit AI" and
"Ask Orbit AI" buttons all navigate to orbit_chat.html via HTTP,
so there are no CORS or file:// issues.

To reset the DB mid-demo without restarting:
    python pay_restore_demo/agents_tools_db/z_reset_world.py

Press Ctrl+C to stop both servers.
"""

import os
import sys
import subprocess
import threading
import time
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

_project_dir = Path(__file__).parent.resolve()
_workspace   = _project_dir.parent

STATIC_PORT = 3000
ADK_PORT    = 8000
CHAT_URL    = f"http://127.0.0.1:{STATIC_PORT}/orbit_chat.html"


# ── Step 1: Reset the database ────────────────────────────────────────────────
def reset_db():
    reset_script = _project_dir / "agents_tools_db" / "z_reset_world.py"
    print("─" * 60)
    print("  Resetting database to Day 1...")
    print("─" * 60)
    result = subprocess.run(
        [sys.executable, str(reset_script)],
        cwd=str(_workspace),
        capture_output=False,
    )
    if result.returncode != 0:
        print("\n  !! DB reset failed. Check z_reset_world.py output above.")
        sys.exit(1)
    print()


# ── Step 2: Start ADK web backend ────────────────────────────────────────────
def start_adk():
    adk_cmd = [
        "adk", "web",
        "--allow_origins", f"http://127.0.0.1:{STATIC_PORT}",
        "--port", str(ADK_PORT),
    ]
    print("─" * 60)
    print(f"  Starting ADK backend on port {ADK_PORT}...")
    print(f"  Command: {' '.join(adk_cmd)}")
    print("─" * 60)
    proc = subprocess.Popen(
        adk_cmd,
        cwd=str(_workspace),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for it to be ready
    import urllib.request
    for _ in range(20):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{ADK_PORT}", timeout=1)
            print(f"  ✓ ADK backend ready at http://127.0.0.1:{ADK_PORT}\n")
            return proc
        except Exception:
            pass
    print(f"  !! ADK backend did not start in time. Check if port {ADK_PORT} is in use.")
    proc.terminate()
    sys.exit(1)


# ── Step 3: Static file server (serves entire project directory) ──────────────
class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress per-request logs — keeps terminal clean during demo

    def end_headers(self):
        # Allow the ADK backend to be called from this origin
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


def start_static_server():
    os.chdir(str(_project_dir))   # serve from project root
    server = HTTPServer(("127.0.0.1", STATIC_PORT), QuietHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print("─" * 60)
    print(f"  ✓ Static file server ready at http://127.0.0.1:{STATIC_PORT}")
    print("─" * 60)
    return server


# ── Step 4: Open browser ─────────────────────────────────────────────────────
def open_browser():
    time.sleep(0.5)
    print(f"\n  Opening: {CHAT_URL}\n")
    webbrowser.open(CHAT_URL)


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print()
    print("=" * 60)
    print("  ORBIT PAY RESTORE DEMO — Launcher")
    print("=" * 60)
    print()

    reset_db()
    adk_proc = start_adk()
    start_static_server()

    print()
    print("=" * 60)
    print("  DEMO IS READY")
    print("=" * 60)
    print()
    print(f"  Chat UI      →  http://127.0.0.1:{STATIC_PORT}/orbit_chat.html")
    print(f"  Architecture →  http://127.0.0.1:{STATIC_PORT}/Project Files/architecture.html")
    print(f"  Help Center  →  http://127.0.0.1:{STATIC_PORT}/knowledge_base/html/index.html")
    print(f"  ADK traces   →  http://127.0.0.1:{ADK_PORT}")
    print()
    print("  All page links ('Chat with Orbit AI', 'Ask Orbit AI') work correctly.")
    print("  Press Ctrl+C to stop.\n")

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        adk_proc.wait()
    except KeyboardInterrupt:
        print("\n  Shutting down...")
        adk_proc.terminate()
        print("  Done.\n")


if __name__ == "__main__":
    main()
