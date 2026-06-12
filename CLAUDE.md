# Plan: Pay Restore Demo — New Independent Multi-Agent Project

## Context
Building a second multi-agent ADK demo using metro_city_demo as the architectural template.
The new demo is SaaS-neutral (no telecom). The trigger use case is a suspended account restore flow driven by this customer utterance:

> "Our team account is suspended — our payment method expired and AutoPay failed. Before I pay, I need you to quickly confirm that our recent projects weren't wiped during the suspension. If our data is safe, I want to pay with our new Visa to get it restored right away and waive any late fees. Also, since our team is expanding, I need to upgrade to the Business plan for the next 3 months."

This utterance contains 6 intents: suspension check, data safety, new card collection, payment, fee waiver, and plan upgrade. The demo showcases the same 3-tier architecture, guardrail patterns, and evaluation-driven development methodology as metro_city — but in a new SaaS world.

---

## 1. Project Identity

| Field | Value |
|---|---|
| **Project name** | pay_restore_demo |
| **Product name** | TBD (generic SaaS — not named yet) |
| **Domain** | Cloud SaaS — project management / team collaboration |
| **Folder** | `c:\Muru_Workspace\pay_restore_demo` |
| **DB file** | `pay_restore.db` |
| **Reset script** | `z_reset_world.py` |
| **Run from** | `c:\Muru_Workspace` (parent — same pattern as metro_city) |

---

## 2. World Design — Plans (4 tiers, B2B — Individual to Enterprise)

| plan_id | plan_name | Price/mo | Max Users | Storage | Per User | Late Fee |
|---------|-----------|----------|-----------|---------|----------|----------|
| P001 | Individual | $10 | 1 | 10 GB | $10.00 | $10 |
| P002 | Team | $49 | 10 | 100 GB | $4.90 | $25 |
| P003 | Business | $129 | 30 | 500 GB | $4.30 | $50 |
| P004 | Enterprise | $399 | 100 | 2 TB | $3.99 | $100 |

---

## 3. Database Schema (2 tables — lean)

```sql
CREATE TABLE plan_catalog (
    plan_id       TEXT PRIMARY KEY,
    plan_name     TEXT,
    monthly_price REAL,
    max_users     INTEGER,
    storage_gb    INTEGER,
    late_fee      REAL
);

CREATE TABLE customer_accounts (
    account_id        INTEGER PRIMARY KEY,   -- 5-digit: 20001–20013
    first_name        TEXT,
    company_name      TEXT,
    plan_name         TEXT,                  -- FK to plan_catalog.plan_name
    tenure_months     REAL,
    autopay_active    INTEGER,               -- 1=True, 0=False (SQLite bool)
    waivers_used_12m  INTEGER,               -- 1=True, 0=False
    pending_balance   REAL,
    status            TEXT,                  -- "ACTIVE" | "SUSPENDED" | "CANCELED"
    email             TEXT,
    card_last4        TEXT,                  -- last 4 digits of card on file (NULL if none)
    card_expired      INTEGER,               -- 1=expired, 0=valid (SQLite bool)
    suspension_date   TEXT,                  -- "YYYY-MM-DD" or NULL
    last_waiver_date  TEXT,                  -- "YYYY-MM-DD" or NULL
    seat_count        INTEGER,               -- active seats in use
    project_count     INTEGER,               -- number of active projects (for data check)
    data_retention_days INTEGER,             -- days data kept post-suspension (always 30)
    downgrade_date    TEXT                   -- "YYYY-MM-DD" or NULL (NULL = permanent plan)
);
```

---

## 4. Demo Accounts (10 active/suspended + 3 canceled)

### Group A — Active / Suspended (20001–20010)

**Table 1 — Identity & Plan**

*(exp) = expired card. Suspended+autopay ON accounts have expired cards (AutoPay tried and failed). Suspended+autopay OFF accounts have valid cards (never charged — customer just missed payment).*

| ID | Name | Company | Email | Card | Card Expired | Plan | Tenure (mo) | Autopay | Balance | Status | Seats | Projects |
|----|------|---------|-------|------|--------------|------|-------------|---------|---------|--------|-------|----------|
| 20001 | Alex | Wavefront | alex@wavefront.io | 4242 (exp) | 1 | Team | 9.0 | ON | $49 | SUSPENDED | 8 | 12 |
| 20002 | Jordan | Sprinto | jordan@sprinto.io | 8831 | 0 | Team | 2.0 | OFF | $49 | SUSPENDED | 2 | 3 |
| 20003 | Sam | Arclight | sam@arclight.io | 5517 (exp) | 1 | Business | 14.0 | ON | $129 | SUSPENDED | 20 | 28 |
| 20004 | Riley | Nomad Labs | riley@nomadlabs.io | 2290 (exp) | 1 | Individual | 7.0 | ON | $10 | SUSPENDED | 1 | 5 |
| 20005 | Morgan | Crestline | morgan@crestline.io | 6644 | 0 | Team | 18.0 | OFF | $49 | SUSPENDED | 7 | 11 |
| 20006 | Casey | Driftwood | casey@driftwood.io | 3311 | 0 | Team | 8.0 | ON | $0 | ACTIVE | 5 | 10 |
| 20007 | Drew | Lumen Co | drew@lumeco.io | 7799 | 0 | Business | 16.0 | ON | $0 | ACTIVE | 25 | 20 |
| 20008 | Quinn | Pathfinder | quinn@pathfinder.io | 1188 | 0 | Business | 24.0 | ON | $0 | ACTIVE | 5 | 22 |
| 20009 | Jamie | Redpine | jamie@redpine.io | 9955 (exp) | 1 | Business | 6.0 | ON | $129 | SUSPENDED | 12 | 18 |
| 20010 | Avery | Stratos | avery@stratos.io | 3388 (exp) | 1 | Enterprise | 30.0 | ON | $399 | SUSPENDED | 45 | 35 |

