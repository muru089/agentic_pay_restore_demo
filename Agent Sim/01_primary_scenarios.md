# Orbit Demo — Primary Personas (13 Accounts)

All personas run against `agents_tools_db/orbit.db`.
Reset the DB before each run: `py pay_restore_demo/agents_tools_db/z_reset_world.py` (from `c:\Muru_Workspace`).
Batch runner: `python "pay_restore_demo/Agent Sim/run_personas.py"` (from `c:\Muru_Workspace`).

---

# Persona 1: The "Perfect" Restore (Primary Demo Script)
**Account ID:** 20001 (Alex, Wavefront)
**Turn Count:** 3 turns

**Account Snapshot:**
- Status: SUSPENDED ⚠️ (5 days — data SAFE, ≤ 30 days)
- Plan: Team ($49/mo)
- Tenure: 9.0 months ✅ (Rule A PASS — needs > 6mo)
- AutoPay: ON ✅ (Rule B PASS)
- Prior Waiver (12mo): None ✅ (Rule C PASS)
- Card on file: 4242 ❌ EXPIRED
- Pending Balance: $49.00

**Waiver Outcome:** GRANTED — all 3 rules pass. $0 late fee.

**Plan Change:** Business upgrade requested for 3 months → DA4 executes → auto-reverts after 90 days.

**Starting Utterance:**
> "Our team account is suspended — our payment method expired and AutoPay failed. Before we pay, I need you to confirm that our recent projects weren't wiped. If our data is safe, I want to pay with our new Visa to get it restored right away and waive any late fees. Also upgrade us to the Business plan for the next 3 months. Account 20001."

**Full Prompt Script:**
- Turn 1: `Our team account is suspended -- our payment method expired and AutoPay failed. Before we pay, I need you to confirm that our recent projects weren't wiped. If our data is safe, I want to pay with our new Visa to get it restored right away and waive any late fees. Also upgrade us to the Business plan for the next 3 months. Account 20001.`
- Turn 2: `The new card number is 4111 1111 1111 4321. Go ahead and restore it.`
- Turn 3: `Yes, upgrade to Business.`

**Expected Tool Chain:**
- Turn 1: T1 (auth) → T0_Get → DA1 (T2 data check, 5d, 12 projects SAFE) + DA2 (T7 balance, T4 waiver preview) in parallel → T0_Set. Card expired → VA announces card 4242 expired, prompts for new card.
- Turn 2: New card provided (4321) → DA2 (T3 payment, $49 to 4321) + DA3 (T5 restore) + DA4 MODE V (T9 validate Business upgrade) in parallel → T0_Set.
- Turn 3: Confirm → DA4 MODE E (T6 Business 3mo + T8 receipt) → T0_Set.

**What to Watch For:**
- Turn 1: Agent opens with empathy, acknowledges the expired card as the likely cause. "It looks like the card ending in 4242 has expired, which is what caused the payment to fail."
- 12 projects confirmed safe ("All 12 projects are intact" — NOT dashboard language since data is safe).
- Waiver sentence includes full reason: "Your late fee has been waived — you've been with us for 9 months, had AutoPay enabled, and haven't used a waiver in the past 12 months."
- Turn 2: `__CARD_FORM__` emitted in Turn 1 reply (adk web: customer types 16-digit number). T3 called with `new_card_last4="4321"` — updates card on file, clears $49.
- Turn 3: DA4 confirms "Your Business upgrade is active for 3 months, reverting on [date]." Receipt sent.
- Best opener for any live demo — cleanest 3-turn happy path showing all 6 intents resolved.

---------------------------------------

# Persona 2: The "New Customer" (Waiver FAIL Rule A)
**Account ID:** 20002 (Jordan, Sprinto)
**Turn Count:** 2 turns

**Account Snapshot:**
- Status: SUSPENDED ⚠️ (5 days — data SAFE)
- Plan: Team ($49/mo)
- Tenure: 2.0 months ❌ (Rule A FAIL — needs > 6mo)
- AutoPay: OFF ❌ (Rule B FAIL)
- Prior Waiver (12mo): None ✅ (Rule C PASS)
- Card on file: 8831 ✅ VALID
- Pending Balance: $49.00

