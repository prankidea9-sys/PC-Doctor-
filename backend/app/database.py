import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "pc_doctor.sqlite3"


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scanned_at TEXT NOT NULL,
                health_score INTEGER NOT NULL,
                health_label TEXT NOT NULL,
                report_json TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cleanups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cleaned_at TEXT NOT NULL,
                freed_bytes INTEGER NOT NULL,
                report_json TEXT NOT NULL
            )
        """)


def save_scan(report: dict) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO scans (scanned_at, health_score, health_label, report_json) VALUES (?, ?, ?, ?)",
            (report["scanned_at"], report["health_score"], report["health_label"], json.dumps(report)),
        )
        return cur.lastrowid


def get_history(limit: int = 20):
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, scanned_at, health_score, health_label FROM scans ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def save_cleanup(report: dict) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO cleanups (cleaned_at, freed_bytes, report_json) VALUES (?, ?, ?)",
            (report["cleaned_at"], report["freed_bytes"], json.dumps(report)),
        )
        return cur.lastrowid


def get_cleanups(limit: int = 10):
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, cleaned_at, freed_bytes FROM cleanups ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
