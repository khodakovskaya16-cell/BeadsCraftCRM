from django import forms

from .models import ProductionOrder


class ProductionOrderForm(forms.ModelForm):
    """Форма створення виробничого завдання."""

    class Meta:
        model = ProductionOrder

        fields = (
            "quantity",
            "notes",
        )

        widgets = {
            "quantity": forms.NumberInput(
                attrs={
                    "min": "1",
                    "step": "1",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": (
                        "Додаткова інформація щодо виготовлення"
                    ),
                }
            ),
        }