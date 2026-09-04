from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class Cart(models.Model):
    """Кошик дефіцитних матеріалів для вибраної схеми."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Активний"
        ORDERED = "ordered", "Замовлення оформлено"

    scheme = models.ForeignKey(
        "schemes.Scheme",
        on_delete=models.CASCADE,
        related_name="shopping_carts",
        verbose_name="Схема",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name="Статус",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Створено",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Оновлено",
    )

    class Meta:
        ordering = (
            "-updated_at",
            "-pk",
        )
        verbose_name = "Кошик"
        verbose_name_plural = "Кошики"

    def __str__(self) -> str:
        return (
            f"Кошик для схеми «{self.scheme.title}» "
            f"— {self.get_status_display()}"
        )

    @property
    def items_count(self) -> int:
        """Кількість позицій у кошику."""

        return self.items.count()


class CartItem(models.Model):
    """Дефіцитний матеріал у кошику."""

    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Кошик",
    )

    material = models.ForeignKey(
        "materials.Material",
        on_delete=models.PROTECT,
        related_name="cart_items",
        verbose_name="Матеріал",
    )

    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.01")),
        ],
        verbose_name="Кількість для придбання",
    )

    class Meta:
        ordering = (
            "material__name",
            "material__color_name",
        )

        constraints = [
            models.UniqueConstraint(
                fields=(
                    "cart",
                    "material",
                ),
                name="unique_material_per_cart",
            ),
        ]

        verbose_name = "Позиція кошика"
        verbose_name_plural = "Позиції кошика"

    def __str__(self) -> str:
        return (
            f"{self.material} — "
            f"{self.quantity} "
            f"{self.material.get_unit_display()}"
        )


class Order(models.Model):
    """Оформлене замовлення матеріалів."""

    class Status(models.TextChoices):
        NEW = "new", "Нове"
        CONFIRMED = "confirmed", "Підтверджено"
        COMPLETED = "completed", "Виконано"
        CANCELLED = "cancelled", "Скасовано"

    cart = models.OneToOneField(
        Cart,
        on_delete=models.PROTECT,
        related_name="order",
        verbose_name="Кошик",
    )

    customer_name = models.CharField(
        max_length=150,
        verbose_name="Ім’я отримувача",
    )

    phone = models.CharField(
        max_length=30,
        verbose_name="Телефон",
    )

    email = models.EmailField(
        blank=True,
        verbose_name="Електронна пошта",
    )

    delivery_address = models.TextField(
        blank=True,
        verbose_name="Адреса доставки",
    )

    comment = models.TextField(
        blank=True,
        verbose_name="Коментар",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        verbose_name="Статус",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата оформлення",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Оновлено",
    )

    class Meta:
        ordering = (
            "-created_at",
            "-pk",
        )
        verbose_name = "Замовлення"
        verbose_name_plural = "Замовлення"

    def __str__(self) -> str:
        return (
            f"{self.order_number} — "
            f"{self.customer_name}"
        )

    @property
    def order_number(self) -> str:
        """Формує номер замовлення."""

        if self.pk is None:
            return "Нове замовлення"

        return f"BC-{self.pk:06d}"


class OrderItem(models.Model):
    """Зафіксована позиція оформленого замовлення."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Замовлення",
    )

    material = models.ForeignKey(
        "materials.Material",
        on_delete=models.PROTECT,
        related_name="order_items",
        verbose_name="Матеріал",
    )

    material_name = models.CharField(
        max_length=200,
        verbose_name="Назва матеріалу",
    )

    article = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Артикул",
    )

    color_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Колір",
    )

    unit_label = models.CharField(
        max_length=30,
        verbose_name="Одиниця вимірювання",
    )

    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.01")),
        ],
        verbose_name="Кількість",
    )

    class Meta:
        ordering = (
            "material_name",
            "color_name",
        )
        verbose_name = "Позиція замовлення"
        verbose_name_plural = "Позиції замовлення"

    def __str__(self) -> str:
        return (
            f"{self.material_name} — "
            f"{self.quantity} {self.unit_label}"
        )