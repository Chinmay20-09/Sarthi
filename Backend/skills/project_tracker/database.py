"""
GitHub Project Tracker — Database layer.

Uses the centralized DatabaseManager instead of creating
its own SQLite connection. Table schemas are defined in
database/models.py.

This ensures no duplicate database connections or scattered
database files across skills.
"""

import logging
from typing import Any

from database.manager import DatabaseManager, get_database
from database.models import CREATE_GITHUB_PROJECTS, CREATE_GITHUB_SUMMARY

logger = logging.getLogger(__name__)


class GitHubDatabase:
    """
    Database access for the GitHub Project Tracker skill.

    Uses DatabaseManager for all queries.
    Tables are defined in database/models.py.
    """

    def __init__(self, db: DatabaseManager | None = None):
        """
        Initialize the database.

        Args:
            db: DatabaseManager instance. If None, uses the global singleton.
        """
        self.db = db or get_database()
        self._initialize_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _initialize_schema(self) -> None:
        """Ensure required tables exist."""
        self.db.create_table(CREATE_GITHUB_PROJECTS)
        self.db.create_table(CREATE_GITHUB_SUMMARY)
        logger.debug("GitHub database schema initialized")

    # ------------------------------------------------------------------
    # Repository CRUD
    # ------------------------------------------------------------------

    def repository_exists(self, repository_name: str) -> bool:
        """Check if a repository is already tracked."""
        result = self.db.fetch_one(
            "SELECT 1 FROM github_projects WHERE name = ?",
            (repository_name,),
        )
        return result is not None

    def add_repository(self, repository: dict) -> None:
        """Add a repository to the tracking database."""
        self.db.execute(
            """
            INSERT OR IGNORE INTO github_projects (
                github_id, name, full_name, description, private,
                html_url, default_branch, language, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                repository["id"],
                repository["name"],
                repository["full_name"],
                repository["description"],
                int(repository["private"]),
                repository["html_url"],
                repository["default_branch"],
                repository["language"],
                repository["created_at"],
                repository["updated_at"],
            ),
        )

    def get_all_repositories(self) -> list[dict[str, Any]]:
        """Get all tracked repositories."""
        return self.db.fetch_all("SELECT * FROM github_projects ORDER BY name")

    def get_repository(self, repository_name: str) -> dict[str, Any] | None:
        """Get a single repository by name."""
        return self.db.fetch_one(
            "SELECT * FROM github_projects WHERE name = ?",
            (repository_name,),
        )

    def delete_repository(self, repository_name: str) -> None:
        """Delete a repository and its summary."""
        self.db.execute("DELETE FROM github_projects WHERE name = ?", (repository_name,))
        self.db.execute("DELETE FROM github_summary WHERE repository = ?", (repository_name,))

    # ------------------------------------------------------------------
    # Summary CRUD
    # ------------------------------------------------------------------

    def update_summary(self, repository_name: str, summary: dict) -> None:
        """Update or insert a repository summary."""
        commit = summary.get("latest_commit") or {}

        self.db.execute(
            """
            INSERT OR REPLACE INTO github_summary (
                repository, stars, forks, watchers, language,
                open_issues, open_pull_requests, last_updated,
                latest_commit_sha, latest_commit_message,
                latest_commit_author, latest_commit_date, latest_commit_url
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                repository_name,
                summary["stars"],
                summary["forks"],
                summary["watchers"],
                summary["language"],
                summary["open_issues"],
                summary["open_pull_requests"],
                summary["last_updated"],
                commit.get("sha"),
                commit.get("message"),
                commit.get("author"),
                commit.get("date"),
                commit.get("url"),
            ),
        )

    def get_summary(self, repository_name: str) -> dict[str, Any] | None:
        """Get the summary for a repository."""
        return self.db.fetch_one(
            "SELECT * FROM github_summary WHERE repository = ?",
            (repository_name,),
        )

    # ------------------------------------------------------------------
    # Legacy
    # ------------------------------------------------------------------

    def close(self) -> None:
        """
        Close the database connection.

        Note: With DatabaseManager, this is optional.
        The manager's connection is shared and closed on exit.
        Kept for backward compatibility.
        """
        pass
