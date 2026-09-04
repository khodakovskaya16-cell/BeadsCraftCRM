from django.contrib import admin

from telegram_bot.models import TelegramUser


@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = (
        "telegram_id",
        "display_name",
        "username",
        "role",
        "is_active",
        "created_at",
    )

    list_filter = (
        "role",
        "is_active",
        "language_code",
        "created_at",
    )

    search_fields = (
        "telegram_id",
        "username",
        "first_name",
        "last_name",
    )

    readonly_fields = (
        "telegram_id",
        "username",
        "first_name",
        "last_name",
        "language_code",
        "created_at",
        "updated_at",
    )

    ordering = (
        "-created_at",
    )

    list_per_page = 25

    fieldsets = (
        (
            "Дані Telegram",
            {
                "fields": (
                    "telegram_id",
                    "username",
                    "first_name",
                    "last_name",
                    "language_code",
                )
            },
        ),
        (
            "Доступ до системи",
            {
                "fields": (
                    "role",
                    "is_active",
                )
            },
        ),
        (
            "Службова інформація",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.display(
        description="Користувач",
        ordering="first_name",
    )
    def display_name(
        self,
        obj: TelegramUser,
    ) -> str:
        full_name = " ".join(
            part
            for part in (
                obj.first_name,
                obj.last_name,
            )
            if part
        ).strip()

        if full_name:
            return full_name

        if obj.username:
            return f"@{obj.username}"

        return "Без імені"