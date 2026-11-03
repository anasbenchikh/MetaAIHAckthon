"""Select the active voice provider."""

import os
from typing import List, Optional

from .base import VoiceProvider, VoiceProviderError
from .fake import FakeProvider
from .retell import RetellProvider

_PROVIDERS = {
    RetellProvider.name: RetellProvider,
    FakeProvider.name: FakeProvider,
}


def available_providers() -> List[str]:
    return sorted(_PROVIDERS)


def get_provider(name: Optional[str] = None) -> VoiceProvider:
    selected = (name or os.getenv("VOICE_PROVIDER") or RetellProvider.name).strip().lower()
    try:
        return _PROVIDERS[selected]()
    except KeyError:
        raise VoiceProviderError(
            f"Unknown VOICE_PROVIDER {selected!r} (expected one of: {', '.join(available_providers())})",
            status_code=500,
        ) from None