**Table 2 — Suspension & Waiver History** *(data_retention_days = 30 for all accounts)*

> Suspension dates are stored as offsets. `z_reset_world.py` computes `today - N days` at runtime
> so days_suspended is always correct regardless of when the demo is run.

| ID | Suspension Date | Susp. Days | Last Waiver Date | Prev Waiver (12mo) | Waiver Result | Archetype |
|----|----------------|------------|-----------------|-------------------|---------------|-----------|
| 20001 | today - 5d | 5 | NULL | 0 | PASS | Primary demo — data safe, waiver PASS, upgrade to Business |
| 20002 | today - 5d | 5 | NULL | 0 | FAIL Rule A | New customer — 2mo account age < 6mo threshold |
| 20003 | today - 35d | 35 | NULL | 0 | PASS | Data AT RISK — 35 days exceeds 30-day retention window |
| 20004 | today - 10d | 10 | today - 90d | 1 | FAIL Rule C | Prior waiver used 3 months ago — Rule A & B pass, Rule C blocks waiver |
| 20005 | today - 3d | 3 | NULL | 0 | FAIL Rule B | Long tenure but autopay OFF |
| 20006 | NULL | — | NULL | 0 | PASS | Active — standalone upgrade demo |
| 20007 | NULL | — | NULL | 0 | PASS | Active — downgrade to Team blocked (25 seats > 10 max) → escalation |
| 20008 | NULL | — | NULL | 0 | PASS | Active — clean downgrade to Team (5 seats within 10-seat limit) |
| 20009 | today - 20d | 20 | NULL | 0 | FAIL Rule A | Boundary fail — 6.0mo is not > 6mo |
| 20010 | today - 8d | 8 | NULL | 0 | PASS | Top tier (Enterprise), perfect restore |

### Group B — Canceled (20011–20013)

**Table 1 — Identity & Plan**

| ID | Name | Company | Email | Card | Card Expired | Plan | Tenure (mo) | Autopay | Balance | Status | Seats | Projects |
|----|------|---------|-------|------|--------------|------|-------------|---------|---------|--------|-------|----------|
| 20011 | Parker | Helix Systems | parker@helixsystems.io | 4411 | 0 | Team | 1.5 | OFF | $0 | CANCELED | 2 | 2 |
| 20012 | Taylor | Brightpath | taylor@brightpath.io | 5522 | 0 | Team | 1.5 | OFF | $0 | CANCELED | 1 | 1 |
| 20013 | Reese | Foundry Labs | reese@foundrylabs.io | 6633 | 0 | Team | 1.5 | OFF | $0 | CANCELED | 2 | 2 |

**Table 2 — Suspension & Waiver History** *(data_retention_days = 30 for all accounts)*

| ID | Suspension Date | Susp. Days | Last Waiver Date | Prev Waiver (12mo) | Waiver Result | Archetype |
|----|----------------|------------|-----------------|-------------------|---------------|-----------|
| 20011 | NULL | — | NULL | 0 | N/A | Churned — win-back demo |
| 20012 | NULL | — | NULL | 0 | N/A | Churned — win-back demo |
| 20013 | NULL | — | NULL | 0 | N/A | Churned — win-back demo |

---

## 5. Agent Architecture (3-tier — mirrors metro_city)

```
root_agent              (agent.py)                   gemini-2.5-flash      ← Uber
  +-- T1_GetAccount        (direct tool: auth)
  +-- DA1_AccountAgent     (DA1_Account_Agent.py)    gemini-2.5-flash      ← upgraded (see note)
  +-- DA2_BillingAgent     (DA2_Billing_Agent.py)    gemini-2.5-flash      ← upgraded (see note)
  +-- DA4_PlanAgent        (DA4_Plan_Agent.py)       gemini-2.5-flash-lite ← Shared Squad
  +-- SA1_RestoreSupervisor (SA1_Restore_Supervisor.py) gemini-2.5-flash   ← Supervisor
        +-- DA1_AccountAgent    (data safety check)            via AgentTool
        +-- DA2_BillingAgent    (payment, fee waiver)          via AgentTool
        +-- DA3_RestoreAgent    (DA3_Restore_Agent.py)         gemini-2.5-flash ← Squad
              +-- T5_RestoreAccount
              +-- T8_SendReceipt
        +-- DA4_PlanAgent       (plan upgrade/downgrade)       via AgentTool ← Shared
              +-- T9_ValidatePlanChange
              +-- T6_ChangePlan
              +-- T8_SendReceipt
```

