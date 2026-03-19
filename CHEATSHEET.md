# Weather Broadcaster — Cheat Sheet

---

## ⚙️ Setup

```bash
# Create and activate virtualenv
python3 -m venv venv && source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure credentials
cp .env.example .env
# Edit .env — fill in Twilio creds and confirm Ollama URL/model

# Initialise DB tables (auto-runs on first use, but safe to run manually)
python3 -c "from database.db import Database; db = Database('./data/weather_broadcast.db'); db.init(); db.close()"

# Seed 10 global test users
python3 database/seed.py
```

**Required `.env` values:**
```
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
LLAMA_API_URL=http://localhost:11434/api/generate
LLAMA_MODEL=llama3
LLAMA_TIMEOUT=60
DB_PATH=./data/weather_broadcast.db
```

---

## 👤 Adding Users

**Single user with name:**
```bash
python3 add_users.py --name "<name>" --phone +<country_code><number> --lat <latitude> --lon <longitude>
```

**Single user without name:**
```bash
python3 add_users.py --phone +<country_code><number> --lat <latitude> --lon <longitude>
```

**Bulk import from CSV:**
```bash
python3 add_users.py --csv
```

**CSV format** (`users_to_add.csv` in project root — `name` column is optional):
```
phone,lat,lon,name
+1XXXXXXXXXX,<latitude>,<longitude>,<name>
+44XXXXXXXXXX,<latitude>,<longitude>,<name>
+33XXXXXXXXXX,<latitude>,<longitude>,
```

**Coordinate format rules:**
- Plain decimal degrees — no degree symbols, no DMS notation
- Latitude: North = positive (`47.6148`), South = negative (`-33.8688`)
- Longitude: East = positive (`139.6503`), West = negative (`-122.3470`)
- Timezone and unit system are **auto-detected** from lat/lon — do not set them manually
- Phone must be **E.164 format**: `+` followed by country code and number, no spaces

---

## 👥 Viewing Users

```bash
python3 list_users.py              # all active users
python3 list_users.py --all        # include inactive users
python3 list_users.py <name>       # search by name (case-insensitive)
python3 list_users.py +<country_code><number> # search by phone
```

---

## 📤 Sending Messages

```bash
python3 send_now.py                           # send to all active users (all timezones)
python3 send_now.py <name>                    # send to a specific user by name
python3 send_now.py +<country_code><number>   # send to a specific user by phone
python3 send_now.py America/Los_Angeles       # send to all users in a timezone
```

> Bypasses the 7:30 AM scheduler — runs immediately. Safe for testing.

---

## 📋 Checking Send Logs

```bash
python3 list_sends.py              # last 20 sends
python3 list_sends.py --all        # full history
python3 list_sends.py --failed     # only failed sends
python3 list_sends.py <name>       # sends for a user by name
python3 list_sends.py +<country_code><number> # sends for a user by phone
```

---

## 📲 Twilio Sandbox Opt-In

> The sandbox silently drops messages to anyone who hasn't sent the join code.
> `status="skipped"` in logs = this is why.

**List all users and their current opt-in status:**
```bash
python3 opt_in_user.py --list
```

