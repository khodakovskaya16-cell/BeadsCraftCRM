from django import forms

from .models import Scheme


class SchemeForm(forms.ModelForm):
    """Форма створення та редагування схеми."""

    class Meta:
        model = Scheme

        fields = (
            "title",
            "source",
            "category",
            "subcategory",
            "author",
            "difficulty",
            "status",
            "tags",
            "description",
            "image_file",
            "pdf_file",
        )

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "placeholder": "Введіть назву схеми",
                }
            ),
            "subcategory": forms.TextInput(
                attrs={
                    "placeholder": "Наприклад: браслети",
                }
            ),
            "author": forms.TextInput(
                attrs={
                    "placeholder": "Автор або майстер",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "Додайте опис схеми",
                }
            ),
            "tags": forms.SelectMultiple(
                attrs={
                    "size": 6,
                }
            ),
        }