> **Model note — gemini-2.0-flash deprecated:** All agents migrated to gemini-2.5-flash family.
> DA1 and DA2 were originally gemini-2.5-flash-lite but upgraded to gemini-2.5-flash due to the
> **Part(text=None) AgentTool bug**: when SA1 calls DA1 and DA2 in parallel via AgentTool,
> flash-lite silently drops its response (returns empty string). flash does not exhibit this bug.
> DA4 is not called in parallel with other DAs from SA1, so flash-lite is safe there.

| Tier | Agent | Model | Responsibility |
|---|---|---|---|
| Uber | root_agent | gemini-2.5-flash | Auth, input safety, routing |
| Supervisor | SA1_RestoreSupervisor | gemini-2.5-flash | 7-state restore state machine. No direct tools. |
| Domain | DA1_AccountAgent | gemini-2.5-flash | Account status, data retention check |
| Domain | DA2_BillingAgent | gemini-2.5-flash | Payment, balance, fee waiver |
| Squad | DA3_RestoreAgent | gemini-2.5-flash | Execute account restore + receipt only |
| Squad (Shared) | DA4_PlanAgent | gemini-2.5-flash-lite | Plan upgrade/downgrade + receipt. Called by root_agent (active accounts) and SA1 (post-restore). T6 lives here only. |

---

## 6. Tool Reference (T1–T9)

| Tool | File | Signature | Purpose |
|------|------|-----------|---------|
| T1 | T1_GetAccount.py | (conn, account_id) | Auth: returns first_name, plan, status, tenure_months, card_last4, card_expired, suspension_date, project_count |
| T2 | T2_CheckDataRetention.py | (conn, account_id) | Calculates days_suspended. Returns data_safe (True if ≤ 30 days), days_suspended, project_count. If data_safe=False, SA1 must issue a soft stop and await explicit customer choice before proceeding. |
| T3 | T3_ProcessPayment.py | (conn, account_id, new_card_last4=None) | Pays full pending_balance. If new_card_last4 provided, updates card_last4 + sets card_expired=0 before charging. Returns amount_charged, card_last4_used. |
| T4 | T4_CheckFeeWaiver.py | (conn, account_id) | 3-rule waiver: tenure > 6mo, autopay=1, no prior waiver in 12mo. Looks up plan_catalog for late_fee. Returns waiver_granted, late_fee_amount, reason |
| T5 | T5_RestoreAccount.py | (conn, account_id) | Sets status=ACTIVE, clears suspension_date, resets billing cycle |
| T6 | T6_ChangePlan.py | (conn, account_id, new_plan_name, duration_months=None) | Updates plan_name in DB. Effective next billing cycle. If duration_months provided, sets downgrade_date = today + (duration_months × 30) days. If None, downgrade_date = NULL (permanent). Called only after T9 clears eligibility. |
| T7 | T7_GetBalance.py | (conn, account_id) | Read-only. Returns pending_balance |
| T8 | T8_SendReceipt.py | (account_id, action_type, details={}) | Confirmation receipt. Opens own DB conn (same T13 pattern) |
| T9 | T9_ValidatePlanChange.py | (conn, account_id, new_plan_name) | Plan detail fetch + eligibility check. Looks up new plan in plan_catalog (price, max_users, storage_gb). Checks seat_count vs new plan max_users. Returns: eligible, direction (upgrade/downgrade), new_plan details, current_seat_count, seat_count_ok, storage_delta. Gates T6 — if eligible=False, T6 must not be called. |

**DB injection:** functools.partial(fn, conn) on T1–T7 and T9. T8 exception: opens own connection.

---

## 7. Business Rules

### Fee Waiver — 3-Rule Logic (T4) ← SAME AS METRO_CITY
All three must be true for $0 late fee. Any single failure = plan-tier late fee (from plan_catalog).
- **Rule A:** tenure_months > 6
- **Rule B:** autopay_active = 1
- **Rule C:** last_waiver_date is NULL or older than 12 months

T4 looks up the customer's plan in plan_catalog to return the correct late fee amount.
Waiver result: either $0 (all rules pass) or the plan's late_fee value + reason for failure.

**T4 reason string format (customer-facing, not internal):**
- PASS: `"you've been with us for N months, had AutoPay enabled, and haven't used a waiver in the past 12 months"`
- FAIL Rule A: `"your account is N months old, which does not meet the 6-month minimum"`
- FAIL Rule B: `"AutoPay was not enabled on your account"`
- FAIL Rule C: `"a waiver was applied N days ago, within the 12-month window"`

DA2 wraps the T4 reason into a complete customer-ready sentence and returns only that sentence:
- PASS:  `"Your late fee has been waived — [T4 reason]."`
- FAIL:  `"A late fee of $X applies — [T4 reason]."`

SA1 relays DA2's sentence verbatim. root_agent (Layer 3) enriches if the reason is missing.

