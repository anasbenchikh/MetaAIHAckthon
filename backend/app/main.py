import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.voice import (
    NormalizedCallEvent,
    OutboundCallRequest,
    RetellProvider,
    VoiceProvider,
    VoiceProviderError,
    get_provider,
)
from app.notify import NotificationError, get_notifier
from app.notify.service import (
    accept_client_message,
    client_notifier,
    deliver_quote,
    due_for_reminder,
    no_pending_quote_message,
    notify_booking,
    notify_new_lead,
    notify_quote_decision,
    notify_reminder,
    refuse_client_message,
)
from app.notify.telegram import TelegramProvider
from app.quotes import build_quote_pdf, compute_totals, normalize_items

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    job_type = Column(String, nullable=True)
    urgency = Column(String, nullable=True)
    address = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Call(Base):
    __tablename__ = "calls"

    id = Column(Integer, primary_key=True, index=True)
    retell_call_id = Column(String, unique=True, index=True, nullable=False)
    from_number = Column(String, nullable=True)
    transcript = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    status = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    job_type = Column(String, nullable=True)
    address = Column(String, nullable=True)
    appointment_time = Column(DateTime, nullable=False, index=True)
    status = Column(String, nullable=True, default="booked")
    created_at = Column(DateTime, default=datetime.utcnow)


class ReminderLog(Base):
    __tablename__ = "reminder_log"
    __table_args__ = (UniqueConstraint("appointment_id", "kind", name="uq_reminder"),)

    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(Integer, nullable=False, index=True)
    kind = Column(String, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)


class BotState(Base):
    __tablename__ = "bot_state"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=True)


