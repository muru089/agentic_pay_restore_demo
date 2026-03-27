# CLAUDE.md — Pay Restore Demo
> This file is the single authoritative reference for all agent logic, business rules, tool design, and debugging.
> Do NOT generate any agent behavior, business rule, or tool response that contradicts this document.
> Code always supersedes any other document where they conflict.

---

## 1. Project Identity

| Field | Value |
|---|---|
| **Project name** | pay_restore_demo |
| **Domain** | Project management / team collaboration platform |
| **Folder** | `c:\Muru_Workspace\pay_restore_demo` |
| **DB file** | `pay_restore.db` |
| **Reset script** | `z_reset_world.py` |
| **Run from** | `c:\Muru_Workspace` (parent directory) |

---

## 2. Plans (5 tiers)

| plan_id | plan_name | Price/mo | Max Users | Storage |
|---------|-----------|----------|-----------|---------|
| P001 | Starter | $29 | 5 | 20 GB |
| P002 | Professional | $79 | 15 | 100 GB |
| P003 | Premium | $149 | 50 | 500 GB |
| P004 | Business | $249 | 150 | 2 TB |
| P005 | Enterprise | $499 | Unlimited | 10 TB |

---

## 3. Database Schema (2 tables)

```sql
CREATE TABLE plan_catalog (
    plan_id       TEXT PRIMARY KEY,
    plan_name     TEXT,
    monthly_price REAL,
    max_users     INTEGER,
    storage_gb    INTEGER
);

CREATE TABLE customer_accounts (
    account_id          INTEGER PRIMARY KEY,   -- 5-digit: 20001–20020
    first_name          TEXT,
    company_name        TEXT,
    plan_name           TEXT,                  -- FK to plan_catalog.plan_name
    tenure_months       REAL,
    autopay_active      INTEGER,               -- 1=True, 0=False
    waivers_used_12m    INTEGER,               -- 1=True, 0=False
    pending_balance     REAL,
    status              TEXT,                  -- "ACTIVE" | "SUSPENDED" | "CANCELED"
    email               TEXT,
    card_last4          TEXT,                  -- last 4 digits of card on file
    suspension_date     TEXT,                  -- "YYYY-MM-DD" or NULL
    last_waiver_date    TEXT,                  -- "YYYY-MM-DD" or NULL
    seat_count          INTEGER,               -- active seats in use
    project_count       INTEGER,               -- number of active projects
    data_retention_days INTEGER               -- days data kept post-suspension (always 30)
);
```

---

## 4. Demo Accounts

### Group A — Active / Suspended (20001–20010)

| ID | Name | Company | Plan | Tenure | Autopay | Balance | Status | Susp.Days | Waiver | Archetype |
|----|------|---------|------|--------|---------|---------|--------|-----------|--------|-----------|
| 20001 | Alex | Wavefront | Professional | 9mo | ON | $79 | SUSPENDED | 5 | PASS | Primary demo — data safe, waiver PASS, upgrade to Premium |
| 20002 | Jordan | Sprinto | Professional | 2mo | OFF | $79 | SUSPENDED | 5 | FAIL (Rule A + B) | New customer, waiver fail |
| 20003 | Sam | Arclight | Premium | 14mo | ON | $149 | SUSPENDED | 35 | PASS | Data AT RISK (35 days > 30-day window) |
| 20004 | Riley | Nomad Labs | Starter | 7mo | ON | $29 | SUSPENDED | 10 | PASS | Small balance, clean restore |
| 20005 | Morgan | Crestline | Business | 18mo | OFF | $249 | SUSPENDED | 3 | FAIL (Rule B — autopay OFF) | Long tenure but no autopay |
| 20006 | Casey | Driftwood | Professional | 8mo | ON | $0 | ACTIVE | — | PASS | Active account, upgrade only |
| 20007 | Drew | Lumen Co | Starter | 1mo | OFF | $0 | ACTIVE | — | FAIL (Rule A + B) | New customer, no issues |
| 20008 | Quinn | Pathfinder | Premium | 24mo | ON | $0 | ACTIVE | — | PASS | Long tenure power user |
| 20009 | Jamie | Redpine | Business | 6mo | ON | $149 | SUSPENDED | 20 | FAIL (Rule A — must be > 6, not =) | Exactly 6.0mo → boundary fail |
| 20010 | Avery | Stratos | Enterprise | 30mo | ON | $499 | SUSPENDED | 8 | PASS | Top tier, perfect restore |

### Group B — Canceled (20011–20020)

Generic churned accounts: Professional plan, 1.5mo tenure, autopay OFF, $0 balance, CANCELED.
Used for win-back demos → route to plan upgrade flow.

---

## 5. Agent Architecture (3-tier)

