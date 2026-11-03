"""Provider-agnostic notification contracts (WhatsApp first)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class NotificationResult:
    provider: str
    message_id: str
    raw: Dict[str, Any] = field(default_factory=dict)


class NotificationError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def normalize_recipient(raw: Any) -> str:
    text = str(raw or "").strip().replace(" ", "").replace("-", "").replace(".", "")
    if text.startswith("+"):
        text = text[1:]
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = "33" + digits[1:]
    if not 8 <= len(digits) <= 15:
        raise NotificationError(f"Invalid recipient number: {raw!r}", status_code=400)
    return digits


class NotificationProvider(ABC):
    name: str = "base"

    @abstractmethod
    def send_text(self, to: str, body: str) -> NotificationResult:
        """Send a free-form text message."""

    @abstractmethod
    def send_template(
        self, to: str, template: str, language: str, params: List[str]
    ) -> NotificationResult:
        """Send a template message with body parameters."""

    @abstractmethod
    def send_document(
        self,
        to: str,
        link: str,
        filename: str,
        caption: str,
        file_bytes: Optional[bytes] = None,
    ) -> NotificationResult:
        """Send a document with a caption message."""
