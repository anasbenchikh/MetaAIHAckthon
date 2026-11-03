"""Telegram Bot API provider."""

import os
from typing import Any, Dict, List, Optional

import httpx

from .base import NotificationError, NotificationProvider, NotificationResult

TELEGRAM_API_BASE_URL = "https://api.telegram.org"


class TelegramProvider(NotificationProvider):
    name = "telegram"

    def __init__(self, token: Optional[str] = None, http_client: Any = None):
        self.token = (
            token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN") or None
        )
        self._http_client = http_client

    def send_text(self, to: str, body: str) -> NotificationResult:
        return self._call("sendMessage", {"chat_id": to, "text": body})

    def send_template(
        self, to: str, template: str, language: str, params: List[str]
    ) -> NotificationResult:
        return self.send_text(to, "\n".join(params))

    def send_document(
        self,
        to: str,
        link: str,
        filename: str,
        caption: str,
        file_bytes: Optional[bytes] = None,
    ) -> NotificationResult:
        if not self.token:
            raise NotificationError(
                "TELEGRAM_BOT_TOKEN is not configured", status_code=500
            )
        content = file_bytes if file_bytes else self._download(link)
        client = self._http_client or httpx
        try:
            if content is not None:
                response = client.post(
                    f"{TELEGRAM_API_BASE_URL}/bot{self.token}/sendDocument",
                    data={"chat_id": to, "caption": caption or filename},
                    files={"document": (filename, content, "application/pdf")},
                    timeout=30.0,
                )
            else:
                response = client.post(
                    f"{TELEGRAM_API_BASE_URL}/bot{self.token}/sendDocument",
                    json={"chat_id": to, "document": link,
                          "caption": caption or filename},
                    timeout=15.0,
                )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise NotificationError(
                f"Telegram API request failed: {exc}", status_code=502
            ) from exc
        return self._parse(response)

    def get_updates(self, offset: Optional[int] = None) -> List[Dict[str, Any]]:
        if not self.token:
            raise NotificationError(
                "TELEGRAM_BOT_TOKEN is not configured", status_code=500
            )
        params: Dict[str, Any] = {"timeout": 0}
        if offset is not None:
            params["offset"] = offset
        client = self._http_client or httpx
        try:
            response = client.get(
                f"{TELEGRAM_API_BASE_URL}/bot{self.token}/getUpdates",
                params=params,
                timeout=20.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise NotificationError(
                f"Telegram API request failed: {exc}", status_code=502
            ) from exc
        try:
            data = response.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict) or not data.get("ok"):
            detail = data.get("description") if isinstance(data, dict) else None
            raise NotificationError(
                f"Telegram API error: {detail or 'unknown'}", status_code=502
            )
        result = data.get("result")
        return result if isinstance(result, list) else []

    def _download(self, link: str) -> Optional[bytes]:
        client = self._http_client or httpx
        try:
            response = client.get(
                link, headers={"ngrok-skip-browser-warning": "true"}, timeout=15.0
            )
            response.raise_for_status()
            return response.content
        except httpx.HTTPError:
            return None

    def _call(self, method: str, payload: Dict[str, Any]) -> NotificationResult:
        if not self.token:
            raise NotificationError(
                "TELEGRAM_BOT_TOKEN is not configured", status_code=500
            )
        client = self._http_client or httpx
        try:
            response = client.post(
                f"{TELEGRAM_API_BASE_URL}/bot{self.token}/{method}",
                json=payload,
                timeout=15.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise NotificationError(
                f"Telegram API request failed: {exc}", status_code=502
            ) from exc
        return self._parse(response)

    def _parse(self, response: Any) -> NotificationResult:
        try:
            data = response.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict) or not data.get("ok"):
            detail = data.get("description") if isinstance(data, dict) else None
            raise NotificationError(
                f"Telegram API error: {detail or 'unknown'}", status_code=502
            )
        result = data.get("result") or {}
        message_id = result.get("message_id")
        return NotificationResult(
            provider=self.name, message_id=str(message_id), raw=data
        )
