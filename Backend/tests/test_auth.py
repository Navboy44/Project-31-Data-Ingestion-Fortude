import unittest
import tempfile
from pathlib import Path

from app import auth


class AuthTests(unittest.TestCase):
    def setUp(self):
        # Use a temporary DB path for isolation
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "users_test.db"
        auth.DB_PATH = self.db_path
        # initialize fresh DB
        auth.init_db()

    def tearDown(self):
        try:
            self.tmpdir.cleanup()
        except Exception:
            pass

    def test_register_and_verify_user(self):
        auth.register_user("alice", "s3cret")
        self.assertTrue(auth.verify_user("alice", "s3cret"))
        self.assertFalse(auth.verify_user("alice", "wrong"))

    def test_token_creation_and_verification(self):
        auth.register_user("bob", "pw")
        token = auth.create_token_with_type("bob", ttl=60, token_type="mfa")
        self.assertIsNotNone(token)
        self.assertEqual(auth.verify_token_with_type(token, "mfa"), "bob")

    def test_totp_generation_and_verification(self):
        secret = auth.generate_mfa_secret()
        code = auth.totp(secret)
        self.assertTrue(auth.verify_totp(secret, code))

    def test_mfa_secret_and_enable(self):
        auth.register_user("carol", "pw2")
        secret = auth.generate_mfa_secret()
        auth.set_mfa_secret("carol", secret)
        # after setting secret, mfa should still be disabled until verify
        self.assertFalse(auth.is_mfa_enabled("carol"))
        auth.enable_mfa("carol")
        self.assertTrue(auth.is_mfa_enabled("carol"))


if __name__ == "__main__":
    unittest.main()