**Waiver Outcome:** DENIED — Rule A fails (tenure too short; autopay also off, but Rule A is cited as the primary failure). $25 late fee (Team plan).

**Payment Note:** T3_ProcessPayment charges the pending_balance only ($49). The $25 late fee is disclosed to the customer and included in DA2's response text, but it is NOT added to T3's charge. The customer sees the fee explained and agrees to it — but the card is charged $49, not $74. This is by design: the late fee is an informational penalty disclosure, not a separate line item collected via T3.

**Starting Utterance:**
> "Our team account is suspended and I need to get it restored. Account 20002."

**Full Prompt Script:**
- Turn 1: `Our team account is suspended and I need to get it restored. Account 20002.`
- Turn 2: `Yes, charge my card on file and restore it.`

**Expected Tool Chain:**
- Turn 1: T1 → T0_Get → DA1 (T2) + DA2 (T7 + T4 waiver preview) in parallel → T0_Set. Card valid → VA offers "Would you like to pay with your card ending in 8831?"
- Turn 2: Consent + card on file confirmed → DA2 (T3: $74 charged to 8831) + DA3 (T5 restore) in parallel → T0_Set.

**What to Watch For:**
- Waiver denial reason is specific: "your account is 2 months old, which does not meet the 6-month minimum." Agent does NOT just say "you don't qualify."
- Card on file is valid → agent offers it as default (no expired card prompt).
- Fee relayed: "A late fee of $25 applies — your account is 2 months old, which does not meet the 6-month minimum."
- Restore completes normally despite the fee.
- Good contrast demo to run immediately after Persona 1 to show waiver logic branching.

---------------------------------------

# Persona 3: The "Data AT RISK" Customer
**Account ID:** 20003 (Sam, Arclight)
**Turn Count:** 3 turns

**Account Snapshot:**
- Status: SUSPENDED ⚠️ (35 days — data AT RISK ❌ exceeds 30-day retention window)
- Plan: Business ($129/mo)
- Tenure: 14.0 months ✅ (Rule A PASS)
- AutoPay: ON ✅ (Rule B PASS)
- Prior Waiver (12mo): None ✅ (Rule C PASS)
- Card on file: 5517 ❌ EXPIRED
- Pending Balance: $129.00

**Waiver Outcome:** GRANTED (all 3 rules pass) — but waiver result is secondary; data risk is the lead concern.

**Data Warning:** 35 days suspended > 30-day retention threshold → "Some projects may have been archived or purged."

**Starting Utterance:**
> "Our business account is suspended and I need to restore it. Account 20003."

**Full Prompt Script:**
- Turn 1: `Our business account is suspended and I need to restore it. Account 20003.`
- Turn 2: `I understand the risk. I want to proceed with the restore.`
- Turn 3: `New card number is 4111 1111 1111 9988. Yes, go ahead.`

**Expected Tool Chain:**
- Turn 1: T1 → T0_Get → DA1 (T2: 35d, data_safe=False) + DA2 (T7 + T4 preview) in parallel → T0_Set. AT RISK disclosed → HARD STOP with two paths (proceed or escalate to data recovery team).
- Turn 2: "I understand the risk" → ROW 5 fires → T0_Set(at_risk_proceeding=1). Card expired → VA prompts for new card. HARD STOP (does NOT call DA2/DA3 here — no card yet).
- Turn 3: New card (9988) + consent → DA2 (T3: $129 to 9988) + DA3 (T5 restore, DATA_AT_RISK=True) in parallel → T0_Set.

