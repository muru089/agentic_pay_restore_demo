"""
T11_CheckStorage
----------------
WHAT THIS TOOL DOES:
    Checks current storage consumption against the account's plan limit.
    Returns whether the account is approaching its storage ceiling.

WHY IT MATTERS:
    Storage near-capacity (>= 90%) causes upload failures and slow project
    access — symptoms that read as "something feels off" to the customer.
    SA1_DiagnosticSupervisor uses this alongside T12 and T2 to pinpoint
    the highest-impact issue. DA5_StorageAgent is the only caller.

INPUTS:
    conn       : Database connection (injected automatically).
    account_id : Customer's 5-digit ID (e.g., 20012).

OUTPUT (success):
    {
        "status":         "success",
        "storage_used_gb": float,
        "plan_storage_gb": int,
        "used_pct":        float,        # 0–100
        "near_limit":      bool,         # True if used_pct >= 90
        "headroom_gb":     float,
        "plan_name":       str
    }
OUTPUT (error):
    {"status": "error", "message": "..."}
"""

import sqlite3

NEAR_LIMIT_THRESHOLD_PCT = 90.0


def T11_CheckStorage(conn, account_id):
    """
    Returns storage usage stats for an account.

    Args:
        conn       : Active SQLite connection (injected by agent framework).
        account_id : 5-digit account ID (integer).

    Returns:
        dict with storage_used_gb, plan_storage_gb, used_pct, near_limit,
        headroom_gb, plan_name.
    """
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT ca.storage_used_gb, pc.storage_gb, ca.plan_name
            FROM   customer_accounts ca
            JOIN   plan_catalog      pc ON pc.plan_name = ca.plan_name
            WHERE  ca.account_id = ?
        """, (account_id,))
        row = cursor.fetchone()

        if not row:
            return {"status": "error", "message": f"Account {account_id} not found."}

        used_gb, plan_gb, plan_name = row

        if used_gb is None:
            return {"status": "error", "message": f"No storage data for account {account_id}."}

        used_pct   = (used_gb / plan_gb) * 100 if plan_gb else 0.0
        near_limit = used_pct >= NEAR_LIMIT_THRESHOLD_PCT
        headroom   = max(0.0, plan_gb - used_gb)

        return {
            "status":          "success",
            "storage_used_gb": round(used_gb, 1),
            "plan_storage_gb": plan_gb,
            "used_pct":        round(used_pct, 1),
            "near_limit":      near_limit,
            "headroom_gb":     round(headroom, 1),
            "plan_name":       plan_name,
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

    print("=== T11_CheckStorage -- Manual Test Run ===\n")

    print("--- Test 1: Taylor 20012 (Team, 95/100 GB — near limit) ---")
    print(T11_CheckStorage(conn, 20012))

    print("\n--- Test 2: Blake 20013 (Business, 45/500 GB — healthy) ---")
    print(T11_CheckStorage(conn, 20013))

    print("\n--- Test 3: Drew 20007 (Business, 380/500 GB — warning zone) ---")
    print(T11_CheckStorage(conn, 20007))

    print("\n--- Test 4: Account not found ---")
    print(T11_CheckStorage(conn, 99999))

    conn.close()
