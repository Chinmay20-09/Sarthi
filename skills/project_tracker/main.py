from .github import GitHubClient
from .database import GitHubDatabase
from .prompts import (
    NEW_REPOSITORY_FOUND,
    REPOSITORY_ADDED,
    REPOSITORY_SKIPPED,
    PROJECT_SUMMARY,
)
from .utils import format_project_summary


class GitHubProjectSkill:
    def __init__(self, username: str, token: str | None = None):
        self.github = GitHubClient(username=username, token=token)
        self.database = GitHubDatabase()

    def execute(self, command: str):
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
                print(
                    NEW_REPOSITORY_FOUND.format(
                        repo_name=repo["name"]
                    )
                )

                choice = input("(yes/no): ").strip().lower()

                if choice in ("yes", "y"):
                    self.database.add_repository(repo)
                    print(
                        REPOSITORY_ADDED.format(
                            repo_name=repo["name"]
                        )
                    )
                else:
                    print(
                        REPOSITORY_SKIPPED.format(
                            repo_name=repo["name"]
                        )
                    )

        return "Repository scan complete."

    def sync_repositories(self):
        repositories = self.database.get_all_repositories()

        for repo in repositories:
            summary = self.github.get_repository_summary(
                repo["name"]
            )
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

        return PROJECT_SUMMARY + "\n\n" + format_project_summary(
            summaries
        )