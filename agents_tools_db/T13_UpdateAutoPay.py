"""
T13_UpdateAutoPay
-----------------
WHAT THIS TOOL DOES:
    Enables or disables AutoPay on a customer's account.
    Non-destructive — no charge is made. No consent gate required.

WHY IT MATTERS (Business Logic):
    - AutoPay status directly affects late fee waiver eligibility (Rule B).
    - Enabling AutoPay on a suspended account BEFORE paying means T4 will
      re-evaluate Rule B at payment time, which may grant the waiver for
      customers who previously failed only on Rule B.
    - Disabling AutoPay is always allowed — customer's explicit preference.
    - Returns the updated autopay_active state for confirmation.

INPUTS:
    conn       : Database connection (injected automatically).
    account_id : Customer's 5-digit ID (e.g., 20005).
    enabled    : 1 to enable AutoPay, 0 to disable AutoPay.

OUTPUT:
    Success: {"status": "success", "account_id": 20005, "autopay_active": 1}
    Error:   {"status": "error", "message": "..."}
"""

import sqlite3
from .log_setup import get_logger

_log = get_logger("tool.T13")


def T13_UpdateAutoPay(conn, account_id, enabled):
    """
    Enables or disables AutoPay for the given account.
    Non-destructive — no payment is processed. No consent gate required.

    Args:
        conn       : Active SQLite database connection (injected by agent framework).
        account_id : The customer's 5-digit account ID (e.g., 20005).
        enabled    : 1 to enable AutoPay, 0 to disable AutoPay.

    Returns:
        dict: Updated AutoPay status or error.
    """
    enabled_int = int(enabled)
    if enabled_int not in (0, 1):
        return {"status": "error", "message": "enabled must be 0 (disable) or 1 (enable)."}

    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE customer_accounts SET autopay_active = ? WHERE account_id = ?",
            (enabled_int, account_id),
        )
        if cursor.rowcount == 0:
            return {"status": "error", "message": f"Account {account_id} not found."}
        conn.commit()

        action = "enabled" if enabled_int else "disabled"
        _log.info(f"AUTOPAY_{action.upper()}  account={account_id}")
        return {
            "status":        "success",
            "account_id":    account_id,
            "autopay_active": enabled_int,
        }
    except sqlite3.Error as e:
        _log.error(f"AUTOPAY_FAIL  account={account_id}  error={e}")
        return {"status": "error", "message": str(e)}


# =============================================================================
# TEST BLOCK
# =============================================================================
if __name__ == "__main__":
    import os
    DB_PATH = os.path.join(os.path.dirname(__file__), "orbit.db")
    conn = sqlite3.connect(DB_PATH)

    print("=== T13_UpdateAutoPay -- Manual Test Run ===\n")

    print("--- Test 1: Morgan (20005) -- enable AutoPay (was OFF) ---")
    result = T13_UpdateAutoPay(conn, 20005, enabled=1)
    print(result)

    cursor = conn.cursor()
    cursor.execute("SELECT autopay_active FROM customer_accounts WHERE account_id=20005")
    print("DB autopay_active:", cursor.fetchone())

    print("\n--- Test 2: Morgan (20005) -- disable AutoPay ---")
    result = T13_UpdateAutoPay(conn, 20005, enabled=0)
    print(result)

    print("\n--- Test 3: Casey (20006, ACTIVE) -- disable AutoPay ---")
    result = T13_UpdateAutoPay(conn, 20006, enabled=0)
    print(result)

    print("\n--- Test 4: Account not found ---")
    print(T13_UpdateAutoPay(conn, 99999, enabled=1))

    print("\n--- Test 5: Invalid enabled value ---")
    print(T13_UpdateAutoPay(conn, 20001, enabled=2))

    conn.close()
    print("\nNOTE: Run z_reset_world.py to restore original AutoPay settings.")
