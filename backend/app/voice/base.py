"""Provider-agnostic voice-call contracts.

Retell is the first implementation; a future Pipecat provider implements the
same ``VoiceProvider`` interface and is selected via ``VOICE_PROVIDER``.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional


@dataclass
class NormalizedCallEvent:
    provider: str
    external_call_id: str
    event_type: str  # "started" | "ended" | "analyzed"
    from_number: Optional[str] = None
    to_number: Optional[str] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None
    status: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OutboundCallRequest:
    to_number: str
    from_number: Optional[str] = None
    agent_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    variables: Optional[Dict[str, Any]] = None


@dataclass
class OutboundCallResult:
    provider: str
    external_call_id: str
    raw: Dict[str, Any] = field(default_factory=dict)


class VoiceProviderError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class VoiceProvider(ABC):
    name: str = "base"

    @abstractmethod
    def parse_webhook(self, body: Any) -> Optional[NormalizedCallEvent]:
        """Normalize a provider webhook payload.

        Returns None when the event should be ignored. Raises
        VoiceProviderError on malformed payloads for handled events.
        """

    @abstractmethod
    def create_call(self, request: OutboundCallRequest) -> OutboundCallResult:
        """Place an outbound call through the provider."""

    def verify_signature(self, raw_body: bytes, headers: Mapping[str, str]) -> bool:
        """Verify a webhook signature. Providers without a scheme allow all."""
        return True
