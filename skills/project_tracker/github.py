import requests


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self, username: str, token: str | None = None):
        self.username = username

        self.headers = {
            "Accept": "application/vnd.github+json"
        }

        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def _get(self, endpoint: str):
        response = requests.get(
            f"{self.BASE_URL}{endpoint}",
            headers=self.headers,
            timeout=15,
        )

        response.raise_for_status()
        return response.json()

    def get_repositories(self):
        repos = self._get(f"/users/{self.username}/repos")

        repositories = []

        for repo in repos:
            repositories.append(
                {
                    "id": repo["id"],
                    "name": repo["name"],
                    "full_name": repo["full_name"],
                    "description": repo.get("description"),
                    "private": repo["private"],
                    "html_url": repo["html_url"],
                    "default_branch": repo["default_branch"],
                    "language": repo.get("language"),
                    "created_at": repo["created_at"],
                    "updated_at": repo["updated_at"],
                }
            )

        return repositories

    def get_repository(self, repository: str):
        return self._get(
            f"/repos/{self.username}/{repository}"
        )

    def get_issues(self, repository: str):
        issues = self._get(
            f"/repos/{self.username}/{repository}/issues?state=open"
        )

        return [
            issue
            for issue in issues
            if "pull_request" not in issue
        ]

    def get_pull_requests(self, repository: str):
        return self._get(
            f"/repos/{self.username}/{repository}/pulls?state=open"
        )

    def get_latest_commit(self, repository: str):
        commits = self._get(
            f"/repos/{self.username}/{repository}/commits?per_page=1"
        )

        if not commits:
            return None

        commit = commits[0]

        return {
            "sha": commit["sha"],
            "message": commit["commit"]["message"],
            "author": commit["commit"]["author"]["name"],
            "date": commit["commit"]["author"]["date"],
            "url": commit["html_url"],
        }

    def get_repository_summary(self, repository: str):
        repo = self.get_repository(repository)
        issues = self.get_issues(repository)
        pulls = self.get_pull_requests(repository)
        latest_commit = self.get_latest_commit(repository)

        return {
            "repository": repository,
            "description": repo.get("description"),
            "stars": repo["stargazers_count"],
            "forks": repo["forks_count"],
            "watchers": repo["watchers_count"],
            "language": repo.get("language"),
            "open_issues": len(issues),
            "open_pull_requests": len(pulls),
            "last_updated": repo["updated_at"],
            "latest_commit": latest_commit,
        }