**What to Watch For:**
- Turn 1: HARD STOP after AT RISK warning. Two paths presented clearly: (A) proceed and restore, (B) connect to data recovery team.
- Turn 2: "I understand the risk" is data-risk acknowledgement ONLY — not payment consent. Agent sets `at_risk_proceeding=1` and then asks for new card. Does NOT call DA2 or DA3 yet. (This was a critical bug that was fixed — see ROW 5/6 card gate.)
- Turn 3: Restore succeeds. Agent does NOT say "28 projects confirmed intact." Uses dashboard language: "We recommend checking your project dashboard to confirm which projects are accessible — some may have been affected."
- Waiver: "Your late fee has been waived — you've been with us for 14 months..." (stated even on AT RISK path).
- This persona validates the ROW 5 CRITICAL note and ROW 6 CARD CHECK FIRST gate working together correctly.

---------------------------------------

# Persona 4: The "Prior Waiver" Customer (Waiver FAIL Rule C)
**Account ID:** 20004 (Riley, Nomad Labs)
**Turn Count:** 3 turns (or 2 — agent may combine card + consent)

**Account Snapshot:**
- Status: SUSPENDED ⚠️ (10 days — data SAFE)
- Plan: Individual ($10/mo)
- Tenure: 7.0 months ✅ (Rule A PASS — 7 > 6)
- AutoPay: ON ✅ (Rule B PASS)
- Prior Waiver (12mo): YES, 90 days ago ❌ (Rule C FAIL)
- Card on file: 2290 ❌ EXPIRED
- Pending Balance: $10.00

**Waiver Outcome:** DENIED — Rule C fails (waiver used 90 days ago, within the 12-month window). Rules A and B both pass — the denial is solely from waiver history. $10 late fee (Individual plan).

**Payment Note:** T3 charges the pending_balance only ($10). The $10 late fee is disclosed to the customer but is NOT added to the T3 charge — the card is charged $10, not $20. See P02 note for the full explanation of this design.

**Starting Utterance:**
> "I need to restore my account. Account 20004."

**Full Prompt Script:**
- Turn 1: `I need to restore my account. Account 20004.`
- Turn 2: `New card is 4111 1111 1111 5678.`
- Turn 3: `Yes, go ahead and charge it.`

**Expected Tool Chain:**
- Turn 1: T1 → T0_Get → DA1 (T2: 10d, 5 projects SAFE) + DA2 (T7 + T4 waiver) in parallel → T0_Set. Card expired → prompts for new card.
- Turn 2 / Turn 3: New card (5678) + consent → DA2 (T3: $20 to 5678) + DA3 (T5 restore) in parallel → T0_Set.

**What to Watch For:**
- Tenure (7 months) and AutoPay both pass — the denial hinges entirely on Rule C.
- Waiver denial message: "A late fee of $10 applies — a waiver was applied 90 days ago, within the 12-month window."
- Individual plan late fee is $10 (not $25 Team fee) — T4 looks up the correct plan tier from plan_catalog.
- Agent may process payment + restore on Turn 2 if card number implies consent (behaviorally acceptable). Turn 3 "Yes, go ahead" then becomes a no-op handled gracefully.
- Good demo of the nuanced Rule C: even loyal autopay customers who used a waiver recently don't qualify.

---------------------------------------

# Persona 5: The "Long-Timer No-AutoPay" Customer (Waiver FAIL Rule B)
**Account ID:** 20005 (Morgan, Crestline)
**Turn Count:** 2 turns

**Account Snapshot:**
- Status: SUSPENDED ⚠️ (3 days — data SAFE)
- Plan: Team ($49/mo)
- Tenure: 18.0 months ✅ (Rule A PASS — 18 > 6)
- AutoPay: OFF ❌ (Rule B FAIL)
- Prior Waiver (12mo): None ✅ (Rule C PASS)
- Card on file: 6644 ✅ VALID
- Pending Balance: $49.00

**Waiver Outcome:** DENIED — Rule B fails (AutoPay was not enabled). Long tenure (18 months) does not override. $25 late fee (Team plan).

**Total Charged:** $49 + $25 = $74.

**Starting Utterance:**
> "This is account 20005. We've been suspended for a few days — I need to get back up. Can you waive the fee? I've been a customer for a long time."

**Full Prompt Script:**
- Turn 1: `This is account 20005. We've been suspended for a few days -- I need to get back up. Can you waive the fee? I've been a customer for a long time.`
- Turn 2: `Use the card on file. Yes, restore it.`

