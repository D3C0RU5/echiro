from contextlib import contextmanager
from pathlib import Path
import os
import sqlite3


# Migrações são aplicadas em ordem e na mesma transação de user_version.
MIGRATIONS = [
    (
        """CREATE TABLE projects (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, jira_url TEXT NOT NULL,
            project_key TEXT NOT NULL, jira_project_id TEXT,
            config_version INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(jira_url, project_key))""",
        """CREATE TABLE connections (
            project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
            credentials BLOB NOT NULL, tested_at TEXT, test_status TEXT)""",
        """CREATE TABLE configurations (
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            version INTEGER NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY(project_id, version))""",
        """CREATE TABLE metadata (
            project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
            data TEXT NOT NULL, fetched_at TEXT NOT NULL)""",
        """CREATE TABLE sprints (
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            jira_id TEXT NOT NULL, data TEXT NOT NULL,
            PRIMARY KEY(project_id, jira_id))""",
        """CREATE TABLE tickets (
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            jira_id TEXT NOT NULL, issue_key TEXT NOT NULL, data TEXT NOT NULL,
            PRIMARY KEY(project_id, jira_id), UNIQUE(project_id, issue_key))""",
        """CREATE TABLE history_events (
            project_id TEXT NOT NULL, ticket_id TEXT NOT NULL,
            jira_id TEXT NOT NULL, data TEXT NOT NULL,
            PRIMARY KEY(project_id, ticket_id, jira_id),
            FOREIGN KEY(project_id, ticket_id) REFERENCES tickets(project_id, jira_id) ON DELETE CASCADE)""",
        """CREATE TABLE sync_runs (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
            status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
            checkpoint TEXT, error_code TEXT, config_version INTEGER NOT NULL)""",
        """CREATE TABLE metric_runs (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
            config_version INTEGER NOT NULL, computed_at TEXT NOT NULL, data TEXT NOT NULL,
            FOREIGN KEY(project_id, config_version) REFERENCES configurations(project_id, version))""",
    ),
    (
        "CREATE UNIQUE INDEX one_running_sync_per_project ON sync_runs(project_id) WHERE status='running'",
        """CREATE TABLE sync_staging (
            run_id TEXT NOT NULL REFERENCES sync_runs(id) ON DELETE CASCADE,
            ticket_id TEXT NOT NULL, updated_at TEXT, data TEXT NOT NULL,
            PRIMARY KEY(run_id, ticket_id))""",
        """CREATE TABLE snapshots (
            project_id TEXT PRIMARY KEY REFERENCES projects(id), run_id TEXT NOT NULL REFERENCES sync_runs(id),
            collected_at TEXT NOT NULL, data TEXT NOT NULL)""",
    ),
]


class Database:
    def __init__(self, path: Path):
        self.path = Path(path).resolve()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.fchmod(descriptor, 0o600)
        os.close(descriptor)
        with self.transaction() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > len(MIGRATIONS):
                raise RuntimeError('Banco criado por uma versão mais recente da aplicação.')
            for index in range(version, len(MIGRATIONS)):
                for statement in MIGRATIONS[index]:
                    db.execute(statement)
                db.execute(f'PRAGMA user_version = {index + 1}')

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()
