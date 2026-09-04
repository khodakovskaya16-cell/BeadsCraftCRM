from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from schemes.models import Scheme
from telegram_bot.models import TelegramUser

from .forms import (
    MaterialForm,
    SchemeMaterialForm,
    StockMovementForm,
)
from .models import (
    Material,
    MaterialType,
    SchemeMaterial,
    StockMovement,
    UserMaterialStock,
)


# =====================================================
# ПОТОЧНИЙ КОРИСТУВАЧ
# =====================================================


def get_current_telegram_user(
    request: HttpRequest,
) -> TelegramUser:
    """Повертає Telegram-профіль поточного користувача сайту."""

    user = getattr(
        request,
        "user",
        None,
    )

    if (
        user is None
        or not user.is_authenticated
    ):
        raise PermissionDenied(
            "Потрібно увійти до системи."
        )

    telegram_user = (
        TelegramUser.objects
        .filter(
            django_user_id=user.pk,
            is_active=True,
        )
        .first()
    )

    if telegram_user is None:
        raise PermissionDenied(
            "Акаунт сайту не пов'язаний "
            "із Telegram-профілем."
        )

    return telegram_user


# =====================================================
# ПЕРСОНАЛЬНИЙ СКЛАД
# =====================================================


@login_required
def material_list(
    request: HttpRequest,
) -> HttpResponse:
    """Відображає персональний склад матеріалів."""

    telegram_user = get_current_telegram_user(
        request
    )

    stocks = (
        UserMaterialStock.objects
        .select_related(
            "material",
            "material__material_type",
        )
        .filter(
            owner=telegram_user
        )
    )

    query = request.GET.get(
        "q",
        "",
    ).strip()

    selected_type = request.GET.get(
        "material_type",
        "",
    )

    selected_stock = request.GET.get(
        "stock",
        "",
    )

    if query:
        stocks = stocks.filter(
            Q(
                material__name__icontains=query
            )
            | Q(
                material__manufacturer__icontains=query
            )
            | Q(
                material__article__icontains=query
            )
            | Q(
                material__color_name__icontains=query
            )
            | Q(
                material__color_code__icontains=query
            )
        )

    if selected_type:
        stocks = stocks.filter(
            material__material_type_id=selected_type
        )

    if selected_stock == "low":
        stocks = stocks.filter(
            quantity_in_stock__lte=F(
                "minimum_stock"
            )
        )

    elif selected_stock == "enough":
        stocks = stocks.filter(
            quantity_in_stock__gt=F(
                "minimum_stock"
            )
        )

    materials = []

    for stock in stocks:
        material = stock.material

        material.personal_quantity = (
            stock.quantity_in_stock
        )

        material.personal_minimum = (
            stock.minimum_stock
        )

        material.personal_is_low = (
            stock.is_low_stock
        )

        material.personal_stock_id = (
            stock.pk
        )

        materials.append(
            material
        )

    context = {
        "materials": materials,
        "material_types": (
            MaterialType.objects.all()
        ),
        "query": query,
        "selected_type": selected_type,
        "selected_stock": selected_stock,
    }

    return render(
        request,
        "materials/material_list.html",
        context,
    )


@login_required
def material_create(
    request: HttpRequest,
) -> HttpResponse:
    """Створює матеріал і персональний запас користувача."""

    telegram_user = get_current_telegram_user(
        request
    )

    if request.method == "POST":
        form = MaterialForm(
            request.POST
        )

        if form.is_valid():
            with transaction.atomic():
                material = form.save()

                UserMaterialStock.objects.create(
                    owner=telegram_user,
                    material=material,
                    quantity_in_stock=(
                        form.cleaned_data[
                            "stock_quantity"
                        ]
                    ),
                    minimum_stock=(
                        form.cleaned_data[
                            "stock_minimum"
                        ]
                    ),
                )

            return redirect(
                "materials:material_list"
            )

    else:
        form = MaterialForm()

    context = {
        "form": form,
        "page_title": "Додати матеріал",
        "button_text": "Зберегти матеріал",
        "cancel_url": reverse(
            "materials:material_list"
        ),
    }

    return render(
        request,
        "materials/material_form.html",
        context,
    )


