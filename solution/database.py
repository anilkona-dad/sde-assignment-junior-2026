
import sqlite3
from pathlib import Path

from config import DATABASE_PATH


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ingestion_drops (
    drop_id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS batches (
    workflow_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    source_drop TEXT NOT NULL,
    PRIMARY KEY (workflow_id, batch_id)
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    phone_hash TEXT NOT NULL,
    encrypted_data BLOB NOT NULL,
    batch_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (workflow_id, phone_hash),
    FOREIGN KEY (workflow_id, batch_id)
        REFERENCES batches(workflow_id, batch_id)
);

CREATE INDEX IF NOT EXISTS idx_leads_workflow
ON leads(workflow_id);

CREATE INDEX IF NOT EXISTS idx_leads_phone_hash
ON leads(workflow_id, phone_hash);

CREATE TABLE IF NOT EXISTS seen_event_ids (
    event_id TEXT PRIMARY KEY,
    first_seen_drop TEXT NOT NULL,
    outcome TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interaction_events (
    event_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    call_id TEXT,
    phone_hash TEXT,
    disposition_code TEXT,
    encrypted_payload BLOB NOT NULL,
    source_drop TEXT NOT NULL,
    FOREIGN KEY (event_id)
        REFERENCES seen_event_ids(event_id)
);

CREATE INDEX IF NOT EXISTS idx_events_workflow_call
ON interaction_events(workflow_id, call_id);

CREATE INDEX IF NOT EXISTS idx_events_phone
ON interaction_events(workflow_id, phone_hash);

CREATE INDEX IF NOT EXISTS idx_events_occurred
ON interaction_events(occurred_at);

CREATE TABLE IF NOT EXISTS event_lead_links (
    event_id TEXT PRIMARY KEY,
    lead_id INTEGER NOT NULL,
    linked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id)
        REFERENCES interaction_events(event_id),
    FOREIGN KEY (lead_id)
        REFERENCES leads(id)
);

CREATE INDEX IF NOT EXISTS idx_event_links_lead
ON event_lead_links(lead_id);

CREATE TABLE IF NOT EXISTS rejections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    reason TEXT NOT NULL,
    UNIQUE (workflow_id, batch_id, row_number)
);

CREATE TABLE IF NOT EXISTS drop_metrics (
    drop_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value INTEGER NOT NULL,
    PRIMARY KEY (drop_id, metric_name),
    FOREIGN KEY (drop_id)
        REFERENCES ingestion_drops(drop_id)
);

CREATE TRIGGER IF NOT EXISTS prevent_event_update
BEFORE UPDATE ON interaction_events
BEGIN
    SELECT RAISE(ABORT, 'interaction_events is append-only');
END;

CREATE TRIGGER IF NOT EXISTS prevent_event_delete
BEFORE DELETE ON interaction_events
BEGIN
    SELECT RAISE(ABORT, 'interaction_events is append-only');
END;
"""


def get_connection(database_path=None):
    """Create a SQLite connection with foreign keys enabled."""
    path = Path(database_path or DATABASE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 5000")

    return connection


def initialize_database(database_path=None):
    """Create all required tables, indexes and ledger protections."""
    connection = get_connection(database_path)

    try:
        connection.executescript(SCHEMA_SQL)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    initialize_database()
    print(f"Database initialized successfully: {DATABASE_PATH}")
