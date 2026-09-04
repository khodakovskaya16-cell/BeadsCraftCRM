from decimal import Decimal

from django import forms

from .models import (
    Material,
    SchemeMaterial,
    StockMovement,
    UserMaterialStock,
)


class MaterialForm(forms.ModelForm):
    """Форма створення та редагування матеріалу."""

    stock_quantity = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        initial=Decimal("0.00"),
        label="Кількість на складі",
        widget=forms.NumberInput(
            attrs={
                "min": "0",
                "step": "0.01",
                "placeholder": "0.00",
            }
        ),
    )

    stock_minimum = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        initial=Decimal("0.00"),
        label="Мінімальний запас",
        widget=forms.NumberInput(
            attrs={
                "min": "0",
                "step": "0.01",
                "placeholder": "0.00",
            }
        ),
    )

    def __init__(
        self,
        *args,
        stock: UserMaterialStock | None = None,
        **kwargs,
    ) -> None:
        self.stock = stock

        super().__init__(
            *args,
            **kwargs,
        )

        if stock is not None:
            self.fields["stock_quantity"].initial = (
                stock.quantity_in_stock
            )
            self.fields["stock_minimum"].initial = (
                stock.minimum_stock
            )

    class Meta:
        model = Material

        fields = (
            "name",
            "material_type",
            "manufacturer",
            "article",
            "color_name",
            "color_code",
            "unit",
            "stock_quantity",
            "stock_minimum",
            "notes",
        )

        widgets = {
            "name": forms.TextInput(
                attrs={
                    "placeholder": "Наприклад: Бісер круглий",
                }
            ),
            "manufacturer": forms.TextInput(
                attrs={
                    "placeholder": "Наприклад: Preciosa",
                }
            ),
            "article": forms.TextInput(
                attrs={
                    "placeholder": "Артикул матеріалу",
                }
            ),
            "color_name": forms.TextInput(
                attrs={
                    "placeholder": "Наприклад: Білий",
                }
            ),
            "color_code": forms.TextInput(
                attrs={
                    "placeholder": "Наприклад: 02090",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": (
                        "Додаткова інформація про матеріал"
                    ),
                }
            ),
        }


class SchemeMaterialForm(forms.ModelForm):
    """Форма додавання матеріалу до схеми."""

    def __init__(
        self,
        *args,
        scheme,
        **kwargs,
    ) -> None:
        self.scheme = scheme

        super().__init__(
            *args,
            **kwargs,
        )

        self.fields["material"].queryset = (
            Material.objects.select_related(
                "material_type"
            ).all()
        )

    class Meta:
        model = SchemeMaterial

        fields = (
            "material",
            "required_quantity",
            "notes",
        )

        widgets = {
            "required_quantity": forms.NumberInput(
                attrs={
                    "min": "0.01",
                    "step": "0.01",
                    "placeholder": "Необхідна кількість",
                }
            ),
            "notes": forms.TextInput(
                attrs={
                    "placeholder": (
                        "Наприклад: основний колір"
                    ),
                }
            ),
        }

    def clean_material(self) -> Material:
        """Не дозволяє двічі додати матеріал до схеми."""

        material = self.cleaned_data["material"]

        existing_requirements = (
            SchemeMaterial.objects.filter(
                scheme=self.scheme,
                material=material,
            )
        )

        if self.instance.pk:
            existing_requirements = (
                existing_requirements.exclude(
                    pk=self.instance.pk
                )
            )

        if existing_requirements.exists():
            raise forms.ValidationError(
                "Цей матеріал уже доданий до схеми."
            )

        return material


class StockMovementForm(forms.Form):
    """Форма надходження або списання матеріалу."""

    quantity = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Кількість",
        widget=forms.NumberInput(
            attrs={
                "min": "0.01",
                "step": "0.01",
                "placeholder": "0.00",
            }
        ),
    )

    note = forms.CharField(
        required=False,
        max_length=250,
        label="Примітка",
        widget=forms.TextInput(
            attrs={
                "placeholder": (
                    "Наприклад: закупівля або використання"
                ),
            }
        ),
    )

    def __init__(
        self,
        *args,
        stock: UserMaterialStock,
        movement_type: str,
        **kwargs,
    ) -> None:
        self.stock = stock
        self.material = stock.material
        self.movement_type = movement_type

        super().__init__(
            *args,
            **kwargs,
        )

    def clean_quantity(self) -> Decimal:
        """Перевіряє кількість під час списання."""

        quantity = self.cleaned_data["quantity"]

        if (
            self.movement_type
            == StockMovement.MovementType.WRITE_OFF
            and quantity > self.stock.quantity_in_stock
        ):
            raise forms.ValidationError(
                "На складі недостатньо матеріалу. "
                f"Доступно: "
                f"{self.stock.quantity_in_stock} "
                f"{self.material.get_unit_display()}."
            )

        return quantity