"""
serve_demo.py - Single-port demo server
Wraps ADK's FastAPI app, adds CORS, and serves orbit_chat.html at /orbit_chat.html

Run from c:\\Muru_Workspace (parent of pay_restore_demo):
    python pay_restore_demo/serve_demo.py

Then open: http://127.0.0.1:8000/orbit_chat.html
"""

import os
import sys
import runpy
import uvicorn
from pathlib import Path
from fastapi import Response
from fastapi.middleware.cors import CORSMiddleware
from google.adk.cli.fast_api import get_fast_api_app

# ── Config ────────────────────────────────────────────────────────────────────
# serve_demo.py lives inside pay_restore_demo/ — agents_dir is the parent
AGENT_DIR   = Path(__file__).parent.parent   # c:\Muru_Workspace
CHAT_HTML   = Path(__file__).parent / "orbit_chat.html"
RESET_SCRIPT = Path(__file__).parent / "agents_tools_db" / "z_reset_world.py"
APP_NAME    = "pay_restore_demo"

# ── Auto-reset DB on every startup ───────────────────────────────────────────
print("\n  Resetting DB to Day 1...")
runpy.run_path(str(RESET_SCRIPT), run_name="__main__")
print()

# ── Build ADK app ─────────────────────────────────────────────────────────────
app = get_fast_api_app(
    agents_dir=str(AGENT_DIR),
    web=True,
    trace_to_cloud=False,
)

# ── CORS (allow everything for local demo) ────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Serve orbit_chat.html at /orbit_chat.html ─────────────────────────────────
@app.get("/orbit_chat.html", include_in_schema=False)
def serve_chat():
    html = CHAT_HTML.read_text(encoding="utf-8")
    return Response(content=html, media_type="text/html")


if __name__ == "__main__":
    print("\n  Orbit Demo Server")
    print("  " + "-" * 45)
    print("  ADK backend  -> http://127.0.0.1:8000")
    print("  Chat UI      -> http://127.0.0.1:8000/orbit_chat.html")
    print("  ADK Dev UI   -> http://127.0.0.1:8000/dev-ui")
    print("  " + "-" * 45 + "\n")
    uvicorn.run(app, host="127.0.0.1", port=8000)
