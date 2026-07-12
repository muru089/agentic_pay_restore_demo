"""
T0_SessionState.py  --  T0_GetSessionState / T0_SetSessionState
===============================================================

Persistent session state for the restore flow.
Opens its own DB connection (same pattern as T8_SendReceipt).
Called directly by root_agent — no DB injection.

STATE FIELDS:
    data_checked        1 = DA1 has run this session
    data_safe           1 = data safe, 0 = AT RISK (>30 days suspended)
    days_suspended      days the account has been suspended
    project_count       number of active projects (from DA1)
    at_risk_disclosed   1 = AT RISK warning has been presented to customer
    at_risk_proceeding  1 = customer chose to proceed despite AT RISK warning
    payment_cleared     1 = DA2 payment succeeded
    amount_paid         amount charged (float)
    new_card_last4      last 4 of new card if customer provided one, else None
    restore_complete    1 = DA3 restore succeeded
    plan_change_requested 1 = customer wants a plan change
    plan_name_requested   target plan name (e.g., "Business")
    plan_duration_months  N months if temporary, None if permanent
    plan_validated      1 = DA4 MODE V has run and been presented
    plan_executed       1 = DA4 MODE E has run (plan changed)
"""

import os
import sqlite3
from datetime import datetime
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "orbit.db")

# Module-level connection — avoids open/close overhead on every T0 call.
# WAL mode + check_same_thread=False matches the pattern used in agent.py / DA2.
_conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None, timeout=30.0)
_conn.execute("PRAGMA journal_mode=WAL")
_conn.row_factory = sqlite3.Row

_DEFAULTS = {
    # T1 cache fields
    "t1_cached":              0,
    "first_name":             None,
    "company_name":           None,
    "plan_name":              None,
    "tenure_months":          None,
    "card_last4":             None,
    "card_expired":           None,
    "pending_balance":        None,
    # restore flow state
    "data_checked":           0,
    "data_safe":              1,
    "days_suspended":         0,
    "project_count":          0,
    "at_risk_disclosed":      0,
    "at_risk_proceeding":     0,
    "payment_cleared":        0,
    "amount_paid":            0.0,
    "new_card_last4":         None,
    "restore_complete":       0,
    "plan_change_requested":  0,
    "plan_name_requested":    None,
    "plan_duration_months":   None,
    "plan_validated":         0,
    "plan_executed":          0,
}


def T0_GetSessionState(account_id: int) -> dict:
    """
    Reads the current restore session state for the given account.
    Returns all state fields as a dict.
    If no session exists yet, returns a fresh default state (all flags = 0).
    Call this at the start of every SUSPENDED account turn (after T1) to
    determine which step to execute next.
    Input: account_id (integer).
    """
    row = _conn.execute(
        "SELECT * FROM session_state WHERE account_id = ?", (account_id,)
    ).fetchone()
    if row:
        return dict(row)
    return {"account_id": account_id, **_DEFAULTS}


