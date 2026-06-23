"""
z_reset_world.py -- Orbit Demo: Database Reset Script
--------------------------------------------------------------------
WHAT THIS SCRIPT DOES:
    Completely wipes orbit.db and rebuilds it from scratch with all
    original seed data. Run this any time you want to return the demo to
    its "Day 1" state (e.g., after a live demo mutated balances or accounts).

HOW TO RUN:
    py pay_restore_demo/agents_tools_db/z_reset_world.py
    (Run from c:\\Muru_Workspace — the PARENT of pay_restore_demo.)

TABLES CREATED:
    1. plan_catalog       -- 4 subscription tiers (Individual → Enterprise)
    2. customer_accounts  -- 15 accounts (10 Active/Suspended + 1 Canceled + 2 Diagnostic + 2 Manual Payer)
    3. session_state      -- persistent restore flow state (written by T0_SetSessionState)

DIAGNOSTIC ACCOUNTS (20012-20013):
    20012 Taylor  Brightline    Team/ACTIVE     storage 95/100 GB (near limit), Slack healthy
    20013 Blake   Nexus Digital Business/ACTIVE storage 45/500 GB, GitHub auth_failure

MANUAL PAYER ACCOUNTS (20014-20015):
    20014 Priya   Clearpath     Business/ACTIVE autopay OFF, $0 balance (just paid), 20mo tenure
    20015 Dana    Ironforge     Team/ACTIVE     autopay OFF, $49 balance (invoice due), 14mo tenure

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
    - storage_used_gb: current storage consumption. Used by T11_CheckStorage.
    - integration_*: integration health fields. Used by T12_CheckIntegration.
"""

import sqlite3
import os
from datetime import datetime, timedelta


