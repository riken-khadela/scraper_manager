import os
import pty
import re
import signal
import subprocess
import threading
import time
import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

# Strip ANSI escape sequences and carriage returns from PTY output
_ANSI_ESCAPE = re.compile(
    rb'(\x9B|\x1B\[)[0-?]*[ -/]*[@-~]'
    rb'|\x1B[^[\]]*'
    rb'|\x0D'
)


def _strip_ansi(data: bytes) -> bytes:
    return _ANSI_ESCAPE.sub(b'', data)


def get_live_log_path(sub_id: int) -> str:
    return f'/tmp/scraper_live_{sub_id}.log'


def get_stdin_queue_path(sub_id: int) -> str:
    return f'/tmp/scraper_stdin_{sub_id}'


@shared_task(bind=True, name='dashboard.tasks.run_scraper_task')
def run_scraper_task(self, sub_scraper_id, triggered_by='manual'):
    """Execute a scraper script via PTY, streaming stdout/stderr live.

    Output is written line-by-line to /tmp/scraper_live_{id}.log.
    Stdin input is forwarded from /tmp/scraper_stdin_{id} (a queue file).
    This allows browser-based interactive input (pdb, input(), etc.).
    """
    from dashboard.models import SubScraper, ScraperRunHistory, ScraperProcess

    try:
        sub_scraper = SubScraper.objects.get(id=sub_scraper_id)
    except SubScraper.DoesNotExist:
        logger.error(f"SubScraper {sub_scraper_id} not found")
        return {'status': 'error', 'message': 'SubScraper not found'}

    run_record = ScraperRunHistory.objects.create(
        sub_scraper=sub_scraper,
        triggered_by=triggered_by,
        status='running',
        started_at=timezone.now(),
    )

    # Clear any stale process record
    ScraperProcess.objects.filter(sub_scraper=sub_scraper).delete()

    run_command = sub_scraper.run_command
    if not run_command:
        run_record.status = 'failed'
        run_record.ended_at = timezone.now()
        run_record.notes = 'No run command configured'
        run_record.duration_seconds = 0
        run_record.save()
        return {'status': 'failed', 'message': 'No run command configured'}

    live_log_path = get_live_log_path(sub_scraper_id)
    stdin_queue_path = get_stdin_queue_path(sub_scraper_id)

    # Clear old files and create fresh stdin queue
    for path in [live_log_path, stdin_queue_path]:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    # Create empty stdin queue file
    try:
        open(stdin_queue_path, 'w').close()
    except OSError:
        pass

    start_time = time.time()
    master_fd = None
    slave_fd = None
    process = None

    try:
        # Open a pseudo-terminal pair — enables interactive scripts
        master_fd, slave_fd = pty.openpty()

        process = subprocess.Popen(
            run_command,
            shell=True,
            executable='/bin/bash',   # bash supports `source`, /bin/sh (Dash) does NOT
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
            preexec_fn=os.setsid,
        )
        # Close slave end in parent — only the child needs it
        os.close(slave_fd)
        slave_fd = None

        proc_record = ScraperProcess.objects.create(
            sub_scraper=sub_scraper,
            pid=process.pid,
            started_at=timezone.now(),
            is_running=True,
            celery_task_id=self.request.id,
        )

        stop_event = threading.Event()

        # ── Thread 1: Read PTY output → live log file ──────────────────
        def output_reader():
            try:
                with open(live_log_path, 'wb') as log_f:
                    while True:
                        try:
                            data = os.read(master_fd, 4096)
                            if not data:
                                break
                            cleaned = _strip_ansi(data)
                            log_f.write(cleaned)
                            log_f.flush()
                        except OSError:
                            # EIO means PTY slave closed (process ended)
                            break
            except Exception as exc:
                logger.error(f"Output reader error for scraper {sub_scraper_id}: {exc}")
            finally:
                stop_event.set()

        # ── Thread 2: stdin queue file → master PTY ────────────────────
        def stdin_forwarder():
            stdin_offset = 0
            while not stop_event.is_set():
                time.sleep(0.05)
                try:
                    with open(stdin_queue_path, 'rb') as f:
                        f.seek(stdin_offset)
                        data = f.read()
                    if data:
                        try:
                            os.write(master_fd, data)
                        except OSError:
                            break
                        stdin_offset += len(data)
                except (OSError, FileNotFoundError):
                    pass

        t_output = threading.Thread(target=output_reader, daemon=True)
        t_stdin = threading.Thread(target=stdin_forwarder, daemon=True)
        t_output.start()
        t_stdin.start()

        # Wait for process to finish
        process.wait()
        stop_event.set()
        t_output.join(timeout=3)
        t_stdin.join(timeout=1)

        duration = time.time() - start_time

        try:
            os.close(master_fd)
        except OSError:
            pass
        master_fd = None

        proc_record.is_running = False
        proc_record.save()

        run_record.status = 'success' if process.returncode == 0 else 'failed'
        run_record.ended_at = timezone.now()
        run_record.duration_seconds = round(duration, 2)

        # Save last portion of log output as notes
        try:
            with open(live_log_path, 'r', errors='replace') as f:
                content = f.read()
            run_record.notes = content[-2000:] if len(content) > 2000 else content
        except Exception:
            pass

        run_record.save()

        # Remove stdin queue
        try:
            os.remove(stdin_queue_path)
        except OSError:
            pass

        return {
            'status': run_record.status,
            'duration': duration,
            'returncode': process.returncode,
        }

    except Exception as e:
        duration = time.time() - start_time
        run_record.status = 'failed'
        run_record.ended_at = timezone.now()
        run_record.duration_seconds = round(duration, 2)
        run_record.notes = f"Exception: {str(e)}"
        run_record.save()

        if process:
            ScraperProcess.objects.filter(
                sub_scraper=sub_scraper, pid=process.pid
            ).update(is_running=False)

        for fd in [master_fd, slave_fd]:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass

        try:
            os.remove(stdin_queue_path)
        except OSError:
            pass

        logger.exception(f"Error running scraper {sub_scraper_id}")
        return {'status': 'failed', 'message': str(e)}
