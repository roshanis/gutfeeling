"""SQLite storage. Each response is one row; answers are kept as JSON keyed by
question id, so adding questions never needs a database migration."""
import csv
import io
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from . import schema

DDL = """
CREATE TABLE IF NOT EXISTS responses (
    id TEXT PRIMARY KEY,
    submitted_at TEXT NOT NULL,
    survey_version INTEGER NOT NULL,
    answers TEXT NOT NULL
)
"""

_lock = threading.Lock()  # one shared connection, used from server threads


def connect(path):
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute(DDL)
    conn.commit()
    return conn


def save(conn, config, answers):
    response_id = str(uuid.uuid4())
    with _lock:
        conn.execute(
            "INSERT INTO responses (id, submitted_at, survey_version, answers) VALUES (?, ?, ?, ?)",
            (response_id, datetime.now(timezone.utc).isoformat(timespec="seconds"),
             config.get("version", 1), json.dumps(answers, sort_keys=True)),
        )
        conn.commit()
    return response_id


def all_responses(conn):
    with _lock:
        rows = conn.execute(
            "SELECT id, submitted_at, survey_version, answers FROM responses ORDER BY submitted_at"
        ).fetchall()
    for rid, ts, version, answers in rows:
        yield {"id": rid, "submitted_at": ts, "survey_version": version, "answers": json.loads(answers)}


def export_csv(conn, config):
    out = io.StringIO()
    meta = ["response_id", "submitted_at", "survey_version"]
    writer = csv.DictWriter(out, fieldnames=meta + schema.columns(config), extrasaction="ignore")
    writer.writeheader()
    for r in all_responses(conn):
        row = schema.flatten(config, r["answers"])
        row.update(response_id=r["id"], submitted_at=r["submitted_at"], survey_version=r["survey_version"])
        writer.writerow(row)
    return out.getvalue()
