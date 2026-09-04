from django.urls import path

from .views import (
    production_cancel,
    production_complete,
    production_create,
    production_detail,
    production_list,
    production_start,
)


app_name = "production"

urlpatterns = [
    path(
        "",
        production_list,
        name="production_list",
    ),
    path(
        "scheme/<int:scheme_pk>/create/",
        production_create,
        name="production_create",
    ),
    path(
        "<int:pk>/",
        production_detail,
        name="production_detail",
    ),
    path(
        "<int:pk>/start/",
        production_start,
        name="production_start",
    ),
    path(
        "<int:pk>/complete/",
        production_complete,
        name="production_complete",
    ),
    path(
        "<int:pk>/cancel/",
        production_cancel,
        name="production_cancel",
    ),
]