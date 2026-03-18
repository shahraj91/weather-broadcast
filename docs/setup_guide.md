# Weather Broadcast System — Setup & Installation Guide

Version 2.0 • March 2026

---

## 1. Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.9+ | 3.12 recommended |
| pytest | any | Already installed |
| Ollama | latest | Must be running locally before starting the app |
| Twilio account | — | Free trial ok — needed for WhatsApp sending |
| Internet access | — | Required for Open-Meteo API + Twilio |

---

## 2. Step-by-Step Setup

### Step 1 — Clone / Create Project Directory

```bash
mkdir weather-broadcast && cd weather-broadcast
# or
git clone <your-repo-url>
```

### Step 2 — Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate      # macOS / Linux
# venv\Scripts\activate       # Windows
```

### Step 3 — Install Python Dependencies

```bash
pip install -r requirements.txt
```

This installs: `apscheduler`, `requests`, `timezonefinder`, `pytz`, `geopy`,
`twilio`, `python-dotenv`, `pytest`, `pytest-cov`.

### Step 4 — Install and Start Ollama

Download Ollama from [ollama.com](https://ollama.com) and install it, then pull a model:

```bash
ollama pull llama3
```

Ollama must be running before the app starts. To start it manually:

```bash
ollama serve
```

Verify it's working:

```bash
curl http://localhost:11434/api/tags
```

You should see a JSON list of available models.

### Step 5 — Set Up Twilio

5a. Sign up at [twilio.com](https://twilio.com) (free trial provides ~$15 credit)

5b. In the Twilio Console, navigate to **Messaging > Try it out > Send a WhatsApp message**

5c. Follow the sandbox instructions — send a join code from your WhatsApp to activate the sandbox

5d. Note down your credentials:
```
Account SID:  ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Auth Token:   your_auth_token
From Number:  whatsapp:+14155238886  (Twilio sandbox number)
```

### Step 6 — Create `.env` File

```bash
cp .env.example .env
```

Then edit `.env`:

```dotenv
# .env — never commit this file
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886

LLAMA_API_URL=http://localhost:11434/api/generate
LLAMA_MODEL=llama3
LLAMA_TIMEOUT=60

DB_PATH=./data/weather_broadcast.db
```

### Step 7 — Create `.gitignore`

```
.env
venv/
__pycache__/
*.pyc
data/
.pytest_cache/
```

### Step 8 — Initialise the Database

```bash
python3 -c "from database.db import Database; Database('./data/weather_broadcast.db').init()"
```

This creates the SQLite database with `users` and `send_logs` tables.

### Step 9 — Seed Test Users

```bash
python3 database/seed.py
```

Adds 10 test users across different timezones and unit systems so you can verify
the pipeline end-to-end.

### Step 10 — Verify Ollama Integration

```bash
curl http://localhost:11434/api/tags       # confirm Ollama is running and model is listed
ollama list                                # list available models
```

If `llama3` is not listed, run `ollama pull llama3`.

### Step 11 — Run the Test Suite

```bash
pytest tests/ -v
```

All unit tests should pass without any network access or credentials.

To skip integration tests:

```bash
pytest tests/ -v -m 'not integration'
```

### Step 12 — Send a Test WhatsApp Message

```bash
python3 send_now.py +YOUR_NUMBER
```

Replace `+YOUR_NUMBER` with a WhatsApp number registered in the Twilio sandbox
(E.164 format, e.g. `+<country_code><number>`). You should receive the message within seconds.

### Step 13 — Start the Scheduler

```bash
python3 main.py
```

The scheduler registers one cron job per unique timezone in the database and runs
continuously, firing at 07:30 local time for each timezone. Use `tmux` or `screen`
in production to keep it running after terminal disconnect.

---

## 3. Project Directory After Setup

```
weather-broadcast/
├── main.py                    # Entry point — starts scheduler
├── scheduler.py               # One APScheduler cron job per timezone
├── add_users.py               # Bulk-import users from users_to_add.csv
├── list_users.py              # Query and display users in the database
├── list_sends.py              # View send history and delivery stats
├── send_now.py                # Manually trigger a broadcast immediately
├── database/
│   ├── db.py
│   ├── models.py
│   └── seed.py
├── weather/
│   └── fetcher.py
├── messaging/
│   ├── formatter.py
│   └── broadcaster.py
├── utils/
│   ├── timezone_resolver.py
│   └── unit_resolver.py
├── data/
│   └── weather_broadcast.db   ← created in Step 8
├── tests/
│   └── ...
├── .env                       ← created in Step 6 (git-ignored)
├── .gitignore
└── requirements.txt
```

---

## 4. Environment Variables Reference

| Variable | Example Value | Required | Default |
|----------|--------------|----------|---------|
| `TWILIO_ACCOUNT_SID` | `ACxxx...xxx` | Yes | — |
| `TWILIO_AUTH_TOKEN` | `your_token` | Yes | — |
| `TWILIO_WHATSAPP_FROM` | `whatsapp:+14155238886` | Yes | — |
| `LLAMA_API_URL` | `http://localhost:11434/api/generate` | No | `http://localhost:11434/api/generate` |
| `LLAMA_MODEL` | `llama3` | No | `llama3` |
| `LLAMA_TIMEOUT` | `60` | No | `60` |
| `DB_PATH` | `./data/weather_broadcast.db` | No | `./data/weather_broadcast.db` |

---

## 5. Twilio Sandbox vs Production

| | Sandbox | Production |
|-|---------|------------|
| Cost | Free (trial credit) | Per-message billing |
| Setup time | ~5 minutes | ~1–2 weeks (Meta approval) |
| Recipients | Only opted-in sandbox numbers | Any WhatsApp number |
| Message templates | Not required | Required for outbound |
| Best for | Development + testing | Live user base |

---

## 6. Troubleshooting

**Ollama not responding**
```bash
ollama serve              # start the Ollama daemon
ollama list               # confirm model is downloaded
ollama pull llama3        # download if missing
curl http://localhost:11434/api/tags   # verify API is reachable
```
Check `LLAMA_API_URL` and `LLAMA_MODEL` in `.env` match your setup.

**Twilio 401 Unauthorized**
- Double-check `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` in `.env`
- Ensure no extra whitespace in the `.env` values

**timezonefinder returns None**
- Verify latitude is between −90 and 90, longitude between −180 and 180
- Some ocean coordinates may not resolve — use the nearest land coordinate

**Scheduler not firing**
```bash
python3 -c "import apscheduler; print(apscheduler.__version__)"
```
- Confirm at least one active user exists in the database with a valid timezone
- Verify the system clock is correct — APScheduler uses the host machine's time

**Open-Meteo returns empty data**
- The API is free but has rate limits — do not exceed ~10,000 requests/day
- Add a short delay between user fetches in high-volume batches