### Data Retention Rule (T2)
- days_suspended = today − suspension_date
- days_suspended ≤ 30: data SAFE — "All [N] projects are intact."
- days_suspended > 30: data AT RISK — "Some projects may have been archived or purged."

**AT RISK post-restore messaging rule:** After a successful restore on the AT RISK path, the VA must
NOT claim "N projects confirmed intact." Instead use: "We recommend checking your project dashboard
to confirm which projects are accessible — some may have been affected." SA1 passes `DATA_AT_RISK=True`
in the DA3 handoff message; DA3 uses this flag to suppress the intact-projects claim in its return.

### Card Payment Flow
At the payment step, two options are always available: card on file or a new card.

**Logic based on card_expired flag:**
- `card_expired = 0` (valid card on file) → VA offers as default: "Would you like to pay with your card on file ending in [XXXX]?"
  - Customer confirms → T3 charges card on file
  - Customer wants new card instead → collect new card → T3 updates card_last4 + card_expired=0, charges new card
- `card_expired = 1` (expired card on file) → skip "use card on file" offer → go directly to new card collection
  - VA: "Your card on file ending in [XXXX] is expired. Please provide your new card details."
- `card_last4 = NULL` (no card on file) → go directly to new card collection
  - VA: "No payment method on file. Please provide your card details."

**Collecting a new card:**
- Phase 1-4 (adk web): customer types card number as text → agent extracts last 4 digits → passes to T3
- Phase 5b (polished demo): agent sends trigger `__CARD_FORM__` → secure form appears inline in chat stream (not a redirect) → customer enters details → client-side Luhn validation → on valid submit: form hides, "Payment Processed ✓" shown, `{"status": "success", "card_last4": "XXXX"}` returned to agent → agent passes to T3

**T3 updated signature:** `(conn, account_id, new_card_last4=None)`
- If `new_card_last4` provided → update card_last4 + set card_expired=0 in DB, then clear balance
- If None → charge card already on file

### Balance Gate
- pending_balance must be $0 before restore proceeds.

### Consent Gate
- Explicit "Yes" / "Go ahead" required before charging. "I guess" / "maybe" = NOT consent.

### Suspension Gate
- Only SUSPENDED accounts enter the restore flow.
- ACTIVE accounts → billing or upgrade only.
- CANCELED accounts → win-back (route to human sales team).

### No Proration
- Plan upgrades effective next billing cycle. No mid-cycle credits.

### Plan Upgrade / Downgrade Rules (DA4 — T9 → T6 → T8)
DA4 is a 3-step squad. T9 always runs first. T6 is gated on T9's output. T8 closes the chain.

**T9 returns:**
- `eligible`: True / False
- `direction`: "upgrade" or "downgrade"
- `new_plan_name`, `new_monthly_price`, `new_max_users`, `new_storage_gb`
- `current_seat_count`, `seat_count_ok`: True / False
- `storage_delta`: e.g. "500 GB → 100 GB" (downgrade) or "100 GB → 500 GB" (upgrade)

**Upgrade path:** T9 always returns eligible=True. DA4 presents new price + storage to customer → confirmation → T6 → T8.

**Downgrade path:**
- T9 checks `seat_count_ok`. If False → eligible=False → HARD STOP → human escalation. T6 never called.
- If True → DA4 presents storage reduction warning (informational, not blocking) → confirmation → T6 → T8.

**Both directions** require explicit customer confirmation before T6 is called.

**Duration rule:**
- Customer specifies a duration ("for 3 months", "for 6 months", etc.) → T6 called with duration_months set → downgrade_date stored in DB. VA confirms: "Your [plan] upgrade is active for [N] months, reverting on [date]."
- No duration mentioned → T6 called with duration_months=None → permanent plan change. downgrade_date = NULL.
- DA4 extracts duration_months from the customer's request and passes it to T6. T9 is not affected by duration.

### Human Escalation Gate
Any scenario the VA cannot resolve routes to a human agent with a clear handoff message.
The VA never dead-ends — it always hands off gracefully.

| Trigger | VA response | Admin action to resume |
|---------|-------------|------------------------|
| Data AT RISK — customer requests specialist | "I'll connect you with our data recovery team. They can assess what may be recoverable before you decide whether to proceed." | Admin advises customer on data status; customer re-initiates restore if they choose to proceed |
| Seat count exceeds new plan limit | "Your team has [X] active seats, which exceeds the [Plan] plan's [Y]-seat limit. I'll connect you with our support team to deactivate seats before downgrading." | DB: reduce seat_count, customer re-initiates downgrade |
| Customer disputes balance | "Let me get a specialist to review this with you." | DB: adjust pending_balance |
| Account needs manual review | "This account requires verification — routing you to our team now." | Any DB correction |
| Suspended account requests cancellation | "I can help route you to our team to process a cancellation. They'll walk you through the final steps." | Human agent processes cancellation |

- Human escalation is a deliberate design choice, not a fallback — the VA knows its own boundaries.
- Demo admin (human agent) can intervene via direct DB edits, then customer resumes the flow normally.

