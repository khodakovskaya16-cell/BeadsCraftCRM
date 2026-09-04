from django.db import models


class Tag(models.Model):
    """Тег для пошуку та групування схем."""

    name = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Назва",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Тег"
        verbose_name_plural = "Теги"

    def __str__(self) -> str:
        return self.name


class Scheme(models.Model):
    """Схема виробу з бісеру."""

    class Source(models.TextChoices):
        OWN = "own", "Моя схема"
        PURCHASED = "purchased", "Куплена схема"
        FREE = "free", "Безкоштовна схема"

    class Category(models.TextChoices):
        JEWELRY = "jewelry", "Прикраси"
        FLOWERS = "flowers", "Квіти"
        TOYS = "toys", "Іграшки"
        KEYCHAINS = "keychains", "Брелоки"
        DECOR = "decor", "Декор"
        ACCESSORIES = "accessories", "Аксесуари"
        CLOTHES = "clothes", "Одяг"
        OTHER = "other", "Інше"

    class Difficulty(models.TextChoices):
        BEGINNER = "beginner", "Початковий рівень"
        INTERMEDIATE = "intermediate", "Середній рівень"
        ADVANCED = "advanced", "Складний рівень"

    class Status(models.TextChoices):
        PLANNED = "planned", "Планую"
        IN_PROGRESS = "in_progress", "У роботі"
        COMPLETED = "completed", "Завершено"
        ARCHIVED = "archived", "Архів"

    class Visibility(models.TextChoices):
        PUBLIC = "public", "Загальнодоступна"
        PRIVATE = "private", "Приватна"
        MODERATION = "moderation", "На модерації"
        REJECTED = "rejected", "Відхилена"

    title = models.CharField(
        max_length=200,
        db_index=True,
        verbose_name="Назва",
    )

    owner = models.ForeignKey(
        "telegram_bot.TelegramUser",
        on_delete=models.PROTECT,
        related_name="schemes",
        null=True,
        blank=True,
        verbose_name="Власник",
    )

    visibility = models.CharField(
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.PUBLIC,
        db_index=True,
        verbose_name="Доступність",
    )

    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        verbose_name="Джерело",
    )

    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        db_index=True,
        verbose_name="Категорія",
    )

    subcategory = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Підкатегорія",
    )

    author = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Автор",
    )

    difficulty = models.CharField(
        max_length=20,
        choices=Difficulty.choices,
        blank=True,
        verbose_name="Складність",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PLANNED,
        db_index=True,
        verbose_name="Статус",
    )

    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name="schemes",
        verbose_name="Теги",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Опис",
    )

    pdf_file = models.FileField(
        upload_to="schemes/pdfs/",
        blank=True,
        verbose_name="PDF-файл",
    )

    image_file = models.ImageField(
        upload_to="schemes/images/",
        blank=True,
        verbose_name="Зображення",
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
        ordering = ["-created_at"]
        verbose_name = "Схема"
        verbose_name_plural = "Схеми"

    def __str__(self) -> str:
        return self.title


class SchemeFavorite(models.Model):
    """Персональне обране Telegram-користувачів."""

    user = models.ForeignKey(
        "telegram_bot.TelegramUser",
        on_delete=models.CASCADE,
        related_name="scheme_favorites",
        verbose_name="Користувач",
    )

    scheme = models.ForeignKey(
        Scheme,
        on_delete=models.CASCADE,
        related_name="favorite_records",
        verbose_name="Схема",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Додано в обране",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Обрана схема"
        verbose_name_plural = "Обрані схеми"

        constraints = [
            models.UniqueConstraint(
                fields=(
                    "user",
                    "scheme",
                ),
                name="unique_user_scheme_favorite",
            )
        ]

    def __str__(self) -> str:
        return (
            f"{self.user} — {self.scheme}"
        )