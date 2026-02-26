"""
Seed Crunchbase scraper data into ScraperHub.
Creates the MainScraper, SubScrapers, accounts, and config.

Run with:  python seed_crunchbase.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scraper_manager.settings')
django.setup()

from django.utils import timezone
from dashboard.models import (
    MainScraper, SubScraper, ScraperSchedule, ScraperAccount, ScraperConfig,
)

print("Seeding Crunchbase data...")

# ── Determine paths ──────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CRUNCHBASE_DIR = os.path.join(BASE_DIR, 'crunchbase')
LOG_DIR = os.path.join(BASE_DIR, 'logs', 'crunchbase')
os.makedirs(LOG_DIR, exist_ok=True)

# ── 1. MainScraper ───────────────────────────────────────────────────────
crunchbase, created = MainScraper.objects.get_or_create(
    name='Crunchbase',
    defaults={
        'description': 'Crunchbase organization scraper with multi-account support',
        'tags': 'crunchbase,organizations,startups,finance',
        'mongo_uri': 'mongodb://admin9:i38kjmx35@localhost:27017/?authSource=admin&authMechanism=SCRAM-SHA-256&readPreference=primary&tls=true&tlsAllowInvalidCertificates=true&directConnection=true',
        'mongo_db_name': 'STARTUPSCRAPERDATA',
    }
)
if created:
    print(f"  ✓ Created MainScraper: Crunchbase (id={crunchbase.pk})")
else:
    print(f"  • MainScraper 'Crunchbase' already exists (id={crunchbase.pk})")

# ── 2. SubScrapers ───────────────────────────────────────────────────────
main_runner, _ = SubScraper.objects.get_or_create(
    main_scraper=crunchbase,
    name='Main Runner (All Accounts)',
    defaults={
        'description': 'Launches main.py which distributes accounts between update and new scrapers',
        'script_path': os.path.join(CRUNCHBASE_DIR, 'main.py'),
        'run_command': f'python {os.path.join(CRUNCHBASE_DIR, "main.py")}',
        'log_folder_path': os.path.join(LOG_DIR, 'main_logs'),
        'mongo_collection_name': 'OrganiztionDetails',
        'is_active': True,
    }
)

new_scrapper, _ = SubScraper.objects.get_or_create(
    main_scraper=crunchbase,
    name='New Scrapper',
    defaults={
        'description': 'Scrapes new organizations from Crunchbase URLs',
        'script_path': os.path.join(CRUNCHBASE_DIR, 'new_scrapper.py'),
        'run_command': f'python {os.path.join(CRUNCHBASE_DIR, "new_scrapper.py")}',
        'log_folder_path': os.path.join(LOG_DIR, 'new_scrapper'),
        'mongo_collection_name': 'OrganiztionDetails',
        'is_active': True,
    }
)

update_scrapper, _ = SubScraper.objects.get_or_create(
    main_scraper=crunchbase,
    name='Update Scrapper',
    defaults={
        'description': 'Updates existing organization data with latest info',
        'script_path': os.path.join(CRUNCHBASE_DIR, 'update_scrapper.py'),
        'run_command': f'python {os.path.join(CRUNCHBASE_DIR, "update_scrapper.py")}',
        'log_folder_path': os.path.join(LOG_DIR, 'update_logs'),
        'mongo_collection_name': 'CorrectData',
        'is_active': True,
    }
)

print(f"  ✓ SubScrapers: Main Runner, New Scrapper, Update Scrapper")

# ── 3. Create log directories ────────────────────────────────────────────
for path in [
    os.path.join(LOG_DIR, 'main_logs'),
    os.path.join(LOG_DIR, 'new_scrapper'),
    os.path.join(LOG_DIR, 'update_logs'),
]:
    os.makedirs(path, exist_ok=True)

# ── 4. Accounts (25 accounts from original main.py) ─────────────────────
ACCOUNTS = [
    {"email": "rikenkhadela22@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+1@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+2@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+3@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+4@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+5@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+6@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+7@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+8@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+9@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+10@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+11@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+12@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+13@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+14@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+15@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+16@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+17@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+18@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+19@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+20@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+21@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+22@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+23@gmail.com", "password": "Riken@123"},
    {"email": "rikenkhadela22+24@gmail.com", "password": "Riken@123"},
]

created_count = 0
for acc in ACCOUNTS:
    _, was_created = ScraperAccount.objects.get_or_create(
        main_scraper=crunchbase,
        email=acc['email'],
        defaults={
            'password': acc['password'],
            'is_active': True,
        }
    )
    if was_created:
        created_count += 1

print(f"  ✓ Accounts: {created_count} new, {len(ACCOUNTS) - created_count} already existed")

# ── 5. Config (defaults: 80% update, 20% new) ───────────────────────────
config, config_created = ScraperConfig.objects.get_or_create(
    main_scraper=crunchbase,
    defaults={
        'update_account_count': 0,   # 0 = auto from ratio
        'new_account_count': 0,      # 0 = auto from ratio
        'update_ratio': 0.8,         # 80% to update, 20% to new
        'batch_size_new': 10,
        'batch_size_update': 10,
        'max_batches_new': 10,
        'max_batches_update': 50,
        'script_base_path': CRUNCHBASE_DIR,
        'log_base_path': LOG_DIR,
    }
)
if config_created:
    print(f"  ✓ Config created: 80/20 ratio, batch=10, max_batches=10/50")
else:
    print(f"  • Config already exists")

# ── 6. Schedules ─────────────────────────────────────────────────────────
for sub in [main_runner, new_scrapper, update_scrapper]:
    ScraperSchedule.objects.get_or_create(
        sub_scraper=sub,
        defaults={'cron_string': '0 6,14,22 * * *', 'is_enabled': False}
    )

print(f"  ✓ Schedules created (disabled by default)")

# ── Summary ──────────────────────────────────────────────────────────────
print()
print("═" * 60)
print("  Crunchbase scraper seeded successfully!")
print(f"  MainScraper ID: {crunchbase.pk}")
print(f"  SubScrapers: Main Runner, New Scrapper, Update Scrapper")
print(f"  Accounts: {ScraperAccount.objects.filter(main_scraper=crunchbase).count()}")
print(f"  Config: {config.update_ratio*100:.0f}% update / {(1-config.update_ratio)*100:.0f}% new")
print()
print(f"  Dashboard:      http://localhost:8000/scrapers/{crunchbase.pk}/")
print(f"  Accounts:       http://localhost:8000/scrapers/{crunchbase.pk}/accounts/")
print(f"  Control Panel:  http://localhost:8000/scrapers/{crunchbase.pk}/control-panel/")
print("═" * 60)
