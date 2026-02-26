#!/bin/bash
# ============================================================
#  ScraperHub — Full Setup & Start Script
#  Handles first-time setup AND regular restarts automatically
# ============================================================

set -e

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$BASE_DIR/env"
PYTHON="$BASE_DIR/env/bin/python"
PIP="$BASE_DIR/env/bin/pip"
CELERY="$BASE_DIR/env/bin/celery"

# ---- Colours ------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*"; exit 1; }
header()  { echo -e "\n${BOLD}${CYAN}==> $*${RESET}"; }

# ---- Source .env -------------------------------------------
if [ -f "$BASE_DIR/.env" ]; then
    # Export every non-comment, non-blank KEY=VALUE line
    set -a
    # shellcheck disable=SC1090
    source <(grep -v '^\s*#' "$BASE_DIR/.env" | grep -v '^\s*$')
    set +a
    success ".env loaded from $BASE_DIR/.env"
else
    warn ".env not found — will create one with defaults shortly"
fi

# ---- Banner -------------------------------------------------
echo -e "${BOLD}${CYAN}"
cat << 'EOF'
  ____                                 _   _       _
 / ___|  ___ _ __ __ _ _ __   ___ _ __| | | |_   _| |__
 \___ \ / __| '__/ _` | '_ \ / _ \ '__| |_| | | | | '_ \
  ___) | (__| | | (_| | |_) |  __/ |  |  _  | |_| | |_) |
 |____/ \___|_|  \__,_| .__/ \___|_|  |_| |_|\__,_|_.__/
                       |_|   Scraper Management Dashboard
EOF
echo -e "${RESET}"

# ============================================================
#  STEP 1 — Check system dependencies
# ============================================================
header "Checking system requirements"

command -v python3 &>/dev/null || error "python3 not found. Install Python 3.10+ first."
success "python3 found → $(python3 --version)"

command -v redis-cli &>/dev/null || error "Redis not found. Install Redis (e.g. sudo apt install redis-server)."

if redis-cli ping &>/dev/null; then
    success "Redis is running"
else
    warn "Redis is not running — attempting to start..."
    if command -v redis-server &>/dev/null; then
        redis-server --daemonize yes --logfile /tmp/scraperhub-redis.log
        sleep 1
        redis-cli ping &>/dev/null && success "Redis started" || error "Could not start Redis. Run: redis-server"
    else
        error "Redis server not installed. Run: sudo apt install redis-server"
    fi
fi

# ============================================================
#  STEP 2 — Virtual environment
# ============================================================
header "Setting up Python virtual environment"

if [ ! -d "$VENV" ]; then
    info "Creating virtual environment at $VENV ..."
    python3 -m venv "$VENV"
    success "Virtual environment created"
else
    success "Virtual environment already exists"
fi

source "$VENV/bin/activate"

# ============================================================
#  STEP 3 — Install / upgrade dependencies
# ============================================================
header "Installing Python dependencies"

if [ -f "$BASE_DIR/requirements.txt" ]; then
    info "Installing from requirements.txt ..."
    "$PIP" install -q --upgrade pip
    "$PIP" install -q -r "$BASE_DIR/requirements.txt"
    success "All dependencies installed"
else
    error "requirements.txt not found in $BASE_DIR"
fi

# ============================================================
#  STEP 4 — Environment file
# ============================================================
header "Checking .env configuration"

if [ ! -f "$BASE_DIR/.env" ]; then
    warn ".env file not found — creating with safe defaults"
    cat > "$BASE_DIR/.env" << 'ENVEOF'
SECRET_KEY=django-insecure-change-this-to-a-long-random-string-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
REDIS_URL=redis://localhost:6379/0
MONGO_URI=mongodb://localhost:27017/
MONGO_DEFAULT_DB=scrapers_db
ENVEOF
    success ".env created with defaults"
else
    success ".env file exists"
fi

# ============================================================
#  STEP 5 — Database migrations
# ============================================================
header "Running database migrations"

cd "$BASE_DIR"
"$PYTHON" manage.py migrate --run-syncdb 2>&1 | grep -E '(Applying|OK|No migrations|Running)' | sed "s/^/  /"
success "Database is up to date"

# ============================================================
#  STEP 6 — Collect static files
# ============================================================
header "Collecting static files"

"$PYTHON" manage.py collectstatic --noinput -v 0 2>&1 | tail -1 | sed "s/^/  /"
success "Static files ready"

# ============================================================
#  STEP 7 — Create superuser (first-run only)
# ============================================================
header "Admin user setup"

