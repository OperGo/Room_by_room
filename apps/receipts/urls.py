from django.urls import path

from . import views

app_name = "receipts"

urlpatterns = [
    path("new/", views.receipt_new, name="new"),
    path("<uuid:uuid>/", views.receipt_review, name="review"),
    path("<uuid:uuid>/save/", views.receipt_save, name="save"),
    path("<uuid:uuid>/confirm/", views.receipt_confirm, name="confirm"),
    path("<uuid:uuid>/attach/", views.receipt_attach, name="attach"),
    path("<uuid:uuid>/discard/", views.receipt_discard, name="discard"),
    path("file/<uuid:uuid>/", views.receipt_file, name="file"),
]
