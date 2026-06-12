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
    - duration_months: customer said "for 3 months" → downgrade_date = today + 90 days.
      No duration → permanent change, downgrade_date = NULL.
    - In a real system, a scheduled job would fire on downgrade_date to revert the plan.
      In this demo, the date is stored and acknowledged verbally.
    - Called via DA4_PlanAgent (Squad) only. Not callable by SA1 directly.

INPUTS:
    conn            : Database connection (injected automatically).
    account_id      : Customer's 5-digit ID (e.g., 20001).
    new_plan_name   : Exact plan name from plan_catalog (e.g., "Business").
    duration_months : Integer (e.g., 3) for temporary upgrade, or None for permanent.

OUTPUT:
    Success: {"status": "success", "account_id": ..., "new_plan_name": ...,
              "downgrade_date": "YYYY-MM-DD" or None, "message": "..."}
    Error:   {"status": "error", "message": "..."}
"""

import sqlite3
from datetime import date, timedelta


def T6_ChangePlan(conn, account_id, new_plan_name, duration_months=None):
    """
    Updates the customer's plan. Stores downgrade_date if duration is specified.

    Args:
        conn            : Active SQLite database connection (injected by agent framework).
        account_id      : The customer's 5-digit account ID (e.g., 20001).
        new_plan_name   : The target plan name (must match plan_catalog.plan_name).
        duration_months : Number of months for temporary change, or None for permanent.

    Returns:
        dict: Confirmation with new plan name and downgrade_date (if applicable).
    """
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT plan_id FROM plan_catalog WHERE plan_name = ?",
            (new_plan_name,)
        )
        if not cursor.fetchone():
            return {"status": "error", "message": f"Plan '{new_plan_name}' not found in catalog."}

        downgrade_date = None
        if duration_months:
            downgrade_date = (date.today() + timedelta(days=duration_months * 30)).isoformat()

        cursor.execute("""
            UPDATE customer_accounts
            SET plan_name = ?, downgrade_date = ?
            WHERE account_id = ?
        """, (new_plan_name, downgrade_date, account_id))

        if cursor.rowcount == 0:
            return {"status": "error", "message": "Account not found."}

        conn.commit()

        if downgrade_date:
            msg = f"Plan updated to {new_plan_name}. Auto-reverts on {downgrade_date}."
        else:
            msg = f"Plan updated to {new_plan_name} (permanent)."

        return {
            "status":         "success",
            "account_id":     account_id,
            "new_plan_name":  new_plan_name,
            "downgrade_date": downgrade_date,
            "message":        msg,
        }

    except sqlite3.Error as e:
        return {"status": "error", "message": str(e)}


# =============================================================================
# TEST BLOCK
# =============================================================================
if __name__ == "__main__":
    import os
    DB_PATH = os.path.join(os.path.dirname(__file__), "pay_restore.db")
    conn = sqlite3.connect(DB_PATH)

    print("=== T6_ChangePlan -- Manual Test Run ===\n")

    print("--- Test 1: Alex (20001) -- upgrade to Business for 3 months ---")
    result = T6_ChangePlan(conn, 20001, "Business", duration_months=3)
    print(result)

    print("\n--- Verify: Alex plan_name and downgrade_date ---")
    cursor = conn.cursor()
    cursor.execute("SELECT plan_name, downgrade_date FROM customer_accounts WHERE account_id=20001")
    print(cursor.fetchone())

    print("\n--- Test 2: Casey (20006) -- permanent downgrade to Individual ---")
    result = T6_ChangePlan(conn, 20006, "Individual")
    print(result)

    print("\n--- Test 3: Plan not found ---")
    print(T6_ChangePlan(conn, 20001, "Platinum"))

    print("\n--- Test 4: Account not found ---")
    print(T6_ChangePlan(conn, 99999, "Business"))

    conn.close()
    print("\nNOTE: Run z_reset_world.py to restore original plan assignments.")
