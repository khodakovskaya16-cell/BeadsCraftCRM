from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.views.decorators.http import require_POST

from schemes.models import Scheme

from .forms import OrderForm
from .models import (
    Cart,
    CartItem,
    Order,
    OrderItem,
)


@require_POST
def cart_build(
    request: HttpRequest,
    scheme_pk: int,
) -> HttpResponse:
    """Формує кошик із дефіцитних матеріалів схеми."""

    scheme = get_object_or_404(
        Scheme.objects.prefetch_related(
            "material_requirements__material"
        ),
        pk=scheme_pk,
    )

    with transaction.atomic():
        active_carts = Cart.objects.filter(
            scheme=scheme,
            status=Cart.Status.ACTIVE,
        ).order_by("-updated_at", "-pk")

        cart = active_carts.first()

        if cart is None:
            cart = Cart.objects.create(
                scheme=scheme,
                status=Cart.Status.ACTIVE,
            )
        else:
            active_carts.exclude(
                pk=cart.pk
            ).delete()

        cart.items.all().delete()

        cart_items = []

        for requirement in (
            scheme.material_requirements.all()
        ):
            shortage = requirement.shortage

            if shortage > 0:
                cart_items.append(
                    CartItem(
                        cart=cart,
                        material=requirement.material,
                        quantity=shortage,
                    )
                )

        CartItem.objects.bulk_create(
            cart_items
        )

        cart.save(
            update_fields=[
                "updated_at",
            ]
        )

    return redirect(
        "shop:cart_detail",
        pk=cart.pk,
    )


def cart_detail(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    """Відображає сформований кошик."""

    cart = get_object_or_404(
        Cart.objects.select_related(
            "scheme"
        ),
        pk=pk,
    )

    items = cart.items.select_related(
        "material",
        "material__material_type",
    ).all()

    context = {
        "cart": cart,
        "items": items,
    }

    return render(
        request,
        "shop/cart_detail.html",
        context,
    )


def checkout(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    """Оформлює замовлення з активного кошика."""

    cart = get_object_or_404(
        Cart.objects.select_related(
            "scheme"
        ).prefetch_related(
            "items__material"
        ),
        pk=pk,
        status=Cart.Status.ACTIVE,
    )

    items = cart.items.select_related(
        "material"
    ).all()

    if not items.exists():
        return redirect(
            "shop:cart_detail",
            pk=cart.pk,
        )

    if request.method == "POST":
        form = OrderForm(
            request.POST
        )

        if form.is_valid():
            with transaction.atomic():
                order = form.save(
                    commit=False
                )

                order.cart = cart
                order.save()

                order_items = []

                for cart_item in items:
                    material = cart_item.material

                    order_items.append(
                        OrderItem(
                            order=order,
                            material=material,
                            material_name=material.name,
                            article=material.article,
                            color_name=material.color_name,
                            unit_label=(
                                material.get_unit_display()
                            ),
                            quantity=cart_item.quantity,
                        )
                    )

                OrderItem.objects.bulk_create(
                    order_items
                )

                cart.status = Cart.Status.ORDERED

                cart.save(
                    update_fields=[
                        "status",
                        "updated_at",
                    ]
                )

            return redirect(
                "shop:order_success",
                pk=order.pk,
            )
    else:
        form = OrderForm()

    context = {
        "cart": cart,
        "items": items,
        "form": form,
    }

    return render(
        request,
        "shop/checkout.html",
        context,
    )


def order_success(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    """Відображає підтвердження оформлення."""

    order = get_object_or_404(
        Order.objects.select_related(
            "cart",
            "cart__scheme",
        ).prefetch_related(
            "items",
        ),
        pk=pk,
    )

    context = {
        "order": order,
        "items": order.items.all(),
    }

    return render(
        request,
        "shop/order_success.html",
        context,
    )
def order_list(
    request: HttpRequest,
) -> HttpResponse:
    """Відображає список оформлених замовлень."""

    orders = (
        Order.objects
        .select_related(
            "cart",
            "cart__scheme",
        )
        .prefetch_related("items")
        .all()
    )

    context = {
        "orders": orders,
    }

    return render(
        request,
        "shop/order_list.html",
        context,
    )