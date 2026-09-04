from django.urls import path

from .views import (
    material_create,
    material_list,
    material_update,
    scheme_material_create,
    scheme_material_delete,
    scheme_material_update,
    stock_movement_create,
    stock_movement_list,
)


app_name = "materials"

urlpatterns = [
    path(
        "",
        material_list,
        name="material_list",
    ),
    path(
        "create/",
        material_create,
        name="material_create",
    ),
    path(
        "<int:pk>/edit/",
        material_update,
        name="material_update",
    ),
    path(
        "movements/",
        stock_movement_list,
        name="stock_movement_list",
    ),
    path(
        "movements/<int:material_pk>/<str:movement_type>/create/",
        stock_movement_create,
        name="stock_movement_create",
    ),
    path(
        "requirements/scheme/<int:scheme_pk>/create/",
        scheme_material_create,
        name="scheme_material_create",
    ),
    path(
        "requirements/<int:pk>/edit/",
        scheme_material_update,
        name="scheme_material_update",
    ),
    path(
        "requirements/<int:pk>/delete/",
        scheme_material_delete,
        name="scheme_material_delete",
    ),
]