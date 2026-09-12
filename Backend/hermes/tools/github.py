"""
github tool — queries GitHub through Sarthi's existing project_tracker skill.

This tool does NOT spawn a second GitHub integration: it instantiates the
same GitHubProjectSkill the Brain's executor uses, resolves the configured
username through the skill's own logic (env var > saved chat setting), and
calls the skill's GitHubClient. Hermes only requests the structured
operation; Sarthi executes it.
"""

import logging
from typing import Any

from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# Operations the tool understands, mapped to a GitHubClient method name.
_OPERATIONS = {
    "repositories": "get_repositories",
    "search": "search_repositories",
    "summary": "get_repository_summary",
    "issues": "get_issues",
    "pull_requests": "get_pull_requests",
    "latest_commit": "get_latest_commit",
    "branches": "get_branches",
    "releases": "get_releases",
}

# Operations that require a repository name argument.
_REQUIRES_REPOSITORY = {
    "summary",
    "issues",
    "pull_requests",
    "latest_commit",
    "branches",
    "releases",
}

# Operations that require a search query argument.
_REQUIRES_QUERY = {"search"}


def _short_sha(sha: str) -> str:
    """First 7 chars of a commit SHA for compact display."""
    return (sha or "")[:7]


class GitHubTool(BaseTool):
    """
    Query GitHub: list repositories, or fetch issues, pull requests, the
    latest commit, or a full status summary for one repository.

    Username resolution matches the GitHubProjectSkill exactly:
        1. SKILL_PROJECT_TRACKER_USERNAME env var
        2. github_username saved via the chat ("set my github username to ...")
    """

    name = "github"
    description = (
        "Query GitHub: list or search the user's repositories, or fetch "
        "issues, pull requests, branches, releases, the latest commit, or a "
        "status summary for one repository."
    )
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": (
                    "One of: repositories, search, summary, issues, pull_requests, "
                    "latest_commit, branches, releases"
                ),
            },
            "repository": {
                "type": "string",
                "description": (
                    "Repository name (required for summary, issues, pull_requests, "
                    "latest_commit, branches, releases)"
                ),
            },
            "query": {
                "type": "string",
                "description": "Search query (required for the search operation).",
            },
        },
        "required": ["operation"],
    }

    # ------------------------------------------------------------------
    # Skill wiring (patched in tests)
    # ------------------------------------------------------------------

    def _get_skill(self):
        """Instantiate the existing GitHubProjectSkill (the Brain's executor path)."""
        from skills.project_tracker.main import GitHubProjectSkill

        return GitHubProjectSkill()

    # ------------------------------------------------------------------
    # BaseTool interface
    # ------------------------------------------------------------------

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Validate arguments and delegate to the existing GitHub skill."""
        operation = str(arguments.get("operation") or "").strip().lower()
        repository = str(arguments.get("repository") or "").strip()
        query = str(arguments.get("query") or "").strip()

        if operation not in _OPERATIONS:
            return ToolResult(
                success=False,
                tool=self.name,
                error=("Unknown GitHub operation. Use one of: " + ", ".join(sorted(_OPERATIONS))),
                invalid=True,
            )

        if operation in _REQUIRES_REPOSITORY and not repository:
            return ToolResult(
                success=False,
                tool=self.name,
                error="A repository name is required for this GitHub operation.",
                invalid=True,
            )

        if operation in _REQUIRES_QUERY and not query:
            return ToolResult(
                success=False,
                tool=self.name,
                error="A search query is required for the search operation.",
                invalid=True,
            )

        try:
            skill = self._get_skill()
            username = skill._ensure_github()
            client = skill.github
        except Exception as e:  # never leak internals upward
            logger.error("github tool could not initialize skill: %s", e)
            return ToolResult(
                success=False,
                tool=self.name,
                error="GitHub could not be reached right now.",
            )

        if not username or client is None:
            return ToolResult(
                success=False,
                tool=self.name,
                error=(
                    "GitHub is not configured. Say 'set my github username to "
                    "<your-username>' in the chat to save it permanently."
                ),
            )

        method = getattr(client, _OPERATIONS[operation])
        try:
            if operation == "repositories":
                data = method()
                return self._repositories_result(data)
            if operation == "search":
                data = method(query)
                return self._search_result(data)
            if operation == "summary":
                data = method(repository)
                return self._summary_result(data)
            if operation == "issues":
                data = method(repository)
                return self._issues_result(repository, data)
            if operation == "pull_requests":
                data = method(repository)
                return self._pull_requests_result(repository, data)
            if operation == "branches":
                data = method(repository)
                return self._branches_result(repository, data)
            if operation == "releases":
                data = method(repository)
                return self._releases_result(repository, data)
            # latest_commit
            data = method(repository)
            return self._latest_commit_result(repository, data)
        except Exception as e:  # never leak internals upward
            logger.error("github tool request failed for %s: %s", operation, e)
            return ToolResult(
                success=False,
                tool=self.name,
                error=self._friendly_error(e, operation, repository),
            )

    # ------------------------------------------------------------------
    # Result formatting (safe, human-readable summaries)
    # ------------------------------------------------------------------

    def _repositories_result(self, repos: list[dict[str, Any]]) -> ToolResult:
        if not repos:
            return ToolResult(
                success=True,
                tool=self.name,
                result="No repositories found.",
                data={"repositories": []},
            )
        names = [repo.get("name") for repo in repos if repo.get("name")]
        result = f"{len(names)} repositories: {', '.join(names)}"
        return ToolResult(
            success=True,
            tool=self.name,
            result=result,
            data={
                "repositories": [
                    {
                        "name": repo.get("name"),
                        "description": repo.get("description"),
                        "language": repo.get("language"),
                        "private": bool(repo.get("private")),
                        "html_url": repo.get("html_url"),
                    }
                    for repo in repos
                ]
            },
        )

    def _summary_result(self, summary: dict[str, Any]) -> ToolResult:
        name = summary.get("repository") or "repository"
        latest = summary.get("latest_commit") or {}
        commit = ""
        if latest:
            commit = (
                f"; latest commit {_short_sha(latest.get('sha') or '')} "
                f"'{latest.get('message') or ''}' by {latest.get('author') or 'unknown'}"
            )
        result = (
            f"{name}: {summary.get('language') or 'unknown language'}, "
            f"{summary.get('stars', 0)} stars, {summary.get('forks', 0)} forks, "
            f"{summary.get('open_issues', 0)} open issues, "
            f"{summary.get('open_pull_requests', 0)} open pull requests"
            f"{commit}"
        )
        return ToolResult(
            success=True,
            tool=self.name,
            result=result,
            data=summary,
        )

    def _issues_result(self, repository: str, issues: list[dict[str, Any]]) -> ToolResult:
        if not issues:
            return ToolResult(
                success=True,
                tool=self.name,
                result=f"No open issues in {repository}.",
                data={"issues": []},
            )
        result = f"{len(issues)} open issues in {repository}: " + "; ".join(
            f"#{issue.get('number')} {issue.get('title')}" for issue in issues
        )
        return ToolResult(
            success=True,
            tool=self.name,
            result=result,
            data={
                "issues": [
                    {
                        "number": issue.get("number"),
                        "title": issue.get("title"),
                        "html_url": issue.get("html_url"),
                        "state": issue.get("state"),
                    }
                    for issue in issues
                ]
            },
        )

    def _pull_requests_result(self, repository: str, pulls: list[dict[str, Any]]) -> ToolResult:
        if not pulls:
            return ToolResult(
                success=True,
                tool=self.name,
                result=f"No open pull requests in {repository}.",
                data={"pull_requests": []},
            )
        result = f"{len(pulls)} open pull requests in {repository}: " + "; ".join(
            f"#{pr.get('number')} {pr.get('title')}" for pr in pulls
        )
        return ToolResult(
            success=True,
            tool=self.name,
            result=result,
            data={
                "pull_requests": [
                    {
                        "number": pr.get("number"),
                        "title": pr.get("title"),
                        "html_url": pr.get("html_url"),
                    }
                    for pr in pulls
                ]
            },
        )

    def _search_result(self, repos: list[dict[str, Any]]) -> ToolResult:
        if not repos:
            return ToolResult(
                success=True,
                tool=self.name,
                result="No repositories found for that search.",
                data={"repositories": []},
            )
        result = f"{len(repos)} repositories found: " + "; ".join(
            f"{repo.get('full_name')} ({repo.get('stars', 0)} stars)" for repo in repos
        )
        return ToolResult(
            success=True,
            tool=self.name,
            result=result,
            data={"repositories": repos},
        )

    def _branches_result(self, repository: str, branches: list[dict[str, Any]]) -> ToolResult:
        if not branches:
            return ToolResult(
                success=True,
                tool=self.name,
                result=f"No branches found in {repository}.",
                data={"branches": []},
            )
        names = [branch.get("name") for branch in branches if branch.get("name")]
        result = f"{len(names)} branches in {repository}: {', '.join(names)}"
        return ToolResult(
            success=True,
            tool=self.name,
            result=result,
            data={"branches": branches},
        )

    def _releases_result(self, repository: str, releases: list[dict[str, Any]]) -> ToolResult:
        if not releases:
            return ToolResult(
                success=True,
                tool=self.name,
                result=f"No releases found in {repository}.",
                data={"releases": []},
            )
        result = f"{len(releases)} releases in {repository}: " + "; ".join(
            f"{release.get('tag_name')} ({release.get('published_at') or 'unknown date'})"
            for release in releases
        )
        return ToolResult(
            success=True,
            tool=self.name,
            result=result,
            data={
                "releases": [
                    {
                        "tag_name": release.get("tag_name"),
                        "name": release.get("name"),
                        "html_url": release.get("html_url"),
                        "published_at": release.get("published_at"),
                    }
                    for release in releases
                ]
            },
        )

    def _latest_commit_result(self, repository: str, commit: dict[str, Any] | None) -> ToolResult:
        if not commit:
            return ToolResult(
                success=True,
                tool=self.name,
                result=f"No commits yet in {repository}.",
                data={"commit": None},
            )
        result = (
            f"Latest commit in {repository}: {_short_sha(commit.get('sha') or '')} "
            f"'{commit.get('message') or ''}' by {commit.get('author') or 'unknown'} "
            f"on {commit.get('date') or 'unknown date'}"
        )
        return ToolResult(
            success=True,
            tool=self.name,
            result=result,
            data={"commit": commit},
        )

    def _friendly_error(self, exc: Exception, operation: str, repository: str) -> str:
        """Map HTTP/connection errors to safe, user-facing messages."""
        status = getattr(exc, "response", None) and getattr(exc.response, "status_code", None)
        if status == 404:
            return f"Repository '{repository}' was not found on GitHub."
        if status in (401, 403):
            return (
                "GitHub authentication failed. Check the access token in "
                "SKILL_PROJECT_TRACKER_TOKEN."
            )
        if status:
            return f"GitHub returned an error (HTTP {status})."
        # Connection / timeout / generic failures
        return "GitHub could not be reached right now."
