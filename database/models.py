"""
Shared database models and table schemas for Sarthi.

Every skill that needs database storage defines its tables here.
All table creation goes through DatabaseManager.create_table().

This centralizes schema definitions so there's no duplication
across skills that need similar tables.
"""

# =============================================================================
# GitHub Project Tracker Tables
# =============================================================================

CREATE_GITHUB_PROJECTS = """
CREATE TABLE IF NOT EXISTS github_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    github_id INTEGER UNIQUE,
    name TEXT UNIQUE,
    full_name TEXT,
    description TEXT,
    private INTEGER,
    html_url TEXT,
    default_branch TEXT,
    language TEXT,
    created_at TEXT,
    updated_at TEXT
)
"""

CREATE_GITHUB_SUMMARY = """
CREATE TABLE IF NOT EXISTS github_summary (
    repository TEXT PRIMARY KEY,
    stars INTEGER,
    forks INTEGER,
    watchers INTEGER,
    language TEXT,
    open_issues INTEGER,
    open_pull_requests INTEGER,
    last_updated TEXT,
    latest_commit_sha TEXT,
    latest_commit_message TEXT,
    latest_commit_author TEXT,
    latest_commit_date TEXT,
    latest_commit_url TEXT
)
"""

# =============================================================================
# Knowledge / Discovery Tables (future)
# =============================================================================

# CREATE_APPLICATIONS = """
# CREATE TABLE IF NOT EXISTS applications (
#     ...
# )
# """

# =============================================================================
# Registry: all known table schemas
# =============================================================================

# When new schemas are added, register them here for migration tracking.
ALL_TABLES: dict[str, str] = {
    "github_projects": CREATE_GITHUB_PROJECTS,
    "github_summary": CREATE_GITHUB_SUMMARY,
}
