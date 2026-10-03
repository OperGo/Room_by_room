def navigation(request):
    match = getattr(request, "resolver_match", None)
    namespace = match.namespace if match else ""
    url_name = match.url_name if match else ""
    active = {
        "core": "home",
        "projects": "projects",
        "shopping": "shopping",
        "costs": "costs",
        "receipts": "costs",
    }.get(namespace, "")
    return {"nav_active": active, "nav_url_name": url_name}
