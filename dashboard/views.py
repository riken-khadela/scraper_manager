import os
import signal
import json
import datetime
from datetime import timedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.paginator import Paginator
from django.contrib import messages

from .models import (
    MainScraper, SubScraper, ScraperRunHistory, ScraperProcess, ScraperSchedule,
    ScraperAccount, ScraperConfig,
)
from .tasks import run_scraper_task
from .schedule_utils import update_celery_schedule, get_next_runs, cron_to_readable



def _mongo_safe(obj):
    """Recursively convert MongoDB/BSON types to JSON-serializable Python types.
    Handles: ObjectId, datetime, Decimal128, bytes, and any other exotic type.
    """
    if isinstance(obj, dict):
        return {k: _mongo_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_mongo_safe(i) for i in obj]
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.hex()
    # Handle bson types without hard-importing bson at module level
    cls_name = type(obj).__name__
    if cls_name == 'ObjectId':
        return str(obj)
    if cls_name == 'Decimal128':
        return float(str(obj))
    if cls_name == 'Regex':
        return str(obj)
    # Primitives that are already JSON-safe
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    # Fallback for anything else
    return str(obj)


def dashboard(request):
    """Global dashboard - shows all main scrapers as cards."""
    main_scrapers = MainScraper.objects.prefetch_related('sub_scrapers').all()

    total_scrapers = SubScraper.objects.filter(is_active=True).count()
    currently_running = ScraperProcess.objects.filter(is_running=True).count()

    # Failed = last run was failed
    failed_last_run = 0
    stale_count = 0
    for sub in SubScraper.objects.filter(is_active=True).prefetch_related('run_history'):
        last_run = sub.run_history.order_by('-started_at').first()
        if last_run and last_run.status == 'failed':
            failed_last_run += 1
        if sub.is_stale:
            stale_count += 1

    context = {
        'main_scrapers': main_scrapers,
        'total_scrapers': total_scrapers,
        'currently_running': currently_running,
        'failed_last_run': failed_last_run,
        'stale_count': stale_count,
    }
    return render(request, 'dashboard/dashboard.html', context)


def scrapers_list(request):
    """All main scrapers list."""
    main_scrapers = MainScraper.objects.prefetch_related('sub_scrapers').all()
    return render(request, 'dashboard/scrapers_list.html', {'main_scrapers': main_scrapers})


def main_scraper_create(request):
    """Create a new main scraper."""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            scraper = MainScraper.objects.create(
                name=name,
                description=request.POST.get('description', ''),
                tags=request.POST.get('tags', ''),
                mongo_uri=request.POST.get('mongo_uri', '').strip(),
                mongo_db_name=request.POST.get('mongo_db_name', '').strip(),
            )
            messages.success(request, f'Main scraper "{name}" created successfully.')
            return redirect('main_scraper_detail', pk=scraper.pk)
        else:
            messages.error(request, 'Name is required.')
    from django.conf import settings as dj_settings
    return render(request, 'dashboard/main_scraper_form.html', {
        'title': 'New Main Scraper',
        'scraper': None,
        'default_mongo_uri': dj_settings.MONGO_URI,
        'default_mongo_db': dj_settings.MONGO_DEFAULT_DB,
    })


def main_scraper_edit(request, pk):
    """Edit a main scraper."""
    scraper = get_object_or_404(MainScraper, pk=pk)
    if request.method == 'POST':
        scraper.name = request.POST.get('name', scraper.name).strip()
        scraper.description = request.POST.get('description', '')
        scraper.tags = request.POST.get('tags', '')
        scraper.mongo_uri = request.POST.get('mongo_uri', '').strip()
        scraper.mongo_db_name = request.POST.get('mongo_db_name', '').strip()
        scraper.save()
        messages.success(request, 'Updated successfully.')
        return redirect('main_scraper_detail', pk=pk)
    from django.conf import settings as dj_settings
    return render(request, 'dashboard/main_scraper_form.html', {
        'title': 'Edit Main Scraper',
        'scraper': scraper,
        'default_mongo_uri': dj_settings.MONGO_URI,
        'default_mongo_db': dj_settings.MONGO_DEFAULT_DB,
    })


