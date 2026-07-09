"""
T6_ChangePlan
-------------
WHAT THIS TOOL DOES:
    Updates the customer's plan in the database. If a duration is specified
    (e.g., 3 months), stores a downgrade_date for automatic revert. If no
    duration, the change is permanent (downgrade_date = NULL).

WHY IT MATTERS (Business Logic):
    - MUST only be called after T9_ValidatePlanChange returns eligible=True.
      T9 is the gate — T6 is the execution. Never call T6 without T9 clearance.
    - All billing cycles start on the 1st of the month. The plan takes effect on
      the 1st of the next calendar month (or a customer-specified future month).
      NOTE: billing_start is always the 1st of the next calendar month from today,
      regardless of where the customer is in their current billing cycle. A customer
      who upgrades on Oct 2nd gets Nov 1st as their billing_start — a near-full month
      wait. This is a deliberate simplification (no proration in this demo).
    - duration_months: "for 3 months" → revert on the 1st of the month that is
      exactly N calendar months after billing_start (not N×30 days). This ensures
      revert always lands on a billing cycle boundary.
    - No duration → permanent change, downgrade_date = NULL.
    - In a real system, a scheduled job would fire on downgrade_date to revert the plan.
      In this demo, the date is stored and acknowledged verbally.
    - Called via DA4_PlanAgent (Squad) only. Not callable by SA1 directly.

INPUTS:
    conn            : Database connection (injected automatically).
    account_id      : Customer's 5-digit ID (e.g., 20001).
    new_plan_name   : Exact plan name from plan_catalog (e.g., "Business").
    duration_months : Integer (e.g., 3) for temporary upgrade, or None for permanent.
    start_month     : Integer 1–12 for a future billing cycle start (optional).
                      If omitted, defaults to the 1st of the next calendar month.
    start_year      : Integer (e.g., 2027) paired with start_month (optional).
                      Required if start_month is provided.

OUTPUT:
    Success: {"status": "success", "account_id": ..., "new_plan_name": ...,
              "billing_start_date": "YYYY-MM-DD",
              "downgrade_date": "YYYY-MM-DD" or None, "message": "..."}
    Error:   {"status": "error", "message": "..."}
"""

import sqlite3
from datetime import date
from .log_setup import get_logger

_log = get_logger("tool.T6")


def _first_of_next_month(d: date) -> date:
    """Returns the 1st of the calendar month immediately after d."""
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _add_months(d: date, n: int) -> date:
    """Adds n calendar months to a date that is already the 1st of a month."""
    raw = d.month + n
    year = d.year + (raw - 1) // 12
    month = ((raw - 1) % 12) + 1
    return date(year, month, 1)


def T6_ChangePlan(conn, account_id, new_plan_name, duration_months=None,
                  start_month=None, start_year=None):
    """
    Updates the customer's plan. Computes billing_start_date (1st of next month
    or a specified future month) and downgrade_date (N calendar months later).

    Args:
        conn            : Active SQLite database connection (injected by agent framework).
        account_id      : The customer's 5-digit account ID (e.g., 20001).
        new_plan_name   : The target plan name (must match plan_catalog.plan_name).
        duration_months : Number of months for temporary change, or None for permanent.
        start_month     : Optional future start month (1–12). Defaults to next month.
        start_year      : Optional year for start_month. Required if start_month given.

    Returns:
        dict: Confirmation with billing_start_date and downgrade_date.
    """
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT plan_id FROM plan_catalog WHERE plan_name = ?",
            (new_plan_name,)
        )
        if not cursor.fetchone():
            return {"status": "error", "message": f"Plan '{new_plan_name}' not found in catalog."}

        today = date.today()
        min_start = _first_of_next_month(today)

        # Billing start is always the 1st of a month.
        if start_month and start_year:
            try:
                requested_start = date(int(start_year), int(start_month), 1)
            except (ValueError, TypeError):
                return {"status": "error",
                        "message": f"Invalid start_month/start_year: {start_month}/{start_year}."}
            # Cannot start in the current month or the past.
            billing_start = max(requested_start, min_start)
        else:
            billing_start = min_start

        # Revert date: N whole calendar months after billing_start.
        downgrade_date = None
        if duration_months is not None:
            try:
                duration_months = int(duration_months)
            except (TypeError, ValueError):
                return {"status": "error",
                        "message": f"Invalid duration_months: {duration_months!r}. Must be an integer."}
            downgrade_date = _add_months(billing_start, duration_months).isoformat()

        cursor.execute("""
            UPDATE customer_accounts
            SET plan_name = ?, downgrade_date = ?
            WHERE account_id = ?
        """, (new_plan_name, downgrade_date, account_id))

        if cursor.rowcount == 0:
            return {"status": "error", "message": "Account not found."}

        conn.commit()

        billing_start_str = billing_start.isoformat()
        if downgrade_date:
            msg = (f"Plan updated to {new_plan_name}. "
                   f"Effective {billing_start_str}. Auto-reverts on {downgrade_date}.")
        else:
            msg = f"Plan updated to {new_plan_name} (permanent). Effective {billing_start_str}."

        _log.info(
            f"PLAN_CHANGE_OK  account={account_id}  new_plan={new_plan_name}"
            f"  billing_start={billing_start_str}  duration_months={duration_months}"
            f"  revert_date={downgrade_date}"
        )
        return {
            "status":             "success",
            "account_id":         account_id,
            "new_plan_name":      new_plan_name,
            "billing_start_date": billing_start_str,
            "downgrade_date":     downgrade_date,
            "message":            msg,
        }

    except sqlite3.Error as e:
        _log.error(f"PLAN_CHANGE_FAIL  account={account_id}  plan={new_plan_name}  error={e}")
        return {"status": "error", "message": str(e)}


# =============================================================================
# TEST BLOCK
# =============================================================================
if __name__ == "__main__":
    import os
    DB_PATH = os.path.join(os.path.dirname(__file__), "orbit.db")
    conn = sqlite3.connect(DB_PATH)

    print("=== T6_ChangePlan -- Manual Test Run ===\n")

    print("--- Test 1: Alex (20001) -- upgrade to Business for 3 months (next month start) ---")
    result = T6_ChangePlan(conn, 20001, "Business", duration_months=3)
    print(result)

    print("\n--- Verify: Alex plan_name, downgrade_date ---")
    cursor = conn.cursor()
    cursor.execute("SELECT plan_name, downgrade_date FROM customer_accounts WHERE account_id=20001")
    print(cursor.fetchone())

    print("\n--- Test 2: Alex -- 4 months starting in August 2026 ---")
    result = T6_ChangePlan(conn, 20001, "Business", duration_months=4,
                           start_month=8, start_year=2026)
    print(result)

    print("\n--- Test 3: Casey (20006) -- permanent downgrade to Individual ---")
    result = T6_ChangePlan(conn, 20006, "Individual")
    print(result)

    print("\n--- Test 4: Plan not found ---")
    print(T6_ChangePlan(conn, 20001, "Platinum"))

    print("\n--- Test 5: Account not found ---")
    print(T6_ChangePlan(conn, 99999, "Business"))

    conn.close()
    print("\nNOTE: Run z_reset_world.py to restore original plan assignments.")