---

## 8. Restore Flow — SA1_RestoreSupervisor (7 states)

```
STATE 1: Balance Gate       → T7 (check balance). If > $0 → ask consent.
STATE 2: Data Safety Check  → DA1: T2 (days_suspended).
                              If data_safe=True  → report safe, proceed to STATE 3.
                              If data_safe=False → SOFT STOP. Present AT RISK notice + two paths:
                                Path A: "Proceed with restore" → customer acknowledges → SIGNAL C
                                Path B: "Speak with data recovery team" → human escalation, HARD STOP
STATE 3: Card Security      → Check card_expired flag (from T1 in transcript).
                              If card_expired=1: proactively prompt for new card — do NOT offer card on file.
                              If card_expired=0 and customer requests new card: collect new card inline.
                              If card_expired=0 and no new card mentioned: offer card on file as default.
STATE 4: Payment            → DA2: T3 (card + full balance).
STATE 5: Fee Waiver         → DA2: T4 (3-rule check). Report $0 or plan-tier late fee + reason.
STATE 6: Restore            → DA3: T5 (restore account) → T8 (restore receipt).
STATE 7: Plan Change        → DA4: T9 → T6 → T8 (upgrade/downgrade if requested).
                              Skipped entirely if customer did not request a plan change.
```

**HANDOFF SIGNALS (priority order — SA1 scans transcript, fires exactly one per turn):**
- SIGNAL D (highest): Payment consent given → run DA2 payment → DA2 fee check → DA3 restore → DA4 plan change (if requested)
- SIGNAL F: Restore confirmed in transcript AND plan validation presented AND customer confirms plan change → call DA4 execute
- SIGNAL E: Data AT RISK reported AND customer chose human escalation → transfer to data recovery team
- SIGNAL C: Data AT RISK reported AND customer chose to proceed despite risk → acknowledge risk, check card, await consent
- SIGNAL A (lowest): Fresh start → run balance check + data safety check in one turn

**DA3 handoff message format:**
- data_safe=True:  `"restore account [id]. [N] projects, [plan_name] plan, amount paid $[X]."`
- data_safe=False: `"restore account [id]. [N] projects, [plan_name] plan, amount paid $[X]. DATA_AT_RISK=True — do not confirm projects intact."`

---

---

## 9. Coding Patterns — Mandatory (mirror metro_city exactly)

### Yield & Resume (Approach B — Ephemeral State)
- SA1_RestoreSupervisor has NO session state, NO persistent variables.
- root_agent passes the FULL conversation transcript to SA1 on EVERY invocation.
- SA1 reads the transcript and self-determines which state to resume at via HANDOFF SIGNALS.
- Each AgentTool call (DA1, DA2, DA3) gets a fresh InMemorySession — SA1 reconstructs context
  from transcript, not from stored state.
- This is the exact same Approach B used in SA1_Moves_Supervisor in metro_city.

### SA1 HANDOFF SIGNALS (priority order, same pattern as metro_city)
SA1 scans the transcript for evidence of prior steps and fires exactly one signal per turn:
```
SIGNAL D (highest): Payment consent given → execute full chain (pay → fee → restore → plan change)
SIGNAL F:           Restore confirmed + plan validation shown + customer confirms → DA4 execute
SIGNAL E:           Data AT RISK reported + customer chose human escalation → transfer
SIGNAL C:           Data AT RISK reported + customer chose to proceed → check card, await consent
SIGNAL A (lowest):  Fresh start → balance check + data safety in one turn
```
ONE signal fires per turn. HARD STOP after each — never combine steps across signals.

### 3-Layer Guardrail Placement (same as metro_city)
| Layer | Where | What |
|---|---|---|
| **Layer 1 — Input** | root_agent ONLY | PII, prompt injection, toxicity, out-of-scope |
| **Layer 2 — Logic** | Each DA agent | Domain-specific rules (consent gate, card security, balance gate) |
| **Layer 3 — Output** | root_agent ONLY | Variable exposure, contradictions, verbosity |
- DA1, DA2, DA3, SA1: Layer 2 / Global Guardrails ONLY. Never add Layer 1 or Layer 3 to DAs.

### 5-Element State Machine Pattern (each DA agent state)
Every state in every DA follows this structure:
```
ENTRY GUARD    → validate preconditions before acting
THE JOB        → call the tool, do the work
PRE-TOOL GUARD → validate inputs before tool call
POST-TOOL GUARD → validate tool output, ground truth enforcement
TRANSITION GUARD → what to return, what to wait for, HARD STOP if applicable
```

### SA1 ONE-STEP-PER-RESPONSE Rule
- SA1 executes EXACTLY one state machine step per response turn.
- Never combine STATE 2 + STATE 3 into one response, even if both could be answered.
- HARD STOP instructions prevent step merging.
- Same guardrail that fixed the "step merging" bug in metro_city CP4.

### Fee Waiver Ground Truth Rule
- Fee result comes ONLY from T4's tool output text.
- SA1 must NEVER infer "fee waived" from tenure, autopay status, or payment history.
- Clearing the balance does NOT grant the fee waiver — they are completely independent.
- Same rule that fixed the hallucination bug in metro_city SA1.