def main_scraper_detail(request, pk):
    """Main scraper detail page - lists all sub scrapers."""
    main_scraper = get_object_or_404(MainScraper, pk=pk)
    sub_scrapers = main_scraper.sub_scrapers.prefetch_related('run_history', 'process', 'schedule').all()

    sub_data = []
    for sub in sub_scrapers:
        last_run = sub.run_history.order_by('-started_at').first()
        process = getattr(sub, 'process', None)
        schedule = getattr(sub, 'schedule', None)
        is_running = process and process.is_running

        sub_data.append({
            'sub': sub,
            'last_run': last_run,
            'is_running': is_running,
            'status': 'running' if is_running else (last_run.status if last_run else 'never_run'),
            'is_stale': sub.is_stale,
            'schedule_summary': schedule.cron_string if schedule else 'No schedule',
            'schedule_enabled': schedule.is_enabled if schedule else False,
        })

    return render(request, 'dashboard/main_scraper_detail.html', {
        'main_scraper': main_scraper,
        'sub_data': sub_data,
    })


def sub_scraper_create(request, pk):
    """Create a new sub scraper under a main scraper."""
    main_scraper = get_object_or_404(MainScraper, pk=pk)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            sub = SubScraper.objects.create(
                main_scraper=main_scraper,
                name=name,
                description=request.POST.get('description', ''),
                script_path=request.POST.get('script_path', ''),
                run_command=request.POST.get('run_command', ''),
                log_folder_path=request.POST.get('log_folder_path', ''),
                mongo_collection_name=request.POST.get('mongo_collection_name', '').strip(),
                is_active=request.POST.get('is_active', 'on') == 'on',
            )
            messages.success(request, f'Sub scraper "{name}" created successfully.')
            return redirect('sub_scraper_detail', pk=pk, sub_id=sub.pk)
        else:
            messages.error(request, 'Name is required.')
    return render(request, 'dashboard/sub_scraper_form.html', {
        'title': 'New Sub Scraper',
        'main_scraper': main_scraper,
        'sub': None,
    })


def sub_scraper_detail(request, pk, sub_id):
    """Sub scraper detail page."""
    main_scraper = get_object_or_404(MainScraper, pk=pk)
    sub = get_object_or_404(SubScraper, pk=sub_id, main_scraper=main_scraper)

    process = getattr(sub, 'process', None)
    is_running = process and process.is_running
    last_run = sub.run_history.order_by('-started_at').first()
    schedule = getattr(sub, 'schedule', None)

    next_runs = []
    if schedule:
        try:
            next_runs = get_next_runs(schedule.cron_string, count=3)
        except Exception:
            pass

    return render(request, 'dashboard/sub_scraper_detail.html', {
        'main_scraper': main_scraper,
        'sub': sub,
        'is_running': is_running,
        'process': process,
        'last_run': last_run,
        'schedule': schedule,
        'next_runs': next_runs,
    })


def sub_scraper_edit(request, pk, sub_id):
    """Edit sub scraper configuration."""
    main_scraper = get_object_or_404(MainScraper, pk=pk)
    sub = get_object_or_404(SubScraper, pk=sub_id, main_scraper=main_scraper)

    errors = {}
    if request.method == 'POST':
        sub.name = request.POST.get('name', sub.name).strip()
        sub.description = request.POST.get('description', '')
        sub.script_path = request.POST.get('script_path', '')
        sub.run_command = request.POST.get('run_command', '')
        sub.log_folder_path = request.POST.get('log_folder_path', '')
        sub.mongo_collection_name = request.POST.get('mongo_collection_name', '').strip()
        sub.is_active = request.POST.get('is_active', '') == 'on'

        # Validate script path
        if sub.script_path and not os.path.exists(sub.script_path):
            errors['script_path'] = f"Script path does not exist: {sub.script_path}"

        if not errors:
            sub.save()
            messages.success(request, 'Configuration updated successfully.')
            return redirect('sub_scraper_detail', pk=pk, sub_id=sub_id)

    return render(request, 'dashboard/sub_scraper_form.html', {
        'title': 'Edit Sub Scraper',
        'main_scraper': main_scraper,
        'sub': sub,
        'errors': errors,
    })


