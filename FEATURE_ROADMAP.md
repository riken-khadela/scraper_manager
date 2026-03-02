# ScraperHub — Feature Roadmap

> Planned features and improvements. Pick items from here when ready to implement.

---

## 📊 Reports & Metrics Page

### Overview Cards
- [ ] Total runs today / this week / this month
- [ ] Success rate (%)
- [ ] Average run duration
- [ ] Total records scraped (`records_inserted` sum)
- [ ] Currently running count
- [ ] Failed in last 24h
- [ ] Stale scrapers (no run in 24h but has active schedule)

### Charts (Chart.js)
- [ ] **Runs over time** — daily success vs failed (stacked line chart)
- [ ] **Records scraped over time** — bar chart of `records_inserted` per day
- [ ] **Success rate trend** — line chart over last 30 days
- [ ] **Duration trend** — avg run duration per day (spot slowdowns)
- [ ] **Per-group breakdown** — horizontal bar comparing groups by runs/records/failure rate
- [ ] **Account utilization** — active vs idle vs errored (donut chart)
- [ ] **Peak hours heatmap** — which hours/days have the most runs

### Tables
- [ ] Top 5 most failing scrapers
- [ ] Slowest scrapers (by avg duration)
- [ ] Most productive scrapers (by total `records_inserted`)
- [ ] Recent failures — last 10 failed runs with notes/error

### MongoDB Metrics
- [ ] Collection growth (document count over time per collection)
- [ ] Database size per group

### Implementation Notes
- New view `reports()` → `/reports/`
- New template `templates/dashboard/reports.html`
- API endpoint `/api/reports-data/?range=7d` returning aggregated JSON
- Use Chart.js CDN (no build step)
- Django ORM aggregations: `Count`, `Avg`, `Sum`, `TruncDay`

---

## 🔴 High Priority

### 🔔 Alerting / Notifications
- [ ] Email notification on scraper failure
- [ ] Slack/Telegram webhook on failure
- [ ] Alert when scraper is stale (no run in X hours despite active schedule)
- [ ] Alert when success rate drops below configurable threshold

### 🔐 Dashboard Authentication
- [ ] Add `@login_required` to all views (currently open to anyone with the URL)
- [ ] Protect sensitive data: credentials, MongoDB queries, run/stop actions

### 📋 Structured Run Summaries
- [ ] First-class fields for `records_inserted`, `records_updated`, `records_failed`
- [ ] Scraper scripts write a JSON summary file; Celery task reads and stores it
- [ ] Display structured summary on run history detail

### 🔄 Auto-Retry on Failure
- [ ] `max_retries` field on SubScraper (default 0 = no retry)
- [ ] `retry_delay` field (seconds, with exponential backoff)
- [ ] Celery task retries automatically on non-zero exit code

### 📦 Scraper Dependencies / Ordering
- [ ] `depends_on` ForeignKey on SubScraper (nullable)
- [ ] When a scraper completes, auto-trigger its dependents
- [ ] Use case: URL collector → detail scraper chain

---

## 🟡 Medium Priority

### 📊 Per-Account Metrics
- [ ] Track records scraped per account
- [ ] Track last success/failure per account
- [ ] Auto-detect rate-limited or banned accounts (consecutive failures)
- [ ] Account health score

### 🏷️ Environment / Profile Support
- [ ] Run scrapers in dev/staging/prod modes with different configs
- [ ] Environment selector on Control Panel
- [ ] Separate MongoDB databases per environment

### 🗑️ Data Cleanup / Archival
- [ ] Auto-archive `ScraperRunHistory` older than N days
- [ ] Purge old live log files from `/tmp/scraper_live_*.log`
- [ ] Configurable retention period per scraper group
- [ ] Management command: `python manage.py cleanup_history --days 90`

### 📝 Scraper Templates
- [ ] Pre-built templates for common patterns (login → paginate → save)
- [ ] Template selector when creating a new sub-scraper
- [ ] Auto-generate boilerplate script from template

### 🌐 Proxy Management
- [ ] `Proxy` model: address, port, auth, is_active, last_checked, success_rate
- [ ] Central proxy pool — scrapers pull from pool instead of hardcoding
- [ ] Auto health-check proxies periodically
- [ ] Proxy rotation strategy (round-robin, least-used, random)

---

## 🟢 Nice to Have

### 🔍 Global Search
- [ ] Search across scrapers, accounts, run history, logs
- [ ] Keyboard shortcut (Ctrl+K) to open search

### 📱 Responsive Design
- [ ] Mobile-friendly dashboard layout
- [ ] Collapsible sidebar on small screens

### 🌙 Dark Mode
- [ ] CSS variable-based theming
- [ ] Toggle in navbar, persisted in localStorage

### 📤 Export
- [ ] Download run history as CSV
- [ ] Export scraper configs as JSON
- [ ] Export reports as PDF

### 🔌 Webhook Integration
- [ ] Configurable webhooks per scraper group
- [ ] Trigger on: run_complete, run_failed, records_threshold
- [ ] JSON payload with run details

### 👥 Multi-User & Roles
- [ ] Role-based access: viewer (read-only), operator (run/stop), admin (full)
- [ ] Per-group permissions
- [ ] Audit log of who ran/stopped what

### 📈 Uptime / SLA Dashboard
- [ ] Scraper availability percentage (scheduled vs actually ran)
- [ ] SLA targets per scraper group
- [ ] Monthly SLA report

---

*Pick any section and we'll implement it together. Start with the Reports page for the biggest impact.*
