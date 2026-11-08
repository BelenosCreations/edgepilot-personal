"""Encrypted server-side Public credential vault.

The Public API secret is never returned to HTTP clients or stored in settings,
logs, source control, or Android/JavaScript storage. EDGE_CREDENTIAL_KEY must
be a stable Fernet key held only as a private Render environment variable.
"""
import os
import sqlite3
from cryptography.fernet import Fernet, InvalidToken


class CredentialError(RuntimeError):
    """Sanitized error; never include secret, ciphertext, or keys."""


class BrokerCredentialStore:
    def __init__(self, db_path, key_provider=None, legacy_provider=None):
        self.db_path = str(db_path)
        self.key_provider = key_provider or (lambda: os.getenv('EDGE_CREDENTIAL_KEY', ''))
        self.legacy_provider = legacy_provider or (lambda: os.getenv('PUBLIC_API_SECRET', ''))

    def _open(self):
        return sqlite3.connect(self.db_path, timeout=20)

    def setup(self):
        with self._open() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS broker_credentials (provider TEXT PRIMARY KEY, ciphertext BLOB, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")

    def _cipher(self):
        key = self.key_provider()
        if not key:
            raise CredentialError('Server encryption key is not configured')
        try:
            return Fernet(key.encode('ascii') if isinstance(key, str) else key)
        except (ValueError, TypeError, UnicodeError):
            raise CredentialError('Server encryption key is invalid') from None

    def encryption_ready(self):
        try:
            self._cipher()
            return True
        except CredentialError:
            return False

    def _row(self):
        with self._open() as conn:
            return conn.execute('SELECT ciphertext FROM broker_credentials WHERE provider=?', ('public',)).fetchone()

    def status(self):
        row = self._row()
        ready = self.encryption_ready()
        if row is not None:
            saved = row[0] is not None
            usable = False
            if saved and ready:
                try:
                    # Validate the vault key without exposing the decrypted data.
                    self._cipher().decrypt(row[0])
                    usable = True
                except (InvalidToken, CredentialError, ValueError, TypeError):
                    usable = False
            return {'configured':saved, 'source':'settings' if saved else 'none',
                    'encryptionReady':ready, 'usable':usable,
                    'message':('Configured in EdgePilot settings' if usable else
                               'Saved key cannot be accessed; check server encryption key' if saved else 'Not connected')}
        legacy = str(self.legacy_provider() or '').strip()
        legacy_ok = bool(legacy and legacy != 'PLACE_PUBLIC_SECRET_HERE')
        return {'configured':legacy_ok, 'source':'environment' if legacy_ok else 'none',
                'encryptionReady':ready, 'usable':legacy_ok,
                'message':'Configured in hosting environment' if legacy_ok else 'Not connected'}

    def save(self, secret):
        if not isinstance(secret, str):
            raise CredentialError('Enter a valid Public API secret')
        secret = secret.strip()
        if not 20 <= len(secret) <= 2048 or any(c in secret for c in '\r\n\0') or secret == 'PLACE_PUBLIC_SECRET_HERE':
            raise CredentialError('Public API secret format is invalid')
        cipher = self._cipher()  # Fail closed before changing existing credential.
        encrypted = cipher.encrypt(secret.encode('utf-8'))
        with self._open() as conn:
            conn.execute("INSERT INTO broker_credentials(provider,ciphertext,updated_at) VALUES('public', ?, CURRENT_TIMESTAMP) ON CONFLICT(provider) DO UPDATE SET ciphertext=excluded.ciphertext, updated_at=CURRENT_TIMESTAMP", (encrypted,))

    def clear(self):
        # Tombstone disables any legacy environment secret after user disconnects.
        with self._open() as conn:
            conn.execute("INSERT INTO broker_credentials(provider,ciphertext,updated_at) VALUES('public', NULL, CURRENT_TIMESTAMP) ON CONFLICT(provider) DO UPDATE SET ciphertext=NULL, updated_at=CURRENT_TIMESTAMP")

    def secret_for_broker(self):
        row = self._row()
        if row is None:
            legacy = str(self.legacy_provider() or '').strip()
            if legacy and legacy != 'PLACE_PUBLIC_SECRET_HERE':
                return legacy
            raise CredentialError('Public API connection is not configured')
        if row[0] is None:
            raise CredentialError('Public API connection is not configured')
        try:
            return self._cipher().decrypt(row[0]).decode('utf-8')
        except (InvalidToken, UnicodeError, ValueError, TypeError):
            raise CredentialError('Saved Public credential cannot be decrypted; restore the original encryption key') from None