@require_POST
def run_scraper(request, pk, sub_id):
    """Trigger a scraper run manually."""
    main_scraper = get_object_or_404(MainScraper, pk=pk)
    sub = get_object_or_404(SubScraper, pk=sub_id, main_scraper=main_scraper)

    # Check if already running
    process = getattr(sub, 'process', None)
    if process and process.is_running:
        return JsonResponse({'status': 'error', 'message': 'Scraper is already running'}, status=400)

    if not sub.run_command:
        return JsonResponse({'status': 'error', 'message': 'No run command configured'}, status=400)

    # Fire the Celery task
    task = run_scraper_task.delay(sub.id, triggered_by='manual')

    return JsonResponse({
        'status': 'ok',
        'message': f'Scraper "{sub.name}" started',
        'task_id': task.id,
    })


@require_POST
def stop_scraper(request, pk, sub_id):
    """Stop a running scraper by killing its process."""
    main_scraper = get_object_or_404(MainScraper, pk=pk)
    sub = get_object_or_404(SubScraper, pk=sub_id, main_scraper=main_scraper)

    process = getattr(sub, 'process', None)
    if not process or not process.is_running:
        return JsonResponse({'status': 'error', 'message': 'No running process found'}, status=400)

    try:
        # Kill the process group
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except ProcessLookupError:
        pass
    except Exception as e:
        # Try direct kill
        try:
            os.kill(process.pid, signal.SIGTERM)
        except Exception:
            pass

    process.is_running = False
    process.save()

    # Update running history record
    running_run = sub.run_history.filter(status='running').first()
    if running_run:
        running_run.status = 'failed'
        running_run.ended_at = timezone.now()
        if running_run.started_at:
            delta = running_run.ended_at - running_run.started_at
            running_run.duration_seconds = round(delta.total_seconds(), 2)
        running_run.notes = 'Manually stopped by user'
        running_run.save()

    return JsonResponse({'status': 'ok', 'message': f'Process {process.pid} stopped'})


def log_viewer(request, pk, sub_id):
    """Log viewer page."""
    main_scraper = get_object_or_404(MainScraper, pk=pk)
    sub = get_object_or_404(SubScraper, pk=sub_id, main_scraper=main_scraper)

    log_files = []
    if sub.log_folder_path and os.path.isdir(sub.log_folder_path):
        for f in os.listdir(sub.log_folder_path):
            if f.endswith('.log') or f.endswith('.txt'):
                full_path = os.path.join(sub.log_folder_path, f)
                log_files.append({
                    'name': f,
                    'path': full_path,
                    'size': os.path.getsize(full_path),
                })

    process = getattr(sub, 'process', None)
    is_running = process and process.is_running

    return render(request, 'dashboard/log_viewer.html', {
        'main_scraper': main_scraper,
        'sub': sub,
        'log_files': log_files,
        'is_running': is_running,
    })


