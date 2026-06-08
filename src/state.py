"""Component 7 — SQLite state, dedup, and audit log.

Tracks:
  - processed_terms: every term already reviewed (approved or rejected) so it is
    never proposed again.
  - runs: one row per scheduled run (period, decision, counts).
  - applied_changes: audit trail of what was actually written to Google Ads.
  - sessions / session_items: live state for the interactive per-item picker.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "searchterms.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_terms (
    term        TEXT PRIMARY KEY,
    kind        TEXT,            -- negative | keyword
    decision    TEXT,            -- applied | rejected
    run_id      TEXT,
    first_seen  TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    started_at  TEXT,
    period      TEXT,
    decision    TEXT,            -- approve_all | reject_all | select | timeout
    n_neg       INTEGER,
    n_kw        INTEGER,
    n_applied   INTEGER
);
CREATE TABLE IF NOT EXISTS applied_changes (
    run_id      TEXT,
    term        TEXT,
    type        TEXT,            -- negative | keyword
    match_type  TEXT,
    target      TEXT,            -- shared set name | ad group name
    applied_at  TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    run_id        TEXT PRIMARY KEY,
    chat_id       TEXT,
    message_id    INTEGER,
    page          INTEGER DEFAULT 0,
    status        TEXT,            -- open | done
    proposal_text TEXT
);
CREATE TABLE IF NOT EXISTS session_items (
    run_id      TEXT,
    idx         INTEGER,
    term        TEXT,
    kind        TEXT,            -- negative | keyword
    match_type  TEXT,
    target      TEXT,            -- ad group (for keywords)
    reason      TEXT,
    selected    INTEGER DEFAULT 1,
    PRIMARY KEY (run_id, idx)
);
"""


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


# ── dedup ───────────────────────────────────────────────────────────────────
def processed_terms(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT term FROM processed_terms").fetchall()
    return {r["term"].lower() for r in rows}


def mark_processed(conn: sqlite3.Connection, term: str, kind: str,
                   decision: str, run_id: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO processed_terms(term, kind, decision, run_id, first_seen) "
        "VALUES (?,?,?,?,?)",
        (term, kind, decision, run_id, _now()),
    )
    conn.commit()


# ── runs ────────────────────────────────────────────────────────────────────
def last_run_date(conn: sqlite3.Connection) -> Optional[dt.date]:
    row = conn.execute(
        "SELECT started_at FROM runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if not row or not row["started_at"]:
        return None
    return dt.datetime.fromisoformat(row["started_at"]).date()


def record_run(conn: sqlite3.Connection, run_id: str, period: str,
               n_neg: int, n_kw: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO runs(run_id, started_at, period, decision, "
        "n_neg, n_kw, n_applied) VALUES (?,?,?,?,?,?,?)",
        (run_id, _now(), period, "pending", n_neg, n_kw, 0),
    )
    conn.commit()


def finalize_run(conn: sqlite3.Connection, run_id: str, decision: str,
                 n_applied: int) -> None:
    conn.execute(
        "UPDATE runs SET decision=?, n_applied=? WHERE run_id=?",
        (decision, n_applied, run_id),
    )
    conn.commit()


def record_applied(conn: sqlite3.Connection, run_id: str, term: str,
                   type_: str, match_type: str, target: str) -> None:
    conn.execute(
        "INSERT INTO applied_changes(run_id, term, type, match_type, target, applied_at) "
        "VALUES (?,?,?,?,?,?)",
        (run_id, term, type_, match_type, target, _now()),
    )
    conn.commit()


# ── interactive session (per-item picker) ───────────────────────────────────
def open_session(conn: sqlite3.Connection, run_id: str, chat_id: str,
                 message_id: int, items: list[dict],
                 proposal_text: str = "") -> None:
    conn.execute(
        "INSERT OR REPLACE INTO sessions(run_id, chat_id, message_id, page, "
        "status, proposal_text) VALUES (?,?,?,0,'open',?)",
        (run_id, chat_id, message_id, proposal_text),
    )
    conn.execute("DELETE FROM session_items WHERE run_id=?", (run_id,))
    for idx, it in enumerate(items):
        conn.execute(
            "INSERT INTO session_items(run_id, idx, term, kind, match_type, target, "
            "reason, selected) VALUES (?,?,?,?,?,?,?,1)",
            (run_id, idx, it["term"], it["kind"], it.get("match_type"),
             it.get("target"), it.get("reason")),
        )
    conn.commit()


def get_session(conn: sqlite3.Connection, run_id: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM sessions WHERE run_id=?", (run_id,)).fetchone()


def get_open_session(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM sessions WHERE status='open' ORDER BY rowid DESC LIMIT 1"
    ).fetchone()


def get_session_by_message(conn: sqlite3.Connection, message_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM sessions WHERE message_id=?", (message_id,)
    ).fetchone()


def session_items(conn: sqlite3.Connection, run_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM session_items WHERE run_id=? ORDER BY idx", (run_id,)
    ).fetchall()


def toggle_item(conn: sqlite3.Connection, run_id: str, idx: int) -> None:
    conn.execute(
        "UPDATE session_items SET selected = 1 - selected WHERE run_id=? AND idx=?",
        (run_id, idx),
    )
    conn.commit()


def set_page(conn: sqlite3.Connection, run_id: str, page: int) -> None:
    conn.execute("UPDATE sessions SET page=? WHERE run_id=?", (page, run_id))
    conn.commit()


def close_session(conn: sqlite3.Connection, run_id: str) -> None:
    conn.execute("UPDATE sessions SET status='done' WHERE run_id=?", (run_id,))
    conn.commit()
