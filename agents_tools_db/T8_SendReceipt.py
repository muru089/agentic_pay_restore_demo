"""
T8_SendReceipt
--------------
WHAT THIS TOOL DOES:
    Generates a formatted confirmation receipt at the end of a completed
    transaction. Looks up the customer's email and produces a summary block
    the agent can reference when saying "I'll send you a confirmation now."

WHY IT MATTERS (Business Logic):
    - Called at the END of every completed flow: DA3 (after restore),
      DA4 (after plan change), DA2 (after payment if needed standalone).
    - Receipt is action-specific: RESTORE includes project count, PAYMENT
      includes amount charged, UPGRADE/DOWNGRADE includes new plan and
      downgrade_date (if temporary).
    - A random Order Reference ID (e.g., #ORD-9X21B) gives the customer
      something to quote if they call back.

SPECIAL NOTE — NO conn INJECTION:
    T8 opens its own database connection internally. Do NOT wrap with
    create_db_tool. Register directly as FunctionTool(T8_SendReceipt).

INPUTS:
    account_id  : Customer's 5-digit ID (used to look up email).
    action_type : "RESTORE", "PAYMENT", "UPGRADE", or "DOWNGRADE".
    details     : Dict with action-specific fields (see below per action type).

OUTPUT:
    {"status": "success", "order_ref": "#ORD-XXXXX", "receipt_text": "..."}
"""

import os
import uuid
import sqlite3


def T8_SendReceipt(account_id, action_type, details=None):
    """
    Generates a formatted confirmation receipt for a completed transaction.
    Opens its own DB connection to fetch customer email and plan info.

    Args:
        account_id  : The customer's 5-digit account ID.
        action_type : "RESTORE", "PAYMENT", "UPGRADE", or "DOWNGRADE".
        details     : Dict of action-specific context. Can be empty or omitted.

    Returns:
        dict: Order reference ID and fully formatted receipt text block.
    """
    db_path = os.path.join(os.path.dirname(__file__), "orbit.db")
    conn    = sqlite3.connect(db_path)
    cursor  = conn.cursor()

    customer_email   = "No Email On File"
    customer_name    = "Valued Customer"

    try:
        cursor.execute(
            "SELECT email, first_name FROM customer_accounts WHERE account_id = ?",
            (account_id,)
        )
        row = cursor.fetchone()
        if row:
            if row[0]:
                customer_email = row[0]
            if row[1]:
                customer_name = row[1]
    except Exception as e:
        print(f"[T8] Email lookup failed: {e}")
    finally:
        conn.close()

    order_ref = f"#ORD-{uuid.uuid4().hex[:6].upper()}"

    if not details:
        details = {}

    lines = []
    lines.append(f"ORDER CONFIRMATION: {order_ref}")
    lines.append(f"Sent to: {customer_email}")
    lines.append("-" * 40)

    if action_type == "RESTORE":
        project_count = details.get("project_count", "N/A")
        plan_name     = details.get("plan_name", "")
        amount_paid   = details.get("amount_paid", 0.00)
        data_at_risk  = details.get("data_at_risk", False)

        lines.append("Action          : Account Restored")
        lines.append(f"Account Status  : ACTIVE")
        lines.append(f"Plan            : {plan_name}")
        lines.append(f"Amount Paid     : ${amount_paid:.2f}")
        if data_at_risk:
            lines.append("Projects        : Data retention review recommended — check your dashboard")
        else:
            lines.append(f"Projects        : {project_count} projects confirmed intact")
        lines.append("-" * 40)
        lines.append("Your account is fully restored. Welcome back!")

    elif action_type == "PAYMENT":
        amount = details.get("amount", 0.00)
        card   = details.get("card_last4", "****")

        lines.append("Action          : Payment Received")
        lines.append(f"Amount Paid     : ${amount:.2f}")
        lines.append(f"Card Charged    : ending in {card}")
        lines.append(f"Balance         : $0.00 (paid in full)")
        lines.append("-" * 40)
        lines.append("Thank you for your payment!")

    elif action_type == "UPGRADE":
        new_plan      = details.get("new_plan_name", "")
        new_price     = details.get("new_monthly_price", 0.00)
        storage       = details.get("new_storage_gb", "")
        downgrade_date = details.get("downgrade_date", None)

        lines.append("Action          : Plan Upgraded")
        lines.append(f"New Plan        : {new_plan}")
        lines.append(f"Monthly Rate    : ${new_price:.2f}/mo")
        lines.append(f"Storage         : {storage} GB")
        if downgrade_date:
            lines.append(f"Auto-Reverts On : {downgrade_date}")
            lines.append("Note            : Plan reverts automatically on the above date.")
        else:
            lines.append("Duration        : Permanent (effective next billing cycle)")
        lines.append("-" * 40)
        lines.append("Plan upgrade confirmed. Changes take effect next billing cycle.")

    elif action_type == "DOWNGRADE":
        new_plan  = details.get("new_plan_name", "")
        new_price = details.get("new_monthly_price", 0.00)
        storage   = details.get("new_storage_gb", "")

        lines.append("Action          : Plan Downgraded")
        lines.append(f"New Plan        : {new_plan}")
        lines.append(f"Monthly Rate    : ${new_price:.2f}/mo")
        lines.append(f"Storage         : {storage} GB")
        lines.append("Duration        : Permanent (effective next billing cycle)")
        lines.append("-" * 40)
        lines.append("Plan downgrade confirmed. Changes take effect next billing cycle.")

    else:
        lines.append(f"Action          : {action_type}")
        lines.append("Transaction completed successfully.")

    return {
        "status":       "success",
        "order_ref":    order_ref,
        "receipt_text": "\n".join(lines),
    }


# =============================================================================
# TEST BLOCK
# =============================================================================
if __name__ == "__main__":
    print("=== T8_SendReceipt -- Manual Test Run ===\n")

    print("--- Test 1: RESTORE receipt for Alex (20001) ---")
    result = T8_SendReceipt(20001, "RESTORE", {
        "project_count": 12,
        "plan_name":     "Team",
        "amount_paid":   49.00,
    })
    print(result["receipt_text"])

    print("\n--- Test 2: PAYMENT receipt ---")
    result = T8_SendReceipt(20001, "PAYMENT", {"amount": 49.00, "card_last4": "4321"})
    print(result["receipt_text"])

    print("\n--- Test 3: UPGRADE receipt with 3-month duration ---")
    result = T8_SendReceipt(20001, "UPGRADE", {
        "new_plan_name":     "Business",
        "new_monthly_price": 129.00,
        "new_storage_gb":    500,
        "downgrade_date":    "2026-09-07",
    })
    print(result["receipt_text"])

    print("\n--- Test 4: DOWNGRADE receipt ---")
    result = T8_SendReceipt(20008, "DOWNGRADE", {
        "new_plan_name":     "Team",
        "new_monthly_price": 49.00,
        "new_storage_gb":    100,
    })
    print(result["receipt_text"])
