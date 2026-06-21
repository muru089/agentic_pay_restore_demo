"""
T7_GetBalance
-------------
WHAT THIS TOOL DOES:
    Read-only balance check. Returns the customer's current pending balance
    without making any changes to the database.

WHY IT MATTERS (Business Logic):
    - SA1 calls this in STATE 1 (Balance Gate) to determine whether to ask
      for payment before restoring. If balance = $0, payment step is skipped.
    - Intentionally separate from T3_ProcessPayment — these are different
      operations and must never be conflated.

INPUTS:
    conn       : Database connection (injected automatically).
    account_id : Customer's 5-digit ID (e.g., 20001).

OUTPUT:
    Found:     {"status": "success", "account_id": ..., "pending_balance": 49.00}
    Not found: {"status": "error",   "message": "Account not found."}
"""

import sqlite3


def T7_GetBalance(conn, account_id):
    """
    Read-only balance lookup. Does NOT charge the customer.

    Args:
        conn       : Active SQLite database connection (injected by agent framework).
        account_id : The customer's 5-digit account ID (e.g., 20001).

    Returns:
        dict: The current pending balance.
    """
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT pending_balance FROM customer_accounts WHERE account_id = ?",
            (account_id,)
        )
        row = cursor.fetchone()

        if not row:
            return {"status": "error", "message": "Account not found."}

        return {
            "status":          "success",
            "account_id":      account_id,
            "pending_balance": row[0],
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

    print("=== T7_GetBalance -- Manual Test Run ===\n")

    print("--- Test 1: Alex (20001) -- should have $49.00 ---")
    print(T7_GetBalance(conn, 20001))

    print("\n--- Test 2: Casey (20006) -- should have $0.00 (ACTIVE) ---")
    print(T7_GetBalance(conn, 20006))

    print("\n--- Test 3: Avery (20010) -- should have $399.00 (Enterprise) ---")
    print(T7_GetBalance(conn, 20010))

    print("\n--- Test 4: Account not found ---")
    print(T7_GetBalance(conn, 99999))

    conn.close()
