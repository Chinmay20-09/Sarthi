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
    # GitHub configuration
    # ------------------------------------------------------------------

    def _load_saved_username(self) -> str:
        """
        Read the GitHub username saved via the user_config skill.

        Returns:
            The saved username, or empty string if not configured yet
        """
        try:
            from database.manager import get_database

            row = get_database().fetch_one(
                "SELECT value FROM settings WHERE key = ?", ("github_username",)
            )
            return row["value"] if row else ""
        except Exception as e:
            logger.debug(f"Could not load saved GitHub username: {e}")
            return ""

    def _ensure_github(self) -> str:
        """
        Make sure a GitHub client exists for the configured username.

        Resolution order:
            1. Explicit constructor argument / SKILL_PROJECT_TRACKER_USERNAME env var
            2. Username saved via the user_config skill (persistent, chat-configured)

        Returns:
            The resolved username (may be empty if GitHub is not configured)
        """
        username = self.username or self._load_saved_username()
        if username and self.github is None:
            self.github = GitHubClient(username=username, token=self.token)
            logger.info(f"GitHub configured for user: {username}")
        return username

    # ------------------------------------------------------------------
    # BaseSkill interface
    # ------------------------------------------------------------------

    def execute(self, intent: str | Intent) -> dict[str, Any]:
        """
        Execute a command based on parsed intent.

        Maps intent action/target combinations to internal handlers:
            - action="check"            → check_new_repositories()
            - action="status" / "show" / "pending" → project_status()
            - action="how" / "what"    → project_status(), but only when the
              target mentions projects/GitHub/repos (casual questions are left
              to the Natural Language Processor fallback)
            - action="sync" / "update"  → sync_repositories()

        Backward compatible: accepts raw strings (routes to execute_text()).
        """
        # Backward compatibility: accept raw strings from legacy callers
        if isinstance(intent, str):
            result = self.execute_text(intent)
            return {"success": True, "status": result}

        action = intent.action.lower() if intent.action else ""
        target = intent.target.lower() if intent.target else ""

        # Configuration commands ("set/configure github username ...") and
        # username queries belong to the user_config skill, not to tracking.
        if action in ("set", "configure") or "username" in target:
            return {
                "success": False,
                "status": "unknown",
                "error": f"Unknown command: {intent.action} {intent.target}",
            }

        # Does this skill own this intent?
        # "what"/"how" are conversational words — only claim them when the
        # question is actually about projects/GitHub/repos, so casual questions
        # ("what is the capital of France?") fall through to the Natural
        # Language Processor fallback instead of getting a GitHub status dump.
        owns = (
            action in ("check", "status", "show", "pending", "sync")
            or (action in ("what", "how") and (
                "project" in target or "github" in target or "repo" in target
            ))
            or "project" in target
            or "github" in target
        )

        # Not our command — let other skills try (and the NLP fallback last).
        # Declining BEFORE resolving GitHub keeps casual conversation out of
        # the dispatch below entirely.
        if not owns:
            return {
                "success": False,
                "status": "unknown",
                "error": f"Unknown command: {intent.action} {intent.target}",
            }

        # Resolve the GitHub username (explicit arg > env var > saved setting)
        # before deciding whether we can fulfill the command.
        username = self._ensure_github()

        # Check if GitHub is configured before making API calls
        if not username:
            # We recognize the command but can't fulfill it — signal
            # ownership so the executor surfaces this helpful message.
            return {
                "success": False,
                "status": "not_configured",
                "handled": True,
                "error": (
                    "GitHub is not configured. "
                    "Say 'set my github username to <your-username>' in the chat "
                    "to save it permanently."
                ),
            }

        # Check / scan GitHub for new repos
        if action in ("check",):
            result = self.check_new_repositories()
            return {"success": True, "status": result}

        # Project status / summary
        if action in ("status", "how", "what", "show", "pending") or "project" in target:
            # Query once — both the text summary and the visual cards use the
            # same repository + summary data so they never diverge.
            repositories = self.database.get_all_repositories()
            result = self.project_status(repositories)
            cards = self._project_cards(repositories)
            payload: dict[str, Any] = {"success": True, "status": result}
            if cards:
                payload["result"] = {
                    "visual": {
                        "type": "project_status",
                        "data": {"projects": cards},
                    }
                }
            return payload

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

    def project_status(self, repositories: list[dict[str, Any]] | None = None) -> str:
        """Get a summary of all tracked projects."""
        if repositories is None:
            repositories = self.database.get_all_repositories()

        if not repositories:
            return (
                "No projects are being tracked yet. "
                "Try saying 'check github' to find your repositories."
            )

        cards = self._project_cards(repositories)

        if not cards:
            return f"Tracking {len(repositories)} repositories but no data synced yet. Try 'sync repositories'."

        summaries = [
            {
                "repository": card["name"],
                "open_issues": card["open_issues"],
                "open_pull_requests": card["open_pull_requests"],
                "stars": card["stars"],
                "last_updated": card["last_updated"],
            }
            for card in cards
        ]

        return PROJECT_SUMMARY + "\n\n" + format_project_summary(summaries)

    def _project_cards(self, repositories: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        """
        Build structured project card data for the chat UI.

        Joins tracked repositories with their latest synced summaries so
        the frontend can render a visual health card per project.

        Args:
            repositories: Tracked repositories. If None, loads from database.

        Returns:
            List of card dicts (one per tracked repo with data synced)
        """
        if repositories is None:
            repositories = self.database.get_all_repositories()
        cards: list[dict[str, Any]] = []

        for repo in repositories:
            summary = self.database.get_summary(repo["name"])
            if not summary:
                continue

            open_issues = int(summary.get("open_issues") or 0)
            open_prs = int(summary.get("open_pull_requests") or 0)
            # Simple health heuristic: open issues/PRs chip away from 100.
            health = max(0, min(100, 100 - (open_issues * 2 + open_prs * 3)))

            cards.append(
                {
                    "name": repo.get("name"),
                    "full_name": repo.get("full_name"),
                    "description": repo.get("description"),
                    "private": bool(repo.get("private")),
                    "html_url": repo.get("html_url"),
                    "language": repo.get("language") or summary.get("language"),
                    "stars": summary.get("stars", 0),
                    "forks": summary.get("forks", 0),
                    "open_issues": open_issues,
                    "open_pull_requests": open_prs,
                    "health": health,
                    "last_updated": summary.get("last_updated"),
                    "latest_commit": {
                        "sha": summary.get("latest_commit_sha"),
                        "message": summary.get("latest_commit_message"),
                        "author": summary.get("latest_commit_author"),
                        "date": summary.get("latest_commit_date"),
                        "url": summary.get("latest_commit_url"),
                    },
                }
            )

        return cards