**Fee waiver relay chain (full path to customer):**
1. T4 returns `reason` as a customer-friendly string (e.g., "you've been with us for 9 months...")
2. DA2 wraps it: returns ONLY `"Your late fee has been waived — [reason]."` or `"A late fee of $X applies — [reason]."`
3. SA1 includes DA2's exact sentence in its SIGNAL D Step 5 restore confirmation — does not paraphrase.
4. root_agent Layer 3: if the reason clause (after em dash) is missing, enriches from SA1 response text.

This chain was engineered after multiple instruction-only attempts failed — the reliable fix was
pushing the customer-ready sentence all the way down to T4/DA2 so SA1 just relays rather than composes.

### DA3_RestoreAgent (Squad Pattern — lean)
- Fire-and-return. Executes T5 (restore) → T8 (receipt) only. No plan change logic.
- T5 must succeed before T8 is called (gate enforced).
- Called by SA1 only. Never by root_agent directly.
- Uses gemini-2.5-flash (NOT flash-lite) — same Part(text=None) risk on multi-tool chains.

**DATA_AT_RISK flag:** SA1 includes `DATA_AT_RISK=True` in the DA3 handoff when T2 found
data_safe=False. DA3 STATE 1 extracts this flag. TRANSITION GUARD branches on it:
- `data_at_risk=False` → return message includes `"[N] projects confirmed intact."`
- `data_at_risk=True`  → return message uses `"Note: data was AT RISK — do not confirm projects intact."` (no count)

### DA4_PlanAgent (Squad + Shared Pattern)
- 3-step fire-and-return: T9 (validate + fetch) → T6 (execute, gated on T9) → T8 (receipt).
- No customer interaction between steps. LLM earns its place via conditional branching on T9 output.
- T9 failure (seat_count_ok=False or plan not found) → HARD STOP. T6 is never called.
- T9 output (new price, storage, direction) feeds both T6 inputs and T8 receipt details.
- DA4 extracts duration_months from the customer request before calling T6. If customer specified
  a duration ("3 months", "6 months", etc.), passes it to T6. Otherwise passes None (permanent).
- Called by root_agent (active account plan changes) AND by SA1 (post-restore, STATE 7).
- T6 and T9 live here only — not in DA3.
- Uses gemini-2.5-flash-lite (DA4 is not called in parallel with other DAs; no Part(text=None) bug).

### DB Tool Injection (functools.partial)
```python
def create_db_tool(fn, conn):
    bound = functools.partial(fn, conn)
    bound.__name__ = fn.__name__
    bound.__doc__  = fn.__doc__
    return FunctionTool(bound)
```
- T8_SendReceipt exception: opens its own `sqlite3.connect("pay_restore.db")` internally.
  Never wrap with create_db_tool.

### SA1 Callbacks (terminal trace — same pattern added in metro_city)
- Add `before_tool_callback` and `after_tool_callback` to SA1_RestoreSupervisor.
- Prints `SA1 → DA1`, `SA1 ← DA1 RSP:...`, `SA1 → DA2`, `SA1 ← DA2 RSP:...`,
  `SA1 → DA3`, `SA1 ← DA3 RSP:...`, `SA1 → DA4`, `SA1 ← DA4 RSP:...` to terminal.
- Surfaces the yield-and-resume coordination visually during demo.

### Tone & Persona (root_agent)
root_agent has a TONE AND PERSONA section before LAYER 1 that shapes all customer-facing responses:
- Lead with empathy before information ("I can see your account is suspended — let me sort this out.")
- Use first name naturally but not on every sentence.
- Deliver good news warmly ("Great news — all 12 projects are intact" not "12 projects confirmed").
- Deliver bad news with care — acknowledge impact before stating outcome.
- Never bullet-point responses to the customer. Use natural flowing sentences.
- Don't over-explain. If customer already confirmed something, don't restate — just move forward.
- Avoid corporate filler: "Please be advised", "Kindly note", "I apologize for any inconvenience."
- Match the customer's energy (stressed/urgent → focused and fast; casual → friendly).

### Card Expiry Acknowledgement (root_agent STATE 1)
After T1 returns on a SUSPENDED account: if `card_expired=True` AND the customer did NOT already
mention a card, payment, or AutoPay issue → add one natural sentence acknowledging the expired
card as the likely suspension cause. Example: "It looks like the card on file ending in 4242 has
expired, which is what caused the payment to fail."
Do NOT add this if the customer already explained the reason — it would feel like you weren't
listening. On the AT RISK path, this gets handled naturally in the Turn 2 card request.

### Receipt Destination
Receipts are always sent to "the customer's email on file." T8 stores to the `receipts` table
and returns an `order_ref` (e.g., `#ORD-2OUHT`). The VA presents this as:
`"A confirmation has been sent to your email on file (#ORD-XXXXX)."`
Never say "sent to you" or give the email address — it may not be current.

---

## 10. Files to Copy from metro_city (and adapt)

