"""Select the active notification provider."""

import os
from typing import List, Optional

from .base import NotificationError, NotificationProvider
from .fake import FakeNotifyProvider
from .meta import MetaWhatsAppProvider
from .telegram import TelegramProvider
from .twilio import TwilioWhatsAppProvider

_PROVIDERS = {
    MetaWhatsAppProvider.name: MetaWhatsAppProvider,
    TwilioWhatsAppProvider.name: TwilioWhatsAppProvider,
    TelegramProvider.name: TelegramProvider,
    FakeNotifyProvider.name: FakeNotifyProvider,
}


def available_providers() -> List[str]:
    return sorted(_PROVIDERS)


def get_notifier(name: Optional[str] = None) -> NotificationProvider:
    selected = (
        name or os.getenv("NOTIFY_PROVIDER") or FakeNotifyProvider.name
    ).strip().lower()
    try:
        return _PROVIDERS[selected]()
    except KeyError:
        raise NotificationError(
            f"Unknown NOTIFY_PROVIDER {selected!r} "
            f"(expected one of: {', '.join(available_providers())})",
            status_code=500,
        ) from None
