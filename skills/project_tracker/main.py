"""
GitHub Project Tracker skill for Sarthi.

Tracks GitHub repositories, monitors issues and pull requests,
and provides project status summaries.
"""

from typing import Any

from brain.intent import Intent
from skills.base import BaseSkill

from .database import GitHubDatabase
from .github import GitHubClient
from .prompts import (
    NEW_REPOSITORY_FOUND,
    PROJECT_SUMMARY,
    REPOSITORY_ADDED,
    REPOSITORY_SKIPPED,
)
from .utils import format_project_summary


class GitHubProjectSkill(BaseSkill):
    """
    Tracks GitHub projects and provides status summaries.

    Accepts parsed Intents from the brain pipeline.
    Maps intent.action/intent.target to internal commands.
    """

    name = "project_tracker"
    description = "Tracks GitHub and Notion projects"
    version = "1.0.0"

    def __init__(self, username: str, token: str | None = None):
        self.github = GitHubClient(username=username, token=token)
        self.database = GitHubDatabase()

    # ------------------------------------------------------------------
    # BaseSkill interface
    # ------------------------------------------------------------------

    def execute(self, intent: str | Intent) -> dict[str, Any]:
        """
        Execute a command based on parsed intent.

        Maps intent action/target combinations to internal handlers:
            - action="check", target="github"  → check_new_repositories()
            - action="sync", target="repositories" → sync_repositories()
            - action="status", target="project" or "projects" → project_status()

        Backward compatible: accepts raw strings (routes to execute_text()).
        """
        # Backward compatibility: accept raw strings from legacy callers
        if isinstance(intent, str):
            result = self.execute_text(intent)
            return {"success": True, "status": result}

        action = intent.action.lower()
        target = intent.target.lower()

        # check github
        if action == "check" or ("check" in action and "github" in target):
            result = self.check_new_repositories()
            return {"success": True, "status": result}

        # sync repositories
        if action == "sync" or ("sync" in target):
            result = self.sync_repositories()
            return {"success": True, "status": result}

        # project status
        if action == "status" or ("project" in target or "projects" in target):
            result = self.project_status()
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

    def check_new_repositories(self):
        repositories = self.github.get_repositories()

        for repo in repositories:
            if not self.database.repository_exists(repo["name"]):
                print(NEW_REPOSITORY_FOUND.format(repo_name=repo["name"]))

                choice = input("(yes/no): ").strip().lower()

                if choice in ("yes", "y"):
                    self.database.add_repository(repo)
                    print(REPOSITORY_ADDED.format(repo_name=repo["name"]))
                else:
                    print(REPOSITORY_SKIPPED.format(repo_name=repo["name"]))

        return "Repository scan complete."

    def sync_repositories(self):
        repositories = self.database.get_all_repositories()

        for repo in repositories:
            summary = self.github.get_repository_summary(repo["name"])
            self.database.update_summary(
                repo["name"],
                summary,
            )

        return "Repositories synced successfully."

    def project_status(self):
        repositories = self.database.get_all_repositories()

        summaries = []

        for repo in repositories:
            summary = self.database.get_summary(repo["name"])

            if summary:
                summaries.append(summary)

        return PROJECT_SUMMARY + "\n\n" + format_project_summary(summaries)