| Source | Destination | Changes |
|---|---|---|
| `z_reset_world.py` | `z_reset_world.py` | New tables (plan_catalog, customer_accounts), new personas, pay_restore.db. All suspension_dates computed dynamically as `today - N days` using `datetime.date.today()` — never hardcoded. |
| `Agent Sim/test_conversation.py` | `Agent Sim/test_conversation.py` | New TURNS, new account IDs, pay_restore.db verification |
| `__init__.py` | `__init__.py` | Update docstring (pay_restore world, new agent names) |
| `T5a_GetBalance.py` | `T7_GetBalance.py` | Rename, update docstring only |
| `T8_CheckFeeWaiver.py` | `T4_CheckFeeWaiver.py` | Change rules: tenure > 6mo (not 3yr), same 3-rule structure |
| `T5_PayBill.py` | `T3_ProcessPayment.py` | Adapt: remove partial payment, always full balance |
| `T13_SendConfirmationReceipt.py` | `T8_SendReceipt.py` | Adapt: new action types (RESTORE, UPGRADE, PAYMENT) |

**Build from scratch (no direct equivalent):**
- `T1_GetAccount.py` — new fields (suspension_date, card_last4, project_count, tenure_months)
- `T2_CheckDataRetention.py` — new: date arithmetic on suspension_date
- `T5_RestoreAccount.py` — new: SET status=ACTIVE, clear suspension_date
- `T6_ChangePlan.py` — new: UPDATE plan_name (called only after T9 clears eligibility)
- `T9_ValidatePlanChange.py` — new: joins customer_accounts + plan_catalog, checks seat_count, returns full plan detail payload for T6 and T8
- All agent files (DA1, DA2, DA3, DA4, SA1, agent.py)
- `CLAUDE.md` — new world, rules, personas

---

## 10. Step-by-Step Setup

### Phase 0 — You do (manual, one-time)
Run these terminal commands:
```powershell
mkdir c:\Muru_Workspace\pay_restore_demo
mkdir "c:\Muru_Workspace\pay_restore_demo\Agent Sim"
copy c:\Muru_Workspace\metro_city_demo\.env c:\Muru_Workspace\pay_restore_demo\.env
cd c:\Muru_Workspace\pay_restore_demo
git init
```
Then start a **new Claude thread** (see prompt below)

### Phase 1 — New Claude thread: Build the world
6. Claude writes `CLAUDE.md` (from this plan)
7. Claude writes `__init__.py`
8. Claude writes `z_reset_world.py` → you run it → DB verified

### Phase 2 — New Claude thread: Build tools
9. T1_GetAccount.py (new)
10. T2_CheckDataRetention.py (new)
11. T3_ProcessPayment.py (adapt T5_PayBill)
12. T4_CheckFeeWaiver.py (adapt T8_CheckFeeWaiver — change 3yr → 6mo)
13. T5_RestoreAccount.py (new)
14. T6_ChangePlan.py (new)
15. T7_GetBalance.py (adapt T5a_GetBalance)
16. T8_SendReceipt.py (adapt T13_SendConfirmationReceipt)
17. T9_ValidatePlanChange.py (new — joins customer_accounts + plan_catalog, seat check, returns plan detail payload)
18. Test each tool in isolation via `if __name__ == "__main__"` block

### Phase 3 — New Claude thread: Build agents
18. DA1_Account_Agent.py (T2 only — T1 runs in root_agent, not duplicated here)
19. DA2_Billing_Agent.py (T3, T4, T7)
20. DA3_Restore_Agent.py — Squad lean (T5, T8)
21. DA4_Plan_Agent.py — Squad + Shared (T9, T6, T8)
22. SA1_Restore_Supervisor.py — 7-state machine, Approach B, no direct tools
23. agent.py — Uber: T1 direct + DA1/DA2/DA4/SA1 as AgentTools

### Phase 4 — New Claude thread: Validate
24. Write `Agent Sim/test_conversation.py`
25. Run Persona 1 (Alex 20001) — primary demo, happy path
26. Run Persona 2 (Jordan 20002) — waiver FAIL
27. Run Persona 3 (Sam 20003) — data AT RISK
28. Fix issues, re-run until all pass
29. Git commit

### Phase 5a — Demo (adk web)
30. `py z_reset_world.py` (from parent c:\Muru_Workspace)
31. `adk web` (from parent c:\Muru_Workspace)
32. Open http://127.0.0.1:8000
33. Card input during demo: type card number as text in adk web OR use card on file

### Phase 5b — Secure Card UI (polish layer)
Build a custom HTML chat page that replaces adk web for the polished demo.

**What to build:**
- Single HTML file with chat UI + card form component
- Connects to the same ADK backend API endpoints that adk web uses
- Agent sends trigger token `__CARD_FORM__` → page renders secure card form
- Card form: masked input (`**** **** **** 1234`), expiry, CVV
- Client-side validation before submit: Luhn algorithm (16-digit mod-10), expiry > today, CVV length
- On valid submit: hide form, show "Payment Processed ✓" bubble, send `{"status": "success", "card_last4": "XXXX"}` back to agent
- Agent never sees raw card data