# Read from .env (already sourced above) with env-var overrides as final fallback
ADMIN_USER="${SCRAPERHUB_ADMIN_USER:-${ADMIN_USER:-admin}}"
ADMIN_PASS="${SCRAPERHUB_ADMIN_PASS:-${ADMIN_PASS:-admin123}}"
ADMIN_EMAIL="${SCRAPERHUB_ADMIN_EMAIL:-${ADMIN_EMAIL:-admin@scraperhub.local}}"

ADMIN_EXISTS=$("$PYTHON" -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','scraper_manager.settings')
django.setup()
from django.contrib.auth import get_user_model
U = get_user_model()
print('yes' if U.objects.filter(username='$ADMIN_USER').exists() else 'no')
" 2>/dev/null)

if [ "$ADMIN_EXISTS" = "no" ]; then
    "$PYTHON" -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','scraper_manager.settings')
django.setup()
from django.contrib.auth import get_user_model
U = get_user_model()
U.objects.create_superuser('$ADMIN_USER', '$ADMIN_EMAIL', '$ADMIN_PASS')
print('Superuser created')
" 2>/dev/null
    success "Admin user created  →  username: $ADMIN_USER  |  password: $ADMIN_PASS"
    warn "Change the admin password after first login!"
else
    success "Admin user '$ADMIN_USER' already exists — skipping creation"
fi

# ============================================================
#  STEP 8 — Kill any stale processes on our ports
# ============================================================
header "Freeing ports"

for PORT in 8000; do
    PID_ON_PORT=$(lsof -ti tcp:$PORT 2>/dev/null || true)
    if [ -n "$PID_ON_PORT" ]; then
        warn "Port $PORT in use by PID $PID_ON_PORT — killing..."
        kill -9 $PID_ON_PORT 2>/dev/null || true
        sleep 1
    fi
done
success "Port 8000 is free"

# ============================================================
#  STEP 9 — Launch all services
# ============================================================
header "Starting services"

LOG_DIR="$BASE_DIR/logs"
mkdir -p "$LOG_DIR"

# Django dev server
info "Starting Django development server..."
"$PYTHON" "$BASE_DIR/manage.py" runserver 0.0.0.0:1109 \
    > "$LOG_DIR/django.log" 2>&1 &
DJANGO_PID=$!
success "Django server    →  PID $DJANGO_PID  |  log: logs/django.log"

# Give Django a moment to start
sleep 1

# Celery worker
info "Starting Celery worker (concurrency=4)..."
"$CELERY" -A scraper_manager worker \
    --loglevel=info \
    --concurrency=4 \
    --logfile="$LOG_DIR/celery_worker.log" \
    --pidfile="$LOG_DIR/celery_worker.pid" \
    -n worker@%h \
    > /dev/null 2>&1 &
WORKER_PID=$!
success "Celery worker    →  PID $WORKER_PID  |  log: logs/celery_worker.log"

# Celery Beat scheduler
info "Starting Celery Beat scheduler..."
"$CELERY" -A scraper_manager beat \
    --loglevel=info \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler \
    --logfile="$LOG_DIR/celery_beat.log" \
    --pidfile="$LOG_DIR/celery_beat.pid" \
    > /dev/null 2>&1 &
BEAT_PID=$!
success "Celery Beat      →  PID $BEAT_PID  |  log: logs/celery_beat.log"

# ============================================================
#  Done — Print access info
# ============================================================
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${GREEN}║          ScraperHub is live!                        ║${RESET}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  ${BOLD}Dashboard:${RESET}   http://localhost:8000/"
echo -e "  ${BOLD}Watcher:${RESET}     http://localhost:8000/watcher/"
echo -e "  ${BOLD}Admin:${RESET}       http://localhost:8000/admin/"
echo -e "             username: ${YELLOW}$ADMIN_USER${RESET}  |  password: ${YELLOW}$ADMIN_PASS${RESET}"
echo ""
echo -e "  ${BOLD}Logs:${RESET}        $LOG_DIR/"
echo -e "  ${BOLD}Stop:${RESET}        Press ${BOLD}Ctrl+C${RESET}"
echo ""

# ============================================================
#  Wait & cleanup on Ctrl+C
# ============================================================
cleanup() {
    echo ""
    header "Shutting down ScraperHub..."
    kill $DJANGO_PID $WORKER_PID $BEAT_PID 2>/dev/null || true

    # Clean up pidfiles
    rm -f "$LOG_DIR/celery_worker.pid" "$LOG_DIR/celery_beat.pid"

    success "All services stopped. Goodbye!"
    exit 0
}

trap cleanup INT TERM

# Tail logs so the terminal isn't silent
tail -f "$LOG_DIR/django.log" &
TAIL_PID=$!

wait $DJANGO_PID 2>/dev/null
cleanup
