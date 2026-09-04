from django.db.models import F
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from materials.models import Material, StockMovement
from production.models import ProductionOrder
from schemes.models import Scheme
from schemes.views import get_favorite_scheme_ids
from shop.models import Order


def dashboard_home(
    request: HttpRequest,
) -> HttpResponse:
    """Відображає головну панель BeadsCraft CRM."""

    low_stock_materials = (
        Material.objects
        .select_related("material_type")
        .filter(
            quantity_in_stock__lte=F("minimum_stock")
        )
    )

    active_productions = (
        ProductionOrder.objects
        .select_related("scheme")
        .filter(
            status__in=(
                ProductionOrder.Status.PLANNED,
                ProductionOrder.Status.IN_PROGRESS,
            )
        )
    )

    recent_orders = (
        Order.objects
        .select_related(
            "cart",
            "cart__scheme",
        )
        .order_by(
            "-created_at",
            "-pk",
        )[:5]
    )

    recent_movements = (
        StockMovement.objects
        .select_related("material")
        .order_by(
            "-created_at",
            "-pk",
        )[:5]
    )

    favorite_scheme_ids = get_favorite_scheme_ids(
        request
    )

    favorite_schemes_count = (
        Scheme.objects
        .filter(
            pk__in=favorite_scheme_ids,
            visibility=Scheme.Visibility.PUBLIC,
        )
        .count()
    )

    context = {
        "schemes_count": (
            Scheme.objects.count()
        ),

        "favorite_schemes_count": (
            favorite_schemes_count
        ),

        "materials_count": (
            Material.objects.count()
        ),

        "low_stock_count": (
            low_stock_materials.count()
        ),

        "orders_count": (
            Order.objects.count()
        ),

        "new_orders_count": (
            Order.objects
            .filter(status=Order.Status.NEW)
            .count()
        ),

        "active_productions_count": (
            active_productions.count()
        ),

        "completed_productions_count": (
            ProductionOrder.objects
            .filter(
                status=ProductionOrder.Status.COMPLETED
            )
            .count()
        ),

        "low_stock_materials": (
            low_stock_materials[:5]
        ),

        "active_productions": (
            active_productions[:5]
        ),

        "recent_orders": recent_orders,

        "recent_movements": recent_movements,
    }

    return render(
        request,
        "dashboard/dashboard_home.html",
        context,
    )