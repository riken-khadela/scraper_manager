from django.contrib import admin
from .models import MainScraper, SubScraper, ScraperSchedule, ScraperRunHistory, ScraperProcess

@admin.register(MainScraper)
class MainScraperAdmin(admin.ModelAdmin):
    list_display = ['name', 'sub_scrapers_count', 'created_at']
    search_fields = ['name', 'tags']

@admin.register(SubScraper)
class SubScraperAdmin(admin.ModelAdmin):
    list_display = ['name', 'main_scraper', 'is_active', 'current_status', 'updated_at']
    list_filter = ['is_active', 'main_scraper']
    search_fields = ['name', 'description']

@admin.register(ScraperSchedule)
class ScraperScheduleAdmin(admin.ModelAdmin):
    list_display = ['sub_scraper', 'cron_string', 'is_enabled', 'updated_at']

@admin.register(ScraperRunHistory)
class ScraperRunHistoryAdmin(admin.ModelAdmin):
    list_display = ['sub_scraper', 'triggered_by', 'status', 'duration_seconds', 'started_at']
    list_filter = ['status', 'triggered_by']

@admin.register(ScraperProcess)
class ScraperProcessAdmin(admin.ModelAdmin):
    list_display = ['sub_scraper', 'pid', 'is_running', 'started_at']
