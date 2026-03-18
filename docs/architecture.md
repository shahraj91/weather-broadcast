# Architecture Overview

## Summary

Weather Broadcaster is a Python 3.12 service that sends personalised WhatsApp weather
messages to a global user base at 7:30 AM in each user's local timezone.

---

## Component map

```
main.py
  └─ scheduler.py             APScheduler — one cron job per IANA timezone
       └─ run_timezone_job()
            ├─ database/db.py              load active users for timezone
            ├─ weather/fetcher.py          fetch forecast from Open-Meteo
            ├─ messaging/formatter.py      generate message via Ollama HTTP API
            └─ messaging/broadcaster.py   send via Twilio WhatsApp API, log result
```

---

## Scheduling

One `CronTrigger` job is registered per distinct IANA timezone found in the database.
Jobs fire at 07:30 local time. Adding a user in a new timezone causes the scheduler
to register a new job on the next restart (or if `scheduler.py` is reloaded).

**Rule:** never create one job per user — only one job per timezone.

---

## Database (SQLite → Postgres)

Schema is Postgres-compatible. Two tables:

### `users`

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | auto-increment |
| `phone` | TEXT UNIQUE | E.164 format |
| `lat` / `lon` | REAL | used for weather + timezone + unit detection |
| `timezone` | TEXT | IANA e.g. `America/New_York` |
| `unit_system` | TEXT | `metric` or `imperial` — auto-detected from location |
| `country_code` | TEXT | ISO 3166-1 alpha-2 |
| `name` | TEXT | recipient's display name, used in the message greeting |
| `active` | INTEGER | 0 = unsubscribed |
| `created_at` | TEXT | ISO timestamp |

### `send_logs`

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | auto-increment |
| `user_id` | INTEGER FK | references `users.id` |
| `status` | TEXT | `success` or `failed` |
| `message_sid` | TEXT | Twilio message SID on success |
| `error` | TEXT | error string on failure |
| `retryable` | INTEGER | whether the failure could be retried |
| `message_body` | TEXT | full message text that was sent |
| `sent_at` | TEXT | ISO timestamp |

Inline migrations in `db.init()` handle adding new columns to existing databases
without requiring a full schema drop.

---

## Weather data (Open-Meteo)

`weather/fetcher.py` calls the Open-Meteo forecast API using lat/lon.
No API key is required. Returned fields: `temp_max`, `temp_min`, `condition`,
`wind_speed`, `humidity`, with units adapted to the user's unit system.

Custom exception: `WeatherFetchError`.

---

## Message generation (Ollama HTTP API)

`messaging/formatter.py` POSTs to the Ollama `/api/generate` endpoint with:
- `LLAMA_API_URL` (default `http://localhost:11434/api/generate`)
- `LLAMA_MODEL` (default `llama3`)
- `LLAMA_TIMEOUT` (default 60 s)

The system prompt instructs the model to produce:
1. A structured weather summary with a personalised greeting (uses `user.name`)
2. A `🌟 Fun Fact:` section

If Ollama is unreachable, times out, or returns an empty response, a static
fallback template is used. The fallback is always present — message generation
never raises to the caller unless the weather data itself is invalid.

Custom exception: `FormatterError`.

---

## WhatsApp delivery (Twilio)

`messaging/broadcaster.py` sends via the Twilio REST API. Phone numbers are
validated to E.164 format before sending. Failed sends are retried up to 3 times
with exponential back-off for transient errors. Every attempt (success or failure)
is written to `send_logs`.

Custom exceptions: `BroadcasterError`, `BroadcasterAuthError`.

---

## Unit and timezone auto-detection

| Utility | Library | Output |
|---------|---------|--------|
| `utils/timezone_resolver.py` | `timezonefinder` | IANA timezone string |
| `utils/unit_resolver.py` | `geopy` (reverse geocode) | `metric` or `imperial`, ISO country code |

Imperial units are used for US, Liberia, and Myanmar. All other countries use metric.
Users are never asked to set their unit preference.

---

## Utility scripts

| Script | Purpose |
|--------|---------|
| `add_users.py` | Bulk-import from `users_to_add.csv` (phone, lat, lon, name) |
| `list_users.py` | Query users by active status, name, or phone |
| `list_sends.py` | View send history; filter by user, status, or date |
| `send_now.py` | Manually trigger a broadcast for a timezone, user, or all |

---

## Error handling conventions

- All external calls raise typed exceptions (never raw `Exception`)
- `WeatherFetchError`, `BroadcasterError`, `BroadcasterAuthError`, `FormatterError`
- Scheduler catches exceptions per-user so one failure never blocks others
- All errors logged with `logging` module (no `print()`)

---

## Testing

Every module has a matching `tests/test_<module>.py`.
All external dependencies (Twilio, Open-Meteo, Ollama, geopy) are mocked via
`unittest.mock.patch`. Tests run without any network access.

```bash
pytest tests/ -v
pytest tests/ --cov=. --cov-report=term-missing
```