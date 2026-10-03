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
    path("<uuid:uuid>/read/", views.receipt_read, name="read"),
    path("<uuid:uuid>/reading.json", views.receipt_reading_status, name="reading_status"),
    path("<uuid:uuid>/apply-reading/", views.receipt_apply_reading, name="apply_reading"),
    path("file/<uuid:uuid>/", views.receipt_file, name="file"),
]
