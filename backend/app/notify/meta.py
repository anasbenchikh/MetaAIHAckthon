"""Meta WhatsApp Cloud API provider."""

import os
from typing import Any, Dict, List, Optional

import httpx

from .base import (
    NotificationError,
    NotificationProvider,
    NotificationResult,
    normalize_recipient,
)

GRAPH_BASE_URL = "https://graph.facebook.com"


class MetaWhatsAppProvider(NotificationProvider):
    name = "meta"

    def __init__(
        self,
        token: Optional[str] = None,
        phone_id: Optional[str] = None,
        api_version: Optional[str] = None,
        http_client: Any = None,
    ):
        self.token = token if token is not None else os.getenv("WHATSAPP_TOKEN") or None
        self.phone_id = (
            phone_id if phone_id is not None else os.getenv("WHATSAPP_PHONE_ID") or None
        )
        self.api_version = (
            api_version
            if api_version is not None
            else os.getenv("WHATSAPP_API_VERSION") or "v22.0"
        )
        self._http_client = http_client

    def send_text(self, to: str, body: str) -> NotificationResult:
        return self._post(
            {"messaging_product": "whatsapp", "to": normalize_recipient(to),
             "type": "text", "text": {"body": body}}
        )

    def send_template(
        self, to: str, template: str, language: str, params: List[str]
    ) -> NotificationResult:
        return self._post(
            {
                "messaging_product": "whatsapp",
                "to": normalize_recipient(to),
                "type": "template",
                "template": {
                    "name": template,
                    "language": {"code": language},
                    "components": [
                        {
                            "type": "body",
                            "parameters": [{"type": "text", "text": p} for p in params],
                        }
                    ],
                },
            }
        )

    def send_document(
        self,
        to: str,
        link: str,
        filename: str,
        caption: str,
        file_bytes: Optional[bytes] = None,
    ) -> NotificationResult:
        return self._post(
            {
                "messaging_product": "whatsapp",
                "to": normalize_recipient(to),
                "type": "document",
                "document": {"link": link, "filename": filename, "caption": caption},
            }
        )

    def _post(self, payload: Dict[str, Any]) -> NotificationResult:
        if not self.token or not self.phone_id:
            raise NotificationError(
                "WHATSAPP_TOKEN / WHATSAPP_PHONE_ID are not configured", status_code=500
            )
        client = self._http_client or httpx
        try:
            response = client.post(
                f"{GRAPH_BASE_URL}/{self.api_version}/{self.phone_id}/messages",
                json=payload,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=15.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise NotificationError(
                f"Meta API request failed: {exc}", status_code=502
            ) from exc
        try:
            data = response.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        messages = data.get("messages")
        message_id = messages[0].get("id") if isinstance(messages, list) and messages else None
        if not message_id:
            raise NotificationError(
                "Meta API response did not include a message id", status_code=502
            )
        return NotificationResult(
            provider=self.name, message_id=str(message_id), raw=data
        )
