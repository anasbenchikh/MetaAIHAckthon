"""In-memory voice provider for tests and local development."""

from itertools import count
from typing import Any, Dict, List, Optional

from .base import (
    NormalizedCallEvent,
    OutboundCallRequest,
    OutboundCallResult,
    VoiceProvider,
    VoiceProviderError,
)

_EVENT_TYPES = {
    "call_started": "started",
    "call_ended": "ended",
    "call_analyzed": "analyzed",
}


class FakeProvider(VoiceProvider):
    name = "fake"

    def __init__(self):
        self.created_calls: List[OutboundCallRequest] = []
        self._ids = count(1)

    def parse_webhook(self, body: Any) -> Optional[NormalizedCallEvent]:
        if not isinstance(body, dict):
            raise VoiceProviderError("Invalid webhook body", status_code=400)
        event = body.get("event")
        event_type = _EVENT_TYPES.get(event) if isinstance(event, str) else None
        if event_type is None:
            return None
        call_data = body.get("call")
        if not isinstance(call_data, dict):
            call_data = {}
        external_call_id = (
            call_data.get("call_id") or body.get("call_id") or body.get("external_call_id")
        )
        if not external_call_id:
            raise VoiceProviderError("Missing call_id", status_code=400)
        raw: Dict[str, Any] = dict(body)
        return NormalizedCallEvent(
            provider=self.name,
            external_call_id=str(external_call_id),
            event_type=event_type,
            from_number=call_data.get("from_number") or body.get("from_number"),
            to_number=call_data.get("to_number") or body.get("to_number"),
            transcript=call_data.get("transcript") or body.get("transcript"),
            summary=call_data.get("summary") or body.get("summary"),
            status=call_data.get("status") or body.get("status") or event,
            raw=raw,
        )

    def create_call(self, request: OutboundCallRequest) -> OutboundCallResult:
        if not request.to_number:
            raise VoiceProviderError("to_number is required", status_code=400)
        self.created_calls.append(request)
        external_call_id = f"fake-call-{next(self._ids)}"
        return OutboundCallResult(
            provider=self.name,
            external_call_id=external_call_id,
            raw={"call_id": external_call_id, "to_number": request.to_number},
        )