def T0_SetSessionState(
    account_id: int,
    # T1 cache fields
    t1_cached:              Optional[int]   = None,
    first_name:             Optional[str]   = None,
    company_name:           Optional[str]   = None,
    plan_name:              Optional[str]   = None,
    tenure_months:          Optional[float] = None,
    card_last4:             Optional[str]   = None,
    card_expired:           Optional[int]   = None,
    pending_balance:        Optional[float] = None,
    # restore flow state
    data_checked:           Optional[int]   = None,
    data_safe:              Optional[int]   = None,
    days_suspended:         Optional[int]   = None,
    project_count:          Optional[int]   = None,
    at_risk_disclosed:      Optional[int]   = None,
    at_risk_proceeding:     Optional[int]   = None,
    payment_cleared:        Optional[int]   = None,
    amount_paid:            Optional[float] = None,
    new_card_last4:         Optional[str]   = None,
    restore_complete:       Optional[int]   = None,
    plan_change_requested:  Optional[int]   = None,
    plan_name_requested:    Optional[str]   = None,
    plan_duration_months:   Optional[int]   = None,
    plan_validated:         Optional[int]   = None,
    plan_executed:          Optional[int]   = None,
) -> dict:
    """
    Updates the restore session state for the given account.
    Only pass the fields you want to change — unspecified fields are left as-is.
    Call this after each completed step to record progress so the next turn
    knows exactly where to resume.
    To explicitly clear a TEXT field to NULL (e.g. plan_name_requested after a
    plan change completes), pass the empty string "" — it is treated as a clear
    sentinel. Omitting a field (or passing None) leaves it unchanged.
    Input: account_id (integer) + any subset of state fields to update.
    Returns the full updated state after the write.
    """
    local_args = {
        # T1 cache fields
        "t1_cached":             t1_cached,
        "first_name":            first_name,
        "company_name":          company_name,
        "plan_name":             plan_name,
        "tenure_months":         tenure_months,
        "card_last4":            card_last4,
        "card_expired":          card_expired,
        "pending_balance":       pending_balance,
        # restore flow state
        "data_checked":          data_checked,
        "data_safe":             data_safe,
        "days_suspended":        days_suspended,
        "project_count":         project_count,
        "at_risk_disclosed":     at_risk_disclosed,
        "at_risk_proceeding":    at_risk_proceeding,
        "payment_cleared":       payment_cleared,
        "amount_paid":           amount_paid,
        "new_card_last4":        new_card_last4,
        "restore_complete":      restore_complete,
        "plan_change_requested": plan_change_requested,
        "plan_name_requested":   plan_name_requested,
        "plan_duration_months":  plan_duration_months,
        "plan_validated":        plan_validated,
        "plan_executed":         plan_executed,
    }
    updates = {}
    for k, v in local_args.items():
        if v is None:
            pass  # omit — leave field unchanged
        elif isinstance(v, str) and v == "":
            updates[k] = None  # empty string sentinel: clear TEXT field to NULL
        else:
            updates[k] = v
    updates["updated_at"] = datetime.now().isoformat()

    exists = _conn.execute(
        "SELECT 1 FROM session_state WHERE account_id = ?", (account_id,)
    ).fetchone()

    if exists:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        _conn.execute(
            f"UPDATE session_state SET {set_clause} WHERE account_id = ?",
            [*updates.values(), account_id],
        )
    else:
        row_data = {"account_id": account_id, **_DEFAULTS, **updates}
        cols = ", ".join(row_data.keys())
        placeholders = ", ".join("?" * len(row_data))
        _conn.execute(
            f"INSERT INTO session_state ({cols}) VALUES ({placeholders})",
            list(row_data.values()),
        )

    row = _conn.execute(
        "SELECT * FROM session_state WHERE account_id = ?", (account_id,)
    ).fetchone()
    return dict(row)


if __name__ == "__main__":
    print("=== T0_SessionState smoke test ===")
    # Uses the module-level _conn — no extra connection setup needed.

    # Fresh read
    s = T0_GetSessionState(20001)
    print(f"Fresh state for 20001: data_checked={s['data_checked']}")

    # Write data check results
    s = T0_SetSessionState(20001, data_checked=1, data_safe=1, project_count=12)
    print(f"After data check: data_checked={s['data_checked']}, project_count={s['project_count']}")

    # Write payment
    s = T0_SetSessionState(20001, payment_cleared=1, amount_paid=49.0, new_card_last4="4321")
    print(f"After payment: payment_cleared={s['payment_cleared']}, card={s['new_card_last4']}")

    # Write restore
    s = T0_SetSessionState(20001, restore_complete=1)
    print(f"After restore: restore_complete={s['restore_complete']}")

    # Read back
    s = T0_GetSessionState(20001)
    print(f"Read back: all flags = {s['data_checked']}/{s['payment_cleared']}/{s['restore_complete']}")
    print("=== PASS ===")
