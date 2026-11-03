"""Focused tests for the monthly stats summary endpoint.

Run inside the API container (no extra test framework, stdlib unittest)::

    docker cp backend/tests plumber-api:/tmp/rectests
    docker exec -w /tmp/rectests plumber-api env PYTHONPATH=/app \\
        DISABLE_SCHEDULER=1 python -m unittest test_stats -v
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


class StatsTest(unittest.TestCase):
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

    def test_monthly_summary(self):
        client = self.client
        self.assertEqual(client.post("/tools/create-lead", json={"name": "S"}).status_code, 200)
        self.assertEqual(
            client.post(
                "/tools/book-appointment",
                json={"name": "S", "appointment_time": "2026-12-01T10:00:00Z"},
            ).status_code,
            200,
        )
        self.assertEqual(
            client.post(
                "/webhook/retell",
                json={"event": "call_ended", "call": {"call_id": "stats-1"}},
            ).status_code,
            200,
        )
        quote_id = (
            client.post(
                "/tools/create-quote",
                json={"name": "S", "items": [{"label": "Job", "qty": 1, "price": 200}]},
            )
            .json()["quote"]["id"]
        )
        self.assertEqual(
            client.patch(f"/quotes/{quote_id}/status", json={"status": "accepted"}).status_code,
            200,
        )
        response = client.get("/stats/summary")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["month"], datetime.utcnow().strftime("%Y-%m"))
        self.assertEqual(body["calls"], 1)
        self.assertEqual(body["leads"], 1)
        self.assertEqual(body["appointments"], 1)
        self.assertEqual(body["accepted_quotes"], 1)
        self.assertEqual(body["accepted_revenue"], 240.0)


if __name__ == "__main__":
    unittest.main()
