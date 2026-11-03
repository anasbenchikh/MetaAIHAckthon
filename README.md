# Plumber AI Agent — Missed-Call Recovery for Plumbers

**Plombier Express Lyon — Dashboard Sarah**: an AI voice agent that answers a plumber's
missed calls, captures the lead, books the appointment, sends the quote, and notifies
everyone — all visible live on a bilingual (FR/EN) dashboard.

Built for demo and hackathon purposes. No authentication.

## What It Does

- **AI call answering (Retell AI)** — when the plumber can't pick up, the voice agent
  answers, collects name / phone / address / problem / urgency, checks availability,
  and books an appointment.
- **Swappable voice adapter** — Retell today, Pipecat tomorrow: all voice calls go
  through a `VoiceProvider` interface (`backend/app/voice/`), so swapping vendor means
  changing one env var, not the routes.
- **Live dashboard (Angular + Material)** — stat cards (leads, appointments, estimated
  recovered revenue), recent leads / appointments / calls with auto-refresh polling,
  leads table with urgency badges, appointments calendar, quotes management, and a
  monthly stats banner.
- **Quotes (devis) as PDF** — create a quote from a lead (client data auto-filled),
  download it as PDF, and send it to the client **and** the plumber.
- **Client ACCEPT flow** — the client replies `ACCEPTE DEV-2026-0003` (or ACCEPT / OK)
  to the Telegram client bot; the quote status flips to `accepted` automatically and
  the plumber is notified.
- **1-click recall** — call-back buttons on leads and calls via the voice provider.
- **Reminders** — automatic reminders ~1h before each appointment.

## Notifications: WhatsApp, SMS, Telegram

All notifications go through a swappable `Notifier` interface (`backend/app/notify/`)
selected with `NOTIFY_PROVIDER`:

| Provider | Channel | Notes |
|---|---|---|
| `telegram` | Telegram bots (plumber bot + client bot) | Current default. Simple setup, no templates, supports PDF upload. |
| `meta` | WhatsApp Cloud API | Official Meta API. Needs a verified business number; subject to the 24h messaging window and template rules. |
| `twilio` | WhatsApp + SMS | Twilio numbers can send both WhatsApp messages and plain SMS — easiest way to reach any phone number. |
| `fake` | Console log | Used for tests. |

Set `NOTIFY_LANG=fr|en` for French or English message templates.

## Architecture

```
Missed call → Retell AI → ngrok tunnel → FastAPI (/webhook/retell, /tools/*)
                                              ├── Postgres (leads, appointments, calls, quotes)
                                              ├── Telegram / WhatsApp / SMS notifications
                                              └── Angular dashboard (polling every 5s)
```

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app, models, routes, scheduler
│   │   ├── quotes.py          # Quote numbering + PDF generation (fpdf2)
│   │   ├── voice/             # VoiceProvider interface: retell, fake, factory
│   │   └── notify/            # Notifier interface: telegram, meta, twilio, fake
│   └── tests/                 # unittest suites (41 tests)
├── frontend/                  # Angular 21 standalone components + Material
│   └── src/app/
│       ├── components/        # dashboard, leads, appointments, quotes
│       ├── services/          # api.service, language.service (FR/EN)
│       └── models/
├── docker-compose.yml         # api + postgres + pgadmin
└── .env.example               # all configuration keys
```

## Quick Start

### 1. Backend (Docker)

```bash
cp .env.example .env   # then fill in tokens
docker compose up -d --build
```

- API: `http://localhost:8000` (`/health`, `/docs`)
- Postgres: `localhost:5432`, pgAdmin: `http://localhost:5050`

### 2. Voice: Retell AI + ngrok

Expose the API publicly (example with ngrok):

```
https://<your-tunnel>/webhook/retell
```

In Retell, set the webhook URL and add three **Custom Functions** pointing at the tunnel:

- `create_lead` → `POST /tools/create-lead`
- `check_availability` → `POST /tools/check-availability`
- `book_appointment` → `POST /tools/book-appointment`

Key env vars: `VOICE_PROVIDER=retell`, `RETELL_API_KEY`, `RETELL_AGENT_ID`, `PUBLIC_BASE_URL`.

### 3. Notifications

Telegram (simplest):

```
NOTIFY_PROVIDER=telegram
NOTIFY_LANG=en
TELEGRAM_BOT_TOKEN=<plumber bot from @BotFather>
TELEGRAM_CLIENT_BOT_TOKEN=<client bot>
PLUMBER_TELEGRAM_CHAT_ID=<plumber chat id>
```

Each bot needs a `/start` from its recipient first. For WhatsApp/SMS via Twilio, set
`NOTIFY_PROVIDER=twilio` plus `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
`TWILIO_WHATSAPP_FROM`, `TWILIO_SMS_FROM`. For Meta WhatsApp, set
`NOTIFY_PROVIDER=meta` plus `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`,
`PLUMBER_WHATSAPP`.

### 4. Frontend

```bash
cd frontend
npm install --legacy-peer-deps
npm start -- --port 4200   # http://localhost:4200
```

The dashboard calls `http://localhost:8000` (see `FRONTEND_URL` in `.env` for CORS).

## API Overview

- `GET /health /leads /appointments /calls /quotes /stats/summary`
- `GET /quotes/{id}/pdf` — download the quote PDF
- `PATCH /quotes/{id}/status` — `draft | sent | accepted | refused`
- `POST /tools/create-lead /tools/check-availability /tools/book-appointment`
- `POST /tools/create-quote /tools/send-quote /tools/place-call`
- `POST /webhook/retell` — Retell events (compat), `POST /webhook/voice` — generic

## Tests

```bash
docker cp backend/tests plumber-api:/tmp/rectests
docker exec -w /tmp/rectests plumber-api env PYTHONPATH=/app DISABLE_SCHEDULER=1 \
  python -m unittest test_notify test_tool_args test_quote test_stats
```

## Demo Script (60 seconds)

1. Call the Retell number and describe a leak → lead + appointment appear live on the dashboard.
2. Create and send the quote from the dashboard → client receives the PDF on Telegram.
3. Reply `ACCEPTE DEV-…` as the client → status flips to `accepted`, plumber is notified.

## Production Notes

- Replace the ngrok tunnel with a VPS + fixed domain + HTTPS.
- Add API authentication, DB backups, and multi-artisan dispatch for real deployment.
