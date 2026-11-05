"""Opens the SQLite database and creates the claims and history tables."""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY,
    passenger TEXT NOT NULL CHECK (trim(passenger) <> ''),
    flight TEXT NOT NULL CHECK (trim(flight) <> ''),
    type TEXT NOT NULL CHECK (type IN ('delayed', 'lost', 'damaged')),
    tier TEXT NOT NULL CHECK (tier IN ('standard', 'silver', 'gold')),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'assigned', 'escalated', 'resolved', 'closed')),
    agent TEXT,
    note TEXT NOT NULL DEFAULT '',
    filed_at TEXT NOT NULL,
    deadline TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY,
    claim_id INTEGER NOT NULL REFERENCES claims(id),
    old_status TEXT,
    new_status TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    changed_at TEXT NOT NULL
);
"""


def connect(path="claims.db"):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