def schedule_management(request, pk, sub_id):
    """Schedule management page."""
    main_scraper = get_object_or_404(MainScraper, pk=pk)
    sub = get_object_or_404(SubScraper, pk=sub_id, main_scraper=main_scraper)

    schedule, created = ScraperSchedule.objects.get_or_create(
        sub_scraper=sub,
        defaults={'cron_string': '0 6,14,22 * * *', 'is_enabled': False}
    )

    errors = {}
    if request.method == 'POST':
        mode = request.POST.get('mode', 'advanced')
        is_enabled = request.POST.get('is_enabled', '') == 'on'

        if mode == 'simple':
            # Build cron from time pickers
            times = request.POST.getlist('run_times')
            if times:
                hours = sorted(set(int(t.split(':')[0]) for t in times if t))
                minutes = sorted(set(int(t.split(':')[1]) for t in times if t))
                minute = minutes[0] if minutes else 0
                hour_str = ','.join(str(h) for h in hours)
                cron_string = f"{minute} {hour_str} * * *"
            else:
                cron_string = schedule.cron_string
        else:
            cron_string = request.POST.get('cron_string', schedule.cron_string).strip()

        # Validate cron string
        try:
            from croniter import croniter
            if not croniter.is_valid(cron_string):
                errors['cron_string'] = f"Invalid cron expression: {cron_string}"
        except Exception as e:
            errors['cron_string'] = str(e)

        if not errors:
            schedule.cron_string = cron_string
            schedule.is_enabled = is_enabled
            schedule.save()

            # Update Celery Beat
            try:
                task_id = update_celery_schedule(sub, schedule)
                schedule.celery_task_id = task_id
                schedule.save(update_fields=['celery_task_id'])
            except Exception as e:
                errors['celery'] = f"Schedule saved but Celery task update failed: {str(e)}"

            if not errors:
                messages.success(request, 'Schedule updated successfully.')
                return redirect('schedule_management', pk=pk, sub_id=sub_id)

    next_runs = []
    try:
        next_runs = get_next_runs(schedule.cron_string, count=3)
    except Exception:
        pass

    return render(request, 'dashboard/schedule_management.html', {
        'main_scraper': main_scraper,
        'sub': sub,
        'schedule': schedule,
        'next_runs': next_runs,
        'cron_readable': cron_to_readable(schedule.cron_string),
        'errors': errors,
    })


