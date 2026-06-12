"""
T5_RestoreAccount
-----------------
WHAT THIS TOOL DOES:
    Restores a suspended account to ACTIVE status. Clears the suspension_date
    and sets status to ACTIVE.

WHY IT MATTERS (Business Logic):
    - Called only AFTER the balance is $0 (balance gate enforced by SA1).
    - This is the point of no return for the restore — once called, the account
      is live again and the customer regains access.
    - Called via DA3_RestoreAgent (Squad). DA3 calls T8_SendReceipt immediately after.
    - Never called directly by SA1 or root_agent.

INPUTS:
    conn       : Database connection (injected automatically).
    account_id : Customer's 5-digit ID (e.g., 20001).

OUTPUT:
    Success: {"status": "success", "account_id": ..., "message": "Account restored to ACTIVE."}
    Error:   {"status": "error", "message": "..."}
"""

import sqlite3


def T5_RestoreAccount(conn, account_id):
    """
    Sets account status to ACTIVE and clears suspension_date.

    Args:
        conn       : Active SQLite database connection (injected by agent framework).
        account_id : The customer's 5-digit account ID (e.g., 20001).

    Returns:
        dict: Confirmation that the account has been restored.
    """
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE customer_accounts
            SET status = 'ACTIVE', suspension_date = NULL
            WHERE account_id = ?
        """, (account_id,))

        if cursor.rowcount == 0:
            return {"status": "error", "message": "Account not found."}

        conn.commit()

        return {
            "status":     "success",
            "account_id": account_id,
            "message":    "Account restored to ACTIVE.",
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

    print("=== T5_RestoreAccount -- Manual Test Run ===\n")

    print("--- Test 1: Alex (20001) -- restore SUSPENDED account ---")
    result = T5_RestoreAccount(conn, 20001)
    print(result)

    print("\n--- Verify: Alex status and suspension_date ---")
    cursor = conn.cursor()
    cursor.execute("SELECT status, suspension_date FROM customer_accounts WHERE account_id=20001")
    print(cursor.fetchone())

    print("\n--- Test 2: Account not found ---")
    print(T5_RestoreAccount(conn, 99999))

    conn.close()
    print("\nNOTE: Run z_reset_world.py to restore original account states.")
