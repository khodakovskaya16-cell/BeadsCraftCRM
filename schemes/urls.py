from django.urls import path

from .views import (
    scheme_create,
    scheme_delete,
    scheme_detail,
    scheme_list,
    scheme_toggle_favorite,
    scheme_update,
)


app_name = "schemes"

urlpatterns = [
    path(
        "",
        scheme_list,
        name="scheme_list",
    ),
    path(
        "create/",
        scheme_create,
        name="scheme_create",
    ),
    path(
        "<int:pk>/edit/",
        scheme_update,
        name="scheme_update",
    ),
    path(
        "<int:pk>/favorite/",
        scheme_toggle_favorite,
        name="scheme_toggle_favorite",
    ),
    path(
        "<int:pk>/delete/",
        scheme_delete,
        name="scheme_delete",
    ),
    path(
        "<int:pk>/",
        scheme_detail,
        name="scheme_detail",
    ),
]