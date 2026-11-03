"""Business notification flows (best-effort, bilingual copy)."""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .base import NotificationError
from .factory import get_notifier
from .telegram import TelegramProvider

logger = logging.getLogger(__name__)


def _lang() -> str:
    lang = (os.getenv("NOTIFY_LANG") or "fr").strip().lower()
    return "en" if lang.startswith("en") else "fr"


def due_for_reminder(now: datetime, appointment_time: datetime, horizon_minutes: int = 65) -> bool:
    return now <= appointment_time <= now + timedelta(minutes=horizon_minutes)


def _fmt_dt(value: Any) -> str:
    if not value:
        return "?"
    text = value if isinstance(value, str) else str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return text


def _fmt_time(value: Any) -> str:
    if not value:
        return "?"
    text = value if isinstance(value, str) else str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%H:%M")
    except ValueError:
        return text


def _use_telegram() -> bool:
    return (os.getenv("NOTIFY_PROVIDER") or "fake").strip().lower() == "telegram"


def _plumber_contact() -> Optional[str]:
    if _use_telegram():
        return os.getenv("PLUMBER_TELEGRAM_CHAT_ID") or None
    return os.getenv("PLUMBER_WHATSAPP") or None


def client_notifier(strict: bool = False):
    token = os.getenv("TELEGRAM_CLIENT_BOT_TOKEN") or None
    if _use_telegram() and token:
        return TelegramProvider(token=token)
    if strict:
        raise NotificationError(
            "TELEGRAM_CLIENT_BOT_TOKEN is not configured", status_code=500
        )
    return get_notifier()


def lead_message(lead: Dict[str, Any], lang: Optional[str] = None) -> str:
    lang = lang or _lang()
    head = (
        f"New lead #{lead.get('id')}"
        if lang == "en"
        else f"Nouveau lead #{lead.get('id')}"
    )
    lines = [
        head,
        f"{lead.get('name') or '?'} ({lead.get('phone') or 'no number' if lang == 'en' else 'sans numéro'})",
        f"{lead.get('job_type') or '?'} [{lead.get('urgency') or '?'}]",
    ]
    if lead.get("address"):
        lines.append(str(lead["address"]))
    if lead.get("description"):
        lines.append(str(lead["description"]))
    return "\n".join(lines)


def booking_plumber_message(appt: Dict[str, Any], lang: Optional[str] = None) -> str:
    lang = lang or _lang()
    when = _fmt_dt(appt.get("appointment_time"))
    if lang == "en":
        return (
            f"Appointment booked #{appt.get('id')}\n"
            f"{appt.get('name') or '?'} — {when}\n"
            f"{appt.get('job_type') or '?'} "
            f"({appt.get('phone') or 'no number'}), {appt.get('address') or ''}".strip()
        )
    return (
        f"RDV #{appt.get('id')} réservé: {appt.get('name') or 'sans nom'} "
        f"le {when} — {appt.get('job_type') or '?'} "
        f"({appt.get('phone') or 'sans numéro'}), {appt.get('address') or ''}".strip()
    )


def booking_customer_message(appt: Dict[str, Any], lang: Optional[str] = None) -> str:
    lang = lang or _lang()
    when = _fmt_dt(appt.get("appointment_time"))
    if lang == "en":
        return (
            f"Hello {appt.get('name') or ''}, your appointment with "
            f"Plombier Express Lyon is confirmed for {when}. See you soon!".strip()
        )
    return (
        f"Bonjour {appt.get('name') or ''}, votre rendez-vous avec "
        f"Plombier Express Lyon est confirmé le {when}. À bientôt !".strip()
    )


def reminder_plumber_message(appt: Dict[str, Any], lang: Optional[str] = None) -> str:
    lang = lang or _lang()
    at = _fmt_time(appt.get("appointment_time"))
    if lang == "en":
        return (
            f"Reminder: appointment in ~1h\n"
            f"{appt.get('name') or '?'} ({appt.get('phone') or 'no number'}) "
            f"at {at} — {appt.get('address') or ''} "
            f"[{appt.get('job_type') or '?'}]".strip()
        )
    return (
        f"Rappel RDV dans ~1h: {appt.get('name') or 'sans nom'} "
        f"({appt.get('phone') or 'sans numéro'}) à {at} — "
        f"{appt.get('address') or ''} [{appt.get('job_type') or '?'}]".strip()
    )


def reminder_customer_message(appt: Dict[str, Any], lang: Optional[str] = None) -> str:
    lang = lang or _lang()
    at = _fmt_time(appt.get("appointment_time"))
    if lang == "en":
        return f"Reminder: your plumbing appointment is today at {at}. Plombier Express Lyon."
    return f"Rappel: votre RDV plombier est aujourd'hui à {at}. Plombier Express Lyon."


def quote_client_caption(quote: Dict[str, Any], lang: Optional[str] = None) -> str:
    lang = lang or _lang()
    total = quote.get("total")
    amount = f"{total:.2f}" if isinstance(total, (int, float)) else "?"
    if lang == "en":
        return (
            f"Hello {quote.get('name') or ''}, please find attached your "
            f"quote {quote.get('number')} ({amount} EUR incl. tax) — "
            "Plombier Express Lyon. Reply ACCEPT to approve."
        )
    return (
        f"Bonjour {quote.get('name') or ''}, voici votre devis {quote.get('number')} "
        f"({amount} EUR TTC) — Plombier Express Lyon. "
        "Répondez ACCEPTE pour valider."
    )


