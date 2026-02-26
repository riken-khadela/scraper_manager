from django.db import models
from django.utils import timezone
from django.conf import settings


class MainScraper(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    tags = models.CharField(max_length=500, blank=True, help_text="Comma-separated tags")

    # ── MongoDB connection for THIS scraper group ───────────────────────
    # If left blank, falls back to MONGO_URI and MONGO_DEFAULT_DB from .env/settings.
    mongo_uri = models.CharField(
        max_length=500, blank=True,
        help_text="MongoDB connection URI for this group (leave blank to use global default)"
    )
    mongo_db_name = models.CharField(
        max_length=200, blank=True,
        help_text="MongoDB database name (leave blank to use global default)"
    )

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    # ── Helpers ─────────────────────────────────────────────────────────

    def get_effective_mongo_uri(self):
        """Returns this scraper's mongo URI or the global fallback."""
        return self.mongo_uri.strip() or settings.MONGO_URI

    def get_effective_mongo_db(self):
        """Returns this scraper's DB name or the global fallback."""
        return self.mongo_db_name.strip() or settings.MONGO_DEFAULT_DB

    def get_mongo_client(self):
        """Returns a PyMongo MongoClient for this scraper group's database."""
        import pymongo
        return pymongo.MongoClient(
            self.get_effective_mongo_uri(),
            serverSelectionTimeoutMS=5000
        )

    def get_mongo_db(self):
        """Returns the PyMongo Database object for this scraper group."""
        client = self.get_mongo_client()
        return client[self.get_effective_mongo_db()]

    @property
    def sub_scrapers_count(self):
        return self.sub_scrapers.count()

    @property
    def health_status(self):
        """Returns green/yellow/red/gray based on last run status of sub scrapers."""
        sub_scrapers = self.sub_scrapers.filter(is_active=True)
        if not sub_scrapers.exists():
            return 'gray'

        statuses = []
        for sub in sub_scrapers:
            last_run = sub.run_history.order_by('-started_at').first()
            if last_run:
                statuses.append(last_run.status)

        if not statuses:
            return 'gray'
        if 'failed' in statuses:
            return 'red'
        if any(s == 'running' for s in statuses):
            return 'green'
        if all(s == 'success' for s in statuses):
            return 'green'
        return 'yellow'


class SubScraper(models.Model):
    main_scraper = models.ForeignKey(MainScraper, on_delete=models.CASCADE, related_name='sub_scrapers')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    script_path = models.CharField(max_length=500, blank=True, help_text="Full server path to script")
    run_command = models.CharField(max_length=1000, blank=True, help_text="e.g. python /home/scrapers/run.py")
    log_folder_path = models.CharField(max_length=500, blank=True, help_text="Full path to log folder")

    # ── MongoDB: each sub-scraper owns ONE collection inside the parent's DB ──
    # The database connection + DB name come from the parent MainScraper.
    mongo_collection_name = models.CharField(
        max_length=200, blank=True,
        help_text="Collection name inside the parent scraper group's database"
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.main_scraper.name} → {self.name}"

    # ── Mongo convenience ────────────────────────────────────────────────

    def get_mongo_collection(self):
        """Returns the PyMongo Collection object for this sub-scraper."""
        if not self.mongo_collection_name:
            raise ValueError(f"Sub-scraper '{self.name}' has no MongoDB collection configured.")
        db = self.main_scraper.get_mongo_db()
        return db[self.mongo_collection_name]

    # ── Status helpers ───────────────────────────────────────────────────

    @property
    def current_status(self):
        process = getattr(self, 'process', None)
        if process and process.is_running:
            return 'running'
        last_run = self.run_history.order_by('-started_at').first()
        if not last_run:
            return 'never_run'
        return last_run.status

    @property
    def last_run(self):
        return self.run_history.order_by('-started_at').first()

    @property
    def is_stale(self):
        """True if last run was more than 24 hours ago and has an active schedule."""
        last_run = self.last_run
        if not last_run:
            return False
        schedule = getattr(self, 'schedule', None)
        if schedule and schedule.is_enabled:
            delta = timezone.now() - last_run.started_at
            return delta.total_seconds() > 86400
        return False


class ScraperSchedule(models.Model):
    sub_scraper = models.OneToOneField(SubScraper, on_delete=models.CASCADE, related_name='schedule')
    cron_string = models.CharField(max_length=100, default='0 6,14,22 * * *')
    is_enabled = models.BooleanField(default=True)
    celery_task_id = models.CharField(max_length=200, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Schedule for {self.sub_scraper.name}: {self.cron_string}"


class ScraperRunHistory(models.Model):
    TRIGGERED_BY_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('manual', 'Manual'),
    ]
    STATUS_CHOICES = [
        ('running', 'Running'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    sub_scraper = models.ForeignKey(SubScraper, on_delete=models.CASCADE, related_name='run_history')
    triggered_by = models.CharField(max_length=20, choices=TRIGGERED_BY_CHOICES, default='manual')
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running')
    records_inserted = models.IntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.sub_scraper.name} - {self.status} @ {self.started_at}"


class ScraperProcess(models.Model):
    sub_scraper = models.OneToOneField(SubScraper, on_delete=models.CASCADE, related_name='process')
    pid = models.IntegerField()
    started_at = models.DateTimeField(default=timezone.now)
    is_running = models.BooleanField(default=True)
    celery_task_id = models.CharField(max_length=200, blank=True, null=True)

    def __str__(self):
        return f"{self.sub_scraper.name} PID:{self.pid}"


class ScraperAccount(models.Model):
    """Stores individual login accounts for scrapers that need multi-account support."""
    STATUS_CHOICES = [
        ('idle', 'Idle'),
        ('running_update', 'Running Update'),
        ('running_new', 'Running New'),
        ('error', 'Error'),
    ]

    main_scraper = models.ForeignKey(MainScraper, on_delete=models.CASCADE, related_name='accounts')
    email = models.EmailField()
    password = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='idle')
    last_used_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']
        unique_together = ['main_scraper', 'email']

    def __str__(self):
        return f"{self.email} ({self.main_scraper.name})"


class ScraperConfig(models.Model):
    """Stores configurable defaults for a scraper group (e.g. account splits, batch sizes)."""
    main_scraper = models.OneToOneField(MainScraper, on_delete=models.CASCADE, related_name='scraper_config')

    # Account distribution
    update_account_count = models.IntegerField(
        default=0, help_text="Fixed number of accounts for update scraper (0 = use ratio)"
    )
    new_account_count = models.IntegerField(
        default=0, help_text="Fixed number of accounts for new scraper (0 = use ratio)"
    )
    update_ratio = models.FloatField(
        default=0.8, help_text="Ratio of active accounts for update when counts are 0 (auto mode)"
    )

    # Batch settings
    batch_size_new = models.IntegerField(default=10)
    batch_size_update = models.IntegerField(default=10)
    max_batches_new = models.IntegerField(default=10)
    max_batches_update = models.IntegerField(default=50)

    # Paths
    script_base_path = models.CharField(
        max_length=500, blank=True, help_text="Base path to scraper scripts directory"
    )
    log_base_path = models.CharField(
        max_length=500, blank=True, help_text="Base path for log output"
    )

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Config for {self.main_scraper.name}"

    def get_distribution(self, active_count):
        """Calculate update/new account split based on config."""
        if self.update_account_count > 0 or self.new_account_count > 0:
            update = min(self.update_account_count, active_count)
            new = min(self.new_account_count, max(0, active_count - update))
            return {'update': update, 'new': new}
        # Auto mode: use ratio
        update = int(active_count * self.update_ratio)
        new = active_count - update
        return {'update': update, 'new': new}
