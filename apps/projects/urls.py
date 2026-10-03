from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="list"),
    path("new/", views.project_create, name="create"),
    path("<uuid:uuid>/", views.project_detail, name="detail"),
    path("<uuid:uuid>/edit/", views.project_edit, name="edit"),
    path("<uuid:uuid>/status/", views.project_status, name="status"),
    path("<uuid:uuid>/tasks/new/", views.task_create, name="task_create"),
    path("<uuid:uuid>/photos/new/", views.photo_upload, name="photo_upload"),
    path("<uuid:uuid>/opening-balance/new/", views.opening_balance_create, name="opening_balance_create"),
    path("opening-balance/<uuid:uuid>/edit/", views.opening_balance_edit, name="opening_balance_edit"),
    path("tasks/<uuid:uuid>/", views.task_detail, name="task_detail"),
    path("tasks/<uuid:uuid>/edit/", views.task_edit, name="task_edit"),
    path("tasks/<uuid:uuid>/complete/", views.task_complete, name="task_complete"),
    path("tasks/<uuid:uuid>/status/", views.task_status, name="task_status"),
    path("tasks/<uuid:uuid>/weekend/", views.task_weekend, name="task_weekend"),
    path("tasks/<uuid:uuid>/dependencies/", views.task_dependencies, name="task_dependencies"),
    path("photos/<uuid:uuid>/file/", views.photo_file, name="photo_file"),
    path("photos/<uuid:uuid>/delete/", views.photo_delete, name="photo_delete"),
    path("photos/<uuid:uuid>/cover/", views.photo_cover, name="photo_cover"),
]