**Expected Tool Chain:**
- Turn 1: T1 → T0_Get → DA1 (T2: 3d SAFE) + DA2 (T7 + T4 waiver) in parallel → T0_Set. Card valid → offer card on file.
- Turn 2: Consent + card on file → DA2 (T3: $74 to 6644) + DA3 (T5 restore) in parallel → T0_Set.

**What to Watch For:**
- Long tenure (18 months) is acknowledged warmly but does not override Rule B.
- Denial message: "A late fee of $25 applies — AutoPay was not enabled on your account."
- Agent does NOT cave to "I've been a customer for a long time" — waiver logic is rules-based, not negotiable.
- Card on file is valid → agent offers it as default: "Would you like to pay with the card on file ending in 6644?"
- Good demo showing the single-rule failure path and handling customer pushback gracefully.

---------------------------------------

# Persona 6: The "Active Upgrader" (ACTIVE Account, Plan Change Only)
**Account ID:** 20006 (Casey, Driftwood)
**Turn Count:** 3 turns

**Account Snapshot:**
- Status: ACTIVE ✅ (no restore needed)
- Plan: Team ($49/mo, 5 seats, 100 GB)
- Tenure: 8.0 months
- AutoPay: ON
- Card on file: 3311 ✅ VALID
- Pending Balance: $0.00

**Outcome:** DA4 executes Team → Business upgrade. Permanent (no duration specified). 5 seats well within Business plan's 30-seat limit.

**Starting Utterance:**
> "I'd like to upgrade my plan. Account 20006."

**Full Prompt Script:**
- Turn 1: `I'd like to upgrade my plan. Account 20006.`
- Turn 2: `I want to upgrade to Business.`
- Turn 3: `Yes, confirm the upgrade.`

**Expected Tool Chain:**
- Turn 1: T1 → ACTIVE detected → no restore flow. Agent asks which plan.
- Turn 2: Plan named → DA4 MODE V (T9: validate Business, eligible=True, direction=upgrade, 5 seats < 30 max). Presents $129/mo and 500 GB. Waits for confirmation.
- Turn 3: Confirm → DA4 MODE E (T6: Business, no duration → permanent) + T8 receipt.

**What to Watch For:**
- No SA1, no DA1, no DA2 called — ACTIVE account goes directly to DA4.
- T9 confirms: `direction=upgrade`, `seat_count_ok=True` (5 seats ≤ 30 max), `storage_delta="100 GB → 500 GB"`.
- T6 called with `duration_months=None` → `downgrade_date=NULL` in DB (permanent upgrade).
- Receipt sent. Confirmation: "Your plan has been upgraded to Business — effective your next billing cycle."
- No revert date stated (permanent).

---------------------------------------

# Persona 7: The "Downgrade Blocked" Customer (ACTIVE, Seat Count Violation)
**Account ID:** 20007 (Drew, Lumen Co)
**Turn Count:** 2 turns (or 1 — blocked immediately after plan named)

