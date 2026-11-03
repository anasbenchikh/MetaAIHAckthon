"""Regression tests for voice-tool argument aliases.

Retell agents send varied field names (customer_name, problem_description,
split date/time...). These tests post representative payloads at the HTTP
level and assert the stored mapping.

Run inside the API container (no extra test framework, stdlib unittest)::

    docker cp backend/tests plumber-api:/tmp/rectests
    docker exec -w /tmp/rectests plumber-api env PYTHONPATH=/app \\
        python -m unittest test_tool_args -v
"""

import os
import tempfile
import unittest
from unittest.mock import patch

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

import app.main as main  # noqa: E402


class ToolAliasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._env = patch.dict(os.environ, {"NOTIFY_PROVIDER": "fake"})
        cls._env.start()
        cls.client = TestClient(main.app)
        cls.client.__enter__()
        test_engine = create_engine(
            f"sqlite:///{_tmp.name}", connect_args={"check_same_thread": False}
        )
        main.SessionLocal.configure(bind=test_engine)
        main.Base.metadata.create_all(bind=test_engine)

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls._env.stop()
        os.unlink(_tmp.name)

    def test_place_call_via_fake_provider(self):
        with patch.dict(os.environ, {"VOICE_PROVIDER": "fake"}):
            response = self.client.post("/tools/place-call", json={"to_number": "+1000"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["provider"], "fake")
        self.assertTrue(body["external_call_id"].startswith("fake-call-"))

    def test_place_call_requires_number(self):
        response = self.client.post("/tools/place-call", json={})
        self.assertEqual(response.status_code, 400)

    def test_create_lead_accepts_retell_field_names(self):
        payload = {
            "customer_name": "Anas Bencher",
            "phone": "0600819100",
            "address": "66 rue de Fès, Afir",
            "problem_description": "Tuyau fissuré qui fuit légèrement.",
            "urgency": "routine",
        }
        response = self.client.post("/tools/create-lead", json=payload)
        self.assertEqual(response.status_code, 200)
        lead = response.json()["lead"]
        self.assertEqual(lead["name"], "Anas Bencher")
        self.assertEqual(lead["phone"], "0600819100")
        self.assertEqual(lead["address"], "66 rue de Fès, Afir")
        self.assertEqual(lead["description"], "Tuyau fissuré qui fuit légèrement.")
        self.assertEqual(lead["urgency"], "routine")

    def test_create_lead_prefers_canonical_names(self):
        payload = {"name": "Canon", "customer_name": "Alias", "phone": "+1"}
        response = self.client.post("/tools/create-lead", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["lead"]["name"], "Canon")

    def test_book_accepts_split_date_and_time(self):
        payload = {"name": "RDV", "date": "2026-11-05", "time": "14:30"}
        response = self.client.post("/tools/book-appointment", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["appointment"]["appointment_time"], "2026-11-05T14:30:00"
        )


if __name__ == "__main__":
    unittest.main()
