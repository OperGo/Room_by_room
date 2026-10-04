"""Read-only view of receipt-reading jobs (Sprint 2C pilot).

    python manage.py receipt_jobs            # what a worker would send now + the last 20 jobs
    python manage.py receipt_jobs --limit 50

Shows only job metadata: status, attempts, timings, model, token usage and a short receipt reference.
Never prints merchants, amounts, file names or provider output, so it is safe to quote in reports.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.receipts.jobs import claimable_jobs
from apps.receipts.models import ExtractionJob

# USD per million tokens (input, output), Anthropic list prices as at October 2026. Cost basis only;
# the Anthropic Console's usage page is the authoritative bill.
PRICES = {"claude-haiku-4-5": (Decimal("1.00"), Decimal("5.00"))}


def _price(model):
    for prefix, price in PRICES.items():
        if (model or "").startswith(prefix):
            return price
    return None


def _ref(job):
    return str(job.draft.uuid)[:8] if job.draft_id else "-"


def _seconds(start, end):
    return f"{(end - start).total_seconds():.1f}" if start and end else "-"


class Command(BaseCommand):
    help = "List claimable receipt-reading jobs and recent job metadata (read-only)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20, help="How many recent jobs to list.")

    def handle(self, limit, **options):
        out = self.stdout.write
        claimable = list(claimable_jobs().select_related("draft"))
        out(f"Claimable now (a running worker would send these to the provider): {len(claimable)}")
        for job in claimable:
            out(f"  job {job.pk}  receipt {_ref(job)}  {job.status}  attempt {job.attempts}/{job.max_attempts}  "
                f"queued {job.created_at:%Y-%m-%d %H:%M}")
        jobs = list(ExtractionJob.objects.select_related("draft").order_by("-created_at", "-id")[:limit])
        out(f"\nRecent jobs (newest first, up to {limit}):")
        out("  job | receipt | status | result | attempts | queued→finished s | last attempt s | model | in/out tokens | error")
        total_in = total_out = 0
        cost = Decimal("0")
        unpriced = 0
        for job in jobs:
            usage = job.usage or {}
            tokens_in, tokens_out = usage.get("input_tokens") or 0, usage.get("output_tokens") or 0
            total_in, total_out = total_in + tokens_in, total_out + tokens_out
            price = _price(job.model_version)
            if price:
                cost += (tokens_in * price[0] + tokens_out * price[1]) / Decimal(1_000_000)
            elif tokens_in or tokens_out:
                unpriced += 1
            out(f"  {job.pk} | {_ref(job)} | {job.status} | {job.result_state} | {job.attempts}/{job.max_attempts} | "
                f"{_seconds(job.created_at, job.finished_at)} | {_seconds(job.started_at, job.finished_at)} | "
                f"{job.model_version or '-'} | {tokens_in}/{tokens_out} | {job.error_code or '-'}")
        out(f"\nTotals for listed jobs: {total_in} input / {total_out} output tokens; "
            f"estimated list-price cost US${cost.quantize(Decimal('0.0001'))}"
            + (f" (+{unpriced} job(s) on an unpriced model)" if unpriced else ""))
