"""Utilities for Celery schedule management and cron helpers."""
from datetime import datetime
from croniter import croniter
from django.utils import timezone


def get_next_runs(cron_string, count=3):
    """Get next N scheduled run times from a cron string."""
    try:
        base = datetime.now()
        cron = croniter(cron_string, base)
        return [cron.get_next(datetime) for _ in range(count)]
    except Exception:
        return []


def cron_to_readable(cron_string):
    """Convert a cron string to human-readable format using cron-descriptor."""
    try:
        from cron_descriptor import get_description
        return get_description(cron_string)
    except Exception:
        return cron_string


def update_celery_schedule(sub_scraper, schedule):
    """Create or update a django-celery-beat PeriodicTask for a sub scraper."""
    from django_celery_beat.models import PeriodicTask, CrontabSchedule

    parts = schedule.cron_string.split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron string: {schedule.cron_string}")

    minute, hour, day_of_month, month_of_year, day_of_week = parts

    crontab, _ = CrontabSchedule.objects.get_or_create(
        minute=minute,
        hour=hour,
        day_of_week=day_of_week,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
    )

    task_name = f"scraper.run.{sub_scraper.id}"
    task_args = f'[{sub_scraper.id}, "scheduled"]'

    periodic_task, created = PeriodicTask.objects.get_or_create(
        name=task_name,
        defaults={
            'task': 'dashboard.tasks.run_scraper_task',
            'crontab': crontab,
            'args': task_args,
            'enabled': schedule.is_enabled,
        }
    )

    if not created:
        periodic_task.crontab = crontab
        periodic_task.enabled = schedule.is_enabled
        periodic_task.args = task_args
        periodic_task.task = 'dashboard.tasks.run_scraper_task'
        periodic_task.save()

    return str(periodic_task.id)
