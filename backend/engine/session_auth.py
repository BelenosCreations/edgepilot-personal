"""Host-only, server-side EdgePilot web sessions.

No Public credentials or original EdgePilot app token are persisted here.
SQLite is intentionally used because the single-user deployment already has a persistent
one-instance database. Do not use this implementation to scale horizontally.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time

COOKIE_NAME = '__Host-edgepilot_session'
SESSION_SECONDS = 8 * 3600
FAILURE_WINDOW_SECONDS = 10 * 60
MAX_FAILURES_PER_SOURCE = 16


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


class SessionStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _open(self):
        return sqlite3.connect(self.db_path, timeout=20)

    def setup(self) -> None:
        with self._open() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS edge_sessions (
                token_sha256 TEXT PRIMARY KEY,
                csrf_sha256 TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            )''')
            conn.execute('''CREATE INDEX IF NOT EXISTS edge_sessions_expiry
                ON edge_sessions(expires_at)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS edge_login_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_sha256 TEXT NOT NULL,
                attempted_at INTEGER NOT NULL
            )''')
            conn.execute('''CREATE INDEX IF NOT EXISTS edge_login_failures_source_time
                ON edge_login_failures(source_sha256, attempted_at)''')

    def blocked(self, source: str, now: int | None = None) -> bool:
        now = int(time.time() if now is None else now)
        with self._open() as conn:
            conn.execute('DELETE FROM edge_login_failures WHERE attempted_at < ?',
                         (now - FAILURE_WINDOW_SECONDS,))
            count = conn.execute(
                'SELECT COUNT(*) FROM edge_login_failures WHERE source_sha256=? AND attempted_at>=?',
                (_digest(source), now - FAILURE_WINDOW_SECONDS)
            ).fetchone()[0]
        return count >= MAX_FAILURES_PER_SOURCE

    def failed_login(self, source: str, now: int | None = None) -> None:
        now = int(time.time() if now is None else now)
        with self._open() as conn:
            conn.execute('INSERT INTO edge_login_failures(source_sha256,attempted_at) VALUES (?,?)',
                         (_digest(source), now))

    def successful_login(self, source: str) -> None:
        with self._open() as conn:
            conn.execute('DELETE FROM edge_login_failures WHERE source_sha256=?', (_digest(source),))

    def issue(self, now: int | None = None) -> tuple[str, str, int]:
        now = int(time.time() if now is None else now)
        session = secrets.token_urlsafe(48)
        csrf = secrets.token_urlsafe(32)
        expires = now + SESSION_SECONDS
        with self._open() as conn:
            conn.execute('DELETE FROM edge_sessions WHERE expires_at <= ?', (now,))
            conn.execute('INSERT INTO edge_sessions VALUES (?,?,?,?)',
                         (_digest(session), _digest(csrf), now, expires))
        return session, csrf, expires

    def validate(self, session: str, csrf: str | None = None, now: int | None = None) -> bool:
        if not isinstance(session, str) or not 25 < len(session) < 256:
            return False
        now = int(time.time() if now is None else now)
        with self._open() as conn:
            row = conn.execute('SELECT csrf_sha256, expires_at FROM edge_sessions WHERE token_sha256=?',
                               (_digest(session),)).fetchone()
        if not row or row[1] <= now:
            return False
        if csrf is None:
            return True
        if not isinstance(csrf, str) or not 20 < len(csrf) < 256:
            return False
        return hmac.compare_digest(row[0], _digest(csrf))

    def revoke(self, session: str) -> None:
        if isinstance(session, str) and session:
            with self._open() as conn:
                conn.execute('DELETE FROM edge_sessions WHERE token_sha256=?', (_digest(session),))

    def renew_csrf(self, session: str, now: int | None = None) -> str | None:
        """Issue a fresh CSRF secret on an authenticated same-origin session refresh."""
        now = int(time.time() if now is None else now)
        if not self.validate(session, now=now):
            return None
        csrf = secrets.token_urlsafe(32)
        with self._open() as conn:
            changed = conn.execute(
                'UPDATE edge_sessions SET csrf_sha256=? WHERE token_sha256=? AND expires_at>?',
                (_digest(csrf), _digest(session), now)).rowcount
        return csrf if changed == 1 else None
