from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction


class MaterialType(models.Model):
    """Тип матеріалу: бісер, нитки, фурнітура тощо."""

    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Назва типу",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Опис",
    )

    class Meta:
        ordering = ("name",)
        verbose_name = "Тип матеріалу"
        verbose_name_plural = "Типи матеріалів"

    def __str__(self) -> str:
        return self.name


class Material(models.Model):
    """Матеріал, який зберігається на складі."""

    class Unit(models.TextChoices):
        GRAM = "gram", "г"
        PIECE = "piece", "шт."
        METER = "meter", "м"
        CENTIMETER = "centimeter", "см"
        PACK = "pack", "уп."
        SET = "set", "набір"

    name = models.CharField(
        max_length=200,
        verbose_name="Назва",
    )

    material_type = models.ForeignKey(
        MaterialType,
        on_delete=models.PROTECT,
        related_name="materials",
        verbose_name="Тип матеріалу",
    )

    manufacturer = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Виробник",
    )

    article = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Артикул",
    )

    color_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Назва кольору",
    )

    color_code = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Код кольору",
    )

    unit = models.CharField(
        max_length=20,
        choices=Unit.choices,
        default=Unit.GRAM,
        verbose_name="Одиниця вимірювання",
    )

    quantity_in_stock = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
        ],
        verbose_name="Кількість на складі",
    )

    minimum_stock = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
        ],
        verbose_name="Мінімальний запас",
    )

    notes = models.TextField(
        blank=True,
        verbose_name="Примітки",
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
            "material_type__name",
            "name",
            "color_name",
        )
        verbose_name = "Матеріал"
        verbose_name_plural = "Матеріали"

    def __str__(self) -> str:
        if self.color_name:
            return f"{self.name} — {self.color_name}"

        return self.name

    @property
    def is_low_stock(self) -> bool:
        """Перевіряє, чи запас досяг мінімального рівня."""

        return self.quantity_in_stock <= self.minimum_stock

    def shortage_for(
        self,
        required_quantity: Decimal,
    ) -> Decimal:
        """Розраховує дефіцит для заданої кількості."""

        required_quantity = Decimal(
            str(required_quantity)
        )

        shortage = (
            required_quantity
            - self.quantity_in_stock
        )

        return max(
            shortage,
            Decimal("0.00"),
        )


class SchemeMaterial(models.Model):
    """Матеріал, необхідний для виготовлення виробу за схемою."""

    scheme = models.ForeignKey(
        "schemes.Scheme",
        on_delete=models.CASCADE,
        related_name="material_requirements",
        verbose_name="Схема",
    )

    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        related_name="scheme_requirements",
        verbose_name="Матеріал",
    )

    required_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.01")),
        ],
        verbose_name="Необхідна кількість",
    )

    notes = models.CharField(
        max_length=250,
        blank=True,
        verbose_name="Примітка",
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
            "material__name",
            "material__color_name",
        )

        constraints = [
            models.UniqueConstraint(
                fields=(
                    "scheme",
                    "material",
                ),
                name="unique_material_per_scheme",
            ),
        ]

        verbose_name = "Матеріал схеми"
        verbose_name_plural = "Матеріали схем"

    def __str__(self) -> str:
        return (
            f"{self.scheme}: "
            f"{self.material} — "
            f"{self.required_quantity} "
            f"{self.material.get_unit_display()}"
        )

    @property
    def available(self) -> bool:
        """Перевіряє достатність матеріалу на складі."""

        return (
            self.material.quantity_in_stock
            >= self.required_quantity
        )

    @property
    def shortage(self) -> Decimal:
        """Повертає кількість матеріалу, якої бракує."""

        return self.material.shortage_for(
            self.required_quantity
        )