@login_required
def material_update(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    """Редагує матеріал і персональний запас."""

    telegram_user = get_current_telegram_user(
        request
    )

    stock = get_object_or_404(
        UserMaterialStock.objects.select_related(
            "material",
            "material__material_type",
        ),
        owner=telegram_user,
        material_id=pk,
    )

    material = stock.material

    if request.method == "POST":
        form = MaterialForm(
            request.POST,
            instance=material,
            stock=stock,
        )

        if form.is_valid():
            with transaction.atomic():
                form.save()

                stock.quantity_in_stock = (
                    form.cleaned_data[
                        "stock_quantity"
                    ]
                )

                stock.minimum_stock = (
                    form.cleaned_data[
                        "stock_minimum"
                    ]
                )

                stock.save(
                    update_fields=(
                        "quantity_in_stock",
                        "minimum_stock",
                        "updated_at",
                    )
                )

            return redirect(
                "materials:material_list"
            )

    else:
        form = MaterialForm(
            instance=material,
            stock=stock,
        )

    context = {
        "form": form,
        "material": material,
        "stock": stock,
        "page_title": (
            f"Редагувати матеріал: "
            f"{material}"
        ),
        "button_text": "Зберегти зміни",
        "cancel_url": reverse(
            "materials:material_list"
        ),
    }

    return render(
        request,
        "materials/material_form.html",
        context,
    )


# =====================================================
# МАТЕРІАЛИ СХЕМ
# =====================================================


def scheme_material_create(
    request: HttpRequest,
    scheme_pk: int,
) -> HttpResponse:
    """Додає необхідний матеріал до схеми."""

    scheme = get_object_or_404(
        Scheme,
        pk=scheme_pk,
    )

    if request.method == "POST":
        form = SchemeMaterialForm(
            request.POST,
            scheme=scheme,
        )

        if form.is_valid():
            requirement = form.save(
                commit=False
            )

            requirement.scheme = scheme
            requirement.save()

            return redirect(
                "schemes:scheme_detail",
                pk=scheme.pk,
            )

    else:
        form = SchemeMaterialForm(
            scheme=scheme,
        )

    context = {
        "form": form,
        "scheme": scheme,
        "page_title": (
            f"Додати матеріал до схеми: "
            f"{scheme.title}"
        ),
        "button_text": "Додати матеріал",
        "cancel_url": reverse(
            "schemes:scheme_detail",
            kwargs={
                "pk": scheme.pk,
            },
        ),
    }

    return render(
        request,
        "materials/scheme_material_form.html",
        context,
    )


def scheme_material_update(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    """Редагує кількість матеріалу для схеми."""

    requirement = get_object_or_404(
        SchemeMaterial.objects.select_related(
            "scheme",
            "material",
        ),
        pk=pk,
    )

    scheme = requirement.scheme

    if request.method == "POST":
        form = SchemeMaterialForm(
            request.POST,
            instance=requirement,
            scheme=scheme,
        )

        if form.is_valid():
            form.save()

            return redirect(
                "schemes:scheme_detail",
                pk=scheme.pk,
            )

    else:
        form = SchemeMaterialForm(
            instance=requirement,
            scheme=scheme,
        )

    context = {
        "form": form,
        "scheme": scheme,
        "requirement": requirement,
        "page_title": (
            f"Редагувати матеріал схеми: "
            f"{scheme.title}"
        ),
        "button_text": "Зберегти зміни",
        "cancel_url": reverse(
            "schemes:scheme_detail",
            kwargs={
                "pk": scheme.pk,
            },
        ),
    }

    return render(
        request,
        "materials/scheme_material_form.html",
        context,
    )


def scheme_material_delete(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    """Видаляє матеріал зі списку потреб схеми."""

    requirement = get_object_or_404(
        SchemeMaterial.objects.select_related(
            "scheme",
            "material",
        ),
        pk=pk,
    )

    scheme_pk = requirement.scheme_id

    if request.method == "POST":
        requirement.delete()

        return redirect(
            "schemes:scheme_detail",
            pk=scheme_pk,
        )

    context = {
        "requirement": requirement,
        "scheme": requirement.scheme,
    }

    return render(
        request,
        "materials/scheme_material_confirm_delete.html",
        context,
    )


# =====================================================
# ЖУРНАЛ РУХУ МАТЕРІАЛІВ
# =====================================================


@login_required
def stock_movement_list(
    request: HttpRequest,
) -> HttpResponse:
    """Відображає персональний журнал руху матеріалів."""

    telegram_user = get_current_telegram_user(
        request
    )

    movements = (
        StockMovement.objects
        .select_related(
            "material",
            "material__material_type",
            "stock",
        )
        .filter(
            stock__owner=telegram_user
        )
    )

    query = request.GET.get(
        "q",
        "",
    ).strip()

    selected_type = request.GET.get(
        "movement_type",
        "",
    )

    if query:
        movements = movements.filter(
            Q(
                material__name__icontains=query
            )
            | Q(
                material__article__icontains=query
            )
            | Q(
                material__color_name__icontains=query
            )
            | Q(
                material__color_code__icontains=query
            )
            | Q(
                note__icontains=query
            )
        )

    if selected_type:
        movements = movements.filter(
            movement_type=selected_type
        )

    context = {
        "movements": movements,
        "query": query,
        "selected_type": selected_type,
        "movement_type_choices": (
            StockMovement.MovementType.choices
        ),
    }

    return render(
        request,
        "materials/stock_movement_list.html",
        context,
    )


@login_required
def stock_movement_create(
    request: HttpRequest,
    material_pk: int,
    movement_type: str,
) -> HttpResponse:
    """Створює рух персонального запасу матеріалу."""

    if (
        movement_type
        not in StockMovement.MovementType.values
    ):
        raise Http404(
            "Невідомий тип операції."
        )

    telegram_user = get_current_telegram_user(
        request
    )

    stock = get_object_or_404(
        UserMaterialStock.objects.select_related(
            "material",
            "material__material_type",
        ),
        owner=telegram_user,
        material_id=material_pk,
    )

    material = stock.material

    form = StockMovementForm(
        request.POST or None,
        stock=stock,
        movement_type=movement_type,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        try:
            StockMovement.create_and_apply(
                stock=stock,
                movement_type=movement_type,
                quantity=(
                    form.cleaned_data[
                        "quantity"
                    ]
                ),
                note=(
                    form.cleaned_data[
                        "note"
                    ]
                ),
            )

        except ValidationError as error:
            form.add_error(
                None,
                " ".join(
                    error.messages
                ),
            )

        else:
            return redirect(
                "materials:stock_movement_list"
            )

    movement_label = (
        StockMovement.MovementType(
            movement_type
        ).label
    )

    context = {
        "form": form,
        "material": material,
        "stock": stock,
        "movement_type": movement_type,
        "movement_label": movement_label,
        "page_title": (
            f"{movement_label}: "
            f"{material}"
        ),
        "button_text": movement_label,
        "is_write_off": (
            movement_type
            == StockMovement.MovementType.WRITE_OFF
        ),
    }

    return render(
        request,
        "materials/stock_movement_form.html",
        context,
    )