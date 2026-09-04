from django.urls import path

from .views import (
    cart_build,
    cart_detail,
    checkout,
    order_list,
    order_success,
)


app_name = "shop"

urlpatterns = [
    path(
        "",
        order_list,
        name="order_list",
    ),

    path(
        "scheme/<int:scheme_pk>/build/",
        cart_build,
        name="cart_build",
    ),

    path(
        "cart/<int:pk>/",
        cart_detail,
        name="cart_detail",
    ),

    path(
        "cart/<int:pk>/checkout/",
        checkout,
        name="checkout",
    ),

    path(
        "order/<int:pk>/success/",
        order_success,
        name="order_success",
    ),
]