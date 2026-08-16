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
# Command History Table
# =============================================================================

CREATE_COMMAND_HISTORY = """
CREATE TABLE IF NOT EXISTS command_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command TEXT,
    action TEXT,
    target TEXT,
    success INTEGER,
    timestamp TEXT
)
"""

# =============================================================================
# Knowledge Memory Table
# =============================================================================

CREATE_KNOWLEDGE_MEMORY = """
CREATE TABLE IF NOT EXISTS knowledge_memory (
    key TEXT PRIMARY KEY,
    value TEXT,
    expires_at TEXT,
    updated_at TEXT
)
"""

# =============================================================================
# Settings Table
# =============================================================================

CREATE_SETTINGS = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
)
"""

# =============================================================================
# Hermes Conversation History Table
# =============================================================================

# One row per message turn, per session. Sessions remember earlier turns so
# Hermes can reference them; persisting them makes that memory survive server
# restarts. id gives insertion order; the store trims per-session rows to a cap.
CREATE_CONVERSATION_MESSAGES = """
CREATE TABLE IF NOT EXISTS conversation_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT
)
"""

# =============================================================================
# Registry: all known table schemas
# =============================================================================

# When new schemas are added, register them here for migration tracking.
ALL_TABLES: dict[str, str] = {
    "github_projects": CREATE_GITHUB_PROJECTS,
    "github_summary": CREATE_GITHUB_SUMMARY,
    "command_history": CREATE_COMMAND_HISTORY,
    "knowledge_memory": CREATE_KNOWLEDGE_MEMORY,
    "settings": CREATE_SETTINGS,
    "conversation_messages": CREATE_CONVERSATION_MESSAGES,
}
