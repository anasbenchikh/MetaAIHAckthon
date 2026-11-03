"""In-memory notification provider for tests and development."""

from itertools import count
from typing import Any, Dict, List, Optional

from .base import NotificationProvider, NotificationResult


class FakeNotifyProvider(NotificationProvider):
    name = "fake"

    def __init__(self):
        self.sent: List[Dict[str, Any]] = []
        self._ids = count(1)

    def send_text(self, to: str, body: str) -> NotificationResult:
        return self._record({"kind": "text", "to": to, "body": body})

    def send_template(
        self, to: str, template: str, language: str, params: List[str]
    ) -> NotificationResult:
        return self._record(
            {"kind": "template", "to": to, "template": template,
             "language": language, "params": params}
        )

    def send_document(
        self,
        to: str,
        link: str,
        filename: str,
        caption: str,
        file_bytes: Optional[bytes] = None,
    ) -> NotificationResult:
        return self._record(
            {"kind": "document", "to": to, "link": link,
             "filename": filename, "caption": caption,
             "has_bytes": file_bytes is not None}
        )

    def _record(self, entry: Dict[str, Any]) -> NotificationResult:
        self.sent.append(entry)
        message_id = f"wamid-fake-{next(self._ids)}"
        return NotificationResult(provider=self.name, message_id=message_id, raw=entry)
