from django.urls import path

from . import views

app_name = "costs"

urlpatterns = [
    path("", views.cost_index, name="index"),
    path("purchases/new/", views.purchase_create, name="purchase_create"),
    path("purchases/<uuid:uuid>/", views.purchase_detail, name="purchase_detail"),
    path("purchases/<uuid:uuid>/correct/", views.purchase_edit, name="purchase_edit"),
    path("purchases/<uuid:uuid>/void/", views.purchase_void, name="purchase_void"),
    path("purchases/<uuid:uuid>/refund/", views.purchase_refund, name="purchase_refund"),
]
