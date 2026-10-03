from django.urls import include, path

urlpatterns = [
    path("", include("apps.core.urls")),
    path("account/", include("apps.accounts.urls")),
    path("projects/", include("apps.projects.urls")),
    path("shopping/", include("apps.shopping.urls")),
    path("costs/", include("apps.costs.urls")),
    path("receipts/", include("apps.receipts.urls")),
]
