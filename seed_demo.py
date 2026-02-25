"""
Seed demo data for ScraperHub.
Run with: python manage.py shell < seed_demo.py
or: python seed_demo.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scraper_manager.settings')
django.setup()

from django.utils import timezone
from datetime import timedelta
from dashboard.models import MainScraper, SubScraper, ScraperSchedule, ScraperRunHistory

print("Seeding demo data...")

# Create main scrapers
news = MainScraper.objects.get_or_create(
    name='News Scrapers',
    defaults={'description': 'Scrapers for major news websites', 'tags': 'news,daily,media'}
)[0]

finance = MainScraper.objects.get_or_create(
    name='Finance Data',
    defaults={'description': 'Financial data and stock market scrapers', 'tags': 'finance,stocks,market'}
)[0]

ecommerce = MainScraper.objects.get_or_create(
    name='E-Commerce Monitor',
    defaults={'description': 'Product price & availability tracking', 'tags': 'ecommerce,prices,products'}
)[0]

# Sub scrapers under News
bbc, _ = SubScraper.objects.get_or_create(
    main_scraper=news, name='BBC News',
    defaults={
        'description': 'Scrapes BBC News homepage and top stories',
        'script_path': '/home/scrapers/news/bbc/run.py',
        'run_command': 'python /home/scrapers/news/bbc/run.py',
        'log_folder_path': '/tmp/demo_logs',
        'mongo_collection_name': 'bbc_articles',
        'mongo_db_name': 'news_db',
        'is_active': True,
    }
)

techcrunch, _ = SubScraper.objects.get_or_create(
    main_scraper=news, name='TechCrunch',
    defaults={
        'description': 'Tech news from TechCrunch',
        'script_path': '/home/scrapers/news/tc/run.py',
        'run_command': 'python /home/scrapers/news/tc/run.py --mode full',
        'log_folder_path': '/tmp/demo_logs',
        'mongo_collection_name': 'techcrunch_articles',
        'mongo_db_name': 'news_db',
        'is_active': True,
    }
)

# Sub scrapers under Finance
yahoo, _ = SubScraper.objects.get_or_create(
    main_scraper=finance, name='Yahoo Finance',
    defaults={
        'description': 'Stock prices and financial news from Yahoo Finance',
        'script_path': '/home/scrapers/finance/yahoo/run.py',
        'run_command': 'python /home/scrapers/finance/yahoo/run.py',
        'log_folder_path': '/tmp/demo_logs',
        'mongo_collection_name': 'yahoo_finance',
        'mongo_db_name': 'finance_db',
        'is_active': True,
    }
)

# Create schedules
for sub in [bbc, techcrunch, yahoo]:
    ScraperSchedule.objects.get_or_create(
        sub_scraper=sub,
        defaults={'cron_string': '0 6,14,22 * * *', 'is_enabled': True}
    )

# Create run history
now = timezone.now()
history_data = [
    (bbc, 'success', 45.2, now - timedelta(hours=2), 1250),
    (bbc, 'success', 38.1, now - timedelta(hours=8), 876),
    (bbc, 'failed', 12.0, now - timedelta(days=1), None),
    (techcrunch, 'success', 67.8, now - timedelta(hours=3), 342),
    (techcrunch, 'success', 72.1, now - timedelta(hours=9), 301),
    (yahoo, 'success', 120.5, now - timedelta(hours=1), 5000),
    (yahoo, 'failed', 5.0, now - timedelta(days=2), None),
]

for sub, status, duration, started, records in history_data:
    if not ScraperRunHistory.objects.filter(sub_scraper=sub, status=status, started_at=started).exists():
        ScraperRunHistory.objects.create(
            sub_scraper=sub,
            triggered_by='scheduled',
            started_at=started,
            ended_at=started + timedelta(seconds=duration),
            duration_seconds=duration,
            status=status,
            records_inserted=records,
            notes='Demo data' if status == 'failed' else ''
        )

# Create demo log files
import os
os.makedirs('/tmp/demo_logs', exist_ok=True)
with open('/tmp/demo_logs/info.log', 'w') as f:
    f.write('\n'.join([
        '2026-02-23 06:00:01 INFO Starting scraper...',
        '2026-02-23 06:00:02 INFO Connected to target website',
        '2026-02-23 06:00:05 INFO Fetching page 1 of 10',
        '2026-02-23 06:00:08 DEBUG Response received: 200',
        '2026-02-23 06:00:10 INFO Parsing 45 articles from page 1',
        '2026-02-23 06:00:15 WARNING Rate limit warning: slow down requests',
        '2026-02-23 06:01:20 INFO Page 2 of 10 - fetching...',
        '2026-02-23 06:01:25 INFO Parsing 38 articles from page 2',
        '2026-02-23 06:05:10 ERROR Failed to fetch page 7: Connection timeout',
        '2026-02-23 06:05:15 INFO Retrying page 7...',
        '2026-02-23 06:05:20 INFO Retry successful',
        '2026-02-23 06:10:00 INFO Scraping complete. Total: 342 articles',
        '2026-02-23 06:10:01 INFO Inserted 342 documents into MongoDB',
        '2026-02-23 06:10:02 INFO Scraper finished successfully',
    ]))

with open('/tmp/demo_logs/error.log', 'w') as f:
    f.write('\n'.join([
        '2026-02-23 06:05:10 ERROR Failed to fetch page 7: Connection timeout',
        '2026-02-23 05:00:01 ERROR yesterday - MongoDB write failed: duplicate key',
    ]))

# Update BBC to point to demo logs
Sub_updated = SubScraper.objects.filter(name__in=['BBC News', 'TechCrunch', 'Yahoo Finance'])
Sub_updated.update(log_folder_path='/tmp/demo_logs')

print("✓ Demo data seeded successfully!")
print(f"  - {MainScraper.objects.count()} main scrapers")
print(f"  - {SubScraper.objects.count()} sub scrapers")
print(f"  - {ScraperRunHistory.objects.count()} run history records")
print(f"  - Demo logs at /tmp/demo_logs/")