**Account Snapshot:**
- Status: ACTIVE ✅
- Plan: Business ($129/mo, 30-seat limit, 500 GB)
- Tenure: 16.0 months
- AutoPay: ON
- Card on file: 7799 ✅ VALID
- Seat Count: 25 active seats ❌ (exceeds Team plan's 10-seat max)

**Outcome:** HARD STOP — T9 returns `seat_count_ok=False`, `eligible=False`. T6 is never called. Agent escalates to human support team.

**Starting Utterance:**
> "I want to downgrade my plan. Account 20007."

**Full Prompt Script:**
- Turn 1: `I want to downgrade my plan. Account 20007.`
- Turn 2: `Downgrade to Team plan.`

**Expected Tool Chain:**
- Turn 1: T1 → ACTIVE → agent asks which plan.
- Turn 2: Plan named → DA4 (T9: validate Team, direction=downgrade, seat_count_ok=False — 25 seats > 10 max, eligible=False). HARD STOP. T6 never called.

**What to Watch For:**
- Exact seat count stated in escalation message: "Your team has 25 active seats, which exceeds the Team plan's 10-seat limit."
- Agent does NOT proceed with the downgrade. T6 is never called (T9 gates it with eligible=False).
- Warm escalation offered: "I'll connect you with our support team to deactivate seats before downgrading."
- DB is unchanged: plan remains Business, seat_count remains 25.
- Good demo of the guardrail: agent knows its limits and hands off gracefully rather than proceeding incorrectly.

---------------------------------------

# Persona 8: The "Clean Downsizer" (ACTIVE, Downgrade Passes Seat Check)
**Account ID:** 20008 (Quinn, Pathfinder)
**Turn Count:** 3 turns

**Account Snapshot:**
- Status: ACTIVE ✅
- Plan: Business ($129/mo, 500 GB)
- Tenure: 24.0 months
- AutoPay: ON
- Card on file: 1188 ✅ VALID
- Seat Count: 5 active seats ✅ (≤ Team plan's 10-seat max)

**Outcome:** Successful downgrade to Team. Storage reduction warning presented (informational, not blocking). Permanent downgrade (no duration specified).

**Starting Utterance:**
> "I want to downgrade my plan. Account 20008."

**Full Prompt Script:**
- Turn 1: `I want to downgrade my plan. Account 20008.`
- Turn 2: `Downgrade to Team plan.`
- Turn 3: `Yes, confirm the downgrade.`

**Expected Tool Chain:**
- Turn 1: T1 → ACTIVE → agent asks which plan.
- Turn 2: Plan named → DA4 (T9: direction=downgrade, seat_count_ok=True — 5 ≤ 10, eligible=True, storage_delta="500 GB → 100 GB"). Storage warning presented.
- Turn 3: Confirm → T6 (Team, permanent) + T8 receipt.

**What to Watch For:**
- T9 seat check passes: 5 seats ≤ 10 max — contrast with Persona 7 where 25 seats blocks the downgrade.
- Storage warning is informational only: "Your storage allocation will drop from 500 GB to 100 GB. Current usage is well within the new limit." (Does not block the downgrade.)
- T6 called with `duration_months=None` → permanent downgrade.
- Good counterpart to Persona 7 — same downgrade path, different outcome based purely on seat count.

---------------------------------------

# Persona 9: The "Boundary Case" (Waiver FAIL Rule A — Exactly 6.0 Months)
**Account ID:** 20009 (Jamie, Redpine)
**Turn Count:** 2 turns

**Account Snapshot:**
- Status: SUSPENDED ⚠️ (20 days — data SAFE)
- Plan: Business ($129/mo)
- Tenure: 6.0 months exactly ❌ (Rule A FAIL — needs STRICTLY greater than 6)
- AutoPay: ON ✅ (Rule B PASS)
- Prior Waiver (12mo): None ✅ (Rule C PASS)
- Card on file: 9955 ❌ EXPIRED
- Pending Balance: $129.00

**Waiver Outcome:** DENIED — 6.0 months is not strictly greater than 6 months. AutoPay is ON and no prior waiver, but Rule A fails at the boundary. $50 late fee (Business plan).

**Payment Note:** T3 charges the pending_balance only ($129). The $50 late fee is disclosed but NOT collected via T3 — the card is charged $129, not $179. See P02 note for the full explanation of this design.

**Starting Utterance:**
> "Account 20009 — suspended 20 days. Can I get the late fee waived? I've had AutoPay on the whole time."

**Full Prompt Script:**
- Turn 1: `Account 20009 -- suspended 20 days. Can I get the late fee waived? I've had AutoPay on the whole time.`
- Turn 2: `New card number is 4111 1111 1111 7777. Yes, go ahead.`

**Expected Tool Chain:**
- Turn 1: T1 → T0_Get → DA1 (T2: 20d SAFE) + DA2 (T7 + T4 waiver) in parallel → T0_Set. Card expired.
- Turn 2: New card (7777) + consent → DA2 (T3: $179 to 7777) + DA3 (T5 restore) in parallel → T0_Set.

**What to Watch For:**
- T4 returns `waiver_granted=False` with reason: "your account is 6 months old, which does not meet the 6-month minimum."
- Agent does NOT grant the waiver despite customer's appeal about AutoPay. AutoPay being ON is accurate but does not override Rule A.
- Business plan late fee = $50 (not $25 Team or $10 Individual) — T4 fetches from plan_catalog.
- $179 total charged ($129 balance + $50 fee).
- Key boundary test: "at least 6 months" would be PASS; "strictly greater than 6" is the rule → 6.0 is FAIL.

---------------------------------------

# Persona 10: The "Top Tier" Enterprise Restore
**Account ID:** 20010 (Avery, Stratos)
**Turn Count:** 2 turns

**Account Snapshot:**
- Status: SUSPENDED ⚠️ (8 days — data SAFE)
- Plan: Enterprise ($399/mo)
- Tenure: 30.0 months ✅ (Rule A PASS)
- AutoPay: ON ✅ (Rule B PASS)
- Prior Waiver (12mo): None ✅ (Rule C PASS)
- Card on file: 3388 ❌ EXPIRED
- Pending Balance: $399.00
- Seat Count: 45, Projects: 35

**Waiver Outcome:** GRANTED — all 3 rules pass. $0 late fee.

**Starting Utterance:**
> "Our enterprise account is suspended. I need it restored. Account 20010."

**Full Prompt Script:**
- Turn 1: `Our enterprise account is suspended. I need it restored. Account 20010.`
- Turn 2: `Please use new card 5500 0055 5555 4321 and restore us now.`

**Expected Tool Chain:**
- Turn 1: T1 → T0_Get → DA1 (T2: 8d, 35 projects SAFE) + DA2 (T7 + T4 waiver) in parallel → T0_Set. Card expired → prompts for new card.
- Turn 2: New card (4321) + consent → DA2 (T3: $399 to 4321) + DA3 (T5 restore) in parallel → T0_Set.

**What to Watch For:**
- 30-month tenure → warm loyalty acknowledgement.
- $399 charged to new card 4321. Card on file updated.
- Waiver: "Your late fee has been waived — you've been with us for 30 months, had AutoPay enabled, and haven't used a waiver in the past 12 months."
- "All 35 projects are intact." (data_safe=True — intact claim is correct here).
- No plan change requested → flow closes warmly after restore receipt.
- `__CARD_FORM__` emitted in Turn 1 (orbit_chat.html) or customer types 16-digit number (adk web).

---------------------------------------

# Persona 11: The "Churned" Customer (Win-Back)
**Account ID:** 20011 (Parker, Helix Systems)
**Turn Count:** 2 turns

**Account Snapshot:**
- Status: CANCELED ❌ (account closed — no restore possible via VA)
- Plan: Team (on record, account closed)
- Tenure: 1.5 months
- AutoPay: OFF
- Card: 4411 (no active billing)

**Outcome:** Win-back script. No restore, no payment, no plan change. Agent routes to human sales team to explore rejoining.

**Starting Utterance:**
> "Hi, I'd like to reactivate my account. Account 20011."

**Full Prompt Script:**
- Turn 1: `Hi, I'd like to reactivate my account. Account 20011.`
- Turn 2: `Yes, I'd like to explore your current plans.`

**Expected Tool Chain:**
- Turn 1: T1 → CANCELED detected → no DA1/DA2/DA3/DA4. Win-back script only.

**What to Watch For:**
- Agent identifies CANCELED status from T1 immediately.
- No restore flow entered. No payment, no balance check, no fee waiver.
- Warm win-back pivot: "Your account is no longer active. I'd love to help you explore getting started again — let me connect you with our team."
- Turn 2: Agent acknowledges interest, routes to sales team. Does not attempt to reactivate in-flow.
- Shortest persona — useful as a quick insert to demonstrate account status handling and clean agent routing.

---------------------------------------

# Persona 12: The "Mystery Performance Issue" — SA1 Diagnostic, Storage Culprit
**Account ID:** 20012 (Taylor, Brightline)
**Turn Count:** 2 turns

**Account Snapshot:**
- Status: ACTIVE ✅
- Plan: Team (100 GB storage limit)
- Tenure: 11.0 months
- AutoPay: ON
- Seat Count: 8 seats (within limit)
- Storage: 95 GB used / 100 GB total — **95% full** (near-limit threshold: 90%)
- Integration: Slack — status healthy, last sync recent

**Diagnostic Finding:** DA5_StorageAgent (T11) returns `near_limit=True` (95%). DA6_IntegrationAgent (T12) returns Slack healthy. DA1 returns account ACTIVE, no issues. SA1 synthesises: **storage is the culprit** — near-limit causes upload failures and slow project access.

**Starting Utterance:**
> "Account 20012 — something feels off lately. Projects are loading slowly and a few uploads just failed. Not sure what's going on."

**Full Prompt Script:**
- Turn 1: `Account 20012 -- something feels off lately. Projects are loading slowly and a few uploads just failed. Not sure what's going on.`
- Turn 2: `Ah, that makes sense. What are my options?`

**Expected Tool Chain:**
- Turn 1: T1 → ACTIVE → ambiguous multi-dimensional complaint detected → root_agent routes to SA1_DiagnosticSupervisor. SA1 fans out: DA1 + DA5 (T11) + DA6 (T12) in parallel. SA1 synthesises → storage culprit identified. Agent explains storage near-limit (95/100 GB) as the cause of upload failures.
- Turn 2: Agent presents upgrade options — Business plan (500 GB) is the natural next step.

**What to Watch For:**
- root_agent correctly identifies the complaint as multi-dimensional (not a billing question, not a single-tool query) and routes to SA1_DiagnosticSupervisor — not directly to DA5 alone.
- SA1 runs DA1 + DA5 + DA6 in parallel in the same turn (parallel fan-out, not sequential).
- T11 returns 95/100 GB, near_limit=True. T12 returns Slack healthy.
- SA1 synthesis: PRIMARY_FINDING=storage, severity=HIGH (near limit). Integration and account both OK.
- Agent presents storage near-limit explanation warmly: "It looks like you're nearly at your 100 GB storage limit — that's what's causing uploads to fail and projects to load slowly."
- Turn 2: Upgrade to Business (500 GB) presented as the resolution path. DA4 ready to execute.

---------------------------------------

# Persona 13: The "Silent Sync Failure" — SA1 Diagnostic, Integration Culprit
**Account ID:** 20013 (Blake, Nexus Digital)
**Turn Count:** 2 turns

**Account Snapshot:**
- Status: ACTIVE ✅
- Plan: Business (500 GB storage limit)
- Tenure: 16.0 months
- AutoPay: ON
- Seat Count: 12 seats
- Storage: 45 GB used / 500 GB total — 9% (healthy, plenty of headroom)
- Integration: GitHub — **auth_failure**, 5 failures in recent window, last sync 3 days ago, `action_required=True`

**Diagnostic Finding:** DA5_StorageAgent (T11) returns 9% — healthy. DA6_IntegrationAgent (T12) returns GitHub auth_failure, 5 failures, last sync 3 days ago. DA1 returns account ACTIVE, no issues. SA1 synthesises: **integration is the culprit** — GitHub auth token likely expired or revoked.

**Starting Utterance:**
> "Account 20013 — things just don't feel right. My team says changes aren't showing up in projects, like it's not syncing. I don't know if it's a billing thing or what."

**Full Prompt Script:**
- Turn 1: `Account 20013 -- things just don't feel right. My team says changes aren't showing up in projects, like it's not syncing. I don't know if it's a billing thing or what.`
- Turn 2: `Yes, please walk me through how to fix the GitHub connection.`

**Expected Tool Chain:**
- Turn 1: T1 → ACTIVE → ambiguous health complaint + "billing thing or what" → root_agent routes to SA1_DiagnosticSupervisor. SA1 fans out: DA1 + DA5 (T11) + DA6 (T12) in parallel. SA1 synthesises → integration culprit identified. Agent confirms it's not a billing issue — GitHub auth is the problem.
- Turn 2: Agent walks through GitHub reconnect steps (revoke old token, generate new one in GitHub → paste into Orbit Settings → Integrations). Steps sourced from SA1/DA6 guidance.

**What to Watch For:**
- "I don't know if it's a billing thing or what" — agent correctly identifies this as NOT a billing issue without running DA2.
- SA1 runs DA1 + DA5 + DA6 in parallel. DA5 (T11) returns healthy; DA6 (T12) returns auth_failure.
- SA1 synthesis: PRIMARY_FINDING=integration, severity=HIGH (action_required=True). Storage and account both OK.
- Agent explains: "It's not a billing issue — your account is in good standing. What we're seeing is that the GitHub integration has lost its connection, likely because the auth token expired or was revoked."
- Contrast with Persona 12: same fan-out architecture, different culprit. Great back-to-back demo pair for showing SA1 routing intelligence.

---

## Quick Reference — All 13 Accounts

| # | ID | Name | Company | Plan | Status | Key Scenario |
|---|-----|------|---------|------|--------|--------------|
| P01 | 20001 | Alex | Wavefront | Team | SUSPENDED | Primary demo — waiver PASS, Business upgrade 3mo |
| P02 | 20002 | Jordan | Sprinto | Team | SUSPENDED | Waiver FAIL Rule A (2mo < 6mo) |
| P03 | 20003 | Sam | Arclight | Business | SUSPENDED | Data AT RISK (35d > 30d), waiver PASS |
| P04 | 20004 | Riley | Nomad Labs | Individual | SUSPENDED | Waiver FAIL Rule C (prior waiver 90d ago) |
| P05 | 20005 | Morgan | Crestline | Team | SUSPENDED | Waiver FAIL Rule B (AutoPay OFF) |
| P06 | 20006 | Casey | Driftwood | Team | ACTIVE | Standalone upgrade Team → Business (permanent) |
| P07 | 20007 | Drew | Lumen Co | Business | ACTIVE | Downgrade BLOCKED — 25 seats > 10 max |
| P08 | 20008 | Quinn | Pathfinder | Business | ACTIVE | Clean downgrade Business → Team (5 seats OK) |
| P09 | 20009 | Jamie | Redpine | Business | SUSPENDED | Waiver FAIL Rule A boundary — exactly 6.0mo |
| P10 | 20010 | Avery | Stratos | Enterprise | SUSPENDED | Top-tier restore — $399, waiver PASS |
| P11 | 20011 | Parker | Helix Systems | Team | CANCELED | Win-back — route to human sales |
| P12 | 20012 | Taylor | Brightline | Team | ACTIVE | SA1 diagnostic — storage culprit (95/100 GB) |
| P13 | 20013 | Blake | Nexus Digital | Business | ACTIVE | SA1 diagnostic — integration culprit (GitHub auth_failure) |

---

## Waiver Rule Summary

| Account | Tenure | AutoPay | Prior Waiver | Rule A | Rule B | Rule C | Result |
|---------|--------|---------|--------------|--------|--------|--------|--------|
| 20001 Alex | 9.0mo | ON | None | ✅ | ✅ | ✅ | PASS — $0 |
| 20002 Jordan | 2.0mo | OFF | None | ❌ | ❌ | ✅ | FAIL A — $25 |
| 20003 Sam | 14.0mo | ON | None | ✅ | ✅ | ✅ | PASS — $0 |
| 20004 Riley | 7.0mo | ON | 90d ago | ✅ | ✅ | ❌ | FAIL C — $10 |
| 20005 Morgan | 18.0mo | OFF | None | ✅ | ❌ | ✅ | FAIL B — $25 |
| 20009 Jamie | 6.0mo | ON | None | ❌ | ✅ | ✅ | FAIL A (boundary) — $50 |
| 20010 Avery | 30.0mo | ON | None | ✅ | ✅ | ✅ | PASS — $0 |