**Mark a user as opted in** (after they've sent the join code from their WhatsApp):
```bash
python3 opt_in_user.py <name>                   # by name
python3 opt_in_user.py +<country_code><number>  # by phone
```

**What the user must send from their WhatsApp** to `<TWILIO_WHATSAPP_FROM number>`:
```
join <TWILIO_SANDBOX_KEYWORD>
```
(Both values are in your `.env` file.)

**Add a user who has already opted in:**
```bash
python3 add_users.py --name "<name>" --phone +<country_code><number> \
  --lat <latitude> --lon <longitude> --opted-in
```

**Run the DB migration** (once, on existing databases before first use):
```bash
python3 migrate_sandbox.py
```

---

## 🕐 Running the Scheduler

```bash
# Start (blocks — sends at 7:30 AM per user's local timezone)
python3 main.py

# Stop
Ctrl+C

# Run in background, log to file
nohup python3 main.py >> weather_broadcast.log 2>&1 &

# Check if it's running
pgrep -a python | grep main.py

# Watch live logs
tail -f weather_broadcast.log
```

---

## 🧪 Testing

```bash
pytest tests/ -v                                          # full test suite
pytest tests/test_formatter.py -v                         # single test file
pytest tests/ -v -m 'not integration'                     # skip integration tests
pytest tests/ --cov=. --cov-report=term-missing           # with coverage report
```

---

## 🗄️ Database — Quick Queries

```bash
# Open the SQLite shell
sqlite3 ./data/weather_broadcast.db
```

```sql
-- Count total users
SELECT COUNT(*) FROM users;

-- List all timezones in use
SELECT DISTINCT timezone FROM users WHERE active = 1 ORDER BY timezone;

-- Check a specific user's details
SELECT * FROM users WHERE phone = '+<country_code><number>';

-- Deactivate a user (preserves history)
UPDATE users SET active = 0 WHERE phone = '+<country_code><number>';
```

---

## 🔧 Troubleshooting

**Verify Ollama is running:**
```bash
curl http://localhost:11434/api/tags
```

**Test Ollama directly:**
```bash
curl -s http://localhost:11434/api/generate \
  -d '{"model":"llama3:8b","prompt":"Say hello.","stream":false}' | python3 -m json.tool
```

**Check `.env` is loaded correctly:**
```bash
python3 -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('TWILIO_ACCOUNT_SID'))"
```

**Re-initialise DB schema without losing data** (safe — uses `CREATE TABLE IF NOT EXISTS`):
```bash
python3 -c "from database.db import Database; db = Database('./data/weather_broadcast.db'); db.init(); print('OK'); db.close()"
```

**Start Ollama if not running:**
```bash
ollama serve &
ollama pull llama3:8b   # first time only
```

---

## 💬 Two-Way Conversation

```bash
# Start webhook (requires WEBHOOK_ENABLED=true in .env)
python3 main.py

# Expose locally with ngrok (separate terminal)
ngrok http 5000
```

**Connect to Twilio:**
1. Copy your ngrok HTTPS URL (e.g. `https://abc123.ngrok.io`)
2. Twilio Console → Messaging → Try it out → Send a WhatsApp message →
   Sandbox Settings → "When a message comes in" → paste URL + `/webhook`
3. Send any WhatsApp message to your sandbox number to test

**Health check:**
```bash
curl http://localhost:5000/health
```

**Supported intents (auto-detected by Llama):**
- `WEATHER_QUERY` — "Will it rain today?", "Hot tomorrow?"
- `ACTIVITY_UPDATE` — "I'm a runner", "I cycle to work"
- `WEATHER_NOW` — "What's the weather now?"
- `UNSUBSCRIBE` — "stop", "unsubscribe", "cancel"
- `GENERAL` — anything else

---

## ⚠️ Risk Alerts

Risk alerts are sent as a **separate message** immediately after the morning broadcast when thresholds are crossed.

**Triggers:**
- Temp high > 35°C / 95°F — extreme heat
- Temp low < -10°C / 14°F — dangerous cold
- Wind > 60 km/h / 37.3 mph — strong winds
- Condition contains "thunderstorm"
- Humidity > 90% AND foggy conditions
- Temp high > 30°C / 86°F AND humidity > 70% — heat index

**Logged in `send_logs` with `status="risk_alert"`:**
```bash
python3 list_sends.py --all   # risk_alert entries visible here
```

---

## 🔒 Safety & Security

### Hallucination Check
```bash
# Enable (default)
HALLUCINATION_CHECK_ENABLED=true   # in .env

# Disable (for testing / prompt tuning)
HALLUCINATION_CHECK_ENABLED=false
```
When enabled, Llama output is validated against actual temp and condition values.
Mismatches fall back to the static template and increment `hallucination_fallbacks_total`.

### Content Safety Filter
```bash
# Enable (default)
SAFETY_CHECK_ENABLED=true   # in .env

# Disable
SAFETY_CHECK_ENABLED=false
```
Two-layer check: keyword blocklist → Llama YES/NO appropriateness prompt.
Unsafe messages are replaced with the static fallback.

### Twilio Signature Validation
```bash
# .env for local development (ngrok URL changes each session)
TWILIO_SIGNATURE_VALIDATION=false
WEBHOOK_BASE_URL=https://your-ngrok-url.ngrok-free.dev

# .env for production
TWILIO_SIGNATURE_VALIDATION=true
WEBHOOK_BASE_URL=https://your-stable-domain.com
```
Invalid signatures return HTTP 403 and are logged with a masked phone number.

---

## 📊 Observability

### View Metrics Endpoint
```bash
# Check all counters and latency averages
curl "http://localhost:5000/metrics?api_key=<METRICS_API_KEY>"
```

Response example:
```json
{
  "messages_sent_total": 42,
  "messages_failed_total": 1,
  "hallucination_fallbacks_total": 0,
  "safety_blocks_total": 0,
  "llama_latency_ms": 1240.5,
  "fallback_rate": 0.0238,
  "webhook_requests_total": 17,
  "webhook_rejected_total": 0
}
```

> Counters are **persistent** — stored in the same SQLite DB as the rest of
> the app (`DB_PATH`). Values survive process restarts.

### Reset a Counter
```bash
# Reset a single counter back to 0 (useful after a test run or incident)
curl -X POST "http://localhost:5000/metrics/reset?name=messages_failed_total&api_key=<METRICS_API_KEY>"
# → {"reset": "messages_failed_total", "value": 0}
```

### Structured Log Format
All key events emit JSON log lines:
```json
{
  "timestamp": "2026-03-18T07:30:00Z",
  "event": "message_sent",
  "user": "+1818***3973",
  "timezone": "America/Los_Angeles",
  "status": "success"
}
```

### Tail and Parse Structured Logs
```bash
tail -f weather_broadcast.log | python3 -m json.tool
```

### Admin Alerts
Set `ADMIN_PHONE` in `.env` to receive WhatsApp alerts for:
- Ollama unreachable at startup
- More than 3 consecutive send failures in a timezone
- Failure rate > 50% in a single job run
