"""
T4_CheckFeeWaiver
-----------------
WHAT THIS TOOL DOES:
    Applies the 3-rule late fee waiver logic. All three rules must pass for
    the customer to receive a $0 late fee. Any single failure returns the
    plan-tier late fee (looked up from plan_catalog).

WHY IT MATTERS (Business Logic):
    - Rule A: tenure_months > 6 (strictly greater than)
    - Rule B: autopay_active = 1
    - Rule C: last_waiver_date is NULL OR older than 12 months
    - SA1 must NEVER infer the waiver result from account data in the transcript.
      The fee result comes ONLY from this tool's output. This is the ground truth rule.
    - Called via DA2_BillingAgent after payment clears.
    - Waiving the fee does NOT happen automatically — SA1 reports the result and
      the customer is informed. This tool only CHECKS eligibility.

INPUTS:
    conn       : Database connection (injected automatically).
    account_id : Customer's 5-digit ID (e.g., 20001).

OUTPUT:
    {"status": "success", "waiver_granted": True,  "late_fee_amount": 0.00,  "reason": "All rules passed."}
    {"status": "success", "waiver_granted": False, "late_fee_amount": 25.00, "reason": "Rule A failed: ..."}
    {"status": "error",   "message": "..."}
"""

import sqlite3
from datetime import date


def T4_CheckFeeWaiver(conn, account_id):
    """
    Checks late fee waiver eligibility using 3-rule logic.
    Looks up the plan-tier late fee from plan_catalog if waiver is denied.

    Args:
        conn       : Active SQLite database connection (injected by agent framework).
        account_id : The customer's 5-digit account ID (e.g., 20001).

    Returns:
        dict: waiver_granted (bool), late_fee_amount, and reason string.
    """
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT ca.tenure_months, ca.autopay_active, ca.last_waiver_date,
                   pc.late_fee, ca.plan_name
            FROM customer_accounts ca
            JOIN plan_catalog pc ON ca.plan_name = pc.plan_name
            WHERE ca.account_id = ?
        """, (account_id,))
        row = cursor.fetchone()

        if not row:
            return {"status": "error", "message": "Account not found."}

        tenure_months, autopay_active, last_waiver_date_str, late_fee, plan_name = row

        today = date.today()

        # Rule A: tenure strictly greater than 6 months
        rule_a = tenure_months > 6

        # Rule B: autopay must be active
        rule_b = bool(autopay_active)

        # Rule C: no waiver used in the past 12 months
        if last_waiver_date_str:
            last_waiver = date.fromisoformat(last_waiver_date_str)
            rule_c = (today - last_waiver).days > 365
        else:
            rule_c = True

        if rule_a and rule_b and rule_c:
            return {
                "status":         "success",
                "waiver_granted": True,
                "late_fee_amount": 0.00,
                "reason": (
                    f"you've been with us for {tenure_months:.0f} months, "
                    f"had AutoPay enabled, and haven't used a waiver in the past 12 months"
                ),
            }

        # Build failure reason (customer-facing — no internal labels)
        failures = []
        if not rule_a:
            failures.append(
                f"your account is {tenure_months:.0f} months old, which does not meet the 6-month minimum"
            )
        if not rule_b:
            failures.append("AutoPay was not enabled on your account")
        if not rule_c:
            days_since_waiver = (today - date.fromisoformat(last_waiver_date_str)).days
            failures.append(
                f"a waiver was applied {days_since_waiver} days ago, within the 12-month window"
            )

        return {
            "status":          "success",
            "waiver_granted":  False,
            "late_fee_amount": late_fee,
            "reason":          ", and ".join(failures),
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

    print("=== T4_CheckFeeWaiver -- Manual Test Run ===\n")

    print("--- Test 1: Alex (20001) -- 9mo, autopay ON, no prior waiver -> PASS ---")
    print(T4_CheckFeeWaiver(conn, 20001))

    print("\n--- Test 2: Jordan (20002) -- 2mo, autopay OFF -> FAIL Rule A + B ---")
    print(T4_CheckFeeWaiver(conn, 20002))

    print("\n--- Test 3: Riley (20004) -- 7mo, autopay ON, waiver 90d ago -> FAIL Rule C ---")
    print(T4_CheckFeeWaiver(conn, 20004))

    print("\n--- Test 4: Morgan (20005) -- 18mo, autopay OFF -> FAIL Rule B ---")
    print(T4_CheckFeeWaiver(conn, 20005))

    print("\n--- Test 5: Jamie (20009) -- 6.0mo exactly -> FAIL Rule A (boundary) ---")
    print(T4_CheckFeeWaiver(conn, 20009))

    print("\n--- Test 6: Avery (20010) -- 30mo, autopay ON -> PASS (Enterprise $0 fee) ---")
    print(T4_CheckFeeWaiver(conn, 20010))

    conn.close()
