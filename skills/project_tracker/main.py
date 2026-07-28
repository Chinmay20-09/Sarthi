"""
GitHub Project Tracker skill for Sarthi.

Tracks GitHub repositories, monitors issues and pull requests,
and provides project status summaries.

Configured via environment variables:
    SKILL_PROJECT_TRACKER_USERNAME — GitHub username (required)
    SKILL_PROJECT_TRACKER_TOKEN   — GitHub personal access token (optional)
"""

import logging
import os
from typing import Any

from brain.intent import Intent
from skills.base import BaseSkill

from .database import GitHubDatabase
from .github import GitHubClient
from .prompts import PROJECT_SUMMARY
from .utils import format_project_summary

logger = logging.getLogger(__name__)


class GitHubProjectSkill(BaseSkill):
    """
    Tracks GitHub projects and provides status summaries.

    Accepts parsed Intents from the brain pipeline.
    Maps intent.action/intent.target to internal commands.

    Environment variables:
        SKILL_PROJECT_TRACKER_USERNAME — GitHub username
        SKILL_PROJECT_TRACKER_TOKEN   — GitHub personal access token (optional)
    """

    name = "project_tracker"
    description = "Tracks GitHub and Notion projects"
    version = "1.0.0"

    def __init__(self, username: str | None = None, token: str | None = None):
        """
        Initialize the GitHub project tracker.

        Args:
            username: GitHub username. Falls back to env var SKILL_PROJECT_TRACKER_USERNAME.
            token: GitHub personal access token. Falls back to env var SKILL_PROJECT_TRACKER_TOKEN.
        """
        self.username = username or os.environ.get("SKILL_PROJECT_TRACKER_USERNAME", "")
        self.token = token or os.environ.get("SKILL_PROJECT_TRACKER_TOKEN")

        if self.username:
            self.github = GitHubClient(username=self.username, token=self.token)
        else:
            self.github = None

        self.database = GitHubDatabase()

    # ------------------------------------------------------------------
    # BaseSkill interface
    # ------------------------------------------------------------------

    def execute(self, intent: str | Intent) -> dict[str, Any]:
        """
        Execute a command based on parsed intent.

        Maps intent action/target combinations to internal handlers:
            - action="check"            → check_new_repositories()
            - action="status" / "how" / "what" → project_status()
            - action="sync" / "update"  → sync_repositories()
            - action="show" / "pending" → project_status()

        Backward compatible: accepts raw strings (routes to execute_text()).
        """
        # Backward compatibility: accept raw strings from legacy callers
        if isinstance(intent, str):
            result = self.execute_text(intent)
            return {"success": True, "status": result}

        action = intent.action.lower() if intent.action else ""
        target = intent.target.lower() if intent.target else ""

        # Check if GitHub is configured before making API calls
        if self.github is None:
            return {
                "success": False,
                "status": "not_configured",
                "error": (
                    "GitHub is not configured. "
                    "Set the SKILL_PROJECT_TRACKER_USERNAME environment variable "
                    "to enable project tracking."
                ),
            }

        # Check / scan GitHub for new repos
        if action in ("check",):
            result = self.check_new_repositories()
            return {"success": True, "status": result}

        # Project status / summary
        if action in ("status", "how", "what", "show", "pending") or "project" in target:
            result = self.project_status()
            return {"success": True, "status": result}

        # Sync repositories
        if action in ("sync",) or "sync" in target:
            result = self.sync_repositories()
            return {"success": True, "status": result}

        # Unknown command via intent
        return {
            "success": False,
            "status": "unknown",
            "error": f"Unknown command: {intent.action} {intent.target}",
        }

    # ------------------------------------------------------------------
    # Legacy string-based command support
    # ------------------------------------------------------------------

    def execute_text(self, command: str) -> str:
        """
        Legacy string-based command execution.

        Parses the string into an Intent first, then dispatches.
        Preserved for backward compatibility with existing callers.

        Args:
            command: Raw text command (e.g., "check github")

        Returns:
            Human-readable result string
        """
        command = command.lower().strip()

        if "check github" in command:
            return self.check_new_repositories()

        elif "project status" in command:
            return self.project_status()

        elif "sync repositories" in command:
            return self.sync_repositories()

        return "Unknown GitHub Project command."

    def check_new_repositories(self) -> str:
        """Check GitHub for new repositories not yet tracked."""
        if self.github is None:
            return "GitHub is not configured. Set SKILL_PROJECT_TRACKER_USERNAME."

        repositories = self.github.get_repositories()
        new_count = 0

        for repo in repositories:
            if not self.database.repository_exists(repo["name"]):
                self.database.add_repository(repo)
                new_count += 1

        if new_count > 0:
            return f"Found and tracked {new_count} new repository/ies."
        return "No new repositories found. All projects are up to date."

    def sync_repositories(self) -> str:
        """Fetch latest data for all tracked repositories."""
        if self.github is None:
            return "GitHub is not configured. Set SKILL_PROJECT_TRACKER_USERNAME."

        repositories = self.database.get_all_repositories()
        if not repositories:
            return "No repositories are being tracked yet. Run 'check' first."

        synced = 0
        for repo in repositories:
            try:
                summary = self.github.get_repository_summary(repo["name"])
                self.database.update_summary(repo["name"], summary)
                synced += 1
            except Exception as e:
                logger.warning(f"Failed to sync {repo['name']}: {e}")

        return f"Synced {synced}/{len(repositories)} repositories successfully."

    def project_status(self) -> str:
        """Get a summary of all tracked projects."""
        repositories = self.database.get_all_repositories()

        if not repositories:
            return (
                "No projects are being tracked yet. "
                "Try saying 'check github' to find your repositories."
            )

        summaries = []
        for repo in repositories:
            summary = self.database.get_summary(repo["name"])
            if summary:
                summaries.append(summary)

        if not summaries:
            return f"Tracking {len(repositories)} repositories but no data synced yet. Try 'sync repositories'."

        return PROJECT_SUMMARY + "\n\n" + format_project_summary(summaries)
