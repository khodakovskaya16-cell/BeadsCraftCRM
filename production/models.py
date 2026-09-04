from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone


class ProductionOrder(models.Model):
    """Виробниче завдання на виготовлення виробу."""

    class Status(models.TextChoices):
        PLANNED = "planned", "Заплановано"
        IN_PROGRESS = "in_progress", "У роботі"
        COMPLETED = "completed", "Завершено"
        CANCELLED = "cancelled", "Скасовано"

    scheme = models.ForeignKey(
        "schemes.Scheme",
        on_delete=models.PROTECT,
        related_name="production_orders",
        verbose_name="Схема",
    )

    owner = models.ForeignKey(
        "telegram_bot.TelegramUser",
        on_delete=models.PROTECT,
        related_name="owned_production_orders",
        null=True,
        blank=True,
        verbose_name="Власник",
    )

    quantity = models.PositiveIntegerField(
        default=1,
        validators=[
            MinValueValidator(1),
        ],
        verbose_name="Кількість виробів",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PLANNED,
        verbose_name="Статус",
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

    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Розпочато",
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Завершено",
    )

    class Meta:
        ordering = (
            "-created_at",
            "-pk",
        )
        verbose_name = "Виробниче завдання"
        verbose_name_plural = "Виробничі завдання"

    def __str__(self) -> str:
        return (
            f"{self.production_number} — "
            f"{self.scheme.title}"
        )

    @property
    def production_number(self) -> str:
        """Формує номер виробничого завдання."""

        if self.pk is None:
            return "Нове завдання"

        return f"PR-{self.pk:06d}"

    def start_production(self) -> None:
        """Перевіряє та списує матеріали зі складу."""

        if self.pk is None:
            raise ValidationError(
                "Спочатку потрібно зберегти виробниче завдання."
            )

        from materials.models import (
            Material,
            SchemeMaterial,
            StockMovement,
        )

        with transaction.atomic():
            production = (
                ProductionOrder.objects
                .select_for_update()
                .select_related("scheme")
                .get(pk=self.pk)
            )

            if production.status != self.Status.PLANNED:
                raise ValidationError(
                    "Запустити можна лише заплановане завдання."
                )

            requirements = list(
                SchemeMaterial.objects
                .select_related("material")
                .filter(scheme=production.scheme)
            )

            if not requirements:
                raise ValidationError(
                    "Для цієї схеми не додано матеріалів."
                )

            material_ids = [
                requirement.material_id
                for requirement in requirements
            ]

            locked_materials = {
                material.pk: material
                for material in (
                    Material.objects
                    .select_for_update()
                    .filter(pk__in=material_ids)
                    .order_by("pk")
                )
            }

            shortages = []

            for requirement in requirements:
                material = locked_materials[
                    requirement.material_id
                ]

                required_total = (
                    requirement.required_quantity
                    * production.quantity
                )

                if material.quantity_in_stock < required_total:
                    shortage = (
                        required_total
                        - material.quantity_in_stock
                    )

                    shortages.append(
                        f"{material}: бракує "
                        f"{shortage} "
                        f"{material.get_unit_display()}"
                    )

            if shortages:
                raise ValidationError(
                    "Недостатньо матеріалів: "
                    + "; ".join(shortages)
                )

            for requirement in requirements:
                material = locked_materials[
                    requirement.material_id
                ]

                required_total = (
                    requirement.required_quantity
                    * production.quantity
                )

                balance_before = (
                    material.quantity_in_stock
                )

                balance_after = (
                    balance_before
                    - required_total
                )

                material.quantity_in_stock = balance_after

                material.save(
                    update_fields=(
                        "quantity_in_stock",
                        "updated_at",
                    )
                )

                StockMovement.objects.create(
                    material=material,
                    movement_type=(
                        StockMovement
                        .MovementType
                        .WRITE_OFF
                    ),
                    quantity=required_total,
                    balance_after=balance_after,
                    note=(
                        "Виробництво "
                        f"{production.production_number}: "
                        f"{production.scheme.title}"
                    ),
                )

                ProductionMaterialUsage.objects.create(
                    production=production,
                    material=material,
                    material_name=material.name,
                    color_name=material.color_name,
                    article=material.article,
                    unit_label=(
                        material.get_unit_display()
                    ),
                    required_quantity=required_total,
                    balance_before=balance_before,
                    balance_after=balance_after,
                )

            production.status = self.Status.IN_PROGRESS
            production.started_at = timezone.now()

            production.save(
                update_fields=(
                    "status",
                    "started_at",
                    "updated_at",
                )
            )

        self.refresh_from_db()

    def complete_production(self) -> None:
        """Позначає виробниче завдання завершеним."""

        with transaction.atomic():
            production = (
                ProductionOrder.objects
                .select_for_update()
                .get(pk=self.pk)
            )

            if production.status != self.Status.IN_PROGRESS:
                raise ValidationError(
                    "Завершити можна лише завдання, "
                    "яке перебуває у роботі."
                )

            production.status = self.Status.COMPLETED
            production.completed_at = timezone.now()

            production.save(
                update_fields=(
                    "status",
                    "completed_at",
                    "updated_at",
                )
            )

        self.refresh_from_db()

    def cancel_production(self) -> None:
        """Скасовує ще не розпочате завдання."""

        with transaction.atomic():
            production = (
                ProductionOrder.objects
                .select_for_update()
                .get(pk=self.pk)
            )

            if production.status != self.Status.PLANNED:
                raise ValidationError(
                    "Скасувати можна лише заплановане завдання."
                )

            production.status = self.Status.CANCELLED

            production.save(
                update_fields=(
                    "status",
                    "updated_at",
                )
            )

        self.refresh_from_db()


class ProductionMaterialUsage(models.Model):
    """Фіксує списання матеріалу для виробничого завдання."""

    production = models.ForeignKey(
        ProductionOrder,
        on_delete=models.CASCADE,
        related_name="material_usages",
        verbose_name="Виробниче завдання",
    )

    material = models.ForeignKey(
        "materials.Material",
        on_delete=models.PROTECT,
        related_name="production_usages",
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

    required_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[
            MinValueValidator(
                Decimal("0.01")
            ),
        ],
        verbose_name="Списана кількість",
    )

    balance_before = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Залишок до списання",
    )

    balance_after = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Залишок після списання",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата списання",
    )

    class Meta:
        ordering = (
            "material_name",
            "color_name",
        )

        constraints = [
            models.UniqueConstraint(
                fields=(
                    "production",
                    "material",
                ),
                name="unique_material_per_production",
            ),
        ]

        verbose_name = "Матеріал виробництва"
        verbose_name_plural = "Матеріали виробництва"

    def __str__(self) -> str:
        return (
            f"{self.material_name} — "
            f"{self.required_quantity} "
            f"{self.unit_label}"
        )