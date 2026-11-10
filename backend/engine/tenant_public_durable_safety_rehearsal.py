"""DISCONNECTED disk-backed safety rehearsal with SYNTHETIC UUIDs only.

This module is NEVER imported by the production Flask API, Observe worker,
Public adapter, or Android. It stores no tokens, provider accounts, secrets or
trading data. A private disposable temp directory demonstrates persistence
across independent Python processes and SQLite writer serialization. It is NOT
a production stop service, HA store, or authorization to issue network calls.
"""
from __future__ import annotations

from contextlib import contextmanager
import math
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import time
import uuid

FIXTURE_PHRASE = "CREATE A NEW OFFLINE SYNTHETIC SAFETY FIXTURE"
MARKER = "EDGEPILOT-DISCONNECTED-SYNTHETIC-SAFETY-v1\n"
ACCOUNT_LIMIT = 2
GLOBAL_LIMIT = 10
WINDOW_SECONDS = 60
LEASE_SECONDS = 10
PAUSE_CLEAR_PHRASE = "CLEAR THIS SYNTHETIC PAUSE ONLY"


class OfflineSafetyDenied(RuntimeError):
    CODES = frozenset(("STATE_UNAVAILABLE", "EMERGENCY_STOP", "ACCOUNT_UNAVAILABLE",
                       "ACCOUNT_PAUSED", "BUDGET_EXHAUSTED", "CLOCK_INVALID",
                       "STALE_LEASE", "OFFLINE_REVIEW_REQUIRED"))
    def __init__(self, code):
        self.code = code if code in self.CODES else "STATE_UNAVAILABLE"
        super().__init__(self.code)


def _synthetic_uuid(value):
    """Never accept Public's provider IDs, free text, or identity tokens."""
    if not isinstance(value, str) or len(value) != 36:
        raise OfflineSafetyDenied("ACCOUNT_UNAVAILABLE")
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        raise OfflineSafetyDenied("ACCOUNT_UNAVAILABLE") from None
    if str(parsed) != value:
        raise OfflineSafetyDenied("ACCOUNT_UNAVAILABLE")
    return value


