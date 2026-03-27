"""
pay_restore_demo
----------------
Multi-agent demo for Pay Restore, built with Google ADK.

Entry point: agent.py (root_agent)

3-Tier Architecture:
    Uber:       agent.py (root_agent)           gemini-2.0-flash
    Supervisor: SA1_Restore_Supervisor          gemini-2.0-flash
    Domain:     DA1_Account_Agent               gemini-2.0-flash-lite
                DA2_Billing_Agent               gemini-2.0-flash-lite
    Squad:      DA3_Restore_Agent               gemini-2.0-flash

Tools: T1 through T11 (see CLAUDE.md for full reference)

Database: pay_restore.db (2 tables: plan_catalog, customer_accounts)

To reset the database to its original state:
    py pay_restore_demo/z_reset_world.py

To launch the ADK web UI (run from c:\\Muru_Workspace — the parent directory):
    adk web
"""
