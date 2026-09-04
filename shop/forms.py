from django import forms

from .models import Order


class OrderForm(forms.ModelForm):
    """Форма оформлення замовлення."""

    class Meta:
        model = Order

        fields = (
            "customer_name",
            "phone",
            "email",
            "delivery_address",
            "comment",
        )

        widgets = {
            "customer_name": forms.TextInput(
                attrs={
                    "placeholder": "Ім’я та прізвище",
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "placeholder": "+380...",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "placeholder": "example@email.com",
                }
            ),
            "delivery_address": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": (
                        "Місто, відділення або адреса доставки"
                    ),
                }
            ),
            "comment": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": (
                        "Додаткова інформація до замовлення"
                    ),
                }
            ),
        }