**Framework:** Google ADK (`google.adk.agents.Agent`, `google.adk.tools.FunctionTool`, `google.adk.tools.agent_tool.AgentTool`)
**LLM:** `gemini-2.0-flash` for root_agent, SA1_RestoreSupervisor, DA3_RestoreAgent; `gemini-2.0-flash-lite` for DA1_AccountAgent, DA2_BillingAgent
**DB Injection:** `functools.partial` used to inject `conn` into all DB tools. Helper: `create_db_tool(fn, conn)` defined in each agent file.
**Exception:** T8_SendReceipt opens its own DB connection internally — do NOT wrap with `create_db_tool`.
**Server Launch:** Run `adk web` from `c:\Muru_Workspace` (parent directory).

```
root_agent              (agent.py)                       gemini-2.0-flash   ← Uber
  +-- T1_GetAccount        (direct tool: auth)
  +-- DA1_AccountAgent     (DA1_Account_Agent.py)        gemini-2.0-flash-lite
  +-- DA2_BillingAgent     (DA2_Billing_Agent.py)        gemini-2.0-flash-lite
  +-- SA1_RestoreSupervisor (SA1_Restore_Supervisor.py)  gemini-2.0-flash   ← Supervisor
        +-- DA1_AccountAgent    (data safety check)          via AgentTool
        +-- DA2_BillingAgent    (payment, fee waiver)        via AgentTool
        +-- DA3_RestoreAgent    (DA3_Restore_Agent.py)       gemini-2.0-flash  ← Squad
              +-- T5_RestoreAccount
              +-- T6_ChangePlan
              +-- T8_SendReceipt
```

| Tier | Agent | Responsibility |
|---|---|---|
| Uber | root_agent | Auth, input safety (PII/injection/toxicity), disambiguation, routing |
| Supervisor | SA1_RestoreSupervisor | 6-state restore state machine. No direct tools. Yields to DAs. |
| Domain | DA1_AccountAgent | Account status, data retention check |
| Domain | DA2_BillingAgent | Payment, balance, fee waiver |
| Squad | DA3_RestoreAgent | Fire-and-return. Executes restore + plan upgrade + receipt. |

**Guardrail placement:**
- **Layer 1 (Input):** Uber Agent only — PII, prompt injection, toxicity, out-of-scope
- **Layer 2 (Logic):** Each domain agent — domain-specific rules (balance gate, consent, card security)
- **Layer 3 (Output):** Uber Agent only — variable exposure, contradictions, verbosity

---

## 6. Tool Reference (T1–T8)

| Tool | File | Signature | Purpose |
|------|------|-----------|---------|
| T1 | T1_GetAccount.py | (conn, account_id) | Auth: returns first_name, plan, status, tenure_months, card_last4, suspension_date, project_count |
| T2 | T2_CheckDataRetention.py | (conn, account_id) | Calculates days_suspended. Returns data_safe (True if ≤ 30 days), project_count |
| T3 | T3_ProcessPayment.py | (conn, account_id) | Pays full pending_balance. Card on file only. Returns amount_charged |
| T4 | T4_CheckFeeWaiver.py | (conn, account_id) | 3-rule waiver: tenure_months > 6, autopay=1, no prior waiver in 12mo. Returns waiver_granted + reason |
| T5 | T5_RestoreAccount.py | (conn, account_id) | Sets status=ACTIVE, clears suspension_date |
| T6 | T6_ChangePlan.py | (conn, account_id, new_plan_name) | Updates plan_name. Effective next billing cycle |
| T7 | T7_GetBalance.py | (conn, account_id) | Read-only. Returns pending_balance |
| T8 | T8_SendReceipt.py | (account_id, action_type, details={}) | Confirmation receipt. Opens own DB conn |

**DB injection:** `functools.partial(fn, conn)` on T1–T7. T8 exception: opens its own `sqlite3.connect("pay_restore.db")` — never wrap with `create_db_tool`.

---

## 7. Business Rules

### Fee Waiver — 3-Rule Logic (T4)
All three must be true for $0 late fee. Any single failure = $25 fee.
- **Rule A:** tenure_months > 6 (strictly greater than — 6.0 months does NOT qualify)
- **Rule B:** autopay_active = 1
- **Rule C:** last_waiver_date is NULL or older than 12 months

On failure: return specific failing rule(s) with reason. Never just say "you do not qualify."

### Data Retention Rule (T2)
- days_suspended = today − suspension_date
- days_suspended ≤ 30: data SAFE — "All [N] projects are intact."
- days_suspended > 30: data AT RISK — "Some projects may have been archived or purged."

### Card Security Hard Stop
- Agent cannot accept new card details via chat. Card on file only.
- Script: "For security, card updates require our billing portal or a support specialist. Would you like to proceed with the card on file ending in [XXXX]?"

### Balance Gate
- pending_balance must be $0 before restore proceeds. Payment required first.

### Consent Gate
- Explicit "Yes" / "Go ahead" required before charging. "I guess" / "maybe" = NOT consent.

### Suspension Gate
- Only SUSPENDED accounts enter the restore flow.
- ACTIVE accounts → billing or upgrade only.
- CANCELED accounts → win-back (offer plan info, no reactivation).

