"""
T9_ValidatePlanChange
---------------------
WHAT THIS TOOL DOES:
    Validates a requested plan change by fetching new plan details and checking
    seat eligibility. Returns the full payload DA4 needs to present to the
    customer and (if approved) pass to T6.

WHY IT MATTERS (Business Logic):
    - T9 is the gate before T6. If T9 returns eligible=False, T6 must NEVER be called.
    - Upgrade path: always eligible=True (no seat restriction going up).
    - Downgrade path: checks if current seat_count fits within new plan's max_users.
      If not -> eligible=False -> HARD STOP -> human escalation.
    - Returns new plan price, storage, and max_users so DA4 can present the full
      picture to the customer before asking for confirmation.
    - storage_delta shows the change in human-readable form (e.g., "100 GB -> 500 GB").

INPUTS:
    conn          : Database connection (injected automatically).
    account_id    : Customer's 5-digit ID (e.g., 20001).
    new_plan_name : Target plan name (e.g., "Business").

OUTPUT:
    {
      "status": "success",
      "eligible": True/False,
      "direction": "upgrade" or "downgrade",
      "current_plan_name": "Team",
      "new_plan_name": "Business",
      "new_monthly_price": 129.00,
      "new_max_users": 30,
      "new_storage_gb": 500,
      "current_seat_count": 8,
      "seat_count_ok": True,
      "storage_delta": "100 GB -> 500 GB",
      "reason": "..."         (only present if eligible=False)
    }
"""

import sqlite3


def T9_ValidatePlanChange(conn, account_id, new_plan_name):
    """
    Validates a plan upgrade or downgrade request and returns the full eligibility payload.

    Args:
        conn          : Active SQLite database connection (injected by agent framework).
        account_id    : The customer's 5-digit account ID (e.g., 20001).
        new_plan_name : The target plan name (must match plan_catalog.plan_name).

    Returns:
        dict: Eligibility result with new plan details and seat check outcome.
    """
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT ca.plan_name, ca.seat_count,
                   pc_current.monthly_price, pc_current.storage_gb,
                   pc_current.max_users
            FROM customer_accounts ca
            JOIN plan_catalog pc_current ON ca.plan_name = pc_current.plan_name
            WHERE ca.account_id = ?
        """, (account_id,))
        current_row = cursor.fetchone()

        if not current_row:
            return {"status": "error", "message": "Account not found."}

        current_plan_name, seat_count, current_price, current_storage, current_max_users = current_row

        cursor.execute("""
            SELECT monthly_price, max_users, storage_gb
            FROM plan_catalog
            WHERE plan_name = ?
        """, (new_plan_name,))
        new_row = cursor.fetchone()

        if not new_row:
            return {"status": "error", "message": f"Plan '{new_plan_name}' not found in catalog."}

        new_price, new_max_users, new_storage = new_row

        if new_plan_name == current_plan_name:
            return {
                "status":  "error",
                "message": f"Customer is already on the {current_plan_name} plan. No change needed.",
            }

        direction = "upgrade" if new_price > current_price else "downgrade"

        seat_count_ok = seat_count <= new_max_users

        def fmt_storage(gb):
            return f"{gb // 1024} TB" if gb >= 1024 else f"{gb} GB"

        storage_delta = f"{fmt_storage(current_storage)} -> {fmt_storage(new_storage)}"

        if direction == "downgrade" and not seat_count_ok:
            return {
                "status":             "success",
                "eligible":           False,
                "direction":          direction,
                "current_plan_name":  current_plan_name,
                "new_plan_name":      new_plan_name,
                "new_monthly_price":  new_price,
                "new_max_users":      new_max_users,
                "new_storage_gb":     new_storage,
                "current_seat_count": seat_count,
                "seat_count_ok":      False,
                "storage_delta":      storage_delta,
                "reason": (
                    f"Seat count {seat_count} exceeds {new_plan_name} plan limit of {new_max_users}. "
                    "Seats must be reduced before downgrading."
                ),
            }

        return {
            "status":             "success",
            "eligible":           True,
            "direction":          direction,
            "current_plan_name":  current_plan_name,
            "new_plan_name":      new_plan_name,
            "new_monthly_price":  new_price,
            "new_max_users":      new_max_users,
            "new_storage_gb":     new_storage,
            "current_seat_count": seat_count,
            "seat_count_ok":      seat_count_ok,
            "storage_delta":      storage_delta,
        }

    except sqlite3.Error as e:
        return {"status": "error", "message": str(e)}


# =============================================================================
# TEST BLOCK
# =============================================================================
if __name__ == "__main__":
    import os
    DB_PATH = os.path.join(os.path.dirname(__file__), "orbit.db")
    conn = sqlite3.connect(DB_PATH)

    print("=== T9_ValidatePlanChange -- Manual Test Run ===\n")

    print("--- Test 1: Alex (20001) Team -> Business upgrade (8 seats < 30 max) ---")
    print(T9_ValidatePlanChange(conn, 20001, "Business"))

    print("\n--- Test 2: Drew (20007) Business -> Team downgrade BLOCKED (25 seats > 10 max) ---")
    print(T9_ValidatePlanChange(conn, 20007, "Team"))

    print("\n--- Test 3: Quinn (20008) Business -> Team downgrade OK (5 seats < 10 max) ---")
    print(T9_ValidatePlanChange(conn, 20008, "Team"))

    print("\n--- Test 4: Casey (20006) Team -> Enterprise upgrade ---")
    print(T9_ValidatePlanChange(conn, 20006, "Enterprise"))

    print("\n--- Test 5: Plan not found ---")
    print(T9_ValidatePlanChange(conn, 20001, "Platinum"))

    print("\n--- Test 6: Account not found ---")
    print(T9_ValidatePlanChange(conn, 99999, "Business"))

    conn.close()
