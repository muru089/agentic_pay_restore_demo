"""
T1_GetAccount
-------------
WHAT THIS TOOL DOES:
    Authenticates a customer by account ID and returns the full account
    snapshot needed by root_agent for routing and by SA1 for state reconstruction.

WHY IT MATTERS (Business Logic):
    - First tool called on every conversation. Root_agent uses it to determine
      routing: SUSPENDED → SA1, ACTIVE → DA1/DA2/DA4 directly, CANCELED → win-back.
    - card_expired is returned here so SA1 can determine the card flow in STATE 3
      without calling a separate tool.
    - SA1 reads card_expired from this tool's output in the transcript — it never
      needs to re-query the DB for card state.

INPUTS:
    conn       : Database connection (injected automatically).
    account_id : Customer's 5-digit ID (e.g., 20001).

OUTPUT:
    Found:     {"status": "success", "account_id": ..., "first_name": ...,
                "company_name": ..., "plan_name": ..., "account_status": ...,
                "tenure_months": ..., "card_last4": ..., "card_expired": ...,
                "suspension_date": ..., "project_count": ..., "pending_balance": ...}
    Not found: {"status": "error", "message": "Account not found."}
"""

import sqlite3


def T1_GetAccount(conn, account_id):
    """
    Authenticates a customer and returns the full account snapshot for routing.

    Args:
        conn       : Active SQLite database connection (injected by agent framework).
        account_id : The customer's 5-digit account ID (e.g., 20001).

    Returns:
        dict: Full account snapshot including status, card state, and suspension info.
    """
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT account_id, first_name, company_name, plan_name, status,
                   tenure_months, card_last4, card_expired, suspension_date,
                   project_count, pending_balance
            FROM customer_accounts
            WHERE account_id = ?
        """, (account_id,))
        row = cursor.fetchone()

        if not row:
            return {"status": "error", "message": "Account not found."}

        return {
            "status":          "success",
            "account_id":      row[0],
            "first_name":      row[1],
            "company_name":    row[2],
            "plan_name":       row[3],
            "account_status":  row[4],
            "tenure_months":   row[5],
            "card_last4":      row[6],
            "card_expired":    bool(row[7]),
            "suspension_date": row[8],
            "project_count":   row[9],
            "pending_balance": row[10],
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

    print("=== T1_GetAccount -- Manual Test Run ===\n")

    print("--- Test 1: Alex (20001) -- SUSPENDED, expired card ---")
    print(T1_GetAccount(conn, 20001))

    print("\n--- Test 2: Casey (20006) -- ACTIVE, valid card ---")
    print(T1_GetAccount(conn, 20006))

    print("\n--- Test 3: Parker (20011) -- CANCELED ---")
    print(T1_GetAccount(conn, 20011))

    print("\n--- Test 4: Account not found ---")
    print(T1_GetAccount(conn, 99999))

    conn.close()