### No Proration
- Plan upgrades effective next billing cycle. No mid-cycle credits or adjustments.

---

## 8. Restore Flow — SA1_RestoreSupervisor (6 states)

```
STATE 1: Balance Gate       → T7 (check balance). If > $0 → inform customer, ask consent to pay.
STATE 2: Data Safety Check  → DA1: T2 (days_suspended). Report safe/at-risk.
STATE 3: Card Security      → If customer mentions new card → HARD STOP. Offer card on file.
STATE 4: Payment            → DA2: T3 (card on file, full balance).
STATE 5: Fee Waiver         → DA2: T4 (3-rule check). Report $0 or $25 + specific reason.
STATE 6: Restore + Upgrade  → DA3: T5 (restore) → T6 (upgrade if requested) → T8 (receipt).
```

**HANDOFF SIGNALS (Approach B — checked in priority order):**

root_agent passes the FULL conversation transcript to SA1 on every invocation. SA1 reads the transcript and self-determines which state to resume at.

- **SIGNAL D (highest):** Restore consent given → DA2 payment → DA2 fee check → DA3 restore → DA3 upgrade (if requested)
- **SIGNAL C:** Data safety confirmed, card security passed → present card-on-file + ask payment consent. HARD STOP.
- **SIGNAL B:** Balance cleared → DA2 fee check → present summary. HARD STOP.
- **SIGNAL A:** Fresh start → balance check (T7) + data safety check (DA1: T2) in one turn. HARD STOP.
- **SIGNAL F (lowest):** Cancel/downgrade only (no restore) → CANCEL FLOW.

ONE signal fires per turn. HARD STOP after each — never combine steps.

---

## 9. Coding Patterns

### Approach B — Ephemeral State Reconstruction
- SA1_RestoreSupervisor has NO session state, NO persistent variables.
- root_agent passes the FULL conversation transcript to SA1 on EVERY invocation.
- SA1 reads the transcript and self-determines which state to resume via HANDOFF SIGNALS.
- Each AgentTool call (DA1, DA2, DA3) gets a fresh InMemorySession.

### SA1 ONE-STEP-PER-RESPONSE Rule
- SA1 executes EXACTLY one state machine step per response turn.
- HARD STOP instructions prevent step merging across states.

### Fee Waiver Ground Truth Rule
- Fee result comes ONLY from T4's tool output.
- SA1 must NEVER infer "fee waived" from tenure, autopay status, or payment history.
- Clearing the balance does NOT grant the fee waiver — they are completely independent.

### DA3_RestoreAgent (Squad Pattern)
- Fire-and-return. No customer interaction between T5 → T6 → T8.
- T5 must succeed before T6 is called (gate enforced).
- Called by SA1 only. Never by root_agent directly.
- Uses `gemini-2.0-flash` (NOT flash-lite) — flash-lite intermittently returns `Part(text=None)` after multi-tool chains.

### DB Tool Injection
```python
def create_db_tool(fn, conn):
    bound = functools.partial(fn, conn)
    bound.__name__ = fn.__name__
    bound.__doc__  = fn.__doc__
    return FunctionTool(bound)
```
T8_SendReceipt exception: opens its own connection — never wrap with `create_db_tool`.

### SA1 Callbacks (terminal trace)
- Add `before_tool_callback` and `after_tool_callback` to SA1_RestoreSupervisor.
- Prints `SA1 → DA1`, `SA1 ← DA1 RSP:...` to terminal when `adk web` is running.

### 5-Element State Machine Pattern (each DA agent state)
```
ENTRY GUARD      → validate preconditions before acting
PRE-TOOL GUARD   → validate inputs before tool call
THE JOB          → call the tool, do the work
POST-TOOL GUARD  → validate tool output, ground truth enforcement
TRANSITION GUARD → what to return, what to wait for, HARD STOP if applicable
```

---

## 10. Primary Demo Script (Persona 1 — Alex 20001)

| Turn | User says |
|------|-----------|
| 1 | "My account is suspended because my card expired and AutoPay failed. Before I pay, I need you to confirm that my recent projects weren't wiped. If my data is safe, I want to pay with my new Visa to get it restored right away and waive the $25 late fee. Also upgrade me to Premium. Account 20001." |
| 2 | "OK, that's a relief. Go ahead and restore it." ← consent, card on file |
| 3 | "Yes, upgrade to Premium." ← plan upgrade confirm |

**Expected flow:**
- T1: auth → Alex, Professional, SUSPENDED, card ending 4242
- T2: 5 days suspended → data SAFE, 12 projects intact
- Card security: "new Visa" → HARD STOP → offer card on file (4242)
- T3: pay $79 → balance cleared
- T4: waiver check → PASS (9mo > 6, autopay ON, no prior waiver) → $0 fee
- T5: restore → ACTIVE
- T6: upgrade to Premium → next billing cycle
- T8: receipt sent

---

## 11. Data Reset

```bash
py pay_restore_demo/z_reset_world.py
```
