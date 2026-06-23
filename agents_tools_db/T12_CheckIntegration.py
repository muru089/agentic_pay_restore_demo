"""
T12_CheckIntegration
--------------------
WHAT THIS TOOL DOES:
    Returns the current health of the account's connected integration
    (e.g., Slack, GitHub, Jira) and flags whether action is required.

WHY IT MATTERS:
    An integration in auth_failure or sync_error state causes changes to
    stop appearing in projects and can look like a platform problem to the
    customer ("things aren't syncing", "account feels broken").
    SA1_DiagnosticSupervisor uses this alongside T11 and T2 to pinpoint
    the actual culprit. DA6_IntegrationAgent is the only caller.

INPUTS:
    conn       : Database connection (injected automatically).
    account_id : Customer's 5-digit ID (e.g., 20013).

STATUS VALUES:
    "healthy"       — integration connected and syncing normally
    "auth_failure"  — authentication token expired or revoked (action required)
    "sync_error"    — connection alive but sync is failing (action required)
    "disconnected"  — integration was removed or never connected (action required)
    "none"          — account has no integration configured (not an error)

OUTPUT (success):
    {
        "status":           "success",
        "integration_name": str | None,
        "integration_status": str,
        "last_sync":        str | None,   # "YYYY-MM-DD" or None
        "auth_failures":    int,
        "action_required":  bool,         # True for auth_failure / sync_error / disconnected
        "days_since_sync":  int | None
    }
OUTPUT (error):
    {"status": "error", "message": "..."}
"""

import sqlite3
from datetime import date

ACTION_REQUIRED_STATUSES = {"auth_failure", "sync_error", "disconnected"}


def T12_CheckIntegration(conn, account_id):
    """
    Returns integration health and whether reconnection is needed.

    Args:
        conn       : Active SQLite connection (injected by agent framework).
        account_id : 5-digit account ID (integer).

    Returns:
        dict with integration_name, integration_status, last_sync,
        auth_failures, action_required, days_since_sync.
    """
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT integration_name, integration_status,
                   integration_last_sync, integration_auth_failures
            FROM   customer_accounts
            WHERE  account_id = ?
        """, (account_id,))
        row = cursor.fetchone()

        if not row:
            return {"status": "error", "message": f"Account {account_id} not found."}

        name, integ_status, last_sync_str, auth_failures = row

        # Treat NULL / 'None' string as no integration
        if not name or name.lower() == "none":
            return {
                "status":             "success",
                "integration_name":   None,
                "integration_status": "none",
                "last_sync":          None,
                "auth_failures":      0,
                "action_required":    False,
                "days_since_sync":    None,
            }

        action_required = integ_status in ACTION_REQUIRED_STATUSES

        days_since_sync = None
        if last_sync_str:
            try:
                last_sync_date  = date.fromisoformat(last_sync_str)
                days_since_sync = (date.today() - last_sync_date).days
            except ValueError:
                pass

        return {
            "status":             "success",
            "integration_name":   name,
            "integration_status": integ_status,
            "last_sync":          last_sync_str,
            "auth_failures":      auth_failures or 0,
            "action_required":    action_required,
            "days_since_sync":    days_since_sync,
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

    print("=== T12_CheckIntegration -- Manual Test Run ===\n")

    print("--- Test 1: Blake 20013 (GitHub auth_failure, 5 failures) ---")
    print(T12_CheckIntegration(conn, 20013))

    print("\n--- Test 2: Taylor 20012 (Slack healthy) ---")
    print(T12_CheckIntegration(conn, 20012))

    print("\n--- Test 3: Sam 20003 (Jira sync_error — suspended 35d) ---")
    print(T12_CheckIntegration(conn, 20003))

    print("\n--- Test 4: Riley 20004 (no integration) ---")
    print(T12_CheckIntegration(conn, 20004))

    print("\n--- Test 5: Account not found ---")
    print(T12_CheckIntegration(conn, 99999))

    conn.close()