class StockMovement(models.Model):
    """Операція надходження або списання матеріалу."""

    class MovementType(models.TextChoices):
        RECEIPT = "receipt", "Надходження"
        WRITE_OFF = "write_off", "Списання"

    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        related_name="stock_movements",
        verbose_name="Матеріал",
    )
    stock = models.ForeignKey(
        "UserMaterialStock",
        on_delete=models.PROTECT,
        related_name="stock_movements",
        null=True,
        blank=True,
        verbose_name="Персональний запас",
    )
    movement_type = models.CharField(
        max_length=20,
        choices=MovementType.choices,
        verbose_name="Тип операції",
    )

    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.01")),
        ],
        verbose_name="Кількість",
    )

    balance_after = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        editable=False,
        verbose_name="Залишок після операції",
    )

    note = models.CharField(
        max_length=250,
        blank=True,
        verbose_name="Примітка",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата операції",
    )

    class Meta:
        ordering = (
            "-created_at",
            "-pk",
        )
        verbose_name = "Рух матеріалу"
        verbose_name_plural = "Рух матеріалів"

    def __str__(self) -> str:
        return (
            f"{self.get_movement_type_display()}: "
            f"{self.material} — "
            f"{self.quantity} "
            f"{self.material.get_unit_display()}"
        )

    @classmethod
    def create_and_apply(
            cls,
            *,
            stock: "UserMaterialStock",
            movement_type: str,
            quantity: Decimal,
            note: str = "",
    ) -> "StockMovement":
        """Створює рух і змінює персональний складський залишок."""

        quantity = Decimal(
            str(quantity)
        )

        if quantity <= Decimal("0.00"):
            raise ValidationError(
                "Кількість повинна бути більшою за нуль."
            )

        if movement_type not in cls.MovementType.values:
            raise ValidationError(
                "Невідомий тип операції."
            )

        with transaction.atomic():
            locked_stock = (
                UserMaterialStock.objects
                .select_for_update()
                .select_related("material")
                .get(pk=stock.pk)
            )

            current_balance = (
                locked_stock.quantity_in_stock
            )

            if movement_type == cls.MovementType.RECEIPT:
                new_balance = (
                        current_balance
                        + quantity
                )

            else:
                if quantity > current_balance:
                    raise ValidationError(
                        "Неможливо списати більше "
                        "матеріалу, ніж є на складі."
                    )

                new_balance = (
                        current_balance
                        - quantity
                )

            locked_stock.quantity_in_stock = (
                new_balance
            )

            locked_stock.save(
                update_fields=(
                    "quantity_in_stock",
                    "updated_at",
                )
            )

            movement = cls.objects.create(
                material=locked_stock.material,
                stock=locked_stock,
                movement_type=movement_type,
                quantity=quantity,
                balance_after=new_balance,
                note=note.strip(),
            )

        return movement

class UserMaterialStock(models.Model):
    """Персональний запас матеріалу користувача."""

    owner = models.ForeignKey(
        "telegram_bot.TelegramUser",
        on_delete=models.PROTECT,
        related_name="material_stocks",
        verbose_name="Власник складу",
    )

    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        related_name="user_stocks",
        verbose_name="Матеріал",
    )

    quantity_in_stock = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(
                Decimal("0.00")
            ),
        ],
        verbose_name="Кількість на складі",
    )

    minimum_stock = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(
                Decimal("0.00")
            ),
        ],
        verbose_name="Мінімальний запас",
    )

    notes = models.TextField(
        blank=True,
        verbose_name="Примітки",
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
            "owner_id",
            "material_id",
        )

        constraints = [
            models.UniqueConstraint(
                fields=(
                    "owner",
                    "material",
                ),
                name="unique_user_material_stock",
            ),
        ]

        verbose_name = "Персональний запас"
        verbose_name_plural = "Персональні запаси"

    def __str__(self) -> str:
        return (
            f"{self.owner}: "
            f"{self.material}"
        )

    @property
    def is_low_stock(self) -> bool:
        """Перевіряє досягнення мінімального запасу."""

        return (
                self.quantity_in_stock
                <= self.minimum_stock
        )

    def shortage_for(
            self,
            required_quantity: Decimal,
    ) -> Decimal:
        """Розраховує дефіцит матеріалу."""

        required_quantity = Decimal(
            str(required_quantity)
        )

        shortage = (
                required_quantity
                - self.quantity_in_stock
        )

        return max(
            shortage,
            Decimal("0.00"),
        )