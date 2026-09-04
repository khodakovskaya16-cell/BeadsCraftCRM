from django.contrib import admin
from django.db.models import Count

from materials.models import SchemeMaterial

from .models import Scheme, SchemeFavorite, Tag


class SchemeMaterialInline(admin.TabularInline):
    model = SchemeMaterial

    fields = (
        "material",
        "required_quantity",
        "notes",
    )

    autocomplete_fields = (
        "material",
    )

    extra = 1


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
    )

    search_fields = (
        "name",
    )

    ordering = (
        "name",
    )


@admin.register(Scheme)
class SchemeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "owner_display",
        "visibility",
        "source",
        "category",
        "difficulty",
        "status",
        "favorites_count",
        "created_at",
    )

    list_filter = (
        "visibility",
        (
            "owner",
            admin.RelatedOnlyFieldListFilter,
        ),
        "source",
        "category",
        "difficulty",
        "status",
    )

    search_fields = (
        "title",
        "author",
        "description",
        "subcategory",
        "tags__name",
        "owner__username",
        "owner__first_name",
        "owner__last_name",
        "=owner__telegram_id",
    )

    filter_horizontal = (
        "tags",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Основна інформація",
            {
                "fields": (
                    "title",
                    "owner",
                    "visibility",
                    "source",
                    "category",
                    "subcategory",
                    "author",
                    "difficulty",
                    "status",
                ),
                "description": (
                    "Для загальної схеми залиште поле "
                    "«Власник» зі значенням "
                    "«Загальна бібліотека»."
                ),
            },
        ),
        (
            "Опис і теги",
            {
                "fields": (
                    "description",
                    "tags",
                )
            },
        ),
        (
            "Файли",
            {
                "fields": (
                    "image_file",
                    "pdf_file",
                )
            },
        ),
        (
            "Службова інформація",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
    )

    inlines = (
        SchemeMaterialInline,
    )

    ordering = (
        "-created_at",
    )

    list_select_related = (
        "owner",
    )

    save_on_top = True

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        return queryset.annotate(
            personal_favorites_count=Count(
                "favorite_records",
                distinct=True,
            )
        )

    @admin.display(
        description="Власник",
        ordering="owner__first_name",
        empty_value="Загальна бібліотека",
    )
    def owner_display(
        self,
        obj: Scheme,
    ) -> str:
        if obj.owner is None:
            return "Загальна бібліотека"

        return str(obj.owner)

    @admin.display(
        description="В обраному",
        ordering="personal_favorites_count",
    )
    def favorites_count(
        self,
        obj: Scheme,
    ) -> int:
        return int(
            getattr(
                obj,
                "personal_favorites_count",
                0,
            )
        )

    def formfield_for_foreignkey(
        self,
        db_field,
        request,
        **kwargs,
    ):
        formfield = super().formfield_for_foreignkey(
            db_field,
            request,
            **kwargs,
        )

        if (
            db_field.name == "owner"
            and formfield is not None
        ):
            formfield.empty_label = (
                "Загальна бібліотека"
            )

        return formfield


@admin.register(SchemeFavorite)
class SchemeFavoriteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_display",
        "user_role",
        "scheme",
        "created_at",
    )

    list_filter = (
        "user__role",
        (
            "user",
            admin.RelatedOnlyFieldListFilter,
        ),
        (
            "scheme",
            admin.RelatedOnlyFieldListFilter,
        ),
        "created_at",
    )

    search_fields = (
        "scheme__title",
        "user__username",
        "user__first_name",
        "user__last_name",
        "=user__telegram_id",
    )

    raw_id_fields = (
        "user",
        "scheme",
    )

    readonly_fields = (
        "created_at",
    )

    ordering = (
        "-created_at",
    )

    list_select_related = (
        "user",
        "scheme",
    )

    date_hierarchy = "created_at"

    @admin.display(
        description="Користувач",
        ordering="user__first_name",
    )
    def user_display(
        self,
        obj: SchemeFavorite,
    ) -> str:
        return str(obj.user)

    @admin.display(
        description="Роль",
        ordering="user__role",
    )
    def user_role(
        self,
        obj: SchemeFavorite,
    ) -> str:
        get_role_display = getattr(
            obj.user,
            "get_role_display",
            None,
        )

        if callable(get_role_display):
            return str(
                get_role_display()
            )

        return str(
            obj.user.role
        )