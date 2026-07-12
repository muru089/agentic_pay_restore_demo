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
import subprocess
import uvicorn
from pathlib import Path
from fastapi import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from google.adk.cli.fast_api import get_fast_api_app

# ── Config ────────────────────────────────────────────────────────────────────
# serve_demo.py lives inside pay_restore_demo/ — agents_dir is the parent
AGENT_DIR      = Path(__file__).parent.parent   # c:\Muru_Workspace
PROJECT_DIR    = Path(__file__).parent          # c:\Muru_Workspace\pay_restore_demo
CHAT_HTML      = PROJECT_DIR / "orbit_chat.html"
ARCH_HTML      = PROJECT_DIR / "Project Files" / "architecture.html"
KB_HTML_DIR    = PROJECT_DIR / "knowledge_base" / "html"
RESET_SCRIPT   = PROJECT_DIR / "agents_tools_db" / "z_reset_world.py"
APP_NAME       = "pay_restore_demo"

# ── Kill any existing process on port 8000 ───────────────────────────────────
def _kill_port(port: int) -> None:
    """Free the port if another process is already listening (Windows)."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                pid = parts[-1]
                if pid.isdigit() and int(pid) != os.getpid():
                    subprocess.run(
                        ["taskkill", "/F", "/PID", pid],
                        capture_output=True, timeout=5
                    )
                    print(f"  Freed port {port} (killed PID {pid})")
    except Exception as e:
        print(f"  Port cleanup skipped: {e}")

_kill_port(8000)

# ── Auto-fix curly/smart quotes in orbit_chat.html ───────────────────────────
# Smart quotes (U+2018/2019/201C/201D) are valid HTML but break JavaScript when
# used as string delimiters. Any editor or copy-paste can silently introduce them.
# Fix unconditionally at startup so the chat UI is always syntactically valid.
def _fix_chat_html() -> None:
    text = CHAT_HTML.read_text(encoding="utf-8")
    fixed = (text
             .replace("‘", "'").replace("’", "'")
             .replace("“", '"').replace("”", '"'))
    if fixed != text:
        count = sum(text.count(c) for c in "‘’“”")
        CHAT_HTML.write_text(fixed, encoding="utf-8")
        print(f"  ⚠  Auto-fixed {count} curly quote(s) in orbit_chat.html (JS would have broken)")
    else:
        print("  orbit_chat.html JS — OK")

_fix_chat_html()

# ── Auto-reset DB on every startup ───────────────────────────────────────────
print("\n  Resetting DB to Day 1...")
runpy.run_path(str(RESET_SCRIPT), run_name="__main__")
print()

# ── Gemini API warm-up ────────────────────────────────────────────────────────
# Pre-warms the Gemini embedding connection so the first demo turn doesn't
# pay cold-start latency (~400ms saved on the first T10 RAG call).
print("  Warming up Gemini API...")
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(PROJECT_DIR / ".env")
    from google import genai as _genai
    _wc = _genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    _wc.models.embed_content(model="gemini-embedding-2", contents="warmup")
    print("  Gemini API ready.\n")
except Exception as _e:
    print(f"  Warm-up skipped: {_e}\n")

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

# ── Serve demo HTML pages ─────────────────────────────────────────────────────
@app.get("/orbit_chat.html", include_in_schema=False)
def serve_chat():
    return Response(content=CHAT_HTML.read_text(encoding="utf-8"), media_type="text/html")

@app.get("/architecture.html", include_in_schema=False)
def serve_arch():
    return Response(content=ARCH_HTML.read_text(encoding="utf-8"), media_type="text/html")

# Also serve at the original path so bookmarks / direct navigation still work.
app.mount(
    "/Project Files",
    StaticFiles(directory=str(PROJECT_DIR / "Project Files")),
    name="project_files",
)

# Serve knowledge_base/html/* so relative links between help-center pages work.
# URL: /knowledge_base/html/index.html, /knowledge_base/html/plans_pricing.html, etc.
app.mount(
    "/knowledge_base/html",
    StaticFiles(directory=str(KB_HTML_DIR), html=True),
    name="kb_html",
)

# ── /reset-db — reset DB mid-demo without restarting the server ──────────────
@app.post("/reset-db", include_in_schema=False)
def reset_db_endpoint():
    try:
        runpy.run_path(str(RESET_SCRIPT), run_name="__main__")
        return JSONResponse({"status": "ok", "message": "Database reset to Day 1"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


if __name__ == "__main__":
    print("\n  Orbit Demo Server")
    print("  " + "-" * 45)
    print("  Chat UI      -> http://127.0.0.1:8000/orbit_chat.html")
    print("  Architecture -> http://127.0.0.1:8000/architecture.html")
    print("  Help Center  -> http://127.0.0.1:8000/knowledge_base/html/index.html")
    print("  ADK Dev UI   -> http://127.0.0.1:8000/dev-ui")
    print("  " + "-" * 45 + "\n")
    uvicorn.run(app, host="127.0.0.1", port=8000)
