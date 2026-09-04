from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path(
        "admin/",
        admin.site.urls,
    ),

    path(
        "",
        include("dashboard.urls"),
    ),

    path(
        "schemes/",
        include("schemes.urls"),
    ),

    path(
        "materials/",
        include("materials.urls"),
    ),

    path(
        "shop/",
        include("shop.urls"),
    ),

    path(
        "production/",
        include("production.urls"),
    ),
]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )