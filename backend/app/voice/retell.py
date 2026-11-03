"""Retell AI voice provider."""

import os
from typing import Any, Dict, Optional

import httpx

from .base import (
    NormalizedCallEvent,
    OutboundCallRequest,
    OutboundCallResult,
    VoiceProvider,
    VoiceProviderError,
)

RETELL_API_BASE_URL = "https://api.retellai.com"
CREATE_CALL_PATH = "/v2/create-phone-call"

_EVENT_TYPES = {
    "call_started": "started",
    "call_ended": "ended",
    "call_analyzed": "analyzed",
}


class RetellProvider(VoiceProvider):
    name = "retell"

    def __init__(
        self,
        api_key: Optional[str] = None,
        agent_id: Optional[str] = None,
        from_number: Optional[str] = None,
        base_url: Optional[str] = None,
        http_client: Any = None,
    ):
        self.api_key = api_key if api_key is not None else os.getenv("RETELL_API_KEY") or None
        self.agent_id = agent_id if agent_id is not None else os.getenv("RETELL_AGENT_ID") or None
        self.from_number = (
            from_number if from_number is not None else os.getenv("RETELL_FROM_NUMBER") or None
        )
        self.base_url = (base_url or os.getenv("RETELL_BASE_URL") or RETELL_API_BASE_URL).rstrip("/")
        self._http_client = http_client

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
            call_data.get("call_id")
            or call_data.get("retell_call_id")
            or body.get("call_id")
            or body.get("retell_call_id")
        )
        if not external_call_id:
            raise VoiceProviderError("Missing call_id", status_code=400)

        summary = None
        call_analysis = call_data.get("call_analysis")
        if isinstance(call_analysis, dict):
            summary = call_analysis.get("call_summary")
        if not summary:
            summary = call_data.get("summary") or body.get("summary")

        return NormalizedCallEvent(
            provider=self.name,
            external_call_id=str(external_call_id),
            event_type=event_type,
            from_number=(
                call_data.get("from_number") or call_data.get("from") or body.get("from_number")
            ),
            to_number=call_data.get("to_number") or call_data.get("to") or body.get("to_number"),
            transcript=call_data.get("transcript") or body.get("transcript"),
            summary=summary,
            status=call_data.get("call_status") or call_data.get("status") or event,
            raw=body,
        )

    def create_call(self, request: OutboundCallRequest) -> OutboundCallResult:
        from_number = request.from_number or self.from_number
        agent_id = request.agent_id or self.agent_id
        if not self.api_key:
            raise VoiceProviderError("RETELL_API_KEY is not configured", status_code=500)
        if not from_number:
            raise VoiceProviderError(
                "from_number is required (provide it or set RETELL_FROM_NUMBER)",
                status_code=400,
            )
        if not agent_id:
            raise VoiceProviderError(
                "agent_id is required (provide it or set RETELL_AGENT_ID)",
                status_code=400,
            )

        payload: Dict[str, Any] = {
            "from_number": from_number,
            "to_number": request.to_number,
            "override_agent_id": agent_id,
        }
        if request.metadata:
            payload["metadata"] = request.metadata
        if request.variables:
            payload["retell_llm_dynamic_variables"] = request.variables

        client = self._http_client or httpx
        try:
            response = client.post(
                f"{self.base_url}{CREATE_CALL_PATH}",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=15.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise VoiceProviderError(f"Retell API request failed: {exc}", status_code=502) from exc

        try:
            data = response.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        external_call_id = data.get("call_id") or data.get("retell_call_id") or data.get("id")
        if not external_call_id:
            raise VoiceProviderError(
                "Retell API response did not include a call_id", status_code=502
            )
        return OutboundCallResult(
            provider=self.name, external_call_id=str(external_call_id), raw=data
        )
