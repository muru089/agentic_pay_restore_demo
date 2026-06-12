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
    1. plan_catalog       -- 4 subscription tiers (Individual → Enterprise)
    2. customer_accounts  -- 13 accounts (10 Active/Suspended + 3 Canceled)

IMPORTANT NOTES:
    - plan_name in customer_accounts must exactly match plan_name in plan_catalog.
    - tenure_months stores tenure as months. Fee waiver Rule A: tenure_months > 6.
    - suspension_date is calculated dynamically from today (not hardcoded) so the
      data_retention_days check (T2) remains accurate on any run date.
    - Sam (20003): 35 days suspended → DATA AT RISK (> 30-day window).
    - Jamie (20009): exactly 6.0 months tenure → waiver FAIL (Rule A: strictly > 6).
    - Riley (20004): prior waiver 90 days ago → waiver FAIL Rule C.
    - card_expired: 1=expired, 0=valid. Suspended+autopay ON accounts have expired cards.
    - downgrade_date: NULL = permanent plan. Set by T6 when customer specifies duration.
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

    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            print("  Deleted old database file.")
        except PermissionError:
            print("  Could not delete file (may be locked). Dropping tables instead.")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("--- INITIATING GLOBAL RESET ---\n")

    # =========================================================================
    # STEP 1: CREATE TABLES
    # =========================================================================

    cursor.execute("DROP TABLE IF EXISTS plan_catalog")
    cursor.execute("""
        CREATE TABLE plan_catalog (
            plan_id       TEXT PRIMARY KEY,
            plan_name     TEXT,
            monthly_price REAL,
            max_users     INTEGER,
            storage_gb    INTEGER,
            late_fee      REAL
        )
    """)

    cursor.execute("DROP TABLE IF EXISTS customer_accounts")
    cursor.execute("""
        CREATE TABLE customer_accounts (
            account_id          INTEGER PRIMARY KEY,
            first_name          TEXT,
            company_name        TEXT,
            plan_name           TEXT,
            tenure_months       REAL,
            autopay_active      INTEGER,
            waivers_used_12m    INTEGER,
            pending_balance     REAL,
            status              TEXT,
            email               TEXT,
            card_last4          TEXT,
            card_expired        INTEGER,
            suspension_date     TEXT,
            last_waiver_date    TEXT,
            seat_count          INTEGER,
            project_count       INTEGER,
            data_retention_days INTEGER,
            downgrade_date      TEXT
        )
    """)

    print("Tables created.\n")

    # =========================================================================
    # STEP 2: SEED PLAN CATALOG
    # 4 tiers. plan_name is the join key used by all billing tools.
    # =========================================================================
    plans = [
        ('P001', 'Individual',  10.00,   1,    10,  10.00),
        ('P002', 'Team',        49.00,  10,   100,  25.00),
        ('P003', 'Business',   129.00,  30,   500,  50.00),
        ('P004', 'Enterprise', 399.00, 100,  2048, 100.00),
    ]
    cursor.executemany("INSERT INTO plan_catalog VALUES (?,?,?,?,?,?)", plans)
    print(f"Plan Catalog: {len(plans)} plans loaded.")

    # =========================================================================
    # STEP 3: SEED CUSTOMER ACCOUNTS
    #
    # Columns: account_id, first_name, company_name, plan_name, tenure_months,
    #          autopay_active, waivers_used_12m, pending_balance, status,
    #          email, card_last4, card_expired, suspension_date, last_waiver_date,
    #          seat_count, project_count, data_retention_days, downgrade_date
    #
    # card_expired: Suspended+autopay ON = 1 (AutoPay tried and failed on expired card)
    #               Suspended+autopay OFF = 0 (missed payment, card still valid)
    #               Active = 0
    # =========================================================================

    today = datetime.now()

    def susp_date(days_ago):
        return (today - timedelta(days=days_ago)).strftime("%Y-%m-%d")

    def waiver_date(days_ago):
        return (today - timedelta(days=days_ago)).strftime("%Y-%m-%d")

    customers = [
        # -----------------------------------------------------------------------
        # Group A — Active / Suspended (20001–20010)
        # -----------------------------------------------------------------------

        # 20001 Alex | Wavefront | Team | 9mo | autopay ON | $49 | SUSPENDED 5d
        # card 4242 expired (autopay ON → AutoPay tried and failed)
        # Waiver: PASS (9>6, autopay=1, no prior waiver) → $0 fee
        # Data: SAFE (5 days < 30). PRIMARY DEMO — upgrade to Business for 3 months.
        (20001, 'Alex',   'Wavefront',   'Team',        9.0,  1, 0,  49.00, 'SUSPENDED',
         'alex@wavefront.io',   '4242', 1, susp_date(5),  None,          8,  12, 30, None),

        # 20002 Jordan | Sprinto | Team | 2mo | autopay OFF | $49 | SUSPENDED 5d
        # card 8831 valid (autopay OFF → AutoPay never tried)
        # Waiver: FAIL Rule A (2mo < 6mo threshold)
        # Data: SAFE (5 days).
        (20002, 'Jordan', 'Sprinto',     'Team',        2.0,  0, 0,  49.00, 'SUSPENDED',
         'jordan@sprinto.io',   '8831', 0, susp_date(5),  None,          2,   3, 30, None),

        # 20003 Sam | Arclight | Business | 14mo | autopay ON | $129 | SUSPENDED 35d
        # card 5517 expired (autopay ON → AutoPay tried and failed)
        # Waiver: PASS → $0 fee
        # Data: AT RISK (35 days > 30-day retention window). Soft stop required.
        (20003, 'Sam',    'Arclight',    'Business',   14.0,  1, 0, 129.00, 'SUSPENDED',
         'sam@arclight.io',     '5517', 1, susp_date(35), None,         20,  28, 30, None),

        # 20004 Riley | Nomad Labs | Individual | 7mo | autopay ON | $10 | SUSPENDED 10d
        # card 2290 expired (autopay ON → AutoPay tried and failed)
        # Waiver: FAIL Rule C (prior waiver used 90 days ago — within 12-month window)
        # Rule A PASS (7>6), Rule B PASS (autopay=1), Rule C BLOCKS.
        (20004, 'Riley',  'Nomad Labs',  'Individual',  7.0,  1, 1,  10.00, 'SUSPENDED',
         'riley@nomadlabs.io',  '2290', 1, susp_date(10), waiver_date(90), 1, 5, 30, None),

        # 20005 Morgan | Crestline | Team | 18mo | autopay OFF | $49 | SUSPENDED 3d
        # card 6644 valid (autopay OFF → AutoPay never tried)
        # Waiver: FAIL Rule B (autopay OFF — long tenure doesn't help)
        # Data: SAFE (3 days).
        (20005, 'Morgan', 'Crestline',   'Team',       18.0,  0, 0,  49.00, 'SUSPENDED',
         'morgan@crestline.io', '6644', 0, susp_date(3),  None,          7,  11, 30, None),

        # 20006 Casey | Driftwood | Team | 8mo | autopay ON | $0 | ACTIVE
        # Standalone upgrade/downgrade demo. No restore needed.
        (20006, 'Casey',  'Driftwood',   'Team',        8.0,  1, 0,   0.00, 'ACTIVE',
         'casey@driftwood.io',  '3311', 0, None,          None,          5,  10, 30, None),

        # 20007 Drew | Lumen Co | Business | 16mo | autopay ON | $0 | ACTIVE
        # Downgrade-blocked demo: 25 seats > Team plan max of 10 → human escalation.
        (20007, 'Drew',   'Lumen Co',    'Business',   16.0,  1, 0,   0.00, 'ACTIVE',
         'drew@lumeco.io',      '7799', 0, None,          None,         25,  20, 30, None),

        # 20008 Quinn | Pathfinder | Business | 24mo | autopay ON | $0 | ACTIVE
        # Clean downgrade demo: 5 seats < Team plan max of 10 → eligible.
        (20008, 'Quinn',  'Pathfinder',  'Business',   24.0,  1, 0,   0.00, 'ACTIVE',
         'quinn@pathfinder.io', '1188', 0, None,          None,          5,  22, 30, None),

        # 20009 Jamie | Redpine | Business | 6.0mo | autopay ON | $129 | SUSPENDED 20d
        # card 9955 expired (autopay ON → AutoPay tried and failed)
        # Waiver: FAIL Rule A — boundary case: 6.0mo is NOT > 6mo (strictly greater)
        # Data: SAFE (20 days).
        (20009, 'Jamie',  'Redpine',     'Business',    6.0,  1, 0, 129.00, 'SUSPENDED',
         'jamie@redpine.io',    '9955', 1, susp_date(20), None,         12,  18, 30, None),

        # 20010 Avery | Stratos | Enterprise | 30mo | autopay ON | $399 | SUSPENDED 8d
        # card 3388 expired (autopay ON → AutoPay tried and failed)
        # Waiver: PASS → $0 fee. Data: SAFE. Top-tier perfect restore demo.
        (20010, 'Avery',  'Stratos',     'Enterprise', 30.0,  1, 0, 399.00, 'SUSPENDED',
         'avery@stratos.io',    '3388', 1, susp_date(8),  None,         45,  35, 30, None),

        # -----------------------------------------------------------------------
        # Group B — Canceled (20011–20013) — win-back demos
        # All on Team plan, 1.5mo tenure, autopay OFF, $0 balance.
        # card_expired=0 (account closed cleanly, card on file still valid).
        # -----------------------------------------------------------------------
        (20011, 'Parker', 'Helix Systems', 'Team',  1.5, 0, 0, 0.00, 'CANCELED',
         'parker@helixsystems.io', '4411', 0, None, None, 2, 2, 30, None),

        (20012, 'Taylor', 'Brightpath',    'Team',  1.5, 0, 0, 0.00, 'CANCELED',
         'taylor@brightpath.io',  '5522', 0, None, None, 1, 1, 30, None),

        (20013, 'Reese',  'Foundry Labs',  'Team',  1.5, 0, 0, 0.00, 'CANCELED',
         'reese@foundrylabs.io',  '6633', 0, None, None, 2, 2, 30, None),
    ]

    cursor.executemany(
        "INSERT INTO customer_accounts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
    print(f"{'ID':<6} {'Plan':<12} {'Price/mo':>9} {'Max Users':>10} {'Storage':>10} {'Late Fee':>9}")
    print("-" * 62)
    for row in cursor.execute(
        "SELECT plan_id, plan_name, monthly_price, max_users, storage_gb, late_fee FROM plan_catalog ORDER BY monthly_price"
    ):
        storage = f"{row[4]} GB" if row[4] < 1000 else f"{row[4] // 1024} TB"
        print(f"{row[0]:<6} {row[1]:<12} ${row[2]:>8.2f} {row[3]:>10} {storage:>10} ${row[5]:>8.2f}")

    print("\n--- CUSTOMER ACCOUNTS ---")
    print(f"{'ID':<7} {'Name':<8} {'Company':<16} {'Plan':<12} {'Mo':>4} {'Auto':>4} {'CExp':>5} {'Balance':>8} {'Status':<10} {'SuspDays':>9} {'Prj':>4} {'Waiver':>8}")
    print("-" * 115)
    for row in cursor.execute("""
        SELECT account_id, first_name, company_name, plan_name, tenure_months,
               autopay_active, card_expired, pending_balance, status,
               suspension_date, project_count, last_waiver_date
        FROM customer_accounts ORDER BY account_id
    """):
        autopay  = "ON"  if row[5] else "OFF"
        card_exp = "YES" if row[6] else "no"
        if row[9]:
            susp_days = (today - datetime.strptime(row[9], "%Y-%m-%d")).days
            susp_str  = f"{susp_days}d"
        else:
            susp_str = "—"
        projects     = str(row[10]) if row[10] else "—"
        waiver_str   = row[11][:10] if row[11] else "—"
        print(
            f"{row[0]:<7} {row[1]:<8} {row[2]:<16} {row[3]:<12} "
            f"{row[4]:>4.1f} {autopay:>4} {card_exp:>5} ${row[7]:>7.2f} "
            f"{row[8]:<10} {susp_str:>9} {projects:>4} {waiver_str:>8}"
        )

    conn.close()
    print("\n--- GLOBAL RESET COMPLETE. Pay Restore is back to Day 1. ---")


if __name__ == "__main__":
    reset_world()
