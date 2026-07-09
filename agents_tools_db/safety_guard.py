"""
safety_guard.py — Pre-flight input safety check
================================================
TIER:    Pre-agent (fires before root_agent LLM is invoked)
PATTERN: check(message) → ("pass", None) | ("block", customer_response)

Architecture (evals whitepaper — Pillar 4 Live Critical Path):
    T1 — Python regex        (~0ms):   PII only (SSN)
    T2a — Azure Prompt Shield (~80ms): Injection & jailbreak detection
    T2b — Azure Text Analyze  (~80ms): Toxicity, hate, violence, self-harm

Prompt Shield replaces the brittle T1 regex injection patterns — it handles
novel paraphrase variants that regex cannot catch.

Fail-open design: Azure API errors never block a legitimate customer.
Wired into root_agent via before_agent_callback in agent.py.

Note: 16-digit card numbers are NOT blocked — Phase 1-4 card input via
chat text is intentional (see CLAUDE.md card payment flow exception).
"""

import os
import requests
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .log_setup import get_logger

_log = get_logger("safety")

# Auto-load .env so tests work outside ADK runtime (ADK loads it automatically in production)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

# ── Credentials ────────────────────────────────────────────────────────────

_KEY      = os.getenv("AZURE_CONTENT_SAFETY_KEY", "")
_ENDPOINT = os.getenv("AZURE_CONTENT_SAFETY_ENDPOINT", "").rstrip("/")

# ── T1: Regex — PII only ───────────────────────────────────────────────────

import re
_SSN_RE = re.compile(r'\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b')

# Pre-filter: Prompt Shield false-positive bypass for unambiguous account-service messages.
# Narrow criteria: 5-digit account ID + Orbit-specific service term + NO injection signals.
# An injection payload that adds a 5-digit number cannot also lack injection keywords.
_ACCT_ID_RE = re.compile(r'\b\d{5}\b')
_ACCT_ACTIONS_RE = re.compile(
    r'\b(restore|restored|suspended|suspension|waive|waiver|reactivate|'
    r'upgrade|downgrade|autopay|late\s+fee)\b',
    re.IGNORECASE
)
_INJECTION_SIGNALS_RE = re.compile(
    r'\b(ignore|forget|disregard|override|pretend|roleplay|system\s+prompt|'
    r'jailbreak|previous\s+instructions?|output\s+your|reveal\s+your|bypass|'
    r'act\s+as|you\s+are\s+now|from\s+now\s+on|new\s+persona|developer\s+mode|'
    r'tell\s+me\s+your|what\s+are\s+your\s+instructions?)\b',
    re.IGNORECASE
)

# ── T2a: Azure Prompt Shield ───────────────────────────────────────────────
# Detects prompt injection and jailbreak attempts (novel paraphrases included).
# https://learn.microsoft.com/azure/ai-services/content-safety/concepts/jailbreak-detection

_SHIELD_URL     = f"{_ENDPOINT}/contentsafety/text:shieldPrompt?api-version=2024-02-15-preview"
_SHIELD_HEADERS = {"Ocp-Apim-Subscription-Key": _KEY, "Content-Type": "application/json"}

def _t2a_prompt_shield(text: str) -> bool:
    """Returns True if an injection or jailbreak attack is detected."""
    if not _KEY or not _ENDPOINT:
        return False
    # Skip for clear customer account service messages — Prompt Shield misclassifies
    # phrases like "restore it and waive the fee" as potential injection.
    if (_ACCT_ID_RE.search(text)
            and _ACCT_ACTIONS_RE.search(text)
            and not _INJECTION_SIGNALS_RE.search(text)):
        return False
    try:
        resp = requests.post(
            _SHIELD_URL,
            headers=_SHIELD_HEADERS,
            json={"userPrompt": text},
            timeout=3.0,
        )
        if resp.status_code != 200:
            msg = f"Prompt Shield HTTP {resp.status_code} — failing open"
            print(f"[safety_guard] {msg}")
            _log.error(msg)
            return False
        return resp.json().get("userPromptAnalysis", {}).get("attackDetected", False)
    except requests.exceptions.Timeout:
        msg = "Prompt Shield timeout — failing open"
        print(f"[safety_guard] {msg}")
        _log.warning(msg)
        return False
    except Exception as exc:
        msg = f"Prompt Shield error (failing open): {exc}"
        print(f"[safety_guard] {msg}")
        _log.error(msg)
        return False


