"""Focused tests for WhatsApp notification provider and flows.

Run inside the API container (no extra test framework, stdlib unittest)::

    docker cp backend/tests plumber-api:/tmp/rectests
    docker exec -w /tmp/rectests plumber-api env PYTHONPATH=/app \\
        python -m unittest test_notify -v
"""

import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import httpx

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/notify-test.db")

from app.notify import (  # noqa: E402
    FakeNotifyProvider,
    MetaWhatsAppProvider,
    NotificationError,
    TelegramProvider,
    TwilioWhatsAppProvider,
    get_notifier,
    normalize_recipient,
)
from app.notify.service import (  # noqa: E402
    accept_client_message,
    client_notifier,
    deliver_quote,
    due_for_reminder,
    notify_booking,
    notify_new_lead,
    quote_decision_plumber_message,
    refuse_client_message,
)


class StubResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class StubDownload:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


class StubHttpClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []
        self.get_calls = []
        self.download = b"%PDF-fake"
        self.fail_download = False
        self.get_payload = None

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return StubResponse(self.payload)

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        if self.fail_download:
            raise httpx.HTTPError("boom")
        if self.get_payload is not None:
            return StubResponse(self.get_payload)
        return StubDownload(self.download)


class NotifyTest(unittest.TestCase):
    def test_normalize_recipient(self):
        self.assertEqual(normalize_recipient("+33611223344"), "33611223344")
        self.assertEqual(normalize_recipient("06 11 22 33 44"), "33611223344")
        self.assertEqual(normalize_recipient("33611223344"), "33611223344")
        with self.assertRaises(NotificationError):
            normalize_recipient("abc")

    def test_meta_send_text_payload(self):
        stub = StubHttpClient({"messages": [{"id": "wamid-1"}]})
        provider = MetaWhatsAppProvider(
            token="tok", phone_id="PID123", api_version="v22.0", http_client=stub
        )
        result = provider.send_text("06 11 22 33 44", "hello")
        self.assertEqual(result.message_id, "wamid-1")
        url, kwargs = stub.calls[0]
        self.assertEqual(url, "https://graph.facebook.com/v22.0/PID123/messages")
        self.assertEqual(kwargs["headers"], {"Authorization": "Bearer tok"})
        self.assertEqual(
            kwargs["json"],
            {
                "messaging_product": "whatsapp",
                "to": "33611223344",
                "type": "text",
                "text": {"body": "hello"},
            },
        )

    def test_meta_send_template_payload(self):
        stub = StubHttpClient({"messages": [{"id": "wamid-2"}]})
        provider = MetaWhatsAppProvider(
            token="tok", phone_id="PID123", http_client=stub
        )
        provider.send_template("0600112233", "rappel_rdv", "fr", ["Marie", "10:00"])
        _, kwargs = stub.calls[0]
        template = kwargs["json"]["template"]
        self.assertEqual(template["name"], "rappel_rdv")
        self.assertEqual(template["language"], {"code": "fr"})
        params = template["components"][0]["parameters"]
        self.assertEqual([p["text"] for p in params], ["Marie", "10:00"])

    def test_meta_missing_credentials(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WHATSAPP_TOKEN", None)
            os.environ.pop("WHATSAPP_PHONE_ID", None)
            provider = MetaWhatsAppProvider(token=None, phone_id=None)
            with self.assertRaises(NotificationError) as ctx:
                provider.send_text("0600112233", "hi")
        self.assertEqual(ctx.exception.status_code, 500)

    def test_factory_selection(self):
        self.assertIsInstance(get_notifier("fake"), FakeNotifyProvider)
        self.assertIsInstance(get_notifier("meta"), MetaWhatsAppProvider)
        self.assertIsInstance(get_notifier("twilio"), TwilioWhatsAppProvider)
        self.assertIsInstance(get_notifier("telegram"), TelegramProvider)
        with self.assertRaises(NotificationError):
            get_notifier("nope")

    def test_twilio_send_text_payload(self):
        stub = StubHttpClient({"sid": "SM123"})
        provider = TwilioWhatsAppProvider(
            account_sid="AC1",
            auth_token="tok",
            from_number="whatsapp:+14155238886",
            http_client=stub,
        )
        result = provider.send_text("06 11 22 33 44", "hello")
        self.assertEqual(result.message_id, "SM123")
        url, kwargs = stub.calls[0]
        self.assertEqual(
            url, "https://api.twilio.com/2010-04-01/Accounts/AC1/Messages.json"
        )
        self.assertEqual(kwargs["auth"], ("AC1", "tok"))
        self.assertEqual(
            kwargs["data"],
            {
                "From": "whatsapp:+14155238886",
                "To": "whatsapp:+33611223344",
                "Body": "hello",
            },
        )

    def test_twilio_missing_credentials(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TWILIO_ACCOUNT_SID", None)
            os.environ.pop("TWILIO_AUTH_TOKEN", None)
            os.environ.pop("TWILIO_WHATSAPP_FROM", None)
            provider = TwilioWhatsAppProvider(
                account_sid=None, auth_token=None, from_number=None
            )
            with self.assertRaises(NotificationError) as ctx:
                provider.send_text("0600112233", "hi")
        self.assertEqual(ctx.exception.status_code, 500)

    def test_telegram_send_text_payload(self):
        stub = StubHttpClient({"ok": True, "result": {"message_id": 42}})
        provider = TelegramProvider(token="tok123", http_client=stub)
        result = provider.send_text("987654", "hello")
        self.assertEqual(result.message_id, "42")
        url, kwargs = stub.calls[0]
        self.assertEqual(url, "https://api.telegram.org/bottok123/sendMessage")
        self.assertEqual(kwargs["json"], {"chat_id": "987654", "text": "hello"})

    def test_telegram_send_document_uploads_bytes(self):
        stub = StubHttpClient({"ok": True, "result": {"message_id": 43}})
        stub.download = b"%PDF-bytes"
        provider = TelegramProvider(token="tok123", http_client=stub)
        provider.send_document("987654", "https://x.test/q.pdf", "q.pdf", "cap")
        self.assertEqual(stub.get_calls[0][0], "https://x.test/q.pdf")
        url, kwargs = stub.calls[0]
        self.assertEqual(url, "https://api.telegram.org/bottok123/sendDocument")
        self.assertEqual(
            kwargs["data"], {"chat_id": "987654", "caption": "cap"}
        )
        self.assertEqual(
            kwargs["files"]["document"], ("q.pdf", b"%PDF-bytes", "application/pdf")
        )

    def test_telegram_send_document_prefers_given_bytes(self):
        stub = StubHttpClient({"ok": True, "result": {"message_id": 45}})
        provider = TelegramProvider(token="tok123", http_client=stub)
        provider.send_document(
            "987654", "https://x.test/q.pdf", "q.pdf", "cap", b"%PDF-direct"
        )
        self.assertEqual(stub.get_calls, [])
        _, kwargs = stub.calls[0]
        self.assertEqual(
            kwargs["files"]["document"], ("q.pdf", b"%PDF-direct", "application/pdf")
        )

    def test_telegram_send_document_link_fallback(self):
        stub = StubHttpClient({"ok": True, "result": {"message_id": 44}})
        stub.fail_download = True
        provider = TelegramProvider(token="tok123", http_client=stub)
        provider.send_document("987654", "https://x.test/q.pdf", "q.pdf", "cap")
        _, kwargs = stub.calls[0]
        self.assertEqual(
            kwargs["json"],
            {"chat_id": "987654", "document": "https://x.test/q.pdf", "caption": "cap"},
        )

    def test_telegram_api_error(self):
        stub = StubHttpClient({"ok": False, "description": "chat not found"})
        provider = TelegramProvider(token="tok123", http_client=stub)
        with self.assertRaises(NotificationError) as ctx:
            provider.send_text("987654", "hi")
        self.assertIn("chat not found", str(ctx.exception))

    def test_telegram_missing_token(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)
            provider = TelegramProvider(token=None)
            with self.assertRaises(NotificationError) as ctx:
                provider.send_text("987654", "hi")
        self.assertEqual(ctx.exception.status_code, 500)

    def test_notify_booking_telegram_skips_customer_phone(self):
        fake = FakeNotifyProvider()
        appt = {
            "id": 3, "name": "Marie", "phone": "0600112233", "job_type": "fuite",
            "address": "Lyon", "appointment_time": "2026-11-02T10:00:00",
        }
        with (
            patch("app.notify.service.get_notifier", return_value=fake),
            patch.dict(
                os.environ,
                {"NOTIFY_PROVIDER": "telegram", "PLUMBER_TELEGRAM_CHAT_ID": "987654"},
            ),
        ):
            self.assertTrue(notify_booking(appt))
        self.assertEqual([m["to"] for m in fake.sent], ["987654"])

    def test_notify_new_lead_english_copy(self):
        fake = FakeNotifyProvider()
        lead = {
            "id": 9, "name": "Anas", "phone": "0600112233", "job_type": "leak",
            "urgency": "urgent", "address": "Lyon", "description": "tap",
        }
        with (
            patch("app.notify.service.get_notifier", return_value=fake),
            patch.dict(
                os.environ, {"NOTIFY_LANG": "en", "PLUMBER_WHATSAPP": "0600998877"}
            ),
        ):
            self.assertTrue(notify_new_lead(lead))
        self.assertIn("New lead #9", fake.sent[0]["body"])

    def test_notify_new_lead_french_default(self):
        fake = FakeNotifyProvider()
        lead = {"id": 9, "name": "Anas"}
        with (
            patch("app.notify.service.get_notifier", return_value=fake),
            patch.dict(os.environ, {"PLUMBER_WHATSAPP": "0600998877"}),
        ):
            os.environ.pop("NOTIFY_LANG", None)
            self.assertTrue(notify_new_lead(lead))
        self.assertIn("Nouveau lead #9", fake.sent[0]["body"])

    def test_deliver_quote_sends_client_and_plumber(self):
        fake = FakeNotifyProvider()
        quote = {
            "id": 1, "number": "DEV-2026-0001", "name": "Marie",
            "phone": "0600112233", "total": 180.0,
        }
        with (
            patch("app.notify.service.get_notifier", return_value=fake),
            patch.dict(
                os.environ,
                {
                    "NOTIFY_LANG": "en",
                    "NOTIFY_PROVIDER": "fake",
                    "PLUMBER_WHATSAPP": "0600998877",
                },
            ),
        ):
            result = deliver_quote(quote, "https://x.test/quotes/1/pdf")
        self.assertIsNotNone(result["client"])
        self.assertIsNotNone(result["plumber"])
        kinds = [(m["to"], m["kind"]) for m in fake.sent]
        self.assertEqual(
            kinds, [("0600112233", "document"), ("0600998877", "document")]
        )
        self.assertIn("DEV-2026-0001", fake.sent[0]["caption"])

    def test_deliver_quote_client_override(self):
        fake = FakeNotifyProvider()
        quote = {
            "id": 1, "number": "DEV-2026-0001", "name": "Marie",
            "phone": "0600112233", "total": 180.0,
        }
        with (
            patch("app.notify.service.client_notifier", return_value=fake),
            patch("app.notify.service.get_notifier", return_value=fake),
            patch.dict(
                os.environ,
                {
                    "NOTIFY_LANG": "en",
                    "NOTIFY_PROVIDER": "fake",
                    "PLUMBER_WHATSAPP": "0600998877",
                },
            ),
        ):
            result = deliver_quote(
                quote, "https://x.test/quotes/1/pdf", None, client_to="987654"
            )
        self.assertIsNotNone(result["client"])
        self.assertEqual(fake.sent[0]["to"], "987654")

    def test_client_notifier_uses_client_bot(self):
        with patch.dict(
            os.environ,
            {"NOTIFY_PROVIDER": "telegram", "TELEGRAM_CLIENT_BOT_TOKEN": "AAA"},
        ):
            notifier = client_notifier()
        self.assertIsInstance(notifier, TelegramProvider)
        self.assertEqual(notifier.token, "AAA")

    def test_client_notifier_falls_back_to_main(self):
        with patch.dict(os.environ, {"NOTIFY_PROVIDER": "fake"}, clear=False):
            os.environ.pop("TELEGRAM_CLIENT_BOT_TOKEN", None)
            self.assertIsInstance(client_notifier(), FakeNotifyProvider)

    def test_client_notifier_strict_raises(self):
        with patch.dict(os.environ, {"NOTIFY_PROVIDER": "telegram"}, clear=False):
            os.environ.pop("TELEGRAM_CLIENT_BOT_TOKEN", None)
            with self.assertRaises(NotificationError) as ctx:
                client_notifier(strict=True)
        self.assertEqual(ctx.exception.status_code, 500)

    def test_deliver_quote_uses_client_bot_for_client(self):
        client_fake, main_fake = FakeNotifyProvider(), FakeNotifyProvider()
        quote = {
            "id": 1, "number": "DEV-2026-0001", "name": "Marie",
            "phone": "0600112233", "total": 180.0,
        }
        with (
            patch("app.notify.service.client_notifier", return_value=client_fake),
            patch("app.notify.service.get_notifier", return_value=main_fake),
            patch.dict(
                os.environ,
                {
                    "NOTIFY_LANG": "en",
                    "NOTIFY_PROVIDER": "fake",
                    "PLUMBER_WHATSAPP": "0600998877",
                },
            ),
        ):
            result = deliver_quote(
                quote, "https://x.test/quotes/1/pdf", None, client_to="987654"
            )
        self.assertIsNotNone(result["client"])
        self.assertEqual(client_fake.sent[0]["to"], "987654")
        self.assertEqual(main_fake.sent[0]["to"], "0600998877")

    def test_telegram_get_updates(self):
        stub = StubHttpClient({"ok": True})
        stub.get_payload = {"ok": True, "result": [{"update_id": 7}]}
        provider = TelegramProvider(token="tok123", http_client=stub)
        updates = provider.get_updates(offset=5)
        self.assertEqual(updates, [{"update_id": 7}])
        url, kwargs = stub.get_calls[0]
        self.assertTrue(url.endswith("/bot tok123/getUpdates".replace(" ", "")))
        self.assertEqual(kwargs["params"], {"timeout": 0, "offset": 5})

    def test_quote_decision_messages(self):
        quote = {"number": "DEV-1", "name": "M", "phone": "P", "total": 100.0}
        self.assertIn("DEV-1", accept_client_message(quote, "en"))
        self.assertIn("DEV-1", refuse_client_message(quote, "fr"))
        plumber = quote_decision_plumber_message(quote, "accepted", "en")
        self.assertIn("ACCEPTED", plumber)
        self.assertIn("100.00", plumber)

    def test_twilio_send_template_not_implemented(self):
        provider = TwilioWhatsAppProvider(
            account_sid="AC1", auth_token="tok", from_number="whatsapp:+14155238886"
        )
        with self.assertRaises(NotificationError):
            provider.send_template("0600112233", "tpl", "fr", ["x"])

    def test_due_for_reminder_window(self):
        now = datetime(2026, 11, 1, 9, 0, 0)
        self.assertTrue(due_for_reminder(now, now + timedelta(minutes=60)))
        self.assertTrue(due_for_reminder(now, now + timedelta(minutes=5)))
        self.assertFalse(due_for_reminder(now, now + timedelta(minutes=66)))
        self.assertFalse(due_for_reminder(now, now - timedelta(minutes=1)))

    def test_notify_new_lead_sends_to_plumber(self):
        fake = FakeNotifyProvider()
        lead = {
            "id": 9, "name": "Anas", "phone": "0600112233", "job_type": "fuite",
            "urgency": "routine", "address": "Fès", "description": "tuyau",
        }
        with (
            patch("app.notify.service.get_notifier", return_value=fake),
            patch.dict(
                os.environ,
                {"NOTIFY_PROVIDER": "fake", "PLUMBER_WHATSAPP": "0600998877"},
            ),
        ):
            self.assertTrue(notify_new_lead(lead))
        self.assertEqual(len(fake.sent), 1)
        self.assertEqual(fake.sent[0]["to"], "0600998877")
        self.assertIn("Anas", fake.sent[0]["body"])

    def test_notify_booking_sends_to_plumber_and_customer(self):
        fake = FakeNotifyProvider()
        appt = {
            "id": 3, "name": "Marie", "phone": "0600112233", "job_type": "fuite",
            "address": "Lyon", "appointment_time": "2026-11-02T10:00:00",
        }
        with (
            patch("app.notify.service.get_notifier", return_value=fake),
            patch.dict(
                os.environ,
                {"NOTIFY_PROVIDER": "fake", "PLUMBER_WHATSAPP": "0600998877"},
            ),
        ):
            self.assertTrue(notify_booking(appt))
        recipients = [m["to"] for m in fake.sent]
        self.assertEqual(recipients, ["0600998877", "0600112233"])


if __name__ == "__main__":
    unittest.main()
