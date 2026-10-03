from django.contrib import messages
from django.shortcuts import get_object_or_404


def owned(model, user, **lookup):
    """Fetch a record only if it belongs to ``user``. Other owners get a 404."""
    return get_object_or_404(model.objects.for_owner(user), **lookup)


def flash_errors(request, exc):
    for message in getattr(exc, "messages", [str(exc)]):
        messages.error(request, message)


def safe_next(request, default):
    """Return the posted ``next`` URL if it is local, otherwise ``default``."""
    from django.utils.http import url_has_allowed_host_and_scheme

    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return target
    return default


def parse_uuid(value):
    import uuid

    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None
