# Weather Broadcast System — Test Plan

Version 2.0 • March 2026

---

## 1. Testing Philosophy

Each module is independently testable. All external dependencies (Open-Meteo API,
Twilio, Ollama, filesystem) are mocked in unit tests so the suite runs offline
with no credentials and zero cost. Integration tests are clearly marked and skipped
in CI unless explicitly enabled.

| Test Type | Scope | Mocking |
|-----------|-------|---------|
| Unit | Single function / class | All external calls mocked |
| Integration | Module-to-module | Real DB, mocked API |
| End-to-end | Full pipeline | Real everything (manual only) |

---

## 2. Test Suite Structure

```
tests/
├── conftest.py                # Shared fixtures
├── test_timezone_resolver.py  # utils/timezone_resolver.py
├── test_unit_resolver.py      # utils/unit_resolver.py
├── test_db.py                 # database/db.py
├── test_fetcher.py            # weather/fetcher.py
├── test_formatter.py          # messaging/formatter.py (incl. activity hints)
├── test_broadcaster.py        # messaging/broadcaster.py
├── test_scheduler.py          # scheduler.py
├── test_risk_engine.py        # conversation/risk_engine.py
└── test_handler.py            # conversation/handler.py
```

---

## 3. Test Cases by Module

### 3.1 Timezone Resolver (`test_timezone_resolver.py`)

| Test ID | Description | Expected Outcome |
|---------|-------------|-----------------|
| TZ-01 | New York coords (40.71, −74.00) | Returns `'America/New_York'` |
| TZ-02 | London coords (51.50, −0.12) | Returns `'Europe/London'` |
| TZ-03 | Tokyo coords (35.68, 139.69) | Returns `'Asia/Tokyo'` |
| TZ-04 | Sydney coords (−33.86, 151.20) | Returns `'Australia/Sydney'` |
| TZ-05 | Invalid lat/lon (999, 999) | Raises `ValueError` |
| TZ-06 | Exactly on timezone boundary | Returns valid IANA string |

### 3.2 Unit Resolver (`test_unit_resolver.py`)

| Test ID | Description | Expected Outcome |
|---------|-------------|-----------------|
| UR-01 | US coordinates | Returns `'imperial'` |
| UR-02 | France coordinates | Returns `'metric'` |
| UR-03 | Liberia coordinates | Returns `'imperial'` |
| UR-04 | Myanmar coordinates | Returns `'imperial'` |
| UR-05 | Japan coordinates | Returns `'metric'` |
| UR-06 | Geocoder returns None | Defaults to `'metric'` |

### 3.3 Database (`test_db.py`)

| Test ID | Description | Expected Outcome |
|---------|-------------|-----------------|
| DB-01 | Add new user with valid data | User persisted, id returned |
| DB-02 | Add duplicate phone number | Raises `IntegrityError` |
| DB-03 | Get users by timezone | Returns only matching active users |
| DB-04 | Deactivate user | `active=0`, excluded from future queries |
| DB-05 | Get all unique timezones | Returns distinct timezone list |
| DB-06 | Empty database query | Returns empty list (no error) |
| DB-07 | Log successful send | Send record written correctly |
| DB-08 | Log failed send | Failed record written, `retryable=True` |
| DB-09 | Add user with `name` field | Name persisted and returned via `_row_to_user` |

### 3.4 Weather Fetcher (`test_fetcher.py`)

| Test ID | Description | Expected Outcome |
|---------|-------------|-----------------|
| WF-01 | Valid metric request | Returns dict with `°C` and `km/h` values |
| WF-02 | Valid imperial request | Returns dict with `°F` and `mph` values |
| WF-03 | API returns 200 with all fields | All expected keys present |
| WF-04 | API returns 500 | Raises `WeatherFetchError` |
| WF-05 | Network timeout | Raises `WeatherFetchError` after 10 s |
| WF-06 | API returns partial data | Handles gracefully with defaults |
| WF-07 | Weather code maps to condition label | Returns human-readable string |

### 3.5 Message Formatter (`test_formatter.py`)

| Test ID | Description | Expected Outcome |
|---------|-------------|-----------------|
| MF-01 | Metric weather data input | Message contains `°C` and `km/h` |
| MF-02 | Imperial weather data input | Message contains `°F` and `mph` |
| MF-03 | Ollama returns valid response | Returns non-empty string |
| MF-04 | Ollama output contains Fun Fact | Message includes `🌟 Fun Fact:` prefix |
| MF-05 | Ollama returns empty/None response | Falls back to static template message |
| MF-06 | Ollama timeout | Falls back to static template message |
| MF-07 | Output exceeds 300 words | Logs warning (not hard fail) |
| MF-08 | Prompt injection in weather data | Input sanitised before prompt |
| MF-09 | `name` passed to `generate()` | Greeting in message uses recipient's name |
| MF-10 | Activity = `runner` | Prompt contains runner-specific hint |
| MF-11 | Activity = `cyclist` | Prompt contains cyclist-specific hint |
| MF-12 | Activity = `farmer` | Prompt contains farmer-specific hint |
| MF-13 | Activity = `photographer` | Prompt contains photographer-specific hint |
| MF-14 | Activity = `parent` | Prompt contains parent-specific hint |
| MF-15 | Activity = `general` | No `Activity context:` added to prompt |

### 3.6 Broadcaster (`test_broadcaster.py`)

