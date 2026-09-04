from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import SchemeForm
from .models import Scheme


FAVORITE_SCHEMES_SESSION_KEY = "favorite_scheme_ids"


def get_favorite_scheme_ids(
    request: HttpRequest,
) -> set[int]:
    """Повертає ID обраних схем із сесії браузера."""

    raw_ids = request.session.get(
        FAVORITE_SCHEMES_SESSION_KEY,
        [],
    )

    favorite_ids: set[int] = set()

    for raw_id in raw_ids:
        try:
            favorite_ids.add(int(raw_id))
        except (TypeError, ValueError):
            continue

    return favorite_ids


def save_favorite_scheme_ids(
    request: HttpRequest,
    favorite_ids: set[int],
) -> None:
    """Зберігає список обраних схем у сесії браузера."""

    request.session[
        FAVORITE_SCHEMES_SESSION_KEY
    ] = sorted(favorite_ids)

    request.session.modified = True


def get_public_schemes_queryset():
    """Повертає загальнодоступні схеми для вебсайту."""

    return Scheme.objects.filter(
        visibility=Scheme.Visibility.PUBLIC,
    )


def scheme_list(request: HttpRequest) -> HttpResponse:
    """Відображає каталог схем із пошуком і фільтрами."""

    schemes_queryset = (
        get_public_schemes_queryset()
        .prefetch_related("tags")
    )

    query = request.GET.get(
        "q",
        "",
    ).strip()

    selected_category = request.GET.get(
        "category",
        "",
    )

    selected_status = request.GET.get(
        "status",
        "",
    )

    if query:
        schemes_queryset = schemes_queryset.filter(
            Q(title__icontains=query)
            | Q(author__icontains=query)
            | Q(description__icontains=query)
            | Q(subcategory__icontains=query)
            | Q(tags__name__icontains=query)
        ).distinct()

    if selected_category:
        schemes_queryset = schemes_queryset.filter(
            category=selected_category,
        )

    if selected_status:
        schemes_queryset = schemes_queryset.filter(
            status=selected_status,
        )

    favorite_ids = get_favorite_scheme_ids(
        request
    )

    schemes = list(
        schemes_queryset
    )

    for scheme in schemes:
        scheme.is_favorite = (
            scheme.pk in favorite_ids
        )

    context = {
        "schemes": schemes,
        "query": query,
        "selected_category": selected_category,
        "selected_status": selected_status,
        "category_choices": Scheme.Category.choices,
        "status_choices": Scheme.Status.choices,
    }

    return render(
        request,
        "schemes/scheme_list.html",
        context,
    )


def scheme_detail(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    """Відображає детальну картку схеми."""

    scheme = get_object_or_404(
        get_public_schemes_queryset().prefetch_related(
            "tags",
            "material_requirements__material",
        ),
        pk=pk,
    )

    favorite_ids = get_favorite_scheme_ids(
        request
    )

    scheme.is_favorite = (
        scheme.pk in favorite_ids
    )

    context = {
        "scheme": scheme,
    }

    return render(
        request,
        "schemes/scheme_detail.html",
        context,
    )


def scheme_create(request: HttpRequest) -> HttpResponse:
    """Створює нову загальнодоступну схему."""

    if request.method == "POST":
        form = SchemeForm(
            request.POST,
            request.FILES,
        )

        if form.is_valid():
            scheme = form.save(
                commit=False
            )

            scheme.owner = None
            scheme.visibility = (
                Scheme.Visibility.PUBLIC
            )

            scheme.save()
            form.save_m2m()

            return redirect(
                "schemes:scheme_detail",
                pk=scheme.pk,
            )
    else:
        form = SchemeForm()

    context = {
        "form": form,
        "page_title": "Додати схему",
        "button_text": "Зберегти схему",
        "cancel_url": reverse(
            "schemes:scheme_list"
        ),
    }

    return render(
        request,
        "schemes/scheme_form.html",
        context,
    )


def scheme_update(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    """Редагує загальнодоступну схему."""

    scheme = get_object_or_404(
        get_public_schemes_queryset(),
        pk=pk,
    )

    if request.method == "POST":
        form = SchemeForm(
            request.POST,
            request.FILES,
            instance=scheme,
        )

        if form.is_valid():
            updated_scheme = form.save()

            return redirect(
                "schemes:scheme_detail",
                pk=updated_scheme.pk,
            )
    else:
        form = SchemeForm(
            instance=scheme
        )

    context = {
        "form": form,
        "scheme": scheme,
        "page_title": (
            f"Редагувати схему: "
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
        "schemes/scheme_form.html",
        context,
    )


@require_POST
def scheme_toggle_favorite(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    """
    Додає схему до персонального обраного
    поточного браузера або видаляє її.
    """

    scheme = get_object_or_404(
        get_public_schemes_queryset(),
        pk=pk,
    )

    favorite_ids = get_favorite_scheme_ids(
        request
    )

    if scheme.pk in favorite_ids:
        favorite_ids.remove(
            scheme.pk
        )
    else:
        favorite_ids.add(
            scheme.pk
        )

    save_favorite_scheme_ids(
        request,
        favorite_ids,
    )

    return redirect(
        "schemes:scheme_detail",
        pk=scheme.pk,
    )


def scheme_delete(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    """Показує підтвердження та видаляє схему."""

    scheme = get_object_or_404(
        get_public_schemes_queryset(),
        pk=pk,
    )

    if request.method == "POST":
        scheme.delete()

        favorite_ids = get_favorite_scheme_ids(
            request
        )

        favorite_ids.discard(
            pk
        )

        save_favorite_scheme_ids(
            request,
            favorite_ids,
        )

        return redirect(
            "schemes:scheme_list"
        )

    context = {
        "scheme": scheme,
    }

    return render(
        request,
        "schemes/scheme_confirm_delete.html",
        context,
    )