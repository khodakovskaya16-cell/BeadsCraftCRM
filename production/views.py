from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.views.decorators.http import require_POST

from materials.models import SchemeMaterial
from schemes.models import Scheme

from .forms import ProductionOrderForm
from .models import ProductionOrder


def production_list(
    request: HttpRequest,
) -> HttpResponse:
    """Відображає всі виробничі завдання."""

    productions = (
        ProductionOrder.objects
        .select_related("scheme")
        .all()
    )

    context = {
        "productions": productions,
    }

    return render(
        request,
        "production/production_list.html",
        context,
    )


def production_create(
    request: HttpRequest,
    scheme_pk: int,
) -> HttpResponse:
    """Створює виробниче завдання для схеми."""

    scheme = get_object_or_404(
        Scheme,
        pk=scheme_pk,
    )

    if request.method == "POST":
        form = ProductionOrderForm(
            request.POST
        )

        if form.is_valid():
            production = form.save(
                commit=False
            )

            production.scheme = scheme
            production.save()

            return redirect(
                "production:production_detail",
                pk=production.pk,
            )
    else:
        form = ProductionOrderForm()

    context = {
        "form": form,
        "scheme": scheme,
    }

    return render(
        request,
        "production/production_form.html",
        context,
    )


def production_detail(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    """Відображає виробниче завдання."""

    production = get_object_or_404(
        ProductionOrder.objects
        .select_related("scheme")
        .prefetch_related(
            "material_usages",
        ),
        pk=pk,
    )

    requirements = (
        SchemeMaterial.objects
        .select_related("material")
        .filter(scheme=production.scheme)
    )

    requirement_rows = []

    for requirement in requirements:
        required_total = (
            requirement.required_quantity
            * production.quantity
        )

        shortage = max(
            required_total
            - requirement.material.quantity_in_stock,
            Decimal("0.00"),
        )

        requirement_rows.append(
            {
                "requirement": requirement,
                "required_total": required_total,
                "available": shortage == 0,
                "shortage": shortage,
            }
        )

    all_available = (
        bool(requirement_rows)
        and all(
            row["available"]
            for row in requirement_rows
        )
    )

    context = {
        "production": production,
        "requirement_rows": requirement_rows,
        "all_available": all_available,
        "usages": production.material_usages.all(),
    }

    return render(
        request,
        "production/production_detail.html",
        context,
    )


@require_POST
def production_start(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    """Запускає виробництво та списує матеріали."""

    production = get_object_or_404(
        ProductionOrder,
        pk=pk,
    )

    try:
        production.start_production()

    except ValidationError as error:
        messages.error(
            request,
            " ".join(error.messages),
        )

    else:
        messages.success(
            request,
            "Виробництво розпочато. "
            "Матеріали списано зі складу.",
        )

    return redirect(
        "production:production_detail",
        pk=production.pk,
    )


@require_POST
def production_complete(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    """Завершує виробниче завдання."""

    production = get_object_or_404(
        ProductionOrder,
        pk=pk,
    )

    try:
        production.complete_production()

    except ValidationError as error:
        messages.error(
            request,
            " ".join(error.messages),
        )

    else:
        messages.success(
            request,
            "Виробниче завдання завершено.",
        )

    return redirect(
        "production:production_detail",
        pk=production.pk,
    )


@require_POST
def production_cancel(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    """Скасовує заплановане завдання."""

    production = get_object_or_404(
        ProductionOrder,
        pk=pk,
    )

    try:
        production.cancel_production()

    except ValidationError as error:
        messages.error(
            request,
            " ".join(error.messages),
        )

    else:
        messages.success(
            request,
            "Виробниче завдання скасовано.",
        )

    return redirect(
        "production:production_detail",
        pk=production.pk,
    )