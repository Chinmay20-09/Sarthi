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
# Chat UI Transcript Table
# =============================================================================

# The chat window's own transcript (user + assistant turns as rendered by the
# UI), keyed by the same session id Hermes uses. This is the "persistent memory
# of one chat": it survives reloads/restarts, and "reset chat" clears it along
# with the Hermes session context in one go. content is a JSON blob of the
# payload used to render the bubble (text, result cards, pipeline strip).
CREATE_CHAT_MESSAGES = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT
)
"""

# =============================================================================
# External Connectors Table
# =============================================================================

CREATE_CONNECTORS = """
CREATE TABLE IF NOT EXISTS connectors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    service TEXT NOT NULL,
    status TEXT DEFAULT 'disconnected',
    config TEXT DEFAULT '{}',
    created_at TEXT,
    updated_at TEXT
)
"""

# =============================================================================
# Browser Automation Profile Registry
# =============================================================================

# Where automated browsing (Browser Awareness) keeps its Chrome profile.
# value is an absolute profile directory path; reusing the same directory
# across runs means the user logs in once and stays logged in for every
# later browser session, while the user's real Chrome profile is untouched.
CREATE_BROWSER_PROFILES = """
CREATE TABLE IF NOT EXISTS browser_profiles (
    name TEXT PRIMARY KEY,
    value TEXT,
    created_at TEXT,
    updated_at TEXT
)
"""

# =============================================================================
# Projects Table
# =============================================================================

# The user's projects (name, GitHub repo, local terminal path) so Sarthi/Hermes
# can relate a mentioned project to its repo and local checkout. name is
# unique (case-insensitive enforcement happens at the API layer; the index
# here is a hard backstop on a table that starts empty).
CREATE_PROJECTS = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    github_url TEXT DEFAULT '',
    terminal_path TEXT DEFAULT '',
    created_at TEXT,
    updated_at TEXT
)
"""

# =============================================================================
# Indexes
# =============================================================================

# The chat/conversation tables are queried exclusively by session — reading a
# session's turns (WHERE session_id = ? ORDER BY id), trimming a session's
# over-cap rows, and deleting a session on chat reset. Without an index every
# one of those is a full table scan that grows with total history across ALL
# sessions, not just the active one.
CREATE_INDEX_CONVERSATION_MESSAGES_SESSION = """
CREATE INDEX IF NOT EXISTS idx_conversation_messages_session
ON conversation_messages (session_id)
"""

CREATE_INDEX_CHAT_MESSAGES_SESSION = """
CREATE INDEX IF NOT EXISTS idx_chat_messages_session
ON chat_messages (session_id)
"""

CREATE_INDEX_PROJECTS_NAME = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_name
ON projects (name)
"""

# =============================================================================
# Registry: all known table schemas
# =============================================================================

# When new schemas are added, register them here for migration tracking.
# DatabaseManager creates every schema here (plus ALL_INDEXES) automatically
# when it connects, so the canonical schema is always present and self-healing.
ALL_TABLES: dict[str, str] = {
    "github_projects": CREATE_GITHUB_PROJECTS,
    "github_summary": CREATE_GITHUB_SUMMARY,
    "command_history": CREATE_COMMAND_HISTORY,
    "knowledge_memory": CREATE_KNOWLEDGE_MEMORY,
    "settings": CREATE_SETTINGS,
    "conversation_messages": CREATE_CONVERSATION_MESSAGES,
    "chat_messages": CREATE_CHAT_MESSAGES,
    "connectors": CREATE_CONNECTORS,
    "browser_profiles": CREATE_BROWSER_PROFILES,
    "projects": CREATE_PROJECTS,
}

# Canonical indexes, also created automatically at connect time.
ALL_INDEXES: dict[str, str] = {
    "idx_conversation_messages_session": CREATE_INDEX_CONVERSATION_MESSAGES_SESSION,
    "idx_chat_messages_session": CREATE_INDEX_CHAT_MESSAGES_SESSION,
    "idx_projects_name": CREATE_INDEX_PROJECTS_NAME,
}
