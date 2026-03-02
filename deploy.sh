#!/bin/bash
set -e

echo "🚀 Deploying scraper_manager..."

cd /home/riken/workspace/scraper_manager

# Pull latest code
git pull origin main

# Activate venv
source env/bin/activate

# Install new dependencies
pip install -r requirements.txt --quiet

# Django commands
python manage.py migrate --noinput
python manage.py collectstatic --noinput

# Restart the running process
pkill -f "manage.py runserver" 2>/dev/null || true
pkill -f "celery" 2>/dev/null || true

sleep 2

# Restart via start.sh in background
nohup bash start.sh > logs/startup.log 2>&1 &

echo "✅ Deployment complete!"
