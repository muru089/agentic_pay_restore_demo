"""
z_reset_world.py -- Pay Restore Demo: Database Reset Script
--------------------------------------------------------------------
WHAT THIS SCRIPT DOES:
    Completely wipes pay_restore.db and rebuilds it from scratch with all
    original seed data. Run this any time you want to return the demo to
    its "Day 1" state (e.g., after a live demo mutated balances or accounts).

HOW TO RUN:
    py pay_restore_demo/z_reset_world.py
    (Run from c:\\Muru_Workspace — the PARENT of pay_restore_demo.)

TABLES CREATED:
    1. plan_catalog       -- 5 subscription tiers (Starter → Enterprise)
    2. customer_accounts  -- 20 accounts (10 Active/Suspended + 10 Canceled)

IMPORTANT NOTES:
    - plan_name in customer_accounts must exactly match plan_name in plan_catalog.
    - tenure_months stores tenure as months (not years). Fee waiver Rule A: tenure_months > 6.
    - suspension_date is calculated dynamically from today (not hardcoded) so the
      data_retention_days check (T2) remains accurate on any run date.
    - Sam (20003): 35 days suspended → DATA AT RISK (> 30-day window).
    - Jamie (20009): exactly 6.0 months tenure → waiver FAIL (Rule A requires strictly > 6).
    - data_retention_days is always 30 for all accounts (platform-wide policy).
"""

import sqlite3
import os
from datetime import datetime, timedelta


