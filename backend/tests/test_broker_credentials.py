"""Encrypted Public API credential storage tests; no real brokerage account involved."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from cryptography.fernet import Fernet
from engine.broker_credentials import BrokerCredentialStore, CredentialError


class BrokerCredentialsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / 'test.db')
        self.key = Fernet.generate_key().decode()
        self.store = BrokerCredentialStore(self.db,
            key_provider=lambda: self.key,
            legacy_provider=lambda: '')
        self.store.setup()
        self.secret = 'Public-Secret-A-B-C-123456789abcdefghijklmn'

    def tearDown(self):
        self.temp.cleanup()

    def test_initial_state_and_status_never_leaks_secret(self):
        self.assertFalse(self.store.status()['configured'])
        self.assertTrue(self.store.status()['encryptionReady'])
        with self.assertRaises(CredentialError):
            self.store.secret_for_broker()
        self.store.save(self.secret)
        self.assertTrue(self.store.status()['configured'])
        self.assertNotIn(self.secret, str(self.store.status()))

    def test_encrypted_at_rest_and_round_trip(self):
        self.store.save(self.secret)
        with sqlite3.connect(self.db) as conn:
            value = conn.execute('SELECT ciphertext FROM broker_credentials WHERE provider=?', ('public',)).fetchone()[0]
        self.assertIsInstance(value, bytes)
        self.assertNotIn(self.secret.encode(), value)
        self.assertEqual(self.store.secret_for_broker(), self.secret)
        self.assertEqual(self.store.status()['source'], 'settings')

    def test_new_store_instance_preserves_encryption(self):
        self.store.save(self.secret)
        second = BrokerCredentialStore(self.db, key_provider=lambda:self.key, legacy_provider=lambda:'')
        second.setup()
        self.assertEqual(second.secret_for_broker(), self.secret)

    def test_replacing_secret_replaces_broker_credential(self):
        self.store.save(self.secret)
        newer = 'Public-Replacement-Key-1234567891234567'
        self.store.save(newer)
        self.assertEqual(self.store.secret_for_broker(), newer)
        with sqlite3.connect(self.db) as conn:
            content = b''.join(x[0] for x in conn.execute('SELECT ciphertext FROM broker_credentials') if x[0])
        self.assertNotIn(self.secret.encode(), content)
        self.assertNotIn(newer.encode(), content)

    def test_missing_encryption_key_fails_before_write(self):
        bad = BrokerCredentialStore(self.db,key_provider=lambda:'',legacy_provider=lambda:'')
        with self.assertRaisesRegex(CredentialError,'not configured'):
            bad.save(self.secret)
        self.assertFalse(bad.status()['configured'])
        self.assertFalse(bad.status()['encryptionReady'])

    def test_missing_or_wrong_key_never_decrypts_or_overwrites(self):
        self.store.save(self.secret)
        saved = BrokerCredentialStore(self.db,key_provider=lambda:Fernet.generate_key().decode(),legacy_provider=lambda:'')
        with self.assertRaisesRegex(CredentialError,'cannot be decrypted'):
            saved.secret_for_broker()
        missing = BrokerCredentialStore(self.db,key_provider=lambda:'',legacy_provider=lambda:'')
        self.assertFalse(missing.status()['usable'])
        with self.assertRaises(CredentialError):
            missing.save('Public-New-Secret-123456789012345')
        self.assertEqual(self.store.secret_for_broker(), self.secret)

    def test_disconnect_revokes_even_legacy_fallback(self):
        legacy = BrokerCredentialStore(self.db,key_provider=lambda:self.key,legacy_provider=lambda:self.secret)
        self.assertEqual(legacy.status()['source'],'environment')
        self.assertEqual(legacy.secret_for_broker(),self.secret)
        legacy.save('new-different-Public-Secret-123456789')
        self.assertEqual(legacy.status()['source'],'settings')
        legacy.clear()
        self.assertEqual(legacy.status()['source'],'none')
        self.assertFalse(legacy.status()['configured'])
        with self.assertRaises(CredentialError):legacy.secret_for_broker()

    def test_invalid_input_fails_closed(self):
        for value in ('', None, 234, '123', 'PLACE_PUBLIC_SECRET_HERE', 'abc\n1234567899999999999999', 'a'*2049):
            with self.subTest(value=str(value)[:12]):
                with self.assertRaises(CredentialError):self.store.save(value)
        self.assertFalse(self.store.status()['configured'])


if __name__=='__main__':
    unittest.main()
