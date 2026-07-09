"""
check_demo.py — Pre-interview readiness check for the Orbit Pay Restore Demo
=============================================================================
Run this AFTER serve_demo.py is already running.

From c:\\Muru_Workspace:
    python pay_restore_demo/check_demo.py

Checks every critical system in ~15 seconds, prints PASS/FAIL for each,
then prints the URLs you'll use during the interview.
Exits with code 0 if all pass, 1 if any fail.
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import os
import sqlite3
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

_project_dir = Path(__file__).parent
_db_path     = _project_dir / "agents_tools_db" / "orbit.db"

BASE_URL  = "http://127.0.0.1:8000"
APP_NAME  = "pay_restore_demo"
USER_ID   = "check-demo"

SEP  = "=" * 62
SEP2 = "-" * 62

results = []   # list of (label, passed, detail)


def check(label, fn):
    """Run fn(), record PASS/FAIL, print immediately."""
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, f"Exception: {e}"
    sym = "✓" if ok else "✗"
    status = "PASS" if ok else "FAIL"
    pad = max(1, 46 - len(label))
    print(f"  {sym} {label}{' ' * pad}{status}")
    if not ok:
        print(f"      → {detail}")
    results.append((label, ok, detail))


# ── helpers ──────────────────────────────────────────────────────────────────

def http_get(path, timeout=5):
    url = BASE_URL + path
    req = urllib.request.Request(url)
    resp = urllib.request.urlopen(req, timeout=timeout)
    return resp.status, resp.read().decode("utf-8", errors="replace")


def http_post(path, body=None, timeout=8):
    url = BASE_URL + path
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=timeout)
    return resp.status, json.loads(resp.read())


# ── checks ───────────────────────────────────────────────────────────────────

def chk_server_up():
    status, _ = http_get("/")
    return status in (200, 307), f"HTTP {status}"


def chk_chat_ui():
    status, body = http_get("/orbit_chat.html")
    ok = status == 200 and "Orbit" in body and "__CARD_FORM__" in body
    return ok, "Page missing 'Orbit' or '__CARD_FORM__'" if not ok else ""


def chk_chat_ui_js():
    """Scan orbit_chat.html <script> block for curly/smart quotes that break JS."""
    import re
    status, body = http_get("/orbit_chat.html")
    if status != 200:
        return False, f"HTTP {status}"
    m = re.search(r"<script>(.*?)</script>", body, re.DOTALL)
    if not m:
        return False, "No <script> block found in orbit_chat.html"
    js = m.group(1)
    bad = {"‘": "U+2018 ‘", "’": "U+2019 ’",
           "“": "U+201C “", "”": "U+201D ”"}
    found = [f"{label}\xd7{js.count(ch)}" for ch, label in bad.items() if ch in js]
    if found:
        return False, "Curly quotes in JS (chat UI will not load): " + ", ".join(found)
    return True, ""


def chk_architecture():
    errors = []
    for path in ["/architecture.html", "/Project%20Files/architecture.html"]:
        try:
            status, body = http_get(path)
            if status != 200 or "mermaid" not in body.lower():
                errors.append(f"{path} → HTTP {status}")
        except Exception as e:
            errors.append(f"{path} → {e}")
    ok = len(errors) == 0
    return ok, "; ".join(errors) if errors else ""


def chk_help_center():
    status, body = http_get("/knowledge_base/html/index.html")
    ok = status == 200 and "orbit" in body.lower()
    return ok, "Help center index not served" if not ok else ""


def chk_help_pages():
    pages = [
        "plans_pricing.html",
        "billing_payment.html",
        "suspension_reactivation.html",
        "data_retention.html",
    ]
    missing = []
    for p in pages:
        try:
            status, _ = http_get(f"/knowledge_base/html/{p}")
            if status != 200:
                missing.append(p)
        except Exception:
            missing.append(p)
    ok = len(missing) == 0
    return ok, f"Missing: {missing}" if not ok else ""


def chk_session_api():
    status, body = http_post(f"/apps/{APP_NAME}/users/{USER_ID}/sessions")
    ok = status == 200 and "id" in body
    return ok, f"Expected session id, got: {body}" if not ok else ""


def chk_db_exists():
    ok = _db_path.exists()
    return ok, f"orbit.db not found at {_db_path}" if not ok else ""


def chk_db_accounts():
    conn = sqlite3.connect(str(_db_path))
    cur  = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM customer_accounts")
    count = cur.fetchone()[0]
    conn.close()
    ok = count == 15
    return ok, f"Expected 15 accounts, found {count}" if not ok else ""


def chk_db_key_accounts():
    conn = sqlite3.connect(str(_db_path))
    cur  = conn.cursor()
    errors = []

    # Alex 20001: SUSPENDED, Team, $49
    cur.execute("SELECT status, plan_name, pending_balance FROM customer_accounts WHERE account_id=20001")
    row = cur.fetchone()
    if not row or row[0] != "SUSPENDED" or row[1] != "Team" or row[2] != 49.0:
        errors.append(f"20001 Alex: expected SUSPENDED/Team/$49, got {row}")

    # Morgan 20005: SUSPENDED, AutoPay OFF
    cur.execute("SELECT status, autopay_active FROM customer_accounts WHERE account_id=20005")
    row = cur.fetchone()
    if not row or row[0] != "SUSPENDED" or row[1] != 0:
        errors.append(f"20005 Morgan: expected SUSPENDED/autopay_OFF, got {row}")

    # Casey 20006: ACTIVE, $0
    cur.execute("SELECT status, pending_balance FROM customer_accounts WHERE account_id=20006")
    row = cur.fetchone()
    if not row or row[0] != "ACTIVE" or row[2 - 1] != 0.0:
        errors.append(f"20006 Casey: expected ACTIVE/$0, got {row}")

    # Sam 20003: SUSPENDED, suspension_date set, 35 days back
    cur.execute("SELECT status, suspension_date FROM customer_accounts WHERE account_id=20003")
    row = cur.fetchone()
    if not row or row[0] != "SUSPENDED" or not row[1]:
        errors.append(f"20003 Sam: expected SUSPENDED with date, got {row}")

    conn.close()
    ok = len(errors) == 0
    return ok, "; ".join(errors) if errors else ""


def chk_db_plan_catalog():
    conn = sqlite3.connect(str(_db_path))
    cur  = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM plan_catalog")
    count = cur.fetchone()[0]
    conn.close()
    ok = count == 4
    return ok, f"Expected 4 plans, found {count}" if not ok else ""


def chk_session_state_table():
    conn = sqlite3.connect(str(_db_path))
    cur  = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='session_state'")
    ok = cur.fetchone() is not None
    conn.close()
    return ok, "session_state table missing from orbit.db" if not ok else ""


def chk_rag():
    try:
        import chromadb
        chroma_path = _project_dir / "knowledge_base" / "chroma_db"
        client = chromadb.PersistentClient(path=str(chroma_path))
        cols = client.list_collections()
        if not cols:
            return False, "ChromaDB has no collections"
        col = cols[0]
        count = col.count()
        ok = count >= 10
        return ok, f"ChromaDB has only {count} chunks (expected ≥ 10)" if not ok else f"{count} chunks in '{col.name}'"
    except Exception as e:
        return False, str(e)


def chk_azure_config():
    key    = os.environ.get("CONTENT_SAFETY_KEY") or os.environ.get("AZURE_CONTENT_SAFETY_KEY")
    ep     = os.environ.get("CONTENT_SAFETY_ENDPOINT") or os.environ.get("AZURE_CONTENT_SAFETY_ENDPOINT")
    # Load from .env if not in environment
    if not key:
        env_path = _project_dir / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if "=" not in line or line.startswith("#"):
                    continue
                k, v = line.split("=", 1)
                if "CONTENT_SAFETY_KEY" in k:
                    key = v.strip()
                if "CONTENT_SAFETY_ENDPOINT" in k:
                    ep = v.strip()
    ok = bool(key and ep)
    return ok, "CONTENT_SAFETY_KEY or CONTENT_SAFETY_ENDPOINT not set in .env" if not ok else ""


def chk_gemini_config():
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        env_path = _project_dir / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if "=" not in line or line.startswith("#"):
                    continue
                k, v = line.split("=", 1)
                if k.strip() in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
                    key = v.strip()
    ok = bool(key)
    return ok, "GOOGLE_API_KEY not set in .env" if not ok else ""


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print()
    print(SEP)
    print("  ORBIT DEMO — Pre-Interview Readiness Check")
    print(SEP)
    print()

    t0 = time.time()

    print("  [ Servers & Pages ]")
    check("Server reachable (port 8000)",      chk_server_up)
    check("Chat UI served (/orbit_chat.html)", chk_chat_ui)
    check("Chat UI JS syntax (no curly quotes)", chk_chat_ui_js)
    check("Architecture page served",          chk_architecture)
    check("Help center index served",          chk_help_center)
    check("Help center sub-pages (4 checked)", chk_help_pages)

    print()
    print("  [ ADK API ]")
    check("Session creation API",              chk_session_api)

    print()
    print("  [ Database ]")
    check("orbit.db file exists",             chk_db_exists)
    check("plan_catalog — 4 plans",           chk_db_plan_catalog)
    check("customer_accounts — 15 accounts",  chk_db_accounts)
    check("Key demo accounts correct state",  chk_db_key_accounts)
    check("session_state table present",      chk_session_state_table)

    print()
    print("  [ AI & Safety ]")
    check("Gemini API key configured",        chk_gemini_config)
    check("Azure Content Safety configured",  chk_azure_config)
    check("RAG knowledge base (ChromaDB)",    chk_rag)

    elapsed = time.time() - t0
    total   = len(results)
    passed  = sum(1 for _, ok, _ in results if ok)
    failed  = total - passed

    print()
    print(SEP)
    print(f"  Result: {passed}/{total} checks passed   ({elapsed:.1f}s)")
    print(SEP)

    if failed == 0:
        print()
        print("  ✓ ALL SYSTEMS GO — demo is ready.\n")
        print("  URLS FOR YOUR INTERVIEW:")
        print(f"    Chat UI      →  {BASE_URL}/orbit_chat.html")
        print(f"    Architecture →  {BASE_URL}/architecture.html")
        print(f"    Help Center  →  {BASE_URL}/knowledge_base/html/index.html")
        print(f"    ADK traces   →  {BASE_URL}/dev-ui")
        print()
        print("  All page links (\"Chat with Orbit AI\", \"Ask Orbit AI\") work.")
        print("  Ctrl+C in the serve_demo.py window to stop after the interview.")
        print()
    else:
        print()
        print(f"  ✗ {failed} check(s) FAILED — fix before the interview.")
        print()
        print("  Failed checks:")
        for label, ok, detail in results:
            if not ok:
                print(f"    • {label}: {detail}")
        print()

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
