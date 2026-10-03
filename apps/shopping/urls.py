from django.urls import path

from . import views

app_name = "shopping"

urlpatterns = [
    path("", views.shopping_list, name="list"),
    path("new/", views.item_create, name="create"),
    path("<uuid:uuid>/edit/", views.item_edit, name="edit"),
    path("<uuid:uuid>/bought/", views.item_toggle_bought, name="toggle_bought"),
    path("<uuid:uuid>/delete/", views.item_delete, name="delete"),
]
