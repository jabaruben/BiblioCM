"""Integridad y persistencia de la clave del servidor."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

from biblio.store import Store


class KeyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".biblio-test-", dir=Path(__file__).parents[1])
        self.path = Path(self.temp.name) / "biblio.sqlite3"
        self.environment = patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "BIBLIO_SECRET_KEY"}, clear=True)
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def create(self, key=None):
        store = Store(self.path, key=key)
        user = store.register("owner", "Nombre", "long-app-password")
        store.add_account(user["id"], "Carné", "123", "secret-portal-password")
        store.close()

    def test_missing_key_never_replaces_existing_database_key(self):
        self.create()
        key_path = self.path.parent / "secret.key"
        key_path.unlink()
        with self.assertRaisesRegex(RuntimeError, "Falta la clave"):
            Store(self.path)
        self.assertFalse(key_path.exists())

    def test_wrong_key_fails_at_startup(self):
        self.create()
        with self.assertRaisesRegex(RuntimeError, "no corresponde"):
            Store(self.path, key=Fernet.generate_key())

    def test_environment_key_is_supported_without_key_file(self):
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"BIBLIO_SECRET_KEY": key}):
            self.create()
            self.assertFalse((self.path.parent / "secret.key").exists())
            store = Store(self.path)
            try:
                self.assertEqual(store.login("owner", "long-app-password")["name"], "Nombre")
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
