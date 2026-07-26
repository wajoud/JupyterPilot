"""
jupyterpilot/session_store.py
─────────────────────────────
SQLite-backed session store for JupyterPilot.

Replaces user_mapping.json as the live source of truth for:
  - Team → VM routing  (table: team_mappings)
  - Per-user session state for crash recovery  (table: user_sessions)

Design decisions:
  - Uses Python stdlib `sqlite3` only — zero new pip dependencies.
  - Thread-safe: check_same_thread=False + a module-level threading.Lock for writes.
  - Provides a ping() health check so spawner.py can gracefully fall back to
    the JSON file if the DB is unreadable.
  - All public methods return plain dicts so they are trivially mockable in tests.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

log = logging.getLogger("jupyterhub")

# Module-level write lock — safe under JupyterHub's asyncio + thread-pool model.
_write_lock = threading.Lock()

# ──────────────────────────────────────────────────────────────────────────────
# DDL
# ──────────────────────────────────────────────────────────────────────────────

_DDL_TEAM_MAPPINGS = """
CREATE TABLE IF NOT EXISTS team_mappings (
    team        TEXT PRIMARY KEY,
    server_ip   TEXT NOT NULL,
    ssh_key     TEXT NOT NULL,
    ssh_user    TEXT DEFAULT NULL
);
"""

_DDL_USER_SESSIONS = """
CREATE TABLE IF NOT EXISTS user_sessions (
    username    TEXT PRIMARY KEY,
    pid         TEXT,
    vm_ip       TEXT,
    port        INTEGER,
    start_time  TEXT,
    role        TEXT    DEFAULT 'user',
    status      TEXT    DEFAULT 'stopped',
    group_name  TEXT
);
"""


# ──────────────────────────────────────────────────────────────────────────────
# SessionStore
# ──────────────────────────────────────────────────────────────────────────────

class SessionStore:
    """
    Thread-safe SQLite wrapper providing team mapping lookups and per-user
    session state management for the JupyterPilot SSH spawner.

    Args:
        db_path: Absolute path to the SQLite database file.
                 Defaults to ``jupyterpilot_state.db`` in the current directory.

    Example::

        store = SessionStore("/var/lib/jupyterhub/jupyterpilot_state.db")
        store.init_db()

        store.set_mapping("team_alpha", "10.0.1.15", "/etc/keys/alpha.pem")
        info = store.get_mapping("team_alpha")
        # {'team': 'team_alpha', 'server_ip': '10.0.1.15',
        #  'ssh_key': '/etc/keys/alpha.pem', 'ssh_user': None}
    """

    def __init__(self, db_path: str = "jupyterpilot_state.db") -> None:
        self._db_path: str = db_path

    # ── Internal helpers ──────────────────────────────────────────────────────

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        """Yield a short-lived connection; always close after use."""
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ── Schema bootstrap ──────────────────────────────────────────────────────

    def init_db(self) -> None:
        """
        Create tables if they do not already exist.

        Call this once when the JupyterHub process starts (module-level in
        spawner.py) so subsequent reads/writes always find a valid schema.
        """
        with _write_lock, self._connect() as conn:
            conn.execute(_DDL_TEAM_MAPPINGS)
            conn.execute(_DDL_USER_SESSIONS)
            conn.commit()
            log.info("SessionStore: DB initialised at %s", self._db_path)

    # ── Health check ──────────────────────────────────────────────────────────

    def ping(self) -> bool:
        """
        Return True if the DB file is reachable and the schema is intact.

        Returns False (and logs a warning) on any error — so callers can
        fall back to user_mapping.json without crashing the hub process.
        """
        try:
            with self._connect() as conn:
                conn.execute("SELECT 1 FROM team_mappings LIMIT 1")
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "SessionStore: DB unreachable at %s — %s. "
                "Spawner will fall back to user_mapping.json.",
                self._db_path,
                exc,
            )
            return False

    # ── Team mapping (replaces user_mapping.json) ─────────────────────────────

    def get_mapping(self, team: str) -> Optional[Dict[str, Any]]:
        """
        Fetch the VM routing record for *team*.

        Returns a dict with keys ``team``, ``server_ip``, ``ssh_key``,
        ``ssh_user`` — or ``None`` if the team is not found.
        """
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT team, server_ip, ssh_key, ssh_user "
                    "FROM team_mappings WHERE team = ?",
                    (team,),
                ).fetchone()
            return dict(row) if row else None
        except Exception as exc:  # noqa: BLE001
            log.error("SessionStore.get_mapping(%s) failed: %s", team, exc)
            return None

    def set_mapping(
        self,
        team: str,
        server_ip: str,
        ssh_key: str,
        ssh_user: Optional[str] = None,
    ) -> None:
        """
        Insert or replace the VM routing record for *team*.

        Args:
            team:      Team / group name (primary key).
            server_ip: IP address of the remote execution VM.
            ssh_key:   Absolute path to the SSH private key file.
            ssh_user:  SSH login username. ``None`` means use the JupyterHub
                       username at connect time.
        """
        with _write_lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO team_mappings "
                "(team, server_ip, ssh_key, ssh_user) VALUES (?, ?, ?, ?)",
                (team, server_ip, ssh_key, ssh_user),
            )
            conn.commit()
        log.info("SessionStore: mapping set for team '%s' → %s", team, server_ip)

    # ── Per-user session state ────────────────────────────────────────────────

    def get_session(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Fetch the live session record for *username*.

        Returns a dict with keys ``username``, ``pid``, ``vm_ip``, ``port``,
        ``start_time``, ``role``, ``status``, ``group_name`` — or ``None``
        if no session row exists for the user.
        """
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT username, pid, vm_ip, port, start_time, "
                    "       role, status, group_name "
                    "FROM user_sessions WHERE username = ?",
                    (username,),
                ).fetchone()
            return dict(row) if row else None
        except Exception as exc:  # noqa: BLE001
            log.error("SessionStore.get_session(%s) failed: %s", username, exc)
            return None

    def set_session(self, username: str, **fields: Any) -> None:
        """
        Upsert the session record for *username*.

        Accepts any subset of the ``user_sessions`` columns as keyword
        arguments.  Fields not provided are left unchanged for existing rows.

        Example::

            store.set_session(
                "alice",
                pid="12345", vm_ip="10.0.1.15", port=8888,
                start_time="2026-07-26T10:00:00Z",
                role="user", status="running", group_name="team_alpha",
            )
        """
        if not fields:
            return

        # Build an UPSERT: INSERT OR IGNORE first, then UPDATE the fields.
        with _write_lock, self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO user_sessions (username) VALUES (?)",
                (username,),
            )
            set_clause = ", ".join(f"{col} = ?" for col in fields)
            conn.execute(
                f"UPDATE user_sessions SET {set_clause} WHERE username = ?",
                (*fields.values(), username),
            )
            conn.commit()
        log.debug("SessionStore: session updated for '%s': %s", username, fields)

    def clear_session(self, username: str) -> None:
        """
        Delete the session row for *username*.

        Called by ``CustomSpawner.clear_state()`` and after a successful
        ``stop()`` to remove stale state.
        """
        with _write_lock, self._connect() as conn:
            conn.execute(
                "DELETE FROM user_sessions WHERE username = ?", (username,)
            )
            conn.commit()
        log.info("SessionStore: session cleared for '%s'", username)
