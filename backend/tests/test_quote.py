"""Focused tests for quote creation, PDF download and WhatsApp sending.

Run inside the API container (no extra test framework, stdlib unittest)::

    docker cp backend/tests plumber-api:/tmp/rectests
    docker exec -w /tmp/rectests plumber-api env PYTHONPATH=/app \\
        DISABLE_SCHEDULER=1 python -m unittest test_quote -v
"""

import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

import app.main as main  # noqa: E402

PAYLOAD = {
    "name": "Marie Dupont",
    "phone": "0600112233",
    "address": "Lyon",
    "job_type": "fuite",
    "items": [
        {"label": "Remplacement robinet", "qty": 1, "price": 120},
        {"label": "Deplacement", "qty": 1, "price": 30},
    ],
    "notes": "Garantie 1 an.",
}


class QuoteTest(unittest.TestCase):
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
        response = cls.client.post("/tools/create-quote", json=PAYLOAD)
        assert response.status_code == 200, response.text
        cls.quote = response.json()["quote"]

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls._env.stop()
        os.unlink(_tmp.name)

    def test_create_quote_totals_and_number(self):
        year = datetime.utcnow().year
        self.assertTrue(self.quote["number"].startswith(f"DEV-{year}-"))
        self.assertEqual(self.quote["subtotal"], 150.0)
        self.assertEqual(self.quote["tax_rate"], 0.20)
        self.assertEqual(self.quote["total"], 180.0)
        self.assertEqual(self.quote["status"], "draft")

    def test_download_pdf(self):
        response = self.client.get(f"/quotes/{self.quote['id']}/pdf")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/pdf", response.headers["content-type"])
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_send_quote_via_fake_provider(self):
        with (
            patch.dict(os.environ, {"NOTIFY_PROVIDER": "fake"}),
            patch.dict(os.environ, {"PUBLIC_BASE_URL": "https://example.test"}),
        ):
            response = self.client.post(
                "/tools/send-quote", json={"quote_id": self.quote["id"]}
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["provider"], "fake")
        self.assertTrue(body["message_id"].startswith("wamid-fake-"))
        self.assertEqual(body["quote"]["status"], "sent")

    def test_create_quote_prefills_from_lead(self):
        lead_response = self.client.post(
            "/tools/create-lead",
            json={"name": "Prefill", "phone": "0611223344", "job_type": "drain"},
        )
        self.assertEqual(lead_response.status_code, 200)
        lead_id = lead_response.json()["lead"]["id"]
        response = self.client.post(
            "/tools/create-quote",
            json={
                "lead_id": lead_id,
                "items": [{"label": "Work", "qty": 1, "price": 50}],
            },
        )
        self.assertEqual(response.status_code, 200)
        quote = response.json()["quote"]
        self.assertEqual(quote["lead_id"], lead_id)
        self.assertEqual(quote["name"], "Prefill")
        self.assertEqual(quote["phone"], "0611223344")
        self.assertEqual(quote["job_type"], "drain")

    def test_create_quote_requires_items(self):
        response = self.client.post("/tools/create-quote", json={"name": "X"})
        self.assertEqual(response.status_code, 400)

    def test_send_quote_unknown_id(self):
        response = self.client.post("/tools/send-quote", json={"quote_id": 99999})
        self.assertEqual(response.status_code, 404)

    def test_set_quote_status(self):
        response = self.client.patch(
            f"/quotes/{self.quote['id']}/status", json={"status": "accepted"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["quote"]["status"], "accepted")
        bad = self.client.patch(
            f"/quotes/{self.quote['id']}/status", json={"status": "nope"}
        )
        self.assertEqual(bad.status_code, 400)


if __name__ == "__main__":
    unittest.main()
