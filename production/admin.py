from django.contrib import admin

from .models import (
    ProductionMaterialUsage,
    ProductionOrder,
)


class ProductionMaterialUsageInline(
    admin.TabularInline
):
    model = ProductionMaterialUsage
    extra = 0

    readonly_fields = (
        "material",
        "material_name",
        "article",
        "color_name",
        "unit_label",
        "required_quantity",
        "balance_before",
        "balance_after",
        "created_at",
    )

    can_delete = False


@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    list_display = (
        "production_number",
        "scheme",
        "quantity",
        "status",
        "created_at",
        "started_at",
        "completed_at",
    )

    list_filter = (
        "status",
        "created_at",
    )

    search_fields = (
        "scheme__title",
        "notes",
    )

    inlines = (
        ProductionMaterialUsageInline,
    )