**Validation rules (client-side JS, ~50 lines):**
- Number: 16 digits, passes Luhn algorithm
- Expiry: MM/YY format, > current month/year
- CVV: 3 digits (Visa/Mastercard)

**Demo impact:** Card security guardrail changes from HARD STOP + redirect to: "Please use the secure card form below" → form appears → customer fills in → success payload returned → agent proceeds.

---

## 11. When to Switch to a New Claude Thread

**Switch after:** CLAUDE.md is finalized and agreed upon (Phase 0 complete + CLAUDE.md written).
The new thread gets the CLAUDE.md as ground truth and metro_city as reference. No more work needed
in this thread.

---

## 12. New Thread Starter Prompt

Paste this verbatim to start the new Claude thread:

---

```
We are building a new multi-agent Google ADK demo called Pay_Restore SaaS Demo.

Reference project (same architecture patterns): c:\Muru_Workspace\metro_city_demo
New project folder: c:\Muru_Workspace\pay_restore_demo (folder already created, .env copied)
CLAUDE.md is at: c:\Muru_Workspace\pay_restore_demo\CLAUDE.md

Ground rules:
- Follow the same 3-tier architecture, tool injection pattern, and Approach B state reconstruction as metro_city.
- Use gemini-2.5-flash for root_agent, SA1_RestoreSupervisor, DA1_AccountAgent, DA2_BillingAgent, DA3_RestoreAgent.
- Use gemini-2.5-flash-lite for DA4_PlanAgent only.
- DO NOT use gemini-2.0-flash or gemini-2.5-flash-lite for DA1/DA2 — flash-lite drops AgentTool responses
  when called in parallel from SA1 (Part(text=None) bug).
- Run all commands from c:\Muru_Workspace (parent directory), not from inside pay_restore_demo.
- DB file is pay_restore.db (not metro_city.db).

Start with Phase 1:
1. Read CLAUDE.md fully.
2. Write __init__.py.
3. Write z_reset_world.py (2 tables: plan_catalog + customer_accounts, 4 plans, 13 accounts).
4. Run it and show me the output.
```

---

## 13. Phase 4 Validation — Issues Found & Fixed

Issues discovered during Persona 1–3 test runs and their resolutions.

| Issue | Root Cause | Fix Applied |
|-------|-----------|-------------|
| `gemini-2.0-flash 404 NOT_FOUND` | Model deprecated | All 6 agent files updated to gemini-2.5-flash/flash-lite |
| DA1 returns empty response | gemini-2.5-flash-lite drops AgentTool response in parallel call from SA1 (Part(text=None) bug) | DA1 upgraded to gemini-2.5-flash |
| DA2 fee waiver returns empty | Same Part(text=None) bug | DA2 upgraded to gemini-2.5-flash |
| Fee waiver reason dropped | SA1 consistently paraphrased "waived" without the reason despite multiple instruction attempts | Push customer-ready sentence to T4→DA2; SA1 relays verbatim; Layer 3 enriches if missing |
| "0 projects confirmed intact" | DA1 was returning empty; SA1 didn't know project_count | Fixed by fixing DA1 model |
| "All 28 projects intact" on AT RISK path | SA1 used "projects intact" language regardless of data risk status | SA1 passes DATA_AT_RISK=True to DA3; DA3 suppresses intact claim; SA1 uses dashboard-check language |
| Transient ReadError (httpcore/httpx) | Network API timeout — not a code bug | Retry the run; DB is always unchanged after these |

## 14. Primary Demo Script (Persona 1 — Alex 20001)

| Turn | User says |
|------|-----------|
| 1 | "Our team account is suspended — our payment method expired and AutoPay failed. Before we pay, I need you to confirm that our recent projects weren't wiped. If our data is safe, I want to pay with our new Visa to get it restored right away and waive any late fees. Also upgrade us to the Business plan. Account 20001." |
| 2 | "The new card number is 4111 1111 1111 4321. Go ahead and restore it." ← new card + consent |
| 3 | "Yes, upgrade to Business." ← plan upgrade confirm |

**Expected flow:**
- T1: auth → Alex, Team plan, SUSPENDED, card ending 4242 (expired)
- T2: 5 days suspended → data SAFE, 12 projects intact
- Card payment flow: card_expired=1 → VA skips "use card on file" offer → prompts for new card
  - "Your card ending in 4242 is expired. Please provide your new card details to proceed."
- Turn 2: customer provides new card → agent extracts last 4 digits (4321)
- T3: called with new_card_last4="4321" → updates card on file, clears balance ($49) → amount_charged=$49
- T4: waiver check → PASS (9mo > 6mo, autopay ON, no prior waiver in 12mo) → $0 late fee (Team plan fee waived)
- T5: restore → ACTIVE
- DA4 T9: validate Business plan upgrade → eligible=True, direction=upgrade, 8 seats < 30 max → seat_count_ok=True
- T6: upgrade to Business, duration_months=3 → downgrade_date = today + 90 days
- T8: receipt sent — confirms upgrade + auto-revert date
