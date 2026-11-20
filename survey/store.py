"""Response storage.

Each response is one row; answers are kept as JSON keyed by question id, so
adding questions never needs a database migration.

- If DATABASE_URL (or POSTGRES_URL, which Vercel/Neon sets) is present, responses
  go to Postgres. Use this when deployed on Vercel, whose disk is not persistent.
- Otherwise they go to a local SQLite file, for development.
"""
import csv
import io
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from . import schema


def database_url():
    return os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")


def open_store(sqlite_path=None):
    url = database_url()
    if url:
        return PostgresStore(url)
    return SqliteStore(sqlite_path or os.environ.get("SQLITE_PATH", "data/responses.db"))


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SqliteStore:
    DDL = """CREATE TABLE IF NOT EXISTS responses (
        id TEXT PRIMARY KEY, submitted_at TEXT NOT NULL,
        survey_version INTEGER NOT NULL, answers TEXT NOT NULL)"""

    def __init__(self, path):
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._lock = threading.Lock()  # one shared connection, used from server threads
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute(self.DDL)
        self.conn.commit()

    def save(self, config, answers):
        rid = str(uuid.uuid4())
        with self._lock:
            self.conn.execute(
                "INSERT INTO responses (id, submitted_at, survey_version, answers) VALUES (?, ?, ?, ?)",
                (rid, _now(), config.get("version", 1), json.dumps(answers, sort_keys=True)))
            self.conn.commit()
        return rid

    def all(self):
        with self._lock:
            rows = self.conn.execute(
                "SELECT id, submitted_at, survey_version, answers FROM responses ORDER BY submitted_at"
            ).fetchall()
        return [{"id": r[0], "submitted_at": r[1], "survey_version": r[2], "answers": json.loads(r[3])}
                for r in rows]


class PostgresStore:
    DDL = """CREATE TABLE IF NOT EXISTS survey_responses (
        id UUID PRIMARY KEY, submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        survey_version INTEGER NOT NULL, answers JSONB NOT NULL)"""

    def __init__(self, url):
        import psycopg  # only needed when deployed with Postgres

        self._psycopg = psycopg
        self.url = url
        self._ready = False

    def _connect(self):
        conn = self._psycopg.connect(self.url, autocommit=True, connect_timeout=10)
        if not self._ready:
            conn.execute(self.DDL)
            self._ready = True
        return conn

    def save(self, config, answers):
        rid = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO survey_responses (id, survey_version, answers) VALUES (%s, %s, %s::jsonb)",
                (rid, config.get("version", 1), json.dumps(answers, sort_keys=True)))
        return rid

    def all(self):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id::text, submitted_at, survey_version, answers FROM survey_responses "
                "ORDER BY submitted_at").fetchall()
        return [{"id": r[0], "submitted_at": r[1].isoformat(timespec="seconds"), "survey_version": r[2],
                 "answers": r[3]} for r in rows]


def export_csv(store, config):
    out = io.StringIO()
    meta = ["response_id", "submitted_at", "survey_version"]
    writer = csv.DictWriter(out, fieldnames=meta + schema.columns(config), extrasaction="ignore")
    writer.writeheader()
    for r in store.all():
        row = schema.flatten(config, r["answers"])
        row.update(response_id=r["id"], submitted_at=r["submitted_at"], survey_version=r["survey_version"])
        writer.writerow(row)
    return out.getvalue()
