# PyCharm + Claude Code Agent — Setup Instructions

## 1. Install Claude Code

Claude Code is Anthropic's agentic CLI that powers the PyCharm plugin.

```bash
npm install -g @anthropic-ai/claude-code
claude --version    # verify install
```

> Requires Node.js 18+. If you don't have it: https://nodejs.org

---

## 2. Install the PyCharm Plugin

1. Open PyCharm → **Settings** → **Plugins**
2. Search for **Claude Code** in the Marketplace tab
3. Click **Install** → restart PyCharm when prompted

---

## 3. Authenticate

In your terminal (or PyCharm's built-in terminal):

```bash
claude
```

Follow the browser prompt to log in with your Anthropic account.
Your credentials are stored at `~/.claude/` — you only do this once.

---

## 4. Open the Project

```bash
cd weather-broadcast
```

Open this folder in PyCharm as the project root.
Claude Code reads `CLAUDE.md` from the project root automatically
at the start of every session — no manual loading needed.

---

## 5. Set Up the Python Environment

```bash
python3 -m venv venv
source venv/bin/activate          # macOS/Linux
# venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

In PyCharm: **Settings → Python Interpreter → Add → Existing → select venv/bin/python**

---

## 6. Configure Credentials

```bash
cp .env.example .env
```

Edit `.env` with your real values:

| Variable | Where to get it |
|---|---|
| `TWILIO_ACCOUNT_SID` | twilio.com Console → Account Info |
| `TWILIO_AUTH_TOKEN` | twilio.com Console → Account Info |
| `TWILIO_WHATSAPP_FROM` | Messaging → Sandbox → your sandbox number |
| `LLAMA_CLI` | command you use to run llama locally e.g. `llama-cli` |
| `LLAMA_MODEL_PATH` | full path to your `.gguf` model file |
| `DB_PATH` | leave as `./data/weather_broadcast.db` |

---

## 7. Initialise the Database & Seed Test Users

```bash
python3 database/seed.py
```

This creates `data/weather_broadcast.db` and inserts 10 test users
across 10 timezones (New York, London, Tokyo, Sydney, etc.).

---

## 8. Run the Test Suite

```bash
pytest tests/ -v
```

All tests are fully mocked — no network, no Twilio, no Llama needed.
Everything should pass on first run.

---

## 9. Using Claude in PyCharm

### Opening the Claude panel
- **macOS**: `⌘ + Shift + C`
- **Windows/Linux**: `Ctrl + Shift + C`
- Or: **Tools → Claude Code**

### Most useful in-session commands

| Command | What it does |
|---|---|
| `/init` | Regenerates CLAUDE.md from your project structure (don't overwrite ours) |
| `/memory` | Browse and edit Claude's auto-memory for this project |
| `/clear` | Start a fresh context — use this between unrelated tasks |
| `/compact` | Summarise long context when it gets unwieldy |
| `@filename.md` | Reference a specific file inline e.g. `@docs/architecture.docx` |

### How to ask Claude to work on this project effectively

**Be specific about which module:**
> "In `messaging/formatter.py`, update the Llama prompt to also mention UV index in the weather summary."

**Reference the docs when needed:**
> "Based on @docs/architecture.docx, add a retry queue for failed sends that replays at the next scheduler run."

**Run tests after changes:**
> "Make the change then run `pytest tests/test_formatter.py -v` and fix any failures."

**Adding a new user programmatically:**
> "Add a user in Nairobi, Kenya to the seed data with the correct timezone and unit system."

---

## 10. How CLAUDE.md Works

`CLAUDE.md` sits in the project root and is **automatically loaded into
every Claude session** for this project. It tells Claude:

- What the project does and its full module layout
- Exact commands to run tests, seed data, and start the app
- Architecture rules it must not break (e.g. one job per timezone, not per user)
- Code conventions (typed exceptions, logging module, dataclasses)
- Where the detailed docs live

**You never need to re-explain the project structure.** Claude reads
`CLAUDE.md` fresh at the start of every session.

### Updating CLAUDE.md
Edit it whenever something permanent changes — a new module, a renamed
command, a new env variable. Keep it under ~150 lines. Move detailed
reference material to `docs/` and reference it with `@docs/filename`.

### CLAUDE.local.md (optional, personal)
Create `CLAUDE.local.md` in the project root and add it to `.gitignore`
for personal preferences you don't want to share with the team:

```markdown
# CLAUDE.local.md  (gitignored — personal only)
- My llama model is at /Users/me/models/llama-3-8b-q4.gguf
- I prefer shorter responses — skip explanations unless I ask
- Always run tests before declaring a task done
```

---

## 11. Recommended PyCharm Settings

- **Auto-save**: on (Claude Code reads live files)
- **Terminal**: use PyCharm's built-in terminal for Claude commands
- **Git**: commit `CLAUDE.md` — don't commit `.env` or `CLAUDE.local.md`

---

## 12. Typical Daily Workflow

```
1. Open PyCharm → project loads, Claude reads CLAUDE.md automatically
2. Open Claude panel (⌘+Shift+C)
3. Ask Claude to work on a specific task
4. Claude edits files, you review in the diff view
5. Run: pytest tests/ -v   ← always verify tests pass
6. /clear between unrelated tasks to keep context fresh
7. Commit your changes
```

---

## Troubleshooting

**Claude doesn't seem to know the project structure**
→ Check that `CLAUDE.md` exists in the project root (not a subdirectory).
→ Run `/memory` to see what Claude has stored about this project.

**Tests fail after Claude makes a change**
→ Ask: "The tests in `test_formatter.py` are failing. Read the error and fix."

**Llama not responding**
→ Verify `LLAMA_CLI` and `LLAMA_MODEL_PATH` in `.env` match your install.
→ Test manually: `llama-cli -m /path/to/model.gguf -p "Hello"`

**Twilio 401 error**
→ Double-check `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` in `.env`.

**Scheduler fires but no messages sent**
→ Ensure at least one active user exists: `python3 -c "from database.db import Database; db=Database(); db.init(); print(db.get_all_timezones())"`
