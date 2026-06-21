"""
pay_restore_demo
----------------
Multi-agent SaaS demo for suspended account restore, built with Google ADK.

Architecture:
    Uber:         agents_tools_db/agent.py (root_agent)   gemini-2.5-flash
    Domain:       DA1_Account_Agent, DA2_Billing_Agent    gemini-2.5-flash
    Squad:        DA3_Restore_Agent                       gemini-2.5-flash
    Squad/Shared: DA4_Plan_Agent                          gemini-2.5-flash

Tools: T1 through T10 (see CLAUDE.md for full reference)
Database: agents_tools_db/pay_restore.db

Reset DB:  py "pay_restore_demo/z_reset_world.py"
Run demo:  adk web  (from c:\\Muru_Workspace)
"""

from .agents_tools_db.agent import root_agent

__all__ = ["root_agent"]
