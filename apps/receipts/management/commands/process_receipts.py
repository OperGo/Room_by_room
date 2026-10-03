import signal
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from apps.receipts.extraction import get_extractor
from apps.receipts.jobs import process_available


class Command(BaseCommand):
    help = "Read queued receipts outside the web request. Use --once (cron/testing) or --watch (long-running worker)."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--once", action="store_true", help="Process claimable jobs, then exit.")
        mode.add_argument("--watch", action="store_true", help="Keep polling for jobs until stopped.")
        parser.add_argument("--interval", type=float, default=3.0, help="Seconds between polls in --watch mode.")
        parser.add_argument("--max-jobs", type=int, default=None, help="Stop after this many jobs (--once).")

    def handle(self, once, watch, interval, max_jobs, **options):
        extractor = get_extractor()
        if extractor is None:
            self.stderr.write("Automatic extraction not configured (ANTHROPIC_API_KEY / RECEIPT_MODEL); "
                              "queued jobs will be marked failed with that reason.")
        elif extractor.is_test_double:
            self.stderr.write(self.style.WARNING("Using the FAKE test extractor: results are synthetic."))
        if once:
            count = process_available(max_jobs=max_jobs)
            self.stdout.write(f"Processed {count} job(s).")
            return
        if interval <= 0:
            raise CommandError("--interval must be positive.")
        stop = {"flag": False}

        def _stop(*_):
            stop["flag"] = True

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)
        self.stdout.write("Watching for receipt jobs. Press Ctrl+C to stop.")
        # One job per iteration, and the stop flag is checked before every claim: on SIGTERM the
        # job in hand finishes, nothing new is claimed and the worker never sleeps once stopping.
        while not stop["flag"]:
            close_old_connections()
            if process_available(max_jobs=1):
                self.stdout.write("Processed 1 job(s).")
                continue  # look for the next job straight away (after re-checking the flag)
            self._idle(interval, stop)
        self.stdout.write("Stopped.")

    @staticmethod
    def _idle(interval, stop):
        """Wait up to ``interval`` seconds between empty polls, waking promptly when asked to stop."""
        deadline = time.monotonic() + interval
        while not stop["flag"]:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(remaining, 0.2))