def quote_plumber_message(quote: Dict[str, Any], lang: Optional[str] = None) -> str:
    lang = lang or _lang()
    total = quote.get("total")
    amount = f"{total:.2f}" if isinstance(total, (int, float)) else "?"
    if lang == "en":
        return (
            f"Quote {quote.get('number')} sent to {quote.get('name') or '?'} "
            f"({quote.get('phone') or 'no number'}): {amount} EUR incl. tax. PDF attached."
        )
    return (
        f"Devis {quote.get('number')} envoyé à {quote.get('name') or '?'} "
        f"({quote.get('phone') or 'sans numéro'}) : {amount} EUR TTC. PDF joint."
    )


def _send_all(messages: List[Tuple[Optional[str], str, Optional[str]]]) -> bool:
    notifier = get_notifier()
    ok = True
    for to, body, template in messages:
        if not to:
            continue
        try:
            if template:
                notifier.send_template(to, template, "fr", [body])
            else:
                notifier.send_text(to, body)
        except NotificationError as exc:
            logger.warning("notification to %s failed: %s", to, exc)
            ok = False
    return ok


def accept_client_message(quote: Dict[str, Any], lang: Optional[str] = None) -> str:
    lang = lang or _lang()
    if lang == "en":
        return (
            f"Thank you! Your quote {quote.get('number')} is accepted. "
            "The plumber will contact you shortly."
        )
    return (
        f"Merci ! Votre devis {quote.get('number')} est accepté. "
        "Le plombier vous contactera."
    )


def refuse_client_message(quote: Dict[str, Any], lang: Optional[str] = None) -> str:
    lang = lang or _lang()
    if lang == "en":
        return (
            f"Your quote {quote.get('number')} has been cancelled. "
            "Reply if you change your mind."
        )
    return (
        f"Votre devis {quote.get('number')} est annulé. "
        "N'hésitez pas si vous changez d'avis."
    )


def no_pending_quote_message(lang: Optional[str] = None) -> str:
    lang = lang or _lang()
    if lang == "en":
        return "No pending quote found. Reply ACCEPT <quote number>."
    return "Aucun devis en attente. Répondez ACCEPTE <numéro de devis>."


def quote_decision_plumber_message(
    quote: Dict[str, Any], decision: str, lang: Optional[str] = None
) -> str:
    lang = lang or _lang()
    total = quote.get("total")
    amount = f"{total:.2f}" if isinstance(total, (int, float)) else "?"
    if lang == "en":
        verb = "ACCEPTED" if decision == "accepted" else "REFUSED"
        return (
            f"Quote {quote.get('number')} {verb} by {quote.get('name') or '?'} "
            f"({quote.get('phone') or 'no number'}): {amount} EUR."
        )
    verb = "ACCEPTÉ" if decision == "accepted" else "REFUSÉ"
    return (
        f"Devis {quote.get('number')} {verb} par {quote.get('name') or '?'} "
        f"({quote.get('phone') or 'sans numéro'}) : {amount} EUR."
    )


def notify_quote_decision(quote: Dict[str, Any], decision: str) -> bool:
    return _send_all(
        [(_plumber_contact(), quote_decision_plumber_message(quote, decision), None)]
    )


def notify_new_lead(lead: Dict[str, Any]) -> bool:
    template = os.getenv("WHATSAPP_TEMPLATE_NEW_LEAD") or None
    return _send_all([(_plumber_contact(), lead_message(lead), template)])


def notify_booking(appt: Dict[str, Any]) -> bool:
    template = os.getenv("WHATSAPP_TEMPLATE_BOOKING") or None
    messages = [(_plumber_contact(), booking_plumber_message(appt), template)]
    if not _use_telegram():
        messages.append((appt.get("phone"), booking_customer_message(appt), template))
    return _send_all(messages)


def notify_reminder(appt: Dict[str, Any]) -> bool:
    template = os.getenv("WHATSAPP_TEMPLATE_REMINDER") or None
    messages = [(_plumber_contact(), reminder_plumber_message(appt), template)]
    if not _use_telegram():
        messages.append((appt.get("phone"), reminder_customer_message(appt), template))
    return _send_all(messages)


def deliver_quote(
    quote: Dict[str, Any],
    pdf_url: str,
    custom_message: Optional[str] = None,
    client_to: Optional[str] = None,
    pdf_bytes: Optional[bytes] = None,
) -> Dict[str, Optional[str]]:
    """Send the quote PDF to the client, plus a copy to the plumber."""
    notifier = get_notifier()
    client_bot = client_notifier()
    filename = f"{quote.get('number')}.pdf"
    result: Dict[str, Optional[str]] = {"client": None, "plumber": None}
    dest = client_to or quote.get("phone")
    if dest:
        caption = custom_message or quote_client_caption(quote)
        try:
            sent = client_bot.send_document(dest, pdf_url, filename, caption, pdf_bytes)
            result["client"] = sent.message_id
        except NotificationError as exc:
            logger.warning("quote send to client failed: %s", exc)
    plumber = _plumber_contact()
    if plumber:
        try:
            sent = notifier.send_document(
                plumber, pdf_url, filename, quote_plumber_message(quote), pdf_bytes
            )
            result["plumber"] = sent.message_id
        except NotificationError as exc:
            logger.warning("quote send to plumber failed: %s", exc)
    return result
