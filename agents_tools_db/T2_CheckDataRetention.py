"""
T2_CheckDataRetention
---------------------
WHAT THIS TOOL DOES:
    Calculates how many days an account has been suspended and determines
    whether the customer's project data is safe or at risk of purge.

WHY IT MATTERS (Business Logic):
    - Platform policy: data is retained for 30 days post-suspension.
    - If days_suspended > 30, projects may have been archived or purged.
    - SA1 uses this in STATE 2. If data_safe=False, SA1 must issue a SOFT STOP
      and present the customer with two paths (proceed or speak with data team)
      before continuing the restore flow.
    - Called via DA1_AccountAgent, not directly by SA1.

INPUTS:
    conn       : Database connection (injected automatically).
    account_id : Customer's 5-digit ID (e.g., 20001).

OUTPUT:
    {"status": "success", "data_safe": True/False,
     "days_suspended": int, "project_count": int,
     "data_retention_days": 30}
    {"status": "error", "message": "..."}
"""

import sqlite3
from datetime import date


def T2_CheckDataRetention(conn, account_id):
    """
    Checks data retention safety for a suspended account.

    Args:
        conn       : Active SQLite database connection (injected by agent framework).
        account_id : The customer's 5-digit account ID (e.g., 20001).

    Returns:
        dict: data_safe flag, days_suspended, project_count, data_retention_days.
    """
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT suspension_date, project_count, data_retention_days
            FROM customer_accounts
            WHERE account_id = ?
        """, (account_id,))
        row = cursor.fetchone()

        if not row:
            return {"status": "error", "message": "Account not found."}

        suspension_date_str, project_count, retention_days = row

        if not suspension_date_str:
            return {
                "status":             "success",
                "data_safe":          True,
                "days_suspended":     0,
                "project_count":      project_count,
                "data_retention_days": retention_days,
            }

        suspension_date = date.fromisoformat(suspension_date_str)
        days_suspended  = (date.today() - suspension_date).days
        data_safe       = days_suspended <= retention_days

        return {
            "status":              "success",
            "data_safe":           data_safe,
            "days_suspended":      days_suspended,
            "project_count":       project_count,
            "data_retention_days": retention_days,
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

    print("=== T2_CheckDataRetention -- Manual Test Run ===\n")

    print("--- Test 1: Alex (20001) -- 5 days, data SAFE ---")
    print(T2_CheckDataRetention(conn, 20001))

    print("\n--- Test 2: Sam (20003) -- 35 days, data AT RISK ---")
    print(T2_CheckDataRetention(conn, 20003))

    print("\n--- Test 3: Casey (20006) -- ACTIVE, no suspension ---")
    print(T2_CheckDataRetention(conn, 20006))

    print("\n--- Test 4: Account not found ---")
    print(T2_CheckDataRetention(conn, 99999))

    conn.close()