class Quote(Base):
    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True, index=True)
    number = Column(String, unique=True, index=True, nullable=True)
    lead_id = Column(Integer, nullable=True)
    name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)
    job_type = Column(String, nullable=True)
    items = Column(JSON, nullable=True)
    subtotal = Column(Float, nullable=True)
    tax_rate = Column(Float, nullable=True)
    total = Column(Float, nullable=True)
    status = Column(String, nullable=True, default="draft")
    notes = Column(Text, nullable=True)
    pdf_data = Column(LargeBinary, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _lead_to_dict(lead: Lead) -> Dict[str, Any]:
    return {
        "id": lead.id,
        "name": lead.name,
        "phone": lead.phone,
        "job_type": lead.job_type,
        "urgency": lead.urgency,
        "address": lead.address,
        "description": lead.description,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
    }


def _appointment_to_dict(appt: Appointment) -> Dict[str, Any]:
    return {
        "id": appt.id,
        "name": appt.name,
        "phone": appt.phone,
        "job_type": appt.job_type,
        "address": appt.address,
        "appointment_time": appt.appointment_time.isoformat() if appt.appointment_time else None,
        "status": appt.status,
        "created_at": appt.created_at.isoformat() if appt.created_at else None,
    }


def _call_to_dict(call: Call) -> Dict[str, Any]:
    return {
        "id": call.id,
        "retell_call_id": call.retell_call_id,
        "from_number": call.from_number,
        "transcript": call.transcript,
        "summary": call.summary,
        "status": call.status,
        "created_at": call.created_at.isoformat() if call.created_at else None,
    }


def _quote_to_dict(quote: Quote) -> Dict[str, Any]:
    return {
        "id": quote.id,
        "number": quote.number,
        "lead_id": quote.lead_id,
        "name": quote.name,
        "phone": quote.phone,
        "address": quote.address,
        "job_type": quote.job_type,
        "items": quote.items,
        "subtotal": quote.subtotal,
        "tax_rate": quote.tax_rate,
        "total": quote.total,
        "status": quote.status,
        "notes": quote.notes,
        "created_at": quote.created_at.isoformat() if quote.created_at else None,
        "pdf_url": f"/quotes/{quote.id}/pdf" if quote.id else None,
    }


def _extract_args(body: Any) -> Dict[str, Any]:
    if not isinstance(body, dict):
        return {}
    args = body.get("args")
    if isinstance(args, dict):
        return args
    return body


def _first_present(data: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None and (not isinstance(value, str) or value.strip()):
            return value
    return None


def _extract_time_value(data: Dict[str, Any]) -> Any:
    value = _first_present(data, "appointment_time", "appointment_datetime", "datetime", "slot")
    if value is not None:
        return value
    date_part = _first_present(data, "date", "appointment_date")
    if date_part is None:
        return None
    time_part = _first_present(data, "time")
    if time_part is None:
        return date_part
    return f"{date_part} {time_part}"


def _parse_appointment_time(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value, tz=timezone.utc)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
    else:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


app = FastAPI(title="plumber-agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:4200")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _create_tables():
    last_error: Optional[Exception] = None
    for _ in range(30):
        try:
            Base.metadata.create_all(bind=engine)
            return
        except Exception as exc:  # db may not be ready yet
            last_error = exc
            time.sleep(2)
    if last_error is not None:
        raise last_error


_scheduler: Optional[BackgroundScheduler] = None


def _reminder_tick():
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        upcoming = (
            db.query(Appointment)
            .filter(Appointment.appointment_time >= now)
            .order_by(Appointment.appointment_time)
            .limit(200)
            .all()
        )
        for appt in upcoming:
            if appt.appointment_time is None or not due_for_reminder(
                now, appt.appointment_time
            ):
                continue
            logged = (
                db.query(ReminderLog)
                .filter(
                    ReminderLog.appointment_id == appt.id,
                    ReminderLog.kind == "reminder_1h",
                )
                .first()
            )
            if logged is not None:
                continue
            try:
                sent = notify_reminder(_appointment_to_dict(appt))
            except Exception:
                sent = False
            if sent:
                db.add(ReminderLog(appointment_id=appt.id, kind="reminder_1h"))
                db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _apply_client_decision(db: Session, text: str, decision: str, chat_id: Any):
    upper = text.upper()
    match = re.search(r"DEV-\d{4}-\d+", upper)
    quote = None
    if match:
        quote = db.query(Quote).filter(Quote.number == match.group(0)).first()
    if quote is None:
        quote = (
            db.query(Quote)
            .filter(Quote.status == "sent")
            .order_by(Quote.id.desc())
            .first()
        )
    token = os.getenv("TELEGRAM_CLIENT_BOT_TOKEN")
    if quote is None:
        if token and chat_id:
            try:
                TelegramProvider(token=token).send_text(
                    str(chat_id), no_pending_quote_message()
                )
            except Exception:
                pass
        return
    quote.status = decision
    db.commit()
    db.refresh(quote)
    if token and chat_id:
        try:
            message = (
                accept_client_message(_quote_to_dict(quote))
                if decision == "accepted"
                else refuse_client_message(_quote_to_dict(quote))
            )
            TelegramProvider(token=token).send_text(str(chat_id), message)
        except Exception:
            pass
    try:
        notify_quote_decision(_quote_to_dict(quote), decision)
    except Exception:
        pass


def _telegram_tick():
    token = os.getenv("TELEGRAM_CLIENT_BOT_TOKEN")
    if (os.getenv("NOTIFY_PROVIDER") or "").strip().lower() != "telegram" or not token:
        return
    db = SessionLocal()
    try:
        state = db.query(BotState).filter(BotState.key == "telegram_offset").first()
        offset = int(state.value) + 1 if state and state.value else None
        updates = TelegramProvider(token=token).get_updates(offset=offset)
        max_id = None
        for update in updates:
            uid = update.get("update_id")
            if isinstance(uid, int) and (max_id is None or uid > max_id):
                max_id = uid
            message = update.get("message") or {}
            text = str(message.get("text") or "").strip()
            chat = message.get("chat") or {}
            if not text or not chat.get("id"):
                continue
            upper = text.upper()
            if "ACCEPT" in upper or "ACCEPTE" in upper:
                _apply_client_decision(db, text, "accepted", chat.get("id"))
            elif "REFUS" in upper or "REFUSE" in upper or "DECLINE" in upper:
                _apply_client_decision(db, text, "refused", chat.get("id"))
        if max_id is not None:
            if state is None:
                state = BotState(key="telegram_offset", value=str(max_id))
                db.add(state)
            else:
                state.value = str(max_id)
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


@app.on_event("startup")
def _start_scheduler():
    global _scheduler
    if os.getenv("DISABLE_SCHEDULER") == "1":
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _reminder_tick, "interval", minutes=1, id="reminders",
        max_instances=1, coalesce=True,
    )
    _scheduler.add_job(
        _telegram_tick, "interval", seconds=20, id="telegram",
        max_instances=1, coalesce=True,
    )
    _scheduler.start()
    print("reminder scheduler started", flush=True)


@app.on_event("shutdown")
def _stop_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/leads")
def list_leads(db: Session = Depends(get_db)):
    leads = db.query(Lead).order_by(Lead.id.desc()).all()
    return [_lead_to_dict(lead) for lead in leads]


@app.get("/appointments")
def list_appointments(db: Session = Depends(get_db)):
    appointments = db.query(Appointment).order_by(Appointment.id.desc()).all()
    return [_appointment_to_dict(appt) for appt in appointments]


@app.get("/calls")
def list_calls(db: Session = Depends(get_db)):
    calls = db.query(Call).order_by(Call.id.desc()).all()
    return [_call_to_dict(call) for call in calls]


@app.post("/tools/create-lead")
async def create_lead(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        body = {}
    data = _extract_args(body)
    lead = Lead(
        name=_first_present(data, "name", "customer_name", "caller_name", "full_name"),
        phone=_first_present(
            data, "phone", "phone_number", "customer_phone", "caller_phone", "from_number"
        ),
        job_type=_first_present(
            data, "job_type", "jobtype", "job", "service_type", "problem_type", "service"
        ),
        urgency=_first_present(data, "urgency", "priority"),
        address=_first_present(data, "address", "customer_address"),
        description=_first_present(
            data,
            "description",
            "problem_description",
            "problem",
            "issue",
            "issue_description",
            "details",
        ),
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    try:
        notify_new_lead(_lead_to_dict(lead))
    except Exception:
        pass
    return {"success": True, "lead": _lead_to_dict(lead)}


@app.post("/tools/book-appointment")
async def book_appointment(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        body = {}
    data = _extract_args(body)
    appointment_time = _parse_appointment_time(_extract_time_value(data))
    if appointment_time is None:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "appointment_time is required (ISO format)"},
        )
    existing = (
        db.query(Appointment)
        .filter(Appointment.appointment_time == appointment_time)
        .first()
    )
    if existing is not None:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "message": "Slot is taken: an appointment already exists at this time.",
                "appointment": _appointment_to_dict(existing),
            },
        )
    appt = Appointment(
        name=_first_present(data, "name", "customer_name", "caller_name", "full_name"),
        phone=_first_present(
            data, "phone", "phone_number", "customer_phone", "caller_phone", "from_number"
        ),
        job_type=_first_present(
            data, "job_type", "jobtype", "job", "service_type", "problem_type", "service"
        ),
        address=_first_present(data, "address", "customer_address"),
        appointment_time=appointment_time,
        status=data.get("status") or "booked",
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)
    try:
        notify_booking(_appointment_to_dict(appt))
    except Exception:
        pass
    return {"success": True, "appointment": _appointment_to_dict(appt)}