def run_history(request, pk, sub_id):
    """Run history page for a sub scraper."""
    main_scraper = get_object_or_404(MainScraper, pk=pk)
    sub = get_object_or_404(SubScraper, pk=sub_id, main_scraper=main_scraper)

    history_qs = sub.run_history.all().order_by('-started_at')
    paginator = Paginator(history_qs, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Stats
    total_runs = history_qs.count()
    success_runs = history_qs.filter(status='success').count()
    success_rate = round((success_runs / total_runs * 100) if total_runs > 0 else 0, 1)
    durations = [r.duration_seconds for r in history_qs if r.duration_seconds is not None]
    avg_duration = round(sum(durations) / len(durations), 2) if durations else None
    last_success = history_qs.filter(status='success').first()

    return render(request, 'dashboard/run_history.html', {
        'main_scraper': main_scraper,
        'sub': sub,
        'page_obj': page_obj,
        'total_runs': total_runs,
        'success_rate': success_rate,
        'avg_duration': avg_duration,
        'last_success': last_success,
    })


def mongo_panel(request, pk, sub_id):
    """MongoDB query panel."""
    main_scraper = get_object_or_404(MainScraper, pk=pk)
    sub = get_object_or_404(SubScraper, pk=sub_id, main_scraper=main_scraper)

    context = {
        'main_scraper': main_scraper,
        'sub': sub,
        # Show which DB/URI is active for this panel
        'mongo_uri_display': main_scraper.get_effective_mongo_uri(),
        'mongo_db_display': main_scraper.get_effective_mongo_db(),
        'mongo_error': None,
        'doc_count': None,
        'last_docs': [],
        'query_results': None,
        'query_error': None,
        'collection_stats': None,
        'last_inserted': None,
    }

    if not sub.mongo_collection_name:
        context['mongo_error'] = 'No MongoDB collection configured for this scraper.'
        return render(request, 'dashboard/mongo_panel.html', context)

    try:
        # Use per-group connection — falls back to .env globals if blank
        client = main_scraper.get_mongo_client()
        db = client[main_scraper.get_effective_mongo_db()]
        collection = db[sub.mongo_collection_name]

        context['doc_count'] = collection.count_documents({})
        context['last_docs'] = [
            _mongo_safe(doc)
            for doc in collection.find({}, limit=5).sort('_id', -1)
        ]

        try:
            stats = db.command('collstats', sub.mongo_collection_name)
            context['collection_stats'] = {
                'count': stats.get('count', 0),
                'size': stats.get('size', 0),
                'avgObjSize': stats.get('avgObjSize', 0),
            }
        except Exception:
            pass

        if request.method == 'POST':
            action = request.POST.get('action', 'query')

            if action == 'last_inserted':
                last_doc = collection.find_one({}, sort=[('_id', -1)])
                if last_doc:
                    from bson import ObjectId
                    oid = last_doc['_id']
                    if isinstance(oid, ObjectId):
                        context['last_inserted'] = oid.generation_time.strftime('%Y-%m-%d %H:%M:%S UTC')
                    else:
                        context['last_inserted'] = str(oid)
                else:
                    context['last_inserted'] = 'No documents found'

            elif action == 'query':
                raw_filter = request.POST.get('filter_query', '{}').strip()
                raw_sort = request.POST.get('sort_query', '{"_id": -1}').strip()
                limit = int(request.POST.get('limit', 10))

                try:
                    filter_dict = json.loads(raw_filter) if raw_filter else {}
                    sort_dict = json.loads(raw_sort) if raw_sort else {'_id': -1}
                    results = [
                        _mongo_safe(doc)
                        for doc in collection.find(filter_dict, limit=limit).sort(list(sort_dict.items()))
                    ]
                    context['query_results'] = json.dumps(results, indent=2)
                    context['filter_query'] = raw_filter
                    context['sort_query'] = raw_sort
                    context['limit'] = limit
                except json.JSONDecodeError as e:
                    context['query_error'] = f"Invalid JSON: {str(e)}"
                except Exception as e:
                    context['query_error'] = f"Query error: {str(e)}"

        client.close()

    except Exception as e:
        context['mongo_error'] = f"MongoDB connection error: {str(e)}"

    return render(request, 'dashboard/mongo_panel.html', context)


def live_terminal(request, pk, sub_id):
    """Live interactive terminal page for a sub scraper."""
    main_scraper = get_object_or_404(MainScraper, pk=pk)
    sub = get_object_or_404(SubScraper, pk=sub_id, main_scraper=main_scraper)

    process = getattr(sub, 'process', None)
    is_running = process and process.is_running

    return render(request, 'dashboard/live_terminal.html', {
        'main_scraper': main_scraper,
        'sub': sub,
        'is_running': is_running,
        'process': process,
    })


def watcher(request):
    """Global process watcher panel."""
    sub_scrapers = SubScraper.objects.filter(is_active=True).select_related(
        'main_scraper'
    ).prefetch_related('run_history', 'process', 'schedule').all()

    watcher_data = []
    for sub in sub_scrapers:
        process = getattr(sub, 'process', None)
        is_running = process and process.is_running
        last_run = sub.run_history.order_by('-started_at').first()
        schedule = getattr(sub, 'schedule', None)
        next_run = None
        if schedule and schedule.is_enabled:
            try:
                runs = get_next_runs(schedule.cron_string, count=1)
                next_run = runs[0] if runs else None
            except Exception:
                pass

        watcher_data.append({
            'sub': sub,
            'is_running': is_running,
            'process': process,
            'last_run': last_run,
            'next_run': next_run,
            'status': 'running' if is_running else (last_run.status if last_run else 'never_run'),
        })

    return render(request, 'dashboard/watcher.html', {
        'watcher_data': watcher_data,
    })


# ═══════════════════════════════════════════════════════════════════
# Account Management & Control Panel views
# ═══════════════════════════════════════════════════════════════════

def account_management(request, pk):
    """Account management page — list, toggle, edit accounts for a main scraper."""
    main_scraper = get_object_or_404(MainScraper, pk=pk)
    accounts = main_scraper.accounts.all()
    config, _ = ScraperConfig.objects.get_or_create(
        main_scraper=main_scraper,
        defaults={'script_base_path': '', 'log_base_path': ''}
    )

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_account':
            email = request.POST.get('email', '').strip()
            password = request.POST.get('password', '').strip()
            if email and password:
                obj, created = ScraperAccount.objects.get_or_create(
                    main_scraper=main_scraper, email=email,
                    defaults={'password': password}
                )
                if created:
                    messages.success(request, f'Account {email} added.')
                else:
                    messages.warning(request, f'Account {email} already exists.')
            else:
                messages.error(request, 'Email and password are required.')

        elif action == 'delete_account':
            acc_id = request.POST.get('account_id')
            ScraperAccount.objects.filter(pk=acc_id, main_scraper=main_scraper).delete()
            messages.success(request, 'Account deleted.')

        elif action == 'bulk_toggle':
            state = request.POST.get('state') == 'on'
            main_scraper.accounts.all().update(is_active=state)
            messages.success(request, f'All accounts {"activated" if state else "deactivated"}.')

        return redirect('account_management', pk=pk)

    active_count = accounts.filter(is_active=True).count()
    distribution = config.get_distribution(active_count)

    return render(request, 'dashboard/account_management.html', {
        'main_scraper': main_scraper,
        'accounts': accounts,
        'config': config,
        'active_count': active_count,
        'total_count': accounts.count(),
        'distribution': distribution,
    })


@csrf_exempt
@require_POST
def account_toggle(request, pk, account_id):
    """AJAX: Toggle an account's active status."""
    main_scraper = get_object_or_404(MainScraper, pk=pk)
    account = get_object_or_404(ScraperAccount, pk=account_id, main_scraper=main_scraper)
    account.is_active = not account.is_active
    account.save(update_fields=['is_active', 'updated_at'])
    return JsonResponse({'status': 'ok', 'is_active': account.is_active, 'email': account.email})


def account_edit(request, pk, account_id):
    """Edit a single account's email/password."""
    main_scraper = get_object_or_404(MainScraper, pk=pk)
    account = get_object_or_404(ScraperAccount, pk=account_id, main_scraper=main_scraper)

    if request.method == 'POST':
        account.email = request.POST.get('email', account.email).strip()
        pwd = request.POST.get('password', '').strip()
        if pwd:
            account.password = pwd
        account.notes = request.POST.get('notes', '')
        account.save()
        messages.success(request, f'Account {account.email} updated.')
        return redirect('account_management', pk=pk)

    return render(request, 'dashboard/account_edit.html', {
        'main_scraper': main_scraper,
        'account': account,
    })


def control_panel(request, pk):
    """Control panel — run scrapers with configurable account splits."""
    main_scraper = get_object_or_404(MainScraper, pk=pk)
    config, _ = ScraperConfig.objects.get_or_create(
        main_scraper=main_scraper,
        defaults={'script_base_path': '', 'log_base_path': ''}
    )
    accounts = main_scraper.accounts.all()
    active_accounts = accounts.filter(is_active=True)
    active_count = active_accounts.count()
    distribution = config.get_distribution(active_count)

    sub_scrapers = main_scraper.sub_scrapers.prefetch_related('process', 'run_history').all()
    sub_data = []
    for sub in sub_scrapers:
        process = getattr(sub, 'process', None)
        is_running = process and process.is_running
        last_run = sub.run_history.order_by('-started_at').first()
        sub_data.append({
            'sub': sub,
            'is_running': is_running,
            'status': 'running' if is_running else (last_run.status if last_run else 'never_run'),
            'last_run': last_run,
        })

    return render(request, 'dashboard/control_panel.html', {
        'main_scraper': main_scraper,
        'config': config,
        'accounts': accounts,
        'active_count': active_count,
        'total_count': accounts.count(),
        'distribution': distribution,
        'sub_data': sub_data,
    })


@require_POST
def update_config(request, pk):
    """Save scraper config (account splits, batch sizes, paths)."""
    main_scraper = get_object_or_404(MainScraper, pk=pk)
    config, _ = ScraperConfig.objects.get_or_create(main_scraper=main_scraper)

    try:
        config.update_account_count = int(request.POST.get('update_account_count', 0))
        config.new_account_count = int(request.POST.get('new_account_count', 0))
        config.update_ratio = float(request.POST.get('update_ratio', 0.8))
        config.batch_size_new = int(request.POST.get('batch_size_new', 10))
        config.batch_size_update = int(request.POST.get('batch_size_update', 10))
        config.max_batches_new = int(request.POST.get('max_batches_new', 10))
        config.max_batches_update = int(request.POST.get('max_batches_update', 50))
        config.script_base_path = request.POST.get('script_base_path', '').strip()
        config.log_base_path = request.POST.get('log_base_path', '').strip()
        config.save()
        messages.success(request, 'Configuration saved.')
    except (ValueError, TypeError) as e:
        messages.error(request, f'Invalid value: {e}')

    return redirect('control_panel', pk=pk)


@require_POST
def run_with_config(request, pk):
    """Launch a scraper run using the saved config — writes JSON config and fires Celery task."""
    import tempfile
    main_scraper = get_object_or_404(MainScraper, pk=pk)
    config, _ = ScraperConfig.objects.get_or_create(main_scraper=main_scraper)

    mode = request.POST.get('mode', 'all')  # all | new_only | update_only
    sub_id = request.POST.get('sub_id')  # which SubScraper to run under

    if not sub_id:
        return JsonResponse({'status': 'error', 'message': 'No sub_scraper selected'}, status=400)

    sub = get_object_or_404(SubScraper, pk=sub_id, main_scraper=main_scraper)

    # Check if already running
    process = getattr(sub, 'process', None)
    if process and process.is_running:
        return JsonResponse({'status': 'error', 'message': 'Scraper is already running'}, status=400)

    # Build config JSON from database
    active_accounts = main_scraper.accounts.filter(is_active=True)
    if not active_accounts.exists():
        return JsonResponse({'status': 'error', 'message': 'No active accounts'}, status=400)

    distribution = config.get_distribution(active_accounts.count())

    config_data = {
        'accounts': [
            {'email': acc.email, 'password': acc.password, 'active': True}
            for acc in active_accounts
        ],
        'update_account_count': distribution['update'],
        'new_account_count': distribution['new'],
        'update_ratio': config.update_ratio,
        'batch_size_new': config.batch_size_new,
        'batch_size_update': config.batch_size_update,
        'max_batches_new': config.max_batches_new,
        'max_batches_update': config.max_batches_update,
        'mode': mode,
        'log_base_path': config.log_base_path or '/tmp/scraper_logs',
        'mongo_uri': main_scraper.get_effective_mongo_uri(),
    }

    # Write config to temp file
    config_dir = os.path.join(tempfile.gettempdir(), 'scraper_configs')
    os.makedirs(config_dir, exist_ok=True)
    config_path = os.path.join(config_dir, f'config_{main_scraper.pk}_{sub.pk}.json')
    with open(config_path, 'w') as f:
        json.dump(config_data, f, indent=2)

    # Build run command
    script_base = config.script_base_path or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'crunchbase'
    )
    main_script = os.path.join(script_base, 'main.py')

    run_command = f'python {main_script} --config-file {config_path} --mode {mode}'

    # Temporarily set the run_command and fire the task
    sub.run_command = run_command
    sub.save(update_fields=['run_command'])

    # Mark accounts as running
    if mode in ('all', 'update_only'):
        role = 'running_update'
    else:
        role = 'running_new'
    active_accounts.update(status=role, last_used_at=timezone.now())

    task = run_scraper_task.delay(sub.id, triggered_by='manual')

    return JsonResponse({
        'status': 'ok',
        'message': f'Scraper "{sub.name}" started in {mode} mode',
        'task_id': task.id,
        'config': {
            'update_accounts': distribution['update'],
            'new_accounts': distribution['new'],
            'mode': mode,
        },
    })