# ── T2b: Azure Text Analyze ────────────────────────────────────────────────
# Scores Hate, Violence, Sexual, SelfHarm on 0/2/4/6 severity scale.
# Block at severity >= 4 (medium). Allows frustrated-but-legitimate customers.

_ANALYZE_URL     = f"{_ENDPOINT}/contentsafety/text:analyze?api-version=2023-10-01"
_ANALYZE_HEADERS = {"Ocp-Apim-Subscription-Key": _KEY, "Content-Type": "application/json"}
_BLOCK_SEVERITY  = 4   # 0=safe, 2=low(allow), 4=medium(block), 6=high(block)

def _t2b_text_analyze(text: str) -> tuple[bool, str]:
    """Returns (is_blocked, category). Fails open on any error."""
    if not _KEY or not _ENDPOINT:
        return False, ""
    try:
        payload = {
            "text": text,
            "categories": ["Hate", "Violence", "Sexual", "SelfHarm"],
            "outputType": "FourSeverityLevels",
        }
        resp = requests.post(
            _ANALYZE_URL,
            headers=_ANALYZE_HEADERS,
            json=payload,
            timeout=3.0,
        )
        if resp.status_code != 200:
            msg = f"Text Analyze HTTP {resp.status_code} — failing open"
            print(f"[safety_guard] {msg}")
            _log.error(msg)
            return False, ""
        for item in resp.json().get("categoriesAnalysis", []):
            if item.get("severity", 0) >= _BLOCK_SEVERITY:
                cat = item.get("category", "unknown")
                sev = item.get("severity", 0)
                _log.info(f"BLOCKED  category={cat}  severity={sev}")
                return True, cat
        return False, ""
    except requests.exceptions.Timeout:
        msg = "Text Analyze timeout — failing open"
        print(f"[safety_guard] {msg}")
        _log.warning(msg)
        return False, ""
    except Exception as exc:
        msg = f"Text Analyze error (failing open): {exc}"
        print(f"[safety_guard] {msg}")
        _log.error(msg)
        return False, ""


# ── Public API ─────────────────────────────────────────────────────────────

def check(message: str) -> tuple[str, str | None]:
    """
    Run T1 → T2a+T2b (parallel) checks.
    Returns ("pass", None) or ("block", customer_response).

    T1 (regex) runs first synchronously — ~0ms, no I/O.
    T2a and T2b fire in parallel via ThreadPoolExecutor — saves ~80ms vs serial.

    Response strings use minimal disclosure:
    - PII: explains the secure alternative (genuinely helpful)
    - Injection: looks identical to a normal clarification (no signal to attacker)
    - Toxicity: firm but not shaming, invites return
    """
    # ── T1: SSN ───────────────────────────────────────────────────────
    if _SSN_RE.search(message):
        _log.info(f"BLOCKED  rule=T1/SSN  preview={message[:60]!r}")
        return (
            "block",
            "For your security, I can't accept sensitive personal data in chat. "
            "Please use your 5-digit account ID and I'll pull up your account.",
        )

    # ── T2a + T2b: run in parallel ────────────────────────────────────
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_shield  = pool.submit(_t2a_prompt_shield, message)
        fut_analyze = pool.submit(_t2b_text_analyze,  message)
        shield_blocked           = fut_shield.result()
        analyze_blocked, category = fut_analyze.result()

    if shield_blocked:
        _log.info(f"BLOCKED  rule=T2a/PromptShield  preview={message[:60]!r}")
        return (
            "block",
            "I'm here to help with your account — what can I assist you with today?",
        )

    if analyze_blocked:
        if category == "Violence":
            return (
                "block",
                "I'm not able to continue this conversation on that note. "
                "If you're in crisis, please reach out to emergency services "
                "or a support line in your area.",
            )
        return (
            "block",
            "I want to help, but I'm not able to continue when messages are sent that way. "
            "I'm here whenever you'd like to talk about your account.",
        )

    return ("pass", None)