def reset_world():
    """
    Drops and recreates all tables, then seeds the full Pay Restore dataset.
    Deletes the old .db file first for a truly clean slate.
    """

    db_path = os.path.join(os.path.dirname(__file__), "orbit.db")

    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            print("  Deleted old database file.")
        except PermissionError:
            print("  Could not delete file (may be locked). Dropping tables instead.")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
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
            account_id              INTEGER PRIMARY KEY,
            first_name              TEXT,
            company_name            TEXT,
            plan_name               TEXT,
            tenure_months           REAL,
            autopay_active          INTEGER,
            waivers_used_12m        INTEGER,
            pending_balance         REAL,
            status                  TEXT,
            email                   TEXT,
            card_last4              TEXT,
            card_expired            INTEGER,
            suspension_date         TEXT,
            last_waiver_date        TEXT,
            seat_count              INTEGER,
            project_count           INTEGER,
            data_retention_days     INTEGER,
            downgrade_date          TEXT,
            storage_used_gb         REAL,
            integration_name        TEXT,
            integration_status      TEXT,
            integration_last_sync   TEXT,
            integration_auth_failures INTEGER
        )
    """)

    cursor.execute("DROP TABLE IF EXISTS session_state")
    cursor.execute("""
        CREATE TABLE session_state (
            account_id              INTEGER PRIMARY KEY,
            data_checked            INTEGER DEFAULT 0,
            data_safe               INTEGER DEFAULT 1,
            days_suspended          INTEGER DEFAULT 0,
            project_count           INTEGER DEFAULT 0,
            at_risk_disclosed       INTEGER DEFAULT 0,
            at_risk_proceeding      INTEGER DEFAULT 0,
            payment_cleared         INTEGER DEFAULT 0,
            amount_paid             REAL    DEFAULT 0.0,
            new_card_last4          TEXT,
            restore_complete        INTEGER DEFAULT 0,
            plan_change_requested   INTEGER DEFAULT 0,
            plan_name_requested     TEXT,
            plan_duration_months    INTEGER,
            plan_validated          INTEGER DEFAULT 0,
            plan_executed           INTEGER DEFAULT 0,
            updated_at              TEXT
        )
    """)

    print("Tables created.\n")

    # =========================================================================
    # STEP 2: SEED PLAN CATALOG
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
    # Columns (23):
    #   account_id, first_name, company_name, plan_name, tenure_months,
    #   autopay_active, waivers_used_12m, pending_balance, status,
    #   email, card_last4, card_expired, suspension_date, last_waiver_date,
    #   seat_count, project_count, data_retention_days, downgrade_date,
    #   storage_used_gb, integration_name, integration_status,
    #   integration_last_sync, integration_auth_failures
    #
    # card_expired: Suspended+autopay ON = 1 (AutoPay tried and failed on expired card)
    #               Suspended+autopay OFF = 0 (missed payment, card still valid)
    #               Active = 0
    #
    # integration_status values: "healthy" | "auth_failure" | "sync_error" |
    #                             "disconnected" | "none"
    # =========================================================================

    today = datetime.now()

    def susp_date(days_ago):
        return (today - timedelta(days=days_ago)).strftime("%Y-%m-%d")

    def sync_date(days_ago):
        return (today - timedelta(days=days_ago)).strftime("%Y-%m-%d")

    def waiver_date(days_ago):
        return (today - timedelta(days=days_ago)).strftime("%Y-%m-%d")

    customers = [
        # -----------------------------------------------------------------------
        # Group A — Active / Suspended (20001–20010)
        # -----------------------------------------------------------------------

        # 20001 Alex | Wavefront | Team | 9mo | autopay ON | $49 | SUSPENDED 5d
        # Waiver: PASS | Data: SAFE | PRIMARY DEMO — upgrade to Business 3mo
        # Storage: 72/100 GB (72%) | Slack: healthy (last sync day before suspension)
        (20001, 'Alex',   'Wavefront',   'Team',        9.0,  1, 0,  49.00, 'SUSPENDED',
         'alex@wavefront.io',   '4242', 1, susp_date(5),  None,
         8,  12, 30, None,
         72.0,  'Slack',  'healthy',      sync_date(6),  0),

        # 20002 Jordan | Sprinto | Team | 2mo | autopay OFF | $49 | SUSPENDED 5d
        # Waiver: FAIL Rule A (2mo < 6mo) | Data: SAFE
        # Storage: 18/100 GB | GitHub: healthy
        (20002, 'Jordan', 'Sprinto',     'Team',        2.0,  0, 0,  49.00, 'SUSPENDED',
         'jordan@sprinto.io',   '8831', 0, susp_date(5),  None,
         2,   3, 30, None,
         18.0,  'GitHub', 'healthy',      sync_date(6),  0),

        # 20003 Sam | Arclight | Business | 14mo | autopay ON | $129 | SUSPENDED 35d
        # Waiver: PASS | Data: AT RISK (35 > 30) | SOFT STOP required
        # Storage: 210/500 GB | Jira: sync_error (35d without sync → stale)
        (20003, 'Sam',    'Arclight',    'Business',   14.0,  1, 0, 129.00, 'SUSPENDED',
         'sam@arclight.io',     '5517', 1, susp_date(35), None,
         20,  28, 30, None,
         210.0, 'Jira',   'sync_error',   sync_date(36), 3),

        # 20004 Riley | Nomad Labs | Individual | 7mo | autopay ON | $10 | SUSPENDED 10d
        # Waiver: FAIL Rule C (waiver 90d ago) | Data: SAFE
        # Storage: 7.5/10 GB (75%) | No integration
        (20004, 'Riley',  'Nomad Labs',  'Individual',  7.0,  1, 1,  10.00, 'SUSPENDED',
         'riley@nomadlabs.io',  '2290', 1, susp_date(10), waiver_date(90),
         1,   5, 30, None,
         7.5,   'None',   'none',         None,          0),

        # 20005 Morgan | Crestline | Team | 18mo | autopay OFF | $49 | SUSPENDED 3d
        # Waiver: FAIL Rule B (autopay OFF) | Data: SAFE
        # Storage: 55/100 GB | Slack: healthy
        (20005, 'Morgan', 'Crestline',   'Team',       18.0,  0, 0,  49.00, 'SUSPENDED',
         'morgan@crestline.io', '6644', 0, susp_date(3),  None,
         7,  11, 30, None,
         55.0,  'Slack',  'healthy',      sync_date(4),  0),

        # 20006 Casey | Driftwood | Team | 8mo | autopay ON | $0 | ACTIVE
        # Standalone upgrade demo. Storage: 45/100 GB | Jira: healthy
        (20006, 'Casey',  'Driftwood',   'Team',        8.0,  1, 0,   0.00, 'ACTIVE',
         'casey@driftwood.io',  '3311', 0, None,          None,
         5,  10, 30, None,
         45.0,  'Jira',   'healthy',      sync_date(1),  0),

        # 20007 Drew | Lumen Co | Business | 16mo | autopay ON | $0 | ACTIVE
        # Downgrade BLOCKED (25 seats > Team max 10). Storage: 380/500 GB | GitHub: healthy
        (20007, 'Drew',   'Lumen Co',    'Business',   16.0,  1, 0,   0.00, 'ACTIVE',
         'drew@lumeco.io',      '7799', 0, None,          None,
         25,  20, 30, None,
         380.0, 'GitHub', 'healthy',      sync_date(1),  0),

        # 20008 Quinn | Pathfinder | Business | 24mo | autopay ON | $0 | ACTIVE
        # Clean downgrade (5 seats ≤ Team max 10). Storage: 50/500 GB | Slack: healthy
        (20008, 'Quinn',  'Pathfinder',  'Business',   24.0,  1, 0,   0.00, 'ACTIVE',
         'quinn@pathfinder.io', '1188', 0, None,          None,
         5,  22, 30, None,
         50.0,  'Slack',  'healthy',      sync_date(1),  0),

        # 20009 Jamie | Redpine | Business | 6.0mo | autopay ON | $129 | SUSPENDED 20d
        # Waiver: FAIL Rule A boundary (6.0 not > 6) | Data: SAFE
        # Storage: 125/500 GB | GitHub: healthy
        (20009, 'Jamie',  'Redpine',     'Business',    6.0,  1, 0, 129.00, 'SUSPENDED',
         'jamie@redpine.io',    '9955', 1, susp_date(20), None,
         12,  18, 30, None,
         125.0, 'GitHub', 'healthy',      sync_date(21), 0),

        # 20010 Avery | Stratos | Enterprise | 30mo | autopay ON | $399 | SUSPENDED 8d
        # Waiver: PASS | Data: SAFE | Top-tier perfect restore
        # Storage: 1200/2048 GB | Slack: healthy
        (20010, 'Avery',  'Stratos',     'Enterprise', 30.0,  1, 0, 399.00, 'SUSPENDED',
         'avery@stratos.io',    '3388', 1, susp_date(8),  None,
         45,  35, 30, None,
         1200.0,'Slack',  'healthy',      sync_date(9),  0),

        # -----------------------------------------------------------------------
        # Group B — Canceled (20011) — win-back demo
        # -----------------------------------------------------------------------
        (20011, 'Parker', 'Helix Systems', 'Team',      1.5,  0, 0,   0.00, 'CANCELED',
         'parker@helixsystems.io', '4411', 0, None,       None,
         2,   2, 30, None,
         5.0,   'None',   'none',         None,          0),

        # -----------------------------------------------------------------------
        # Group C — Diagnostic Accounts (20012-20013)
        # Active accounts with storage/integration signals for DiagnosticSupervisor
        # -----------------------------------------------------------------------

        # 20012 Taylor | Brightline | Team | 11mo | autopay ON | $0 | ACTIVE
        # Diagnostic trigger: ambiguous "something feels off / projects loading slow"
        # Storage: 95/100 GB (95% — near limit, likely the cause of slowness)
        # Slack integration: healthy (not the issue)
        # DiagSupervisor synthesizes: data OK, integration OK, storage is the culprit
        (20012, 'Taylor', 'Brightline',  'Team',       11.0,  1, 0,   0.00, 'ACTIVE',
         'taylor@brightline.io', '4499', 0, None,         None,
         8,  18, 30, None,
         95.0,  'Slack',  'healthy',      sync_date(1),  0),

        # 20013 Blake | Nexus Digital | Business | 16mo | autopay ON | $0 | ACTIVE
        # Diagnostic trigger: ambiguous "account feels broken / things not syncing"
        # Storage: 45/500 GB (9% — healthy, not the issue)
        # GitHub integration: auth_failure (5 auth failures in 7 days, last sync 3 days ago)
        # DiagSupervisor synthesizes: data OK, storage OK, integration is the culprit
        (20013, 'Blake',  'Nexus Digital','Business',  16.0,  1, 0,   0.00, 'ACTIVE',
         'blake@nexusdigital.io','7733', 0, None,         None,
         12,  22, 30, None,
         45.0,  'GitHub', 'auth_failure', sync_date(3),  5),

        # -----------------------------------------------------------------------
        # Group D — Manual Payer Accounts (20014-20015)
        # Active accounts with AutoPay OFF — demonstrate manual billing flow
        # -----------------------------------------------------------------------

        # 20014 Priya | Clearpath | Business | 20mo | autopay OFF | $0 | ACTIVE
        # Just paid this month — no balance due. Long-tenure manual payer.
        # Note: if ever suspended, waiver FAIL Rule B (autopay OFF)
        # Storage: 220/500 GB | Jira: healthy
        (20014, 'Priya',  'Clearpath',   'Business',  20.0,  0, 0,   0.00, 'ACTIVE',
         'priya@clearpath.io',   '6691', 0, None,         None,
         14,  26, 30, None,
         220.0, 'Jira',   'healthy',      sync_date(1),  0),

        # 20015 Dana | Ironforge | Team | 14mo | autopay OFF | $49 | ACTIVE
        # Invoice due — active account in grace period with unpaid monthly bill.
        # Demonstrates active-account billing flow (DA2 STATE 4 — no restore, no fee waiver).
        # Storage: 60/100 GB | GitHub: healthy
        (20015, 'Dana',   'Ironforge',   'Team',      14.0,  0, 0,  49.00, 'ACTIVE',
         'dana@ironforge.io',    '7722', 0, None,         None,
         6,   12, 30, None,
         60.0,  'GitHub', 'healthy',      sync_date(1),  0),
    ]

    cursor.executemany(
        "INSERT INTO customer_accounts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
    print(f"{'ID':<7} {'Name':<8} {'Company':<16} {'Plan':<12} {'Mo':>4} {'Auto':>4} "
          f"{'CExp':>5} {'Balance':>8} {'Status':<10} {'SuspDays':>9} {'Prj':>4} "
          f"{'Storage':>10} {'Integration':<22} {'Waiver':>10}")
    print("-" * 140)
    for row in cursor.execute("""
        SELECT account_id, first_name, company_name, plan_name, tenure_months,
               autopay_active, card_expired, pending_balance, status,
               suspension_date, project_count, last_waiver_date,
               storage_used_gb, integration_name, integration_status,
               integration_auth_failures
        FROM customer_accounts ORDER BY account_id
    """):
        autopay   = "ON"  if row[5] else "OFF"
        card_exp  = "YES" if row[6] else "no"
        susp_str  = f"{(today - datetime.strptime(row[9], '%Y-%m-%d')).days}d" if row[9] else "—"
        projects  = str(row[10]) if row[10] else "—"
        waiver_s  = row[11][:10] if row[11] else "—"
        storage_s = f"{row[12]:.0f} GB" if row[12] else "—"
        integ_s   = f"{row[13]}/{row[14]}" if row[13] and row[13] != 'None' else "—"
        auth_f    = f"({row[15]} failures)" if row[15] and row[15] > 0 else ""
        print(
            f"{row[0]:<7} {row[1]:<8} {row[2]:<16} {row[3]:<12} "
            f"{row[4]:>4.1f} {autopay:>4} {card_exp:>5} ${row[7]:>7.2f} "
            f"{row[8]:<10} {susp_str:>9} {projects:>4} "
            f"{storage_s:>10} {integ_s:<16}{auth_f:<6} {waiver_s:>10}"
        )

    conn.close()
    print("\n--- GLOBAL RESET COMPLETE. Pay Restore is back to Day 1. ---")


if __name__ == "__main__":
    reset_world()