def _check_availability(value: Any, db: Session):
    appointment_time = _parse_appointment_time(value)
    if appointment_time is None:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "appointment_time is required (ISO format)"},
        )
    existing = (
        db.query(Appointment)
        .filter(Appointment.appointment_time == appointment_time)
        .first()
    )
    if existing is not None:
        return {
            "success": True,
            "available": False,
            "message": (
                "Slot taken: an appointment already exists at "
                f"{existing.appointment_time.isoformat()}."
            ),
        }
    return {
        "success": True,
        "available": True,
        "message": f"Slot available at {appointment_time.isoformat()}.",
    }


@app.get("/tools/check-availability")
async def check_availability_get(
    appointment_time: Optional[str] = None, db: Session = Depends(get_db)
):
    return _check_availability(appointment_time, db)


@app.post("/tools/check-availability")
async def check_availability_post(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        body = {}
    data = _extract_args(body)
    return _check_availability(_extract_time_value(data), db)


@app.post("/tools/send-whatsapp")
async def send_whatsapp(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    data = _extract_args(body)
    to = data.get("to")
    message = data.get("message")
    if not to or not message:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "to and message are required"},
        )
    via = data.get("via")
    try:
        notifier = client_notifier(strict=True) if via == "client" else get_notifier()
        result = notifier.send_text(to, message)
    except NotificationError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "message": str(exc)},
        )
    return {
        "success": True,
        "provider": result.provider,
        "message_id": result.message_id,
    }


