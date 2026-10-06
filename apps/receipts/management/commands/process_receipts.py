import signal
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, close_old_connections, connections
from django.db.migrations.executor import MigrationExecutor

from apps.receipts.extraction import get_extractor
from apps.receipts.jobs import claimable_jobs, process_available


def pending_migrations():
    """Names of migrations not yet applied to the database (empty when the schema is current).

    The web service applies migrations when it starts; with auto-deploy the cron job can start the new code
    first. The worker must not claim or touch jobs until the schema matches the code. Database errors raised
    while checking are not treated as "pending": they propagate as real failures."""
    executor = MigrationExecutor(connections[DEFAULT_DB_ALIAS])
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return [f"{migration.app_label}.{migration.name}" for migration, backwards in plan if not backwards]


class Command(BaseCommand):
    help = "Read queued receipts outside the web request. Use --once (cron/testing) or --watch (long-running worker)."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--once", action="store_true", help="Process claimable jobs, then exit.")
        mode.add_argument("--watch", action="store_true", help="Keep polling for jobs until stopped.")
        parser.add_argument("--interval", type=float, default=3.0, help="Seconds between polls in --watch mode.")
        parser.add_argument("--max-jobs", type=int, default=None, help="Stop after this many jobs (--once).")

    def say(self, message):
        # Flush every line: on Render stdout is a pipe, and buffered lines would appear late or never.
        self.stdout.write(message)
        self.stdout.flush()

    def handle(self, once, watch, interval, max_jobs, **options):
        if watch and interval <= 0:
            raise CommandError("--interval must be positive.")
        extractor = get_extractor()
        if extractor is None:
            self.stderr.write("Automatic extraction not configured (ANTHROPIC_API_KEY / RECEIPT_MODEL); "
                              "queued jobs will be marked failed with that reason.")
        elif extractor.is_test_double:
            self.stderr.write(self.style.WARNING("Using the FAKE test extractor: results are synthetic."))
        waiting = pending_migrations()
        if waiting and once:
            self._say_deferred(waiting)
            return  # exit 0: the next scheduled run tries again
        if waiting:
            self._say_deferred(waiting)
            stop = self._install_stop()
            while waiting and not stop["flag"]:
                self._idle(interval, stop)
                close_old_connections()
                waiting = pending_migrations()
            if stop["flag"]:
                self.say("Stopped.")
                return
            self.say("Database migrations applied; starting.")
        # Say up front which jobs would be sent to the provider, so nothing is read unannounced.
        pending = list(claimable_jobs().values_list("pk", flat=True)[:20])
        self.say(f"Claimable at start: {len(pending)} job(s)" + (f" (ids {pending})" if pending else ""))
        if once:
            count = process_available(max_jobs=max_jobs)
            self.say(f"Processed {count} job(s).")
            return
        stop = self._install_stop()
        self.say("Watching for receipt jobs. Press Ctrl+C to stop.")
        # One job per iteration, and the stop flag is checked before every claim: on SIGTERM the
        # job in hand finishes, nothing new is claimed and the worker never sleeps once stopping.
        while not stop["flag"]:
            close_old_connections()
            if process_available(max_jobs=1):
                self.say("Processed 1 job(s).")
                continue  # look for the next job straight away (after re-checking the flag)
            self._idle(interval, stop)
        self.say("Stopped.")

    def _say_deferred(self, waiting):
        self.say(f"Deferred: database migrations not yet applied ({', '.join(waiting)}). No jobs claimed or "
                 "changed; reading resumes once the web deploy has migrated.")

    def _install_stop(self):
        if getattr(self, "_stop_flag", None) is None:
            self._stop_flag = {"flag": False}

            def _stop(*_):
                self._stop_flag["flag"] = True

            signal.signal(signal.SIGTERM, _stop)
            signal.signal(signal.SIGINT, _stop)
        return self._stop_flag

    @staticmethod
    def _idle(interval, stop):
        """Wait up to ``interval`` seconds between empty polls, waking promptly when asked to stop."""
        deadline = time.monotonic() + interval
        while not stop["flag"]:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(remaining, 0.2))