| Test ID | Description | Expected Outcome |
|---------|-------------|-----------------|
| BC-01 | Send to valid E.164 number | Twilio called with correct params |
| BC-02 | Twilio returns 201 Created | Returns success status |
| BC-03 | Twilio returns 429 rate limit | Retries with backoff ×3 |
| BC-04 | Twilio returns 401 auth error | Raises `BroadcasterAuthError` |
| BC-05 | Network unreachable | Raises `BroadcasterError` after retries |
| BC-06 | Invalid phone format | Raises `ValueError` before API call |
| BC-07 | Rate delay between sends | 0.5 s sleep called between messages |

### 3.7 Scheduler (`test_scheduler.py`)

| Test ID | Description | Expected Outcome |
|---------|-------------|-----------------|
| SC-01 | 3 users in 3 different timezones | 3 separate cron jobs created |
| SC-02 | 5 users all in same timezone | 1 shared cron job created |
| SC-03 | New user added after start | New job registered dynamically |
| SC-04 | Job fires at correct UTC equivalent | UTC time matches 06:30 local |
| SC-05 | User deactivated mid-run | Skipped gracefully in job execution |
| SC-06 | Weather fetch fails once, recovers on retry | Message sent; fetch called twice |
| SC-07 | Weather fetch fails all retries | No message sent; logged as failed |

### 3.8 Risk Engine (`test_risk_engine.py`)

| Test ID | Description | Expected Outcome |
|---------|-------------|-----------------|
| RE-01 | temp_max = 35.1°C | Extreme heat alert returned |
| RE-02 | temp_max = 35.0°C | No extreme heat alert |
| RE-03 | temp_min = −10.1°C | Cold alert returned |
| RE-04 | temp_min = −10.0°C | No cold alert |
| RE-05 | wind_speed = 60.1 km/h | Wind alert returned |
| RE-06 | wind_speed = 60.0 km/h | No wind alert |
| RE-07 | condition = "Thunderstorm" | Thunderstorm alert returned |
| RE-08 | condition = "Moderate rain" | No thunderstorm alert |
| RE-09 | humidity = 91, condition = "Foggy" | Fog alert returned |
| RE-10 | humidity = 90, condition = "Foggy" | No fog alert |
| RE-11 | temp_max = 30.1°C, humidity = 71 | Heat index alert returned |
| RE-12 | temp_max = 30.0°C, humidity = 75 | No heat index alert |
| RE-13 | Normal conditions | Returns empty list |
| RE-14 | Thunderstorm + wind > 60 km/h | Both alerts returned |
| RE-15 | Imperial thresholds (95°F, 14°F, 37.3 mph, 86°F) | Correct imperial boundaries |

### 3.9 Conversation Handler (`test_handler.py`)

| Test ID | Description | Expected Outcome |
|---------|-------------|-----------------|
| CH-01 | Unknown phone number | Friendly "not registered" message |
| CH-02 | Intent = WEATHER_QUERY | Fetches forecast, returns weather info |
| CH-03 | Intent = ACTIVITY_UPDATE | Saves activity to DB, returns confirmation |
| CH-04 | Intent = WEATHER_NOW | Returns current conditions immediately |
| CH-05 | Intent = UNSUBSCRIBE | Deactivates user in DB, returns confirmation |
| CH-06 | Intent = GENERAL | Returns non-empty Llama response |
| CH-07 | Llama fails on GENERAL intent | Returns static fallback string |
| CH-08 | Every intent | `update_conversation_context` called after reply |

---

## 4. Shared Fixtures (`conftest.py`)

```python
@pytest.fixture
def sample_user():
    return User(
        phone='+12125550100',
        lat=40.7128,
        lon=-74.0060,
        timezone='America/New_York',
        unit_system='imperial',
        name='Test User',
    )

@pytest.fixture
def mock_weather_imperial():
    return {
        'temp_max': 72,
        'temp_min': 55,
        'temp_unit': '°F',
        'condition': 'Partly Cloudy',
        'wind_speed': 10,
        'wind_unit': 'mph',
        'humidity': 65,
        'unit_system': 'imperial',
    }

@pytest.fixture
def mock_weather_metric():
    return {
        'temp_max': 22,
        'temp_min': 13,
        'temp_unit': '°C',
        'condition': 'Partly Cloudy',
        'wind_speed': 16,
        'wind_unit': 'km/h',
        'humidity': 65,
        'unit_system': 'metric',
    }

@pytest.fixture
def test_db(tmp_path):
    db = Database(str(tmp_path / 'test.db'))
    db.init()
    yield db
    db.close()
```

---

## 5. Running Tests

### Full suite
```bash
pytest tests/ -v
```

### Single module
```bash
pytest tests/test_fetcher.py -v
```

### Skip integration tests
```bash
pytest tests/ -v -m 'not integration'
```

### Coverage report
```bash
pytest tests/ --cov=. --cov-report=term-missing
```

---

## 6. Coverage Targets

| Module | Target Coverage | Priority |
|--------|----------------|----------|
| `utils/timezone_resolver.py` | 100% | High |
| `utils/unit_resolver.py` | 100% | High |
| `database/db.py` | 95%+ | High |
| `weather/fetcher.py` | 90%+ | High |
| `messaging/formatter.py` | 85%+ | Medium |
| `messaging/broadcaster.py` | 90%+ | High |
| `scheduler.py` | 80%+ | Medium |
| `conversation/risk_engine.py` | 90%+ | High |
| `conversation/handler.py` | 85%+ | High |