@app.post("/tools/create-quote")
async def create_quote(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        body = {}
    data = _extract_args(body)
    items = normalize_items(data.get("items"))
    if not items:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "at least one item is required"},
        )
    try:
        tax_rate = float(data.get("tax_rate", 0.20))
    except (TypeError, ValueError):
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "tax_rate must be a number"},
        )
    lead_id = data.get("lead_id")
    lead = db.query(Lead).filter(Lead.id == lead_id).first() if lead_id else None
    quote = Quote(
        lead_id=lead_id,
        name=_first_present(data, "name", "customer_name") or (lead.name if lead else None),
        phone=_first_present(data, "phone", "phone_number", "customer_phone")
        or (lead.phone if lead else None),
        address=_first_present(data, "address", "customer_address")
        or (lead.address if lead else None),
        job_type=_first_present(data, "job_type", "jobtype", "job", "service")
        or (lead.job_type if lead else None),
        items=items,
        tax_rate=tax_rate,
        status="draft",
        notes=data.get("notes"),
    )
    db.add(quote)
    db.flush()
    quote.number = f"DEV-{datetime.utcnow().year}-{quote.id:04d}"
    totals = compute_totals(items, tax_rate)
    quote.subtotal = totals["subtotal"]
    quote.total = totals["total"]
    quote.pdf_data = build_quote_pdf(
        {
            "number": quote.number,
            "name": quote.name,
            "phone": quote.phone,
            "address": quote.address,
            "job_type": quote.job_type,
            "items": items,
            "tax_rate": tax_rate,
            "notes": quote.notes,
        }
    )
    db.commit()
    db.refresh(quote)
    return {"success": True, "quote": _quote_to_dict(quote)}


@app.get("/quotes")
def list_quotes(db: Session = Depends(get_db)):
    quotes = db.query(Quote).order_by(Quote.id.desc()).all()
    return [_quote_to_dict(quote) for quote in quotes]


@app.get("/quotes/{quote_id}/pdf")
def download_quote_pdf(quote_id: int, db: Session = Depends(get_db)):
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if quote is None or not quote.pdf_data:
        return JSONResponse(status_code=404, content={"message": "Quote not found"})
    return Response(
        content=bytes(quote.pdf_data),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{quote.number}.pdf"'},
    )


@app.post("/tools/send-quote")
async def send_quote(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        body = {}
    data = _extract_args(body)
    quote_id = data.get("quote_id") or data.get("id")
    if not quote_id:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "quote_id is required"},
        )
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if quote is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "Quote not found"},
        )
    if not quote.phone:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Quote has no client phone number"},
        )
    base_url = os.getenv("PUBLIC_BASE_URL")
    if not base_url:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "PUBLIC_BASE_URL is not configured"},
        )
    result = deliver_quote(
        _quote_to_dict(quote),
        f"{base_url.rstrip('/')}/quotes/{quote.id}/pdf",
        data.get("message"),
        data.get("to"),
        bytes(quote.pdf_data) if quote.pdf_data else None,
    )
    if result["client"] is None:
        return JSONResponse(
            status_code=502,
            content={"success": False, "message": "Could not send quote to client"},
        )
    quote.status = "sent"
    db.commit()
    return {
        "success": True,
        "provider": get_notifier().name,
        "message_id": result["client"],
        "plumber_message_id": result["plumber"],
        "quote": _quote_to_dict(quote),
    }