class OfflineDurableSafetyRehearsal:
    """Fail-closed SQLite rehearsal; only disposable private /tmp fixtures.

    A new instance or process can reopen the SAME fixture after exit. A
    deleted fixture is unavailable, never automatically recreated. A newly
    bootstrapped fixture has no knowledge of prior stops: this class MUST
    NOT be used as a production emergency mechanism.
    """
    def __init__(self, directory, *, clock=None):
        self.directory = Path(directory)
        self.db_path = self.directory / "offline-synthetic-safety.sqlite"
        self.marker_path = self.directory / "SYNTHETIC-ONLY.marker"
        self.clock = clock if clock is not None else time.time
        self._validate_directory()

    def _validate_directory(self):
        try:
            root = self.directory
            tmp = Path(tempfile.gettempdir()).resolve(strict=True)
            real = root.resolve(strict=True)
            info = root.lstat()
            # The temporary directory can be redirected with TMPDIR. Never
            # accept /data (Render persistent volume) or a custom disk root.
            # The rehearsal runs on Linux and is intentionally limited to
            # the standard scratch roots, independently of TMPDIR.
            scratch_roots = (Path("/tmp").resolve(strict=True),
                             Path("/var/tmp").resolve(strict=True))
            approved_scratch = any(
                real != base and real.is_relative_to(base)
                for base in scratch_roots
            )
            if (root.is_symlink() or not stat.S_ISDIR(info.st_mode) or
                not approved_scratch or
                not real.is_relative_to(tmp) or real == tmp or
                real == Path("/data") or real.is_relative_to(Path("/data")) or
                info.st_uid != os.geteuid() or
                stat.S_IMODE(info.st_mode) != 0o700):
                raise OfflineSafetyDenied("STATE_UNAVAILABLE")
        except (OSError, RuntimeError, ValueError):
            raise OfflineSafetyDenied("STATE_UNAVAILABLE") from None

    def _private_file(self, path):
        try:
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or
                info.st_uid != os.geteuid() or
                stat.S_IMODE(info.st_mode) != 0o600):
                raise OfflineSafetyDenied("STATE_UNAVAILABLE")
            return (info.st_dev, info.st_ino)
        except OSError:
            raise OfflineSafetyDenied("STATE_UNAVAILABLE") from None

    def _check_fixture(self):
        self._validate_directory()
        self._private_file(self.marker_path)
        db_identity = self._private_file(self.db_path)
        try:
            if self.marker_path.read_bytes() != MARKER.encode("ascii"):
                raise OfflineSafetyDenied("STATE_UNAVAILABLE")
        except OSError:
            raise OfflineSafetyDenied("STATE_UNAVAILABLE") from None
        return db_identity

    @classmethod
    def create_fixture(cls, directory, *, phrase, clock=None):
        """An EXPLICIT new test fixture, never an automatic recovery path."""
        if phrase != FIXTURE_PHRASE:
            raise OfflineSafetyDenied("OFFLINE_REVIEW_REQUIRED")
        obj = cls(directory, clock=clock)
        try:
            if any(obj.directory.iterdir()):
                raise OfflineSafetyDenied("STATE_UNAVAILABLE")
            for path, data in ((obj.marker_path, MARKER.encode("ascii")),
                               (obj.db_path, b"")):
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                             getattr(os, "O_NOFOLLOW", 0), 0o600)
                with os.fdopen(fd, "wb") as out:
                    out.write(data)
            with obj._connection() as con:
                con.executescript("""
                CREATE TABLE offline_guard(
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    stopped INTEGER NOT NULL CHECK(stopped IN (0,1)),
                    revision INTEGER NOT NULL CHECK(revision>=1),
                    last_at INTEGER NOT NULL DEFAULT 0
                );
                INSERT INTO offline_guard(id,stopped,revision,last_at)
                  VALUES(1,0,1,0);
                CREATE TRIGGER no_synthetic_unstop
                  BEFORE UPDATE OF stopped ON offline_guard
                  WHEN OLD.stopped=1 AND NEW.stopped<>1
                  BEGIN SELECT RAISE(ABORT,'irreversible synthetic stop'); END;
                CREATE TRIGGER no_synthetic_guard_delete
                  BEFORE DELETE ON offline_guard
                  BEGIN SELECT RAISE(ABORT,'guard cannot be deleted'); END;
                CREATE TABLE offline_accounts(
                    owner_id TEXT NOT NULL,
                    account_id TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL CHECK(state IN ('ACTIVE','PAUSED','REVOKED')),
                    revision INTEGER NOT NULL CHECK(revision>=1),
                    PRIMARY KEY(owner_id, account_id)
                );
                CREATE TABLE offline_usage(
                    id INTEGER PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    admitted_at INTEGER NOT NULL,
                    FOREIGN KEY(owner_id,account_id)
                      REFERENCES offline_accounts(owner_id,account_id)
                );
                CREATE INDEX idx_offline_usage_time ON offline_usage(admitted_at);
                CREATE INDEX idx_offline_usage_account
                  ON offline_usage(owner_id,account_id,admitted_at);
                CREATE TABLE offline_leases(
                    lease_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    guard_revision INTEGER NOT NULL,
                    account_revision INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    FOREIGN KEY(owner_id,account_id)
                      REFERENCES offline_accounts(owner_id,account_id)
                );
                CREATE TABLE offline_audit(
                    id INTEGER PRIMARY KEY,
                    event TEXT NOT NULL CHECK(event IN
                        ('ENROLL','ADMIT','PAUSE','RESUME','REVOKE','STOP')),
                    at_seconds INTEGER NOT NULL
                );
                CREATE TRIGGER no_synthetic_audit_delete
                  BEFORE DELETE ON offline_audit
                  BEGIN SELECT RAISE(ABORT,'audit cannot be deleted'); END;
                CREATE TRIGGER no_synthetic_audit_update
                  BEFORE UPDATE ON offline_audit
                  BEGIN SELECT RAISE(ABORT,'audit cannot be rewritten'); END;
                """)
        except (OSError, sqlite3.Error):
            raise OfflineSafetyDenied("STATE_UNAVAILABLE") from None
        return obj

    @contextmanager
    def _connection(self):
        identity = self._check_fixture()
        try:
            # mode=rw prohibits silently creating a missing replacement database.
            con = sqlite3.connect(self.db_path.as_uri() + "?mode=rw",
                                  uri=True, timeout=5, isolation_level=None)
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA busy_timeout=5000")
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("PRAGMA synchronous=FULL")
            if self._private_file(self.db_path) != identity:
                raise OfflineSafetyDenied("STATE_UNAVAILABLE")
            try:
                yield con
            finally:
                con.close()
        except sqlite3.Error:
            raise OfflineSafetyDenied("STATE_UNAVAILABLE") from None

    @contextmanager
    def _transaction(self):
        with self._connection() as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                yield con
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise

    def _now(self):
        try:
            value = self.clock()
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or value < 0 or value > 253402300799):
                raise OfflineSafetyDenied("CLOCK_INVALID")
            return int(value)
        except (TypeError, ValueError, OverflowError):
            raise OfflineSafetyDenied("CLOCK_INVALID") from None

    @staticmethod
    def _guard(con):
        row = con.execute("SELECT stopped,revision,last_at FROM offline_guard WHERE id=1").fetchone()
        if row is None:
            raise OfflineSafetyDenied("STATE_UNAVAILABLE")
        if row["stopped"]:
            raise OfflineSafetyDenied("EMERGENCY_STOP")
        return row

    @staticmethod
    def _account(con, owner, account):
        row = con.execute("""SELECT state,revision FROM offline_accounts
            WHERE owner_id=? AND account_id=?""", (owner,account)).fetchone()
        if row is None or row["state"] == "REVOKED":
            raise OfflineSafetyDenied("ACCOUNT_UNAVAILABLE")
        if row["state"] == "PAUSED":
            raise OfflineSafetyDenied("ACCOUNT_PAUSED")
        return row

    @staticmethod
    def _audit(con, event, now):
        con.execute("INSERT INTO offline_audit(event,at_seconds) VALUES(?,?)",(event,now))

    def enroll_synthetic(self, owner_id, account_id):
        owner, account = _synthetic_uuid(owner_id), _synthetic_uuid(account_id)
        now = self._now()
        with self._transaction() as con:
            self._guard(con)
            try:
                con.execute("""INSERT INTO offline_accounts
                    (owner_id,account_id,state,revision) VALUES(?,?,'ACTIVE',1)""",
                    (owner,account))
            except sqlite3.IntegrityError:
                raise OfflineSafetyDenied("ACCOUNT_UNAVAILABLE") from None
            self._audit(con, "ENROLL", now)
        return {"syntheticAccountRegistered":True,"liveConnectionEnabled":False}

    def admit_synthetic(self, owner_id, account_id):
        owner, account = _synthetic_uuid(owner_id), _synthetic_uuid(account_id)
        now = self._now()
        with self._transaction() as con:
            guard = self._guard(con)
            row = self._account(con,owner,account)
            if now < guard["last_at"]:
                raise OfflineSafetyDenied("CLOCK_INVALID")
            con.execute("DELETE FROM offline_usage WHERE admitted_at<=?",
                        (now - WINDOW_SECONDS,))
            total = con.execute("SELECT COUNT(*) FROM offline_usage").fetchone()[0]
            scoped = con.execute("""SELECT COUNT(*) FROM offline_usage
                    WHERE owner_id=? AND account_id=?""",(owner,account)).fetchone()[0]
            if total >= GLOBAL_LIMIT or scoped >= ACCOUNT_LIMIT:
                raise OfflineSafetyDenied("BUDGET_EXHAUSTED")
            lease_id = str(uuid.uuid4())
            con.execute("""INSERT INTO offline_usage(owner_id,account_id,admitted_at)
                           VALUES(?,?,?)""",(owner,account,now))
            con.execute("""INSERT INTO offline_leases
                    (lease_id,owner_id,account_id,guard_revision,account_revision,expires_at)
                    VALUES(?,?,?,?,?,?)""",
                    (lease_id,owner,account,guard["revision"],row["revision"],
                     now + LEASE_SECONDS))
            con.execute("UPDATE offline_guard SET last_at=? WHERE id=1",(now,))
            self._audit(con,"ADMIT",now)
        return {"leaseId":lease_id, "offlineOnly":True,
                "networkAuthorized":False,"tradingAuthorized":False}

    def revalidate_synthetic(self, owner_id, account_id, lease_id):
        owner, account = _synthetic_uuid(owner_id), _synthetic_uuid(account_id)
        _synthetic_uuid(lease_id)
        now = self._now()
        with self._transaction() as con:
            guard = self._guard(con)
            current = self._account(con,owner,account)
            row = con.execute("""SELECT guard_revision,account_revision,expires_at
                FROM offline_leases WHERE lease_id=? AND owner_id=? AND account_id=?""",
                (lease_id,owner,account)).fetchone()
            if (row is None or row["expires_at"] <= now or
                row["guard_revision"] != guard["revision"] or
                row["account_revision"] != current["revision"]):
                raise OfflineSafetyDenied("STALE_LEASE")
        # A successful check is NOT permission to send a request; a stop may
        # occur immediately after this check. Production would need a
        # downstream atomic execution gate/cancellation protocol.
        return {"offlineLeaseValidAtCheck":True,"networkAuthorized":False,
                "tradingAuthorized":False}

    def pause_synthetic(self, owner_id, account_id):
        owner,account = _synthetic_uuid(owner_id),_synthetic_uuid(account_id)
        now = self._now()
        with self._transaction() as con:
            self._guard(con)
            self._account(con,owner,account)
            con.execute("""UPDATE offline_accounts SET state='PAUSED',revision=revision+1
                WHERE owner_id=? AND account_id=?""",(owner,account))
            self._audit(con,"PAUSE",now)
        return {"offlinePaused":True}

    def resume_paused_synthetic(self, owner_id, account_id, *,
                                expected_revision, phrase):
        owner,account = _synthetic_uuid(owner_id),_synthetic_uuid(account_id)
        if (phrase != PAUSE_CLEAR_PHRASE or type(expected_revision) is not int
            or expected_revision < 1):
            raise OfflineSafetyDenied("OFFLINE_REVIEW_REQUIRED")
        now = self._now()
        with self._transaction() as con:
            self._guard(con)
            changed = con.execute("""UPDATE offline_accounts
                SET state='ACTIVE',revision=revision+1
                WHERE owner_id=? AND account_id=? AND state='PAUSED'
                  AND revision=?""",
                (owner,account,expected_revision)).rowcount
            if changed != 1:
                raise OfflineSafetyDenied("OFFLINE_REVIEW_REQUIRED")
            self._audit(con,"RESUME",now)
        return {"syntheticPauseCleared":True,"liveNetworkEnabled":False}

    def revoke_synthetic(self, owner_id, account_id):
        owner,account = _synthetic_uuid(owner_id),_synthetic_uuid(account_id)
        now = self._now()
        with self._transaction() as con:
            changed = con.execute("""UPDATE offline_accounts
                SET state='REVOKED',revision=revision+1
                WHERE owner_id=? AND account_id=? AND state<>'REVOKED'""",
                (owner,account)).rowcount
            if changed != 1:
                raise OfflineSafetyDenied("ACCOUNT_UNAVAILABLE")
            self._audit(con,"REVOKE",now)
        return {"syntheticRevoked":True,"liveNetworkEnabled":False}

    def emergency_stop(self):
        now = self._now()
        with self._transaction() as con:
            row = con.execute("SELECT stopped FROM offline_guard WHERE id=1").fetchone()
            if row is None:
                raise OfflineSafetyDenied("STATE_UNAVAILABLE")
            if not row["stopped"]:
                con.execute("""UPDATE offline_guard SET stopped=1,revision=revision+1
                    WHERE id=1""")
                self._audit(con,"STOP",now)
        return {"syntheticEmergencyStopped":True,"productionStopDeployed":False}

    def is_stopped(self):
        with self._connection() as con:
            row = con.execute("SELECT stopped FROM offline_guard WHERE id=1").fetchone()
            if row is None:
                raise OfflineSafetyDenied("STATE_UNAVAILABLE")
            return bool(row["stopped"])

    def account_revision(self, owner_id, account_id):
        owner,account = _synthetic_uuid(owner_id),_synthetic_uuid(account_id)
        with self._connection() as con:
            row = con.execute("""SELECT revision FROM offline_accounts
                WHERE owner_id=? AND account_id=?""",(owner,account)).fetchone()
            if row is None:
                raise OfflineSafetyDenied("ACCOUNT_UNAVAILABLE")
            return row["revision"]

    def audit_summary(self):
        """Redacted diagnostic even after STOP; never authorizes unstop.

        Incident analysis must remain possible while the guard is stopped.
        All accounts and identifiers are deliberately excluded from output.
        SQLite errors and missing guard/audit state still fail closed.
        """
        with self._connection() as con:
            row = con.execute("""SELECT stopped,revision
                FROM offline_guard WHERE id=1""").fetchone()
            if row is None:
                raise OfflineSafetyDenied("STATE_UNAVAILABLE")
            counts = con.execute("""SELECT event,COUNT(*) AS n
                FROM offline_audit GROUP BY event""").fetchall()
            return {"offlineOnly":True,"productionIntegrated":False,
                    "emergencyStopped":bool(row["stopped"]),
                    "safetyRevision":row["revision"],
                    "eventCounts":{r["event"]:r["n"] for r in counts}}