def reset_world():
    """
    Drops and recreates all tables, then seeds the full Pay Restore dataset.
    Deletes the old .db file first for a truly clean slate.
    """

    db_path = os.path.join(os.path.dirname(__file__), "pay_restore.db")

    # Delete the old DB file to guarantee no stale schema or data carries over.
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            print("  Deleted old database file.")
        except PermissionError:
            print("  Could not delete file (it may be locked). Attempting to drop tables instead.")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("--- INITIATING GLOBAL RESET ---\n")

    # =========================================================================
    # STEP 1: CREATE TABLES
    # Drop first (in case the delete above failed and old tables exist).
    # =========================================================================

    # --- plan_catalog ---
    # 5 tiers. plan_name is the join key used by all billing tools.
    cursor.execute("DROP TABLE IF EXISTS plan_catalog")
    cursor.execute("""
        CREATE TABLE plan_catalog (
            plan_id       TEXT PRIMARY KEY,
            plan_name     TEXT,
            monthly_price REAL,
            max_users     INTEGER,   -- NULL = unlimited (Enterprise)
            storage_gb    INTEGER    -- storage quota in GB
        )
    """)

    # --- customer_accounts ---
    # One row per account. status: "ACTIVE", "SUSPENDED", or "CANCELED".
    # SUSPENDED = failed payment; account locked until restored.
    cursor.execute("DROP TABLE IF EXISTS customer_accounts")
    cursor.execute("""
        CREATE TABLE customer_accounts (
            account_id          INTEGER PRIMARY KEY,   -- 5-digit: 20001-20020
            first_name          TEXT,
            company_name        TEXT,
            plan_name           TEXT,                  -- FK to plan_catalog.plan_name
            tenure_months       REAL,                  -- months on platform
            autopay_active      INTEGER,               -- 1 = True, 0 = False
            waivers_used_12m    INTEGER,               -- 1 = True, 0 = False
            pending_balance     REAL,
            status              TEXT,                  -- "ACTIVE" | "SUSPENDED" | "CANCELED"
            email               TEXT,
            card_last4          TEXT,                  -- last 4 digits of card on file
            suspension_date     TEXT,                  -- "YYYY-MM-DD" or NULL
            last_waiver_date    TEXT,                  -- "YYYY-MM-DD" or NULL
            seat_count          INTEGER,               -- active seats in use
            project_count       INTEGER,               -- number of active projects
            data_retention_days INTEGER                -- days data kept post-suspension (always 30)
        )
    """)

    print("Tables created.\n")

    # =========================================================================
    # STEP 2: SEED PLAN CATALOG
    # 5 tiers: Starter → Enterprise. Storage in GB (2 TB = 2048, 10 TB = 10240).
    # plan_name values here must match exactly what customer_accounts.plan_name uses.
    # =========================================================================
    plans = [
        ('P001', 'Starter',      29.00,    5,    20),
        ('P002', 'Professional', 79.00,   15,   100),
        ('P003', 'Premium',     149.00,   50,   500),
        ('P004', 'Business',    249.00,  150,  2048),
        ('P005', 'Enterprise',  499.00, None, 10240),
    ]
    cursor.executemany("INSERT INTO plan_catalog VALUES (?,?,?,?,?)", plans)
    print(f"Plan Catalog: {len(plans)} plans loaded.")

    # =========================================================================
    # STEP 3: SEED CUSTOMER ACCOUNTS
    #
    # GROUP A — Active / Suspended (20001–20010):
    #   10 demo personas. Mix of ACTIVE and SUSPENDED for restore demos.
    #   suspension_date calculated dynamically from today to keep T2 accurate.
    #
    # GROUP B — Canceled (20011–20020):
    #   Generic churned accounts on Professional plan. Used for win-back demos.
    #
    # KEY NOTES:
    #   - Fee Waiver Rule A: tenure_months > 6 (strictly greater than)
    #   - Sam (20003): 35 days suspended → data AT RISK (> 30-day window)
    #   - Jamie (20009): exactly 6.0 months → boundary FAIL on Rule A
    #   - Jordan (20002): 2mo tenure → FAIL Rule A; autopay OFF → FAIL Rule B
    #   - Morgan (20005): autopay OFF → FAIL Rule B (even with 18mo tenure)
    # =========================================================================

    today = datetime.now()

    def susp_date(days_ago):
        """Return ISO date string for a suspension that occurred N days ago."""
        return (today - timedelta(days=days_ago)).strftime("%Y-%m-%d")

    # Columns: account_id, first_name, company_name, plan_name, tenure_months,
    #          autopay_active, waivers_used_12m, pending_balance, status,
    #          email, card_last4, suspension_date, last_waiver_date,
    #          seat_count, project_count, data_retention_days
    customers = [
        # --- Group A: Active / Suspended ---

        # 20001 Alex: 9mo, autopay ON, $79 balance, SUSPENDED 5 days
        #   Waiver: PASS (9>6, autopay=1, no prior waiver) → $0 fee
        #   Data: SAFE (5 days < 30). Primary demo persona. Upgrade to Premium requested.
        (20001, 'Alex',   'Wavefront',   'Professional', 9.0,  1, 0,  79.00, 'SUSPENDED',
         'alex@wavefront.io',   '4242', susp_date(5),  None, 8,  12, 30),

        # 20002 Jordan: 2mo, autopay OFF, $79 balance, SUSPENDED 5 days
        #   Waiver: FAIL Rule A (2mo < 6) + Rule B (autopay OFF) → $25 fee
        #   Data: SAFE (5 days).
        (20002, 'Jordan', 'Sprinto',     'Professional', 2.0,  0, 0,  79.00, 'SUSPENDED',
         'jordan@sprinto.com',  '7890', susp_date(5),  None, 2,   3, 30),

        # 20003 Sam: 14mo, autopay ON, $149 balance, SUSPENDED 35 days
        #   Waiver: PASS → $0 fee
        #   Data: AT RISK (35 days > 30-day window). Projects may be purged.
        (20003, 'Sam',    'Arclight',    'Premium',     14.0,  1, 0, 149.00, 'SUSPENDED',
         'sam@arclight.co',     '1111', susp_date(35), None, 15, 28, 30),

        # 20004 Riley: 7mo, autopay ON, $29 balance, SUSPENDED 10 days
        #   Waiver: PASS → $0 fee. Data: SAFE. Small balance, easy restore.
        (20004, 'Riley',  'Nomad Labs',  'Starter',      7.0,  1, 0,  29.00, 'SUSPENDED',
         'riley@nomadlabs.io',  '5555', susp_date(10), None, 1,   4, 30),

        # 20005 Morgan: 18mo, autopay OFF, $249 balance, SUSPENDED 3 days
        #   Waiver: FAIL Rule B (autopay OFF) → $25 fee. Data: SAFE.
        (20005, 'Morgan', 'Crestline',   'Business',    18.0,  0, 0, 249.00, 'SUSPENDED',
         'morgan@crestline.co', '9999', susp_date(3),  None, 30, 45, 30),

        # 20006 Casey: 8mo, autopay ON, $0, ACTIVE
        #   No restore needed. Used for standalone billing / upgrade demos.
        (20006, 'Casey',  'Driftwood',   'Professional', 8.0,  1, 0,   0.00, 'ACTIVE',
         'casey@driftwood.io',  '3333', None,           None, 5,  10, 30),

        # 20007 Drew: 1mo, autopay OFF, $0, ACTIVE
        #   New customer. Used for plan info demos. Waiver FAIL if upgrade billed.
        (20007, 'Drew',   'Lumen Co',    'Starter',      1.0,  0, 0,   0.00, 'ACTIVE',
         'drew@lumenko.com',    '6666', None,           None, 1,   2, 30),

        # 20008 Quinn: 24mo, autopay ON, $0, ACTIVE
        #   Long-tenure power user. Used for billing / autopay toggle demos.
        (20008, 'Quinn',  'Pathfinder',  'Premium',     24.0,  1, 0,   0.00, 'ACTIVE',
         'quinn@pathfinder.ai', '2222', None,           None, 20, 18, 30),

        # 20009 Jamie: 6.0mo exactly, autopay ON, $149 balance, SUSPENDED 20 days
        #   Waiver: FAIL Rule A (6.0 not > 6 — boundary edge case). Data: SAFE.
        (20009, 'Jamie',  'Redpine',     'Business',     6.0,  1, 0, 149.00, 'SUSPENDED',
         'jamie@redpine.io',    '8888', susp_date(20), None, 12, 22, 30),

        # 20010 Avery: 30mo, autopay ON, $499 balance, SUSPENDED 8 days
        #   Waiver: PASS → $0 fee. Data: SAFE. Top-tier Enterprise suspended account.
        (20010, 'Avery',  'Stratos',     'Enterprise',  30.0,  1, 0, 499.00, 'SUSPENDED',
         'avery@stratos.tech',  '4444', susp_date(8),  None, 80, 67, 30),

        # --- Group B: Canceled (win-back demos) ---
        # Generic churned accounts on Professional plan, 1.5mo tenure, autopay OFF.
        # Used to demo "your account is canceled — here are our current plans."
        (20011, 'Taylor',   'Boxwood Co',      'Professional', 1.5, 0, 0, 0.00, 'CANCELED', 'taylor@boxwood.co',     '0000', None, None, 0, 0, 30),
        (20012, 'Jordan',   'Millstream Inc',  'Professional', 1.5, 0, 0, 0.00, 'CANCELED', 'jordanm@millstream.io', '0000', None, None, 0, 0, 30),
        (20013, 'Bailey',   'Cedarstone',      'Professional', 1.5, 0, 0, 0.00, 'CANCELED', 'bailey@cedarstone.co',  '0000', None, None, 0, 0, 30),
        (20014, 'Parker',   'Irongate Labs',   'Professional', 1.5, 0, 0, 0.00, 'CANCELED', 'parker@irongate.io',    '0000', None, None, 0, 0, 30),
        (20015, 'Reese',    'Maplewood Tech',  'Professional', 1.5, 0, 0, 0.00, 'CANCELED', 'reese@maplewood.tech',  '0000', None, None, 0, 0, 30),
        (20016, 'Cameron',  'Sunfield Co',     'Professional', 1.5, 0, 0, 0.00, 'CANCELED', 'cameron@sunfield.co',   '0000', None, None, 0, 0, 30),
        (20017, 'Finley',   'Clearpath Inc',   'Professional', 1.5, 0, 0, 0.00, 'CANCELED', 'finley@clearpath.io',   '0000', None, None, 0, 0, 30),
        (20018, 'Hayden',   'Ridgeline Labs',  'Professional', 1.5, 0, 0, 0.00, 'CANCELED', 'hayden@ridgeline.co',   '0000', None, None, 0, 0, 30),
        (20019, 'Rowan',    'Westbrook Co',    'Professional', 1.5, 0, 0, 0.00, 'CANCELED', 'rowan@westbrook.co',    '0000', None, None, 0, 0, 30),
        (20020, 'Sage',     'Northvale Inc',   'Professional', 1.5, 0, 0, 0.00, 'CANCELED', 'sage@northvale.io',     '0000', None, None, 0, 0, 30),
    ]
    cursor.executemany(
        "INSERT INTO customer_accounts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        customers
    )
    print(f"Customer Accounts: {len(customers)} accounts loaded.")

    conn.commit()
    conn.close()

    # =========================================================================
    # STEP 4: PRINT VERIFICATION TABLE
    # =========================================================================
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("\n--- PLAN CATALOG ---")
    print(f"{'ID':<6} {'Plan Name':<15} {'Price/mo':>9} {'Max Users':>10} {'Storage':>10}")
    print("-" * 55)
    for row in cursor.execute("SELECT plan_id, plan_name, monthly_price, max_users, storage_gb FROM plan_catalog ORDER BY monthly_price"):
        max_users = str(row[3]) if row[3] is not None else "Unlimited"
        storage = f"{row[4]} GB" if row[4] < 1000 else f"{row[4] // 1024} TB"
        print(f"{row[0]:<6} {row[1]:<15} ${row[2]:>8.2f} {max_users:>10} {storage:>10}")

    print("\n--- CUSTOMER ACCOUNTS ---")
    print(f"{'ID':<7} {'Name':<8} {'Company':<18} {'Plan':<15} {'Tenure':>8} {'Auto':>5} {'Balance':>9} {'Status':<10} {'SuspDays':>9} {'Projects':>8}")
    print("-" * 110)
    for row in cursor.execute("""
        SELECT account_id, first_name, company_name, plan_name, tenure_months,
               autopay_active, pending_balance, status, suspension_date, project_count
        FROM customer_accounts ORDER BY account_id
    """):
        autopay = "ON" if row[5] else "OFF"
        # Calculate days suspended
        if row[8]:
            susp_days = (today - datetime.strptime(row[8], "%Y-%m-%d")).days
            susp_str = f"{susp_days}d"
        else:
            susp_str = "—"
        projects = str(row[9]) if row[9] else "—"
        print(f"{row[0]:<7} {row[1]:<8} {row[2]:<18} {row[3]:<15} {row[4]:>6.1f}mo {autopay:>5} ${row[6]:>8.2f} {row[7]:<10} {susp_str:>9} {projects:>8}")

    conn.close()
    print("\n--- GLOBAL RESET COMPLETE. Pay Restore is back to Day 1. ---")


# =============================================================================
# ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    reset_world()