@app.patch("/quotes/{quote_id}/status")
async def set_quote_status(quote_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        body = {}
    status = body.get("status") if isinstance(body, dict) else None
    if status not in ("draft", "sent", "accepted", "refused"):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "status must be one of: draft, sent, accepted, refused",
            },
        )
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if quote is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "Quote not found"},
        )
    quote.status = status
    db.commit()
    db.refresh(quote)
    return {"success": True, "quote": _quote_to_dict(quote)}


@app.get("/stats/summary")
def stats_summary(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    calls = db.query(Call).filter(Call.created_at >= month_start).count()
    leads = db.query(Lead).filter(Lead.created_at >= month_start).count()
    appointments = (
        db.query(Appointment).filter(Appointment.created_at >= month_start).count()
    )
    accepted = (
        db.query(Quote)
        .filter(Quote.status == "accepted", Quote.created_at >= month_start)
        .all()
    )
    revenue = round(sum(q.total or 0 for q in accepted), 2)
    return {
        "month": month_start.strftime("%Y-%m"),
        "calls": calls,
        "leads": leads,
        "appointments": appointments,
        "accepted_quotes": len(accepted),
        "accepted_revenue": revenue,
    }


def _upsert_call_from_event(db: Session, event: NormalizedCallEvent):
    existing = db.query(Call).filter(Call.retell_call_id == event.external_call_id).first()
    if existing is not None:
        if event.from_number is not None:
            existing.from_number = event.from_number
        if event.transcript is not None:
            existing.transcript = event.transcript
        if event.summary is not None:
            existing.summary = event.summary
        if event.status is not None:
            existing.status = event.status
        db.commit()
        db.refresh(existing)
        return existing, True
    call = Call(
        retell_call_id=event.external_call_id,
        from_number=event.from_number,
        transcript=event.transcript,
        summary=event.summary,
        status=event.status,
    )
    db.add(call)
    db.commit()
    db.refresh(call)
    return call, False


def _handle_provider_webhook(body: Any, provider: VoiceProvider, db: Session):
    if not isinstance(body, dict):
        return JSONResponse(status_code=400, content={"message": "Invalid JSON body"})
    try:
        event = provider.parse_webhook(body)
    except VoiceProviderError as exc:
        return JSONResponse(status_code=exc.status_code, content={"message": str(exc)})
    if event is None:
        return {"status": "ignored", "event": body.get("event")}
    call, updated = _upsert_call_from_event(db, event)
    return {"success": True, "call": _call_to_dict(call), "updated": updated}


@app.post("/webhook/retell")
async def retell_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"message": "Invalid JSON body"})
    return _handle_provider_webhook(body, RetellProvider(), db)


@app.post("/webhook/voice")
async def voice_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"message": "Invalid JSON body"})
    try:
        provider = get_provider()
    except VoiceProviderError as exc:
        return JSONResponse(status_code=exc.status_code, content={"message": str(exc)})
    return _handle_provider_webhook(body, provider, db)


@app.post("/tools/place-call")
async def place_call(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        body = {}
    data = _extract_args(body)
    to_number = data.get("to_number")
    if not to_number:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "to_number is required"},
        )
    try:
        provider = get_provider()
    except VoiceProviderError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "message": str(exc)},
        )
    metadata = data.get("metadata")
    variables = data.get("variables")
    try:
        result = provider.create_call(
            OutboundCallRequest(
                to_number=to_number,
                from_number=data.get("from_number"),
                agent_id=data.get("agent_id"),
                metadata=metadata if isinstance(metadata, dict) else None,
                variables=variables if isinstance(variables, dict) else None,
            )
        )
    except VoiceProviderError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "message": str(exc)},
        )
    call = Call(
        retell_call_id=result.external_call_id,
        from_number=data.get("from_number"),
        status="initiated",
    )
    db.add(call)
    db.commit()
    db.refresh(call)
    return {
        "success": True,
        "provider": result.provider,
        "external_call_id": result.external_call_id,
        "call": _call_to_dict(call),
    }
