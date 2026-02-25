import os
import json
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import SubScraper, ScraperProcess
from .schedule_utils import get_next_runs
from .tasks import get_live_log_path, get_stdin_queue_path


def _tail_file(file_path, num_lines=100):
    """Read last N lines from a file efficiently using seek from end."""
    try:
        with open(file_path, 'rb') as f:
            f.seek(0, 2)
            file_size = f.tell()

            if file_size == 0:
                return []

            chunk_size = 8192
            lines = []
            remaining = file_size
            buffer = b''

            while remaining > 0 and len(lines) <= num_lines:
                read_size = min(chunk_size, remaining)
                remaining -= read_size
                f.seek(remaining)
                chunk = f.read(read_size)
                buffer = chunk + buffer
                lines = buffer.split(b'\n')

                if len(lines) > num_lines + 1:
                    break

            result_lines = [l.decode('utf-8', errors='replace') for l in lines if l]
            return result_lines[-num_lines:]
    except FileNotFoundError:
        return []
    except Exception as e:
        return [f"Error reading file: {str(e)}"]


def api_log_tail(request):
    """Return the last N lines of a log file as JSON."""
    file_path = request.GET.get('file_path', '')
    num_lines = int(request.GET.get('num_lines', 100))

    if not file_path:
        return JsonResponse({'error': 'file_path is required'}, status=400)

    if not os.path.isfile(file_path):
        return JsonResponse({'error': f'File not found: {file_path}'}, status=404)

    num_lines = max(10, min(num_lines, 1000))
    lines = _tail_file(file_path, num_lines)
    return JsonResponse({'lines': lines, 'file': os.path.basename(file_path)})


def api_status(request, sub_id):
    """Return current status of a sub scraper."""
    try:
        sub = SubScraper.objects.get(pk=sub_id)
    except SubScraper.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    process = getattr(sub, 'process', None)
    is_running = process and process.is_running
    last_run = sub.run_history.order_by('-started_at').first()

    return JsonResponse({
        'sub_id': sub.id,
        'name': sub.name,
        'is_running': is_running,
        'pid': process.pid if process and is_running else None,
        'status': 'running' if is_running else (last_run.status if last_run else 'never_run'),
        'last_run_at': last_run.started_at.isoformat() if last_run else None,
        'last_run_status': last_run.status if last_run else None,
        # Does the live log file exist?
        'has_live_log': os.path.isfile(get_live_log_path(sub_id)),
        # Can we send stdin right now?
        'stdin_available': os.path.isfile(get_stdin_queue_path(sub_id)),
    })


def api_live_log(request, sub_id):
    """Return live log lines for a running scraper with line-offset support.

    Query params:
        offset (int): number of lines already seen by the client (default 0)

    Response:
        { lines: [...], total: N, is_running: bool }
    """
    log_path = get_live_log_path(sub_id)
    offset = int(request.GET.get('offset', 0))

    # Check running status
    try:
        sub = SubScraper.objects.get(pk=sub_id)
        process = getattr(sub, 'process', None)
        is_running = bool(process and process.is_running)
    except SubScraper.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    if not os.path.isfile(log_path):
        return JsonResponse({
            'lines': [],
            'total': 0,
            'is_running': is_running,
        })

    try:
        with open(log_path, 'r', errors='replace') as f:
            content = f.read()

        all_lines = content.split('\n')
        # Remove trailing empty line artifact from split
        if all_lines and all_lines[-1] == '':
            all_lines = all_lines[:-1]

        total = len(all_lines)
        new_lines = all_lines[offset:] if offset < total else []

        return JsonResponse({
            'lines': new_lines,
            'total': total,
            'is_running': is_running,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_POST
def api_send_input(request, sub_id):
    """Send a line of input to the running scraper's stdin.

    Body (JSON): { "input": "some text" }
    The text is appended to the stdin queue file which the Celery worker reads
    and forwards to the process's PTY master fd.
    """
    stdin_queue_path = get_stdin_queue_path(sub_id)

    if not os.path.isfile(stdin_queue_path):
        return JsonResponse(
            {'error': 'No active stdin queue — scraper may not be running'},
            status=400,
        )

    try:
        body = json.loads(request.body)
        text = body.get('input', '')
    except (json.JSONDecodeError, AttributeError):
        text = request.POST.get('input', '')

    # Always append a newline so input() / readline() in the script unblocks
    line = text + '\n'

    try:
        with open(stdin_queue_path, 'ab') as f:
            f.write(line.encode('utf-8'))
        return JsonResponse({'status': 'ok', 'sent': text})
    except OSError as e:
        return JsonResponse({'error': f'Failed to write to stdin: {str(e)}'}, status=500)


def api_watcher_data(request):
    """Return watcher data for all active scrapers."""
    sub_scrapers = SubScraper.objects.filter(is_active=True).select_related(
        'main_scraper'
    ).prefetch_related('run_history', 'process', 'schedule').all()

    data = []
    for sub in sub_scrapers:
        process = getattr(sub, 'process', None)
        is_running = process and process.is_running
        last_run = sub.run_history.order_by('-started_at').first()
        schedule = getattr(sub, 'schedule', None)

        next_run = None
        if schedule and schedule.is_enabled:
            try:
                runs = get_next_runs(schedule.cron_string, count=1)
                next_run = runs[0].isoformat() if runs else None
            except Exception:
                pass

        data.append({
            'sub_id': sub.id,
            'name': sub.name,
            'main_scraper': sub.main_scraper.name,
            'main_scraper_id': sub.main_scraper_id,
            'is_running': bool(is_running),
            'pid': process.pid if process and is_running else None,
            'status': 'running' if is_running else (last_run.status if last_run else 'never_run'),
            'last_run_at': last_run.started_at.isoformat() if last_run else None,
            'next_run': next_run,
        })

    return JsonResponse({'scrapers': data})
