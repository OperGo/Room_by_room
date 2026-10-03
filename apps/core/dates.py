import datetime

from django.utils import timezone


def local_today():
    """The owner's local date (Europe/Jersey via TIME_ZONE)."""
    return timezone.localdate()


def this_weekend_saturday(today=None):
    """Saturday of the current weekend (today if Saturday, yesterday if Sunday)."""
    today = today or local_today()
    weekday = today.weekday()  # Monday=0 ... Sunday=6
    if weekday == 6:
        return today - datetime.timedelta(days=1)
    return today + datetime.timedelta(days=5 - weekday)
