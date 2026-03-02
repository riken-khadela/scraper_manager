# ScraperHub — Project Overview & Documentation

> A Django-based management dashboard for orchestrating, scheduling, monitoring, and controlling web scrapers with Celery task execution, live terminal streaming, and MongoDB integration.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [How to Run](#how-to-run)
- [Features](#features)
- [Data Models](#data-models)
- [How to Add a Scraper Group (MainScraper)](#how-to-add-a-scraper-group-mainscraper)
- [How to Update a Scraper Group](#how-to-update-a-scraper-group)
- [How to Add a Sub-Scraper](#how-to-add-a-sub-scraper)
- [How to Manage Sub-Scrapers](#how-to-manage-sub-scrapers)
- [Scheduling](#scheduling)
- [Account Management](#account-management)
- [Control Panel & Config](#control-panel--config)
- [Live Terminal](#live-terminal)
- [MongoDB Panel](#mongodb-panel)
- [Log Viewer](#log-viewer)
- [Watcher Panel](#watcher-panel)
- [API Endpoints](#api-endpoints)
- [Seed Scripts](#seed-scripts)
- [Crunchbase Scraper (Bundled Example)](#crunchbase-scraper-bundled-example)
- [Environment Variables](#environment-variables)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                   Browser (Dashboard UI)                 │
│  Dashboard · Watcher · Log Viewer · Live Terminal · Mongo│
└───────────────────────┬──────────────────────────────────┘
                        │ HTTP / JSON API
┌───────────────────────▼──────────────────────────────────┐
│               Django Application (port 1109)             │
│   views.py · api_views.py · models.py · admin.py         │
└───────┬───────────────────────────────────────┬──────────┘
        │ Celery task dispatch                  │ PyMongo
┌───────▼───────────┐                  ┌────────▼─────────┐
│  Celery Worker    │                  │     MongoDB      │
│  (Redis broker)   │                  │  (per-group DB)  │
│  PTY-based exec   │                  └──────────────────┘
│  Live log stream  │
└───────┬───────────┘
        │ subprocess (PTY)
┌───────▼───────────┐
│  Scraper Scripts  │
│  (Python scripts) │
└───────────────────┘
```

**Key flow:** Dashboard UI → Django view → Celery task → PTY subprocess → scraper script. Output streams back to a temp log file that the browser polls via API.

---

## Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Web framework | Django | 5.2.11 |
| Template engine | Jinja2 (via django-jinja) | 2.11.0 |
| Task queue | Celery | 5.6.2 |
| Message broker | Redis | 7.2.0 |
| Scheduler | django-celery-beat | 2.8.1 |
| Database (app) | SQLite3 | — |
| Database (scraped data) | MongoDB (PyMongo) | 4.16.0 |
| Cron parsing | croniter + cron-descriptor | 6.0.0 / 2.0.6 |

---

## Project Structure

```
scraper_manager/                  ← Project root
├── manage.py                     ← Django management CLI
├── start.sh                      ← Full setup & start script (all services)
├── requirements.txt              ← Python dependencies
├── .env                          ← Environment variables
├── db.sqlite3                    ← SQLite database (Django models)
├── seed_demo.py                  ← Seeds demo data (News, Finance, E-Commerce)
├── seed_crunchbase.py            ← Seeds real Crunchbase scraper + accounts
│
├── scraper_manager/              ← Django project package
│   ├── settings.py               ← Django settings (reads .env, Celery, Mongo config)
│   ├── urls.py                   ← URL routing (30+ routes)
│   ├── celery.py                 ← Celery app configuration
│   ├── wsgi.py / asgi.py         ← WSGI/ASGI entry points
│
├── dashboard/                    ← Main Django app
│   ├── models.py                 ← 7 models (MainScraper, SubScraper, Schedule, etc.)
│   ├── views.py                  ← 20+ views (CRUD, run/stop, schedule, mongo, etc.)
│   ├── api_views.py              ← 5 JSON API endpoints (logs, status, watcher, terminal)
│   ├── tasks.py                  ← Celery task: PTY-based script execution with live log
│   ├── schedule_utils.py         ← Cron helpers, Celery Beat schedule management
│   ├── admin.py                  ← Django admin registration for all models
│   ├── migrations/               ← Database migration files
│
├── crunchbase/                   ← Bundled Crunchbase scraper
│   ├── main.py                   ← Thread manager (distributes accounts to scrapers)
│   ├── new_scrapper.py           ← Scrapes NEW organizations from Crunchbase
│   ├── update_scrapper.py        ← Updates EXISTING organization data
│
├── templates/                    ← Jinja2 HTML templates
│   ├── base.html                 ← Base layout (sidebar, nav, CSS/JS)
│   └── dashboard/                ← 16 page templates
│       ├── dashboard.html        ← Home: all scraper groups as cards
│       ├── scrapers_list.html    ← Table listing of all groups
│       ├── main_scraper_form.html← Create/edit scraper group
│       ├── main_scraper_detail.html ← Group detail: lists sub-scrapers
│       ├── sub_scraper_detail.html  ← Sub-scraper detail + actions
│       ├── sub_scraper_form.html    ← Create/edit sub-scraper
│       ├── log_viewer.html       ← Browse & tail log files
│       ├── live_terminal.html    ← Real-time terminal output + stdin input
│       ├── schedule_management.html ← Cron schedule editor (simple + advanced)
│       ├── run_history.html      ← Paginated run history with stats
│       ├── mongo_panel.html      ← MongoDB query explorer
│       ├── account_management.html  ← Account list, add, toggle, delete
│       ├── account_edit.html     ← Edit single account
│       ├── control_panel.html    ← Config-driven launch with account splits
│       ├── watcher.html          ← Global process watcher
│       └── _watcher_table.html   ← Partial: watcher table rows
│
├── static/
│   ├── css/main.css              ← Global styles
│   └── js/main.js                ← Client-side JavaScript
│
└── logs/                         ← Runtime logs (Django, Celery worker, Celery beat)
```

---

## How to Run

### One-command startup (recommended)

```bash
bash start.sh
```

`start.sh` performs **all** setup automatically:
1. Checks system dependencies (Python 3.10+, Redis)
2. Creates/activates virtual environment (`env/`)
3. Installs Python dependencies from `requirements.txt`
4. Creates `.env` with defaults if missing
5. Runs Django migrations
6. Collects static files
7. Creates admin superuser (default: `admin` / `admin123`)
8. Frees port 8000/1109, starts Django, Celery worker (4 threads), Celery Beat
9. Tails Django logs to the terminal

### Manual startup

```bash
# 1. Activate venv
source env/bin/activate

# 2. Install deps
pip install -r requirements.txt

# 3. Run migrations
python manage.py migrate

# 4. Collect static
python manage.py collectstatic --noinput

# 5. Start Django
python manage.py runserver 0.0.0.0:1109

# 6. Start Celery worker (separate terminal)
celery -A scraper_manager worker --loglevel=info --concurrency=4

# 7. Start Celery Beat (separate terminal)
celery -A scraper_manager beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

### Access points

| Page | URL |
|------|-----|
| Dashboard | `http://localhost:1109/` |
| Watcher | `http://localhost:1109/watcher/` |
| Admin | `http://localhost:1109/admin/` |

---

## Features

### 1. Scraper Group Management (MainScraper)
- Create, edit, delete scraper groups
- Each group can have its own MongoDB URI and database
- Tags for categorization
- Health status indicator (green/yellow/red/gray)

### 2. Sub-Scraper Management
- Multiple sub-scrapers per group
- Each sub-scraper has: script path, run command, log folder, MongoDB collection
- Active/inactive toggle

### 3. One-Click Run / Stop
- Manual run via dashboard button (fires Celery task)
- Stop running scrapers (kills process group via SIGTERM)

### 4. Live Terminal
- Real-time stdout/stderr streaming in the browser
- **Interactive stdin** — send input to running scripts (supports `input()`, pdb, etc.)
- PTY-based execution (pseudo-terminal)
- ANSI escape sequence stripping

### 5. Cron Scheduling
- Per-sub-scraper cron schedules
- Simple mode (pick times from dropdowns) or advanced mode (raw cron expression)
- Validation via `croniter`
- Human-readable cron descriptions via `cron-descriptor`
- Manages `django-celery-beat` PeriodicTask objects

### 6. Run History
- Tracks every run: trigger type (manual/scheduled), status, duration, records inserted
- Paginated history view
- Stats: success rate, average duration, last success

### 7. MongoDB Panel
- View document count, collection stats (size, avgObjSize)
- Query explorer: custom filter, sort, limit
- Last inserted document timestamp
- Per-group MongoDB connection (falls back to global)

### 8. Log Viewer
- Browse `.log` and `.txt` files from the configured log folder
- Tail last N lines via AJAX API

### 9. Account Management
- Store login credentials for scrapers that need multi-account support
- Add, edit, delete, toggle active/inactive
- Bulk toggle all accounts
- Account status tracking (idle, running_update, running_new, error)

### 10. Control Panel
- Configure account distribution (update vs. new scraper ratio)
- Batch size and max batch settings
- Script/log base paths
- Launch scrapers with dynamically generated JSON config files

### 11. Watcher Panel
- Global view of all active sub-scrapers
- Real-time status (running/success/failed/never_run)
- PID display, next scheduled run
- Auto-refreshing via AJAX

---

## Data Models

| Model | Purpose |
|-------|---------|
| **MainScraper** | Scraper group with name, description, tags, and per-group MongoDB connection |
| **SubScraper** | Individual scraper under a group; stores script path, run command, log path, collection name |
| **ScraperSchedule** | One-to-one with SubScraper; stores cron string + enabled flag + Celery task ID |
| **ScraperRunHistory** | Each run record: trigger type, status, duration, records inserted, notes |
| **ScraperProcess** | One-to-one with SubScraper; tracks PID, running state, Celery task ID |
| **ScraperAccount** | Login credentials per MainScraper; email, password, active flag, status |
| **ScraperConfig** | One-to-one with MainScraper; account distribution ratios, batch sizes, paths |

---

## How to Add a Scraper Group (MainScraper)

### Via the Dashboard UI
1. Go to the **Dashboard** (`/`)
2. Click **"+ New Scraper"** button
3. Fill in:
   - **Name** — e.g. "LinkedIn Scrapers"
   - **Description** — what this group of scrapers does
   - **Tags** — comma-separated, e.g. "linkedin,profiles,social"
   - **MongoDB URI** — leave blank to use the global default from `.env`
   - **MongoDB Database** — leave blank for the global default
4. Click **Save**

### Via Django Admin
1. Go to `/admin/` → **Main scrapers** → **Add**
2. Fill in the fields and save

### Via Seed Script
```python
from dashboard.models import MainScraper

MainScraper.objects.create(
    name='My Scraper Group',
    description='Scrapes data from example.com',
    tags='example,demo',
    mongo_uri='mongodb://localhost:27017/',     # optional
    mongo_db_name='example_db',                # optional
)
```

---

## How to Update a Scraper Group

### Via the Dashboard UI
1. Go to `Dashboard → click scraper card → Edit` button
2. Update any fields (name, description, tags, MongoDB URI/DB)
3. Click **Save**

### Via Django Admin
1. Go to `/admin/` → **Main scrapers** → click the scraper → edit → save

---

## How to Add a Sub-Scraper

1. Navigate to the **Main Scraper detail page** (`/scrapers/<id>/`)
2. Click **"+ Add Sub Scraper"**
3. Fill in:
   - **Name** — e.g. "Profile Scraper"
   - **Description** — what this specific scraper does
   - **Script Path** — full server path to the Python script (validated on save)
   - **Run Command** — the exact shell command, e.g. `python /home/scrapers/profile.py`
   - **Log Folder Path** — folder where `.log` files are written
   - **MongoDB Collection** — collection name inside the parent's database
   - **Active** — toggle on/off
4. Click **Save**

---

## How to Manage Sub-Scrapers

From the **sub-scraper detail page** (`/scrapers/<id>/sub/<sub_id>/`), you can:

| Action | How |
|--------|-----|
| **Run** | Click the "Run" button (POST to `/scrapers/<id>/sub/<sub_id>/run/`) |
| **Stop** | Click the "Stop" button (kills process via SIGTERM) |
| **Edit** | Click "Edit" to update script path, run command, log path, collection |
| **View Logs** | Click "Logs" to browse and tail log files |
| **Live Terminal** | Click "Terminal" for real-time output and interactive stdin |
| **Schedule** | Click "Schedule" to set a cron schedule (simple or advanced mode) |
| **History** | Click "History" to view all past runs with stats |
| **MongoDB** | Click "MongoDB" to query the scraper's collection |

---

## Scheduling

Each sub-scraper can have a **cron schedule**:

### Simple mode
Pick specific run times from a time picker; the system builds the cron expression automatically.

### Advanced mode
Enter a raw cron expression (5-field format): `minute hour day_of_month month day_of_week`

**Examples:**
- `0 6,14,22 * * *` — run at 06:00, 14:00, 22:00 daily
- `*/30 * * * *` — every 30 minutes
- `0 0 * * 1` — midnight every Monday

Schedules are synced to `django-celery-beat` PeriodicTask objects, which Celery Beat picks up automatically.

---

## Account Management

For scrapers that require login (e.g. Crunchbase), the system supports multi-account management:

1. Navigate to **Accounts** (`/scrapers/<id>/accounts/`)
2. **Add account** — enter email + password
3. **Toggle** — activate/deactivate individual accounts
4. **Bulk toggle** — activate or deactivate all accounts at once
5. **Edit** — change email, password, or notes
6. **Delete** — remove an account

Account status tracking: `idle`, `running_update`, `running_new`, `error`.

---

## Control Panel & Config

The **Control Panel** (`/scrapers/<id>/control-panel/`) provides:

| Setting | Description |
|---------|-------------|
| `update_account_count` | Fixed accounts for update scraper (0 = auto) |
| `new_account_count` | Fixed accounts for new scraper (0 = auto) |
| `update_ratio` | Auto-mode ratio (default 0.8 = 80% update, 20% new) |
| `batch_size_new` | Batch size for new scraper (default 10) |
| `batch_size_update` | Batch size for update scraper (default 10) |
| `max_batches_new` | Max batches for new scraper (default 10) |
| `max_batches_update` | Max batches for update scraper (default 50) |
| `script_base_path` | Base path to scraper scripts |
| `log_base_path` | Base path for log output |

**Run modes:** `all` (both update + new), `new_only`, `update_only`

When launched from the Control Panel, the system:
1. Builds a JSON config file with all settings + active accounts
2. Writes it to `/tmp/scraper_configs/`
3. Constructs the run command: `python main.py --config-file <path> --mode <mode>`
4. Fires the Celery task

---

## Live Terminal

The live terminal (`/scrapers/<id>/sub/<sub_id>/terminal/`) provides:

- **Real-time output streaming** — polls `/api/live-log/<sub_id>/` every second
- **Interactive input** — sends text via `/api/send-input/<sub_id>/`
- **PTY-based execution** — the Celery task runs the script under a pseudo-terminal, enabling `input()`, pdb, and other interactive features
- **ANSI stripping** — escape sequences are cleaned from the output

---

## MongoDB Panel

The MongoDB panel (`/scrapers/<id>/sub/<sub_id>/mongo/`) shows:

- **Connection info** — which URI and database is in use
- **Document count** — total documents in the collection
- **Collection stats** — size, average object size
- **Last 5 documents** — sorted by `_id` descending
- **Last inserted timestamp** — extracted from the latest ObjectId
- **Query explorer** — enter custom filter JSON, sort JSON, and limit

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/logs/?file_path=...&num_lines=100` | Tail a log file |
| GET | `/api/status/<sub_id>/` | Get sub-scraper status (running, pid, has live log) |
| GET | `/api/live-log/<sub_id>/?offset=N` | Get new live log lines since offset |
| POST | `/api/send-input/<sub_id>/` | Send stdin input to running scraper (JSON body: `{"input": "text"}`) |
| GET | `/api/watcher-data/` | Get status of all active scrapers (JSON) |

---

## Seed Scripts

### `seed_demo.py` — Demo data
Creates 3 demo scraper groups (News, Finance, E-Commerce) with sub-scrapers, schedules, and sample run history. Useful for testing the dashboard.

```bash
python seed_demo.py
```

### `seed_crunchbase.py` — Real Crunchbase scraper
Seeds the Crunchbase MainScraper with 3 sub-scrapers (Main Runner, New Scrapper, Update Scrapper), 25 accounts, config, and schedules.

```bash
python seed_crunchbase.py
```

---

## Crunchbase Scraper (Bundled Example)

Located in `crunchbase/`, this is a real-world scraper bundled with the project:

| File | Purpose |
|------|---------|
| `main.py` | **Thread manager** — distributes active accounts between update and new scrapers, supports alternating mode (1 account) and parallel mode (2+ accounts) |
| `new_scrapper.py` | Scrapes **new** organizations from Crunchbase. Fetches URLs with priority system (pending → old unread → any unread), scrapes summary/financial/news pages, saves to MongoDB |
| `update_scrapper.py` | **Updates** existing organizations. Priority system: blank descriptions → obfuscated funding → recently founded companies (2020-2025) → stale data → flagged URLs |

**Execution flow:**
1. `main.py` loads accounts (from config file or defaults)
2. Calculates thread distribution (update vs. new)
3. Spawns subprocess threads running `new_scrapper.py` or `update_scrapper.py`
4. Each subprocess logs in to Crunchbase, fetches batches, scrapes pages, and upserts into MongoDB

**CLI usage:**
```bash
# Automatic distribution
python crunchbase/main.py

# Manual split
python crunchbase/main.py --update 5 --new 3

# With config file from Control Panel
python crunchbase/main.py --config-file /tmp/scraper_configs/config_1_1.json --mode all
```

---

## Environment Variables

Configured in `.env` at the project root:

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `django-insecure-...` | Django secret key |
| `DEBUG` | `True` | Debug mode |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hosts |
| `REDIS_URL` | `redis://localhost:6380/0` | Redis URL for Celery broker |
| `MONGO_URI` | `mongodb://localhost:27017/` | Default MongoDB connection URI |
| `MONGO_DEFAULT_DB` | `scrapers_db` | Default MongoDB database name |

---

*This document was generated by analyzing every source file in the ScraperHub workspace. Last updated: 2026-02-28.*
