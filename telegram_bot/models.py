# Create your models here.
from django.conf import settings
from django.db import models

class TelegramUser(models.Model):
    class Role(models.TextChoices):
        CUSTOMER = (
            "customer",
            "Користувач",
        )
        MANAGER = (
            "manager",
            "Менеджер",
        )
        ADMIN = (
            "admin",
            "Адміністратор",
        )

    django_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="telegram_profile",
        null=True,
        blank=True,
        verbose_name="Користувач сайту",
    )

    telegram_id = models.BigIntegerField(
        unique=True,
        verbose_name="Telegram ID",
    )

    username = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Ім’я користувача Telegram",
    )

    first_name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Ім’я",
    )

    last_name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Прізвище",
    )

    language_code = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Код мови",
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CUSTOMER,
        verbose_name="Роль",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активний",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата реєстрації",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата оновлення",
    )

    def __str__(self) -> str:
        full_name = " ".join(
            part
            for part in [
                self.first_name,
                self.last_name,
            ]
            if part
        ).strip()

        if full_name:
            return full_name

        if self.username:
            return f"@{self.username}"

        return f"Telegram ID: {self.telegram_id}"

    class Meta:
        verbose_name = "Користувач Telegram"
        verbose_name_plural = "Користувачі Telegram"
        ordering = [
            "-created_at",
        ]