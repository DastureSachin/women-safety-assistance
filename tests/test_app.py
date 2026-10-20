import os
import re
import sqlite3
import tempfile
import unittest
from contextlib import closing

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-not-for-deployment")

from app import create_app  # noqa: E402


class SafetyAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = os.path.join(self.temp_dir.name, "test.sqlite")
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "unit-test-secret",
                "WTF_CSRF_ENABLED": True,
                "DATABASE": self.database,
            }
        )
        self.client = self.app.test_client()
        self._register("alice@example.com", "Alice")
        self._register("bob@example.com", "Bob")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _token(self, page):
        response = self.client.get(page)
        self.assertEqual(response.status_code, 200)
        match = re.search(
            rb'<input[^>]*name="csrf_token"[^>]*value="([^"]+)"',
            response.data,
        )
        self.assertIsNotNone(match, "CSRF token should be present on forms")
        return match.group(1).decode()

    def _post(self, page, data, csrf_page=None):
        data = dict(data)
        data["csrf_token"] = self._token(csrf_page or page)
        return self.client.post(page, data=data, follow_redirects=True)

    def _register(self, email, name):
        return self._post(
            "/register",
            {"name": name, "email": email, "password": "safe-password-123"},
        )

    def _login(self, email, password="safe-password-123"):
        return self._post("/login", {"email": email, "password": password})

    def test_registration_hashes_password_and_rejects_duplicate_email(self):
        response = self._register("alice@example.com", "Alice Two")
        self.assertIn(b"already exists", response.data)
        with closing(sqlite3.connect(self.database)) as connection:
            password = connection.execute(
                "SELECT password FROM users WHERE email = ?",
                ("alice@example.com",),
            ).fetchone()[0]
        self.assertNotEqual(password, "safe-password-123")
        self.assertTrue(password.startswith(("scrypt:", "pbkdf2:")))

    def test_registration_validates_fields(self):
        response = self._post(
            "/register",
            {"name": "", "email": "not-an-email", "password": "short"},
        )
        self.assertIn(b"Enter a name", response.data)
        response = self._post(
            "/register",
            {"name": "Name", "email": "not-an-email", "password": "password-123"},
        )
        self.assertIn(b"Enter a valid email", response.data)
        self.assertEqual(
            self.client.post(
                "/register",
                data={"name": "No token", "email": "x@y.com", "password": "12345678"},
            ).status_code,
            400,
        )

    def test_login_invalid_credentials_protection_and_logout(self):
        self.assertEqual(self.client.get("/").status_code, 302)
        response = self._login("alice@example.com", "wrong-password")
        self.assertIn(b"Invalid email or password", response.data)

        response = self._login("alice@example.com")
        self.assertIn(b"Welcome, Alice", response.data)
        self.assertEqual(self.client.get("/").status_code, 200)

        response = self._post("/logout", {}, csrf_page="/")
        self.assertIn(b"You have been logged out", response.data)
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_legacy_plaintext_password_is_migrated(self):
        self.database = os.path.join(self.temp_dir.name, "legacy.sqlite")
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                ("Legacy", "legacy@example.com", "legacy-password"),
            )
            connection.commit()
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "unit-test-secret",
                "WTF_CSRF_ENABLED": True,
                "DATABASE": self.database,
            }
        )
        self.client = self.app.test_client()
        with closing(sqlite3.connect(self.database)) as connection:
            password = connection.execute(
                "SELECT password FROM users WHERE email = ?",
                ("legacy@example.com",),
            ).fetchone()[0]
        self.assertNotEqual(password, "legacy-password")
        self.assertTrue(password.startswith(("scrypt:", "pbkdf2:")))
        self.assertIn(
            b"Welcome, Legacy",
            self._login("legacy@example.com", "legacy-password").data,
        )

    def test_contact_crud_and_user_ownership(self):
        self._login("alice@example.com")
        response = self._post(
            "/contacts",
            {"name": "Trusted friend", "phone": "+1 555-555-5555", "relationship": "Friend"},
        )
        self.assertIn(b"Trusted friend", response.data)
        contact_id = self._contact_id()

        self._post("/logout", {}, csrf_page="/")
        self._login("bob@example.com")
        self.assertNotIn(b"Trusted friend", self.client.get("/contacts").data)
        response = self.client.post(
            f"/contacts/{contact_id}/delete",
            data={"csrf_token": self._token("/contacts")},
        )
        self.assertEqual(response.status_code, 404)

        self._post("/logout", {}, csrf_page="/")
        self._login("alice@example.com")
        response = self._post(
            f"/contacts/{contact_id}/delete", {}, csrf_page="/contacts"
        )
        self.assertNotIn(b"Trusted friend", response.data)

    def _contact_id(self):
        with closing(sqlite3.connect(self.database)) as connection:
            return connection.execute(
                "SELECT id FROM contacts WHERE name = ?", ("Trusted friend",)
            ).fetchone()[0]

    def test_contact_validation(self):
        self._login("alice@example.com")
        response = self._post(
            "/contacts", {"name": "Bad", "phone": "abc", "relationship": ""}
        )
        self.assertIn(b"valid phone number", response.data)
        with closing(sqlite3.connect(self.database)) as connection:
            count = connection.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        self.assertEqual(count, 0)

    def test_incident_creation_and_user_ownership(self):
        self._login("alice@example.com")
        response = self._post(
            "/reports",
            {
                "title": "Unsafe street",
                "description": "The street light was out.",
                "location": "19.0760, 72.8777",
            },
        )
        self.assertIn(b"Unsafe street", response.data)
        self.assertIn(b"19.0760, 72.8777", response.data)

        self._post("/logout", {}, csrf_page="/")
        self._login("bob@example.com")
        self.assertNotIn(b"Unsafe street", self.client.get("/reports").data)

    def test_incident_validation_and_csrf(self):
        self._login("alice@example.com")
        response = self._post(
            "/reports",
            {"title": "Test", "description": "Details", "location": "999,999"},
        )
        self.assertIn(b"valid latitude, longitude", response.data)
        with closing(sqlite3.connect(self.database)) as connection:
            count = connection.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
        self.assertEqual(count, 0)
        self.assertEqual(
            self.client.post(
                "/reports",
                data={"title": "No token", "description": "No token"},
            ).status_code,
            400,
        )

    def test_safety_tips_require_authentication(self):
        self.assertEqual(self.client.get("/safety-tips").status_code, 302)
        self._login("alice@example.com")
        self.assertEqual(self.client.get("/safety-tips").status_code, 200)


if __name__ == "__main__":
    unittest.main()
