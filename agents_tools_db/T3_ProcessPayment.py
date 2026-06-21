"""
T3_ProcessPayment
-----------------
WHAT THIS TOOL DOES:
    Charges the customer's full pending balance. If a new card is provided,
    updates the card on file first (last 4 digits + clears expired flag),
    then charges. Always clears the full balance — no partial payments.

WHY IT MATTERS (Business Logic):
    - The balance gate (STATE 1) ensures there IS a balance before DA2 calls this.
    - The consent gate ensures the customer has said "yes" before this is called.
    - If new_card_last4 is provided: updates card_last4 + sets card_expired=0 in DB,
      then clears pending_balance. This handles the expired card path.
    - If new_card_last4 is None: charges the card already on file (card_expired=0).
    - Returns amount_charged and card_last4_used so SA1 can confirm to the customer.

INPUTS:
    conn            : Database connection (injected automatically).
    account_id      : Customer's 5-digit ID (e.g., 20001).
    new_card_last4  : Last 4 digits of new card as string (e.g., "4321"), or None.

OUTPUT:
    Success: {"status": "success", "amount_charged": 49.00, "card_last4_used": "4321"}
    Error:   {"status": "error", "message": "..."}
"""

import sqlite3
from .log_setup import get_logger

_log = get_logger("tool.T3")


def T3_ProcessPayment(conn, account_id, new_card_last4=None):
    """
    Charges the customer's full pending balance.
    If new_card_last4 is provided, updates card on file before charging.

    Args:
        conn           : Active SQLite database connection (injected by agent framework).
        account_id     : The customer's 5-digit account ID (e.g., 20001).
        new_card_last4 : Last 4 digits of new card (string), or None to use card on file.

    Returns:
        dict: Amount charged and card last 4 used.
    """
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT pending_balance, card_last4 FROM customer_accounts
            WHERE account_id = ?
        """, (account_id,))
        row = cursor.fetchone()

        if not row:
            return {"status": "error", "message": "Account not found."}

        pending_balance, card_on_file = row

        if new_card_last4:
            cursor.execute("""
                UPDATE customer_accounts
                SET card_last4 = ?, card_expired = 0
                WHERE account_id = ?
            """, (new_card_last4, account_id))
            card_last4_used = new_card_last4
        else:
            card_last4_used = card_on_file

        cursor.execute("""
            UPDATE customer_accounts
            SET pending_balance = 0.00
            WHERE account_id = ?
        """, (account_id,))

        conn.commit()

        _log.info(
            f"PAYMENT_OK  account={account_id}  amount={pending_balance:.2f}"
            f"  card_last4={card_last4_used}  new_card={'yes' if new_card_last4 else 'no'}"
        )
        return {
            "status":         "success",
            "amount_charged": pending_balance,
            "card_last4_used": card_last4_used,
        }

    except sqlite3.Error as e:
        _log.error(f"PAYMENT_FAIL  account={account_id}  error={e}")
        return {"status": "error", "message": str(e)}


# =============================================================================
# TEST BLOCK
# =============================================================================
if __name__ == "__main__":
    import os
    DB_PATH = os.path.join(os.path.dirname(__file__), "pay_restore.db")
    conn = sqlite3.connect(DB_PATH)

    print("=== T3_ProcessPayment -- Manual Test Run ===\n")

    print("--- Test 1: Alex (20001) -- new card '4321', charge $49 ---")
    result = T3_ProcessPayment(conn, 20001, new_card_last4="4321")
    print(result)

    print("\n--- Verify: Alex card_last4 and balance updated ---")
    cursor = conn.cursor()
    cursor.execute("SELECT card_last4, card_expired, pending_balance FROM customer_accounts WHERE account_id=20001")
    print(cursor.fetchone())

    print("\n--- Test 2: Jordan (20002) -- card on file, charge $49 ---")
    result = T3_ProcessPayment(conn, 20002)
    print(result)

    print("\n--- Test 3: Casey (20006) -- $0 balance ---")
    result = T3_ProcessPayment(conn, 20006)
    print(result)

    print("\n--- Test 4: Account not found ---")
    print(T3_ProcessPayment(conn, 99999))

    conn.close()
    print("\nNOTE: Run z_reset_world.py to restore original balances.")
