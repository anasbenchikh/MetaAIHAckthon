"""Twilio WhatsApp provider (Messages resource)."""

import os
from typing import Any, List, Optional

import httpx

from .base import (
    NotificationError,
    NotificationProvider,
    NotificationResult,
    normalize_recipient,
)

TWILIO_API_BASE_URL = "https://api.twilio.com"


class TwilioWhatsAppProvider(NotificationProvider):
    name = "twilio"

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None,
        http_client: Any = None,
    ):
        self.account_sid = (
            account_sid
            if account_sid is not None
            else os.getenv("TWILIO_ACCOUNT_SID") or None
        )
        self.auth_token = (
            auth_token
            if auth_token is not None
            else os.getenv("TWILIO_AUTH_TOKEN") or None
        )
        self._from_raw = (
            from_number
            if from_number is not None
            else os.getenv("TWILIO_WHATSAPP_FROM") or None
        )
        self._http_client = http_client

    @staticmethod
    def _channel_address(value: str) -> str:
        text = value.strip()
        if text.startswith("whatsapp:"):
            return text
        return f"whatsapp:+{normalize_recipient(text)}"

    def send_text(self, to: str, body: str) -> NotificationResult:
        if not self.account_sid or not self.auth_token or not self._from_raw:
            raise NotificationError(
                "TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_WHATSAPP_FROM "
                "are not configured",
                status_code=500,
            )
        client = self._http_client or httpx
        try:
            response = client.post(
                f"{TWILIO_API_BASE_URL}/2010-04-01/Accounts/{self.account_sid}/Messages.json",
                data={
                    "From": self._channel_address(self._from_raw),
                    "To": f"whatsapp:+{normalize_recipient(to)}",
                    "Body": body,
                },
                auth=(self.account_sid, self.auth_token),
                timeout=15.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise NotificationError(
                f"Twilio API request failed: {exc}", status_code=502
            ) from exc
        try:
            data = response.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        message_id = data.get("sid")
        if not message_id:
            raise NotificationError(
                "Twilio API response did not include a message sid", status_code=502
            )
        return NotificationResult(
            provider=self.name, message_id=str(message_id), raw=data
        )

    def send_template(
        self, to: str, template: str, language: str, params: List[str]
    ) -> NotificationResult:
        raise NotificationError(
            "Template messages are not implemented for the Twilio provider; "
            "leave WHATSAPP_TEMPLATE_* empty to send text.",
            status_code=500,
        )

    def send_document(
        self,
        to: str,
        link: str,
        filename: str,
        caption: str,
        file_bytes: Optional[bytes] = None,
    ) -> NotificationResult:
        if not self.account_sid or not self.auth_token or not self._from_raw:
            raise NotificationError(
                "TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_WHATSAPP_FROM "
                "are not configured",
                status_code=500,
            )
        client = self._http_client or httpx
        try:
            response = client.post(
                f"{TWILIO_API_BASE_URL}/2010-04-01/Accounts/{self.account_sid}/Messages.json",
                data={
                    "From": self._channel_address(self._from_raw),
                    "To": f"whatsapp:+{normalize_recipient(to)}",
                    "Body": caption or filename,
                    "MediaUrl": link,
                },
                auth=(self.account_sid, self.auth_token),
                timeout=15.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise NotificationError(
                f"Twilio API request failed: {exc}", status_code=502
            ) from exc
        try:
            data = response.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        message_id = data.get("sid")
        if not message_id:
            raise NotificationError(
                "Twilio API response did not include a message sid", status_code=502
            )
        return NotificationResult(
            provider=self.name, message_id=str(message_id), raw=data
        )
