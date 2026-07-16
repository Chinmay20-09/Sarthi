import sqlite3
from pathlib import Path


DATABASE_PATH = Path("database") / "sarthi.db"


class GitHubDatabase:
    def __init__(self):
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

        self.connection = sqlite3.connect(DATABASE_PATH)
        self.connection.row_factory = sqlite3.Row

        self.create_tables()

    def create_tables(self):
        cursor = self.connection.cursor()

        cursor.execute(
            """
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
        )

        cursor.execute(
            """
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
        )

        self.connection.commit()

    def repository_exists(self, repository_name: str) -> bool:
        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT 1
            FROM github_projects
            WHERE name = ?
            """,
            (repository_name,),
        )

        return cursor.fetchone() is not None

    def add_repository(self, repository: dict):
        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT OR IGNORE INTO github_projects (
                github_id,
                name,
                full_name,
                description,
                private,
                html_url,
                default_branch,
                language,
                created_at,
                updated_at
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

        self.connection.commit()

    def get_all_repositories(self):
        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM github_projects
            ORDER BY name
            """
        )

        return [dict(row) for row in cursor.fetchall()]

    def get_repository(self, repository_name: str):
        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM github_projects
            WHERE name = ?
            """,
            (repository_name,),
        )

        row = cursor.fetchone()

        return dict(row) if row else None

    def update_summary(self, repository_name: str, summary: dict):
        commit = summary.get("latest_commit") or {}

        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO github_summary (
                repository,
                stars,
                forks,
                watchers,
                language,
                open_issues,
                open_pull_requests,
                last_updated,
                latest_commit_sha,
                latest_commit_message,
                latest_commit_author,
                latest_commit_date,
                latest_commit_url
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

        self.connection.commit()

    def get_summary(self, repository_name: str):
        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM github_summary
            WHERE repository = ?
            """,
            (repository_name,),
        )

        row = cursor.fetchone()

        return dict(row) if row else None

    def delete_repository(self, repository_name: str):
        cursor = self.connection.cursor()

        cursor.execute(
            """
            DELETE FROM github_projects
            WHERE name = ?
            """,
            (repository_name,),
        )

        cursor.execute(
            """
            DELETE FROM github_summary
            WHERE repository = ?
            """,
            (repository_name,),
        )

        self.connection.commit()

    def close(self):
        self.connection.close()