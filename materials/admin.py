from django.contrib import admin

from .models import Material, MaterialType, SchemeMaterial


@admin.register(MaterialType)
class MaterialTypeAdmin(admin.ModelAdmin):
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


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "material_type",
        "manufacturer",
        "article",
        "color_name",
        "color_code",
        "unit",
        "quantity_in_stock",
        "minimum_stock",
        "low_stock_status",
    )

    list_filter = (
        "material_type",
        "unit",
        "manufacturer",
    )

    search_fields = (
        "name",
        "manufacturer",
        "article",
        "color_name",
        "color_code",
    )

    autocomplete_fields = (
        "material_type",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    list_select_related = (
        "material_type",
    )

    ordering = (
        "material_type__name",
        "name",
        "color_name",
    )

    @admin.display(
        boolean=True,
        description="Малий запас",
    )
    def low_stock_status(
        self,
        obj: Material,
    ) -> bool:
        return obj.is_low_stock


@admin.register(SchemeMaterial)
class SchemeMaterialAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "scheme",
        "material",
        "required_quantity",
        "unit_display",
        "available_status",
        "shortage_display",
    )

    search_fields = (
        "scheme__title",
        "material__name",
        "material__article",
        "material__color_name",
        "material__color_code",
    )

    autocomplete_fields = (
        "scheme",
        "material",
    )

    list_select_related = (
        "scheme",
        "material",
    )

    @admin.display(
        description="Одиниця",
    )
    def unit_display(
        self,
        obj: SchemeMaterial,
    ) -> str:
        return obj.material.get_unit_display()

    @admin.display(
        boolean=True,
        description="Достатньо",
    )
    def available_status(
        self,
        obj: SchemeMaterial,
    ) -> bool:
        return obj.available

    @admin.display(
        description="Дефіцит",
    )
    def shortage_display(
        self,
        obj: SchemeMaterial,
    ) -> str:
        return (
            f"{obj.shortage} "
            f"{obj.material.get_unit_display()}"
        )