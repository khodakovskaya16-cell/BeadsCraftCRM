from html import escape
from math import ceil

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from asgiref.sync import sync_to_async
from django.db.models import Count, Exists, OuterRef, Q

from schemes.models import Scheme, SchemeFavorite
from telegram_bot.models import TelegramUser
from telegram_bot.utils.navigation import send_screen


router = Router(name="schemes")

PAGE_SIZE = 5


# =====================================================
# ДОПОМІЖНІ ФУНКЦІЇ
# =====================================================


def get_display_value(
    instance: Scheme,
    field_name: str,
) -> str:
    """
    Повертає підпис значення поля choices.
    """

    display_method = getattr(
        instance,
        f"get_{field_name}_display",
        None,
    )

    if callable(display_method):
        value = display_method()
    else:
        value = getattr(
            instance,
            field_name,
            None,
        )

    if value in (None, ""):
        return "Не вказано"

    return str(value)


def get_choice_label(
    field_name: str,
    value: str,
) -> str:
    """
    Повертає український підпис choices
    без створення об'єкта Scheme.
    """

    try:
        field = Scheme._meta.get_field(
            field_name
        )

        choices = dict(
            field.flatchoices
        )

        return str(
            choices.get(
                value,
                value,
            )
        )

    except Exception:
        return str(value)


def get_visibility_icon(
    visibility: str,
) -> str:
    icons = {
        str(Scheme.Visibility.PUBLIC): "🌍",
        str(Scheme.Visibility.PRIVATE): "🔒",
        str(Scheme.Visibility.MODERATION): "⏳",
        str(Scheme.Visibility.REJECTED): "🚫",
    }

    return icons.get(
        str(visibility),
        "📚",
    )


def shorten_text(
    text: str,
    max_length: int = 43,
) -> str:
    if len(text) <= max_length:
        return text

    return (
        text[:max_length - 3]
        + "..."
    )


def get_telegram_user_role(
    telegram_id: int,
) -> str:
    """
    Повертає роль активного Telegram-користувача.

    Якщо користувача не знайдено, застосовується
    найбезпечніша роль customer.
    """

    role = (
        TelegramUser.objects
        .filter(
            telegram_id=telegram_id,
            is_active=True,
        )
        .values_list(
            "role",
            flat=True,
        )
        .first()
    )

    return str(
        role or "customer"
    )


def get_accessible_schemes_queryset(
    telegram_id: int,
):
    """
    Правила доступу до схем:

    admin:
        бачить усі схеми;

    manager:
        бачить загальнодоступні,
        схеми на модерації та власні;

    customer:
        бачить загальнодоступні та власні.
    """

    role = get_telegram_user_role(
        telegram_id
    )

    if role == "admin":
        return (
            Scheme.objects
            .all()
            .distinct()
        )

    if role == "manager":
        return (
            Scheme.objects
            .filter(
                Q(
                    visibility=(
                        Scheme.Visibility.PUBLIC
                    )
                )
                | Q(
                    visibility=(
                        Scheme.Visibility.MODERATION
                    )
                )
                | Q(
                    owner__telegram_id=telegram_id
                )
            )
            .distinct()
        )

    return (
        Scheme.objects
        .filter(
            Q(
                visibility=(
                    Scheme.Visibility.PUBLIC
                )
            )
            | Q(
                owner__telegram_id=telegram_id
            )
        )
        .distinct()
    )



def annotate_user_favorite(
    queryset,
    telegram_id: int,
):
    """
    Додає до кожної схеми ознаку,
    чи є вона в персональному обраному
    поточного Telegram-користувача.
    """

    return queryset.annotate(
        is_favorite_for_user=Exists(
            SchemeFavorite.objects.filter(
                user__telegram_id=telegram_id,
                user__is_active=True,
                scheme_id=OuterRef("pk"),
            )
        )
    )


@sync_to_async(thread_sensitive=True)
def toggle_scheme_favorite(
    scheme_id: int,
    telegram_id: int,
) -> dict:
    """
    Додає або видаляє схему з персонального обраного.
    Перед зміною повторно перевіряє доступ до схеми.
    """

    user = (
        TelegramUser.objects
        .filter(
            telegram_id=telegram_id,
            is_active=True,
        )
        .first()
    )

    if user is None:
        return {
            "ok": False,
            "is_favorite": False,
            "message": (
                "Користувача не знайдено. "
                "Надішліть /start."
            ),
        }

    try:
        scheme = (
            get_accessible_schemes_queryset(
                telegram_id
            )
            .get(pk=scheme_id)
        )
    except Scheme.DoesNotExist:
        return {
            "ok": False,
            "is_favorite": False,
            "message": (
                "Схему не знайдено або "
                "у вас немає доступу."
            ),
        }

    favorite = (
        SchemeFavorite.objects
        .filter(
            user=user,
            scheme=scheme,
        )
        .first()
    )

    if favorite is not None:
        favorite.delete()

        return {
            "ok": True,
            "is_favorite": False,
            "message": (
                "Схему видалено з обраного."
            ),
        }

    SchemeFavorite.objects.create(
        user=user,
        scheme=scheme,
    )

    return {
        "ok": True,
        "is_favorite": True,
        "message": (
            "Схему додано в обране."
        ),
    }


async def safe_edit_message(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """
    Безпечно редагує поточний екран бота.
    """

    try:
        await message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    except TelegramBadRequest as error:
        if (
            "message is not modified"
            not in str(error)
        ):
            raise


# =====================================================
# ЗАВАНТАЖЕННЯ ФІЛЬТРІВ
# =====================================================


@sync_to_async(thread_sensitive=True)
def load_filter_options(
    field_name: str,
    telegram_id: int,
) -> list[dict]:
    """
    Завантажує категорії або статуси лише
    серед схем, доступних поточному користувачу.
    """

    queryset = (
        get_accessible_schemes_queryset(
            telegram_id
        )
        .exclude(
            **{
                f"{field_name}__isnull": True
            }
        )
        .exclude(
            **{
                field_name: ""
            }
        )
        .values(field_name)
        .annotate(
            schemes_count=Count("id")
        )
        .order_by(field_name)
    )

    options = []

    for row in queryset:
        value = str(
            row[field_name]
        )

        options.append(
            {
                "value": value,
                "label": get_choice_label(
                    field_name,
                    value,
                ),
                "count": row[
                    "schemes_count"
                ],
            }
        )

    return options


def get_options_sync(
    field_name: str,
    telegram_id: int,
) -> list[dict]:
    """
    Синхронний варіант для використання
    всередині іншої ORM-функції.
    """

    queryset = (
        get_accessible_schemes_queryset(
            telegram_id
        )
        .exclude(
            **{
                f"{field_name}__isnull": True
            }
        )
        .exclude(
            **{
                field_name: ""
            }
        )
        .values(field_name)
        .annotate(
            schemes_count=Count("id")
        )
        .order_by(field_name)
    )

    options = []

    for row in queryset:
        value = str(
            row[field_name]
        )

        options.append(
            {
                "value": value,
                "label": get_choice_label(
                    field_name,
                    value,
                ),
                "count": row[
                    "schemes_count"
                ],
            }
        )

    return options


# =====================================================
# ЗАВАНТАЖЕННЯ СПИСКУ СХЕМ
# =====================================================


@sync_to_async(thread_sensitive=True)
def load_schemes_page(
    mode: str,
    option_index: int,
    page: int,
    telegram_id: int,
) -> dict:
    """
    Завантажує лише схеми, які користувач
    має право переглядати.
    """

    queryset = (
        get_accessible_schemes_queryset(
            telegram_id
        )
    )

    section_title = "Доступні схеми"

    if mode == "available":
        role = get_telegram_user_role(
            telegram_id
        )

        if role == "admin":
            section_title = (
                "Усі схеми — адміністратор"
            )

        elif role == "manager":
            section_title = (
                "Доступні схеми — менеджер"
            )

        else:
            section_title = (
                "Доступні схеми"
            )

    elif mode == "public":
        queryset = queryset.filter(
            visibility=(
                Scheme.Visibility.PUBLIC
            )
        )

        section_title = (
            "Загальна бібліотека"
        )

    elif mode == "mine":
        queryset = queryset.filter(
            owner__telegram_id=telegram_id
        )

        section_title = "Мої схеми"

    elif mode == "favorite":
        queryset = queryset.filter(
            favorite_records__user__telegram_id=(
                telegram_id
            ),
            favorite_records__user__is_active=True,
        ).distinct()

        section_title = "Мої обрані схеми"

    elif mode == "category":
        categories = get_options_sync(
            "category",
            telegram_id,
        )

        if (
            option_index < 0
            or option_index >= len(categories)
        ):
            return {
                "schemes": [],
                "total_count": 0,
                "page": 1,
                "total_pages": 1,
                "section_title": (
                    "Категорію не знайдено"
                ),
            }

        category = categories[
            option_index
        ]

        queryset = queryset.filter(
            category=category["value"]
        )

        section_title = (
            f"Категорія: "
            f"{category['label']}"
        )

    elif mode == "status":
        statuses = get_options_sync(
            "status",
            telegram_id,
        )

        if (
            option_index < 0
            or option_index >= len(statuses)
        ):
            return {
                "schemes": [],
                "total_count": 0,
                "page": 1,
                "total_pages": 1,
                "section_title": (
                    "Статус не знайдено"
                ),
            }

        status = statuses[
            option_index
        ]

        queryset = queryset.filter(
            status=status["value"]
        )

        section_title = (
            f"Статус: "
            f"{status['label']}"
        )

    queryset = annotate_user_favorite(
        queryset,
        telegram_id,
    )

    total_count = queryset.count()

    if total_count == 0:
        return {
            "schemes": [],
            "total_count": 0,
            "page": 1,
            "total_pages": 1,
            "section_title": section_title,
        }

    total_pages = ceil(
        total_count / PAGE_SIZE
    )

    page = max(
        1,
        min(page, total_pages),
    )

    start_index = (
        page - 1
    ) * PAGE_SIZE

    end_index = (
        start_index
        + PAGE_SIZE
    )

    page_queryset = (
        queryset
        .select_related("owner")
        .order_by("-id")
        [start_index:end_index]
    )

    schemes = []

    for scheme in page_queryset:
        schemes.append(
            {
                "id": scheme.pk,
                "title": str(
                    getattr(
                        scheme,
                        "title",
                        "Без назви",
                    )
                ),
                "is_favorite": bool(
                    getattr(
                        scheme,
                        "is_favorite_for_user",
                        False,
                    )
                ),
                "visibility": str(
                    getattr(
                        scheme,
                        "visibility",
                        "",
                    )
                ),
            }
        )

    return {
        "schemes": schemes,
        "total_count": total_count,
        "page": page,
        "total_pages": total_pages,
        "section_title": section_title,
    }


# =====================================================
# ЗАВАНТАЖЕННЯ КАРТКИ СХЕМИ
# =====================================================


@sync_to_async(thread_sensitive=True)
def load_scheme_detail(
    scheme_id: int,
    telegram_id: int,
) -> dict | None:
    try:
        scheme = (
            annotate_user_favorite(
                get_accessible_schemes_queryset(
                    telegram_id
                ),
                telegram_id,
            )
            .select_related("owner")
            .get(pk=scheme_id)
        )
    except Scheme.DoesNotExist:
        return None

    description = str(
        getattr(
            scheme,
            "description",
            "",
        )
        or ""
    )

    if len(description) > 2000:
        description = (
            description[:2000]
            + "..."
        )

    author = str(
        getattr(
            scheme,
            "author",
            "",
        )
        or ""
    )

    owner_text = (
        str(scheme.owner)
        if scheme.owner is not None
        else "Загальна бібліотека"
    )

    return {
        "id": scheme.pk,
        "title": str(
            getattr(
                scheme,
                "title",
                "Без назви",
            )
        ),
        "category": get_display_value(
            scheme,
            "category",
        ),
        "difficulty": get_display_value(
            scheme,
            "difficulty",
        ),
        "status": get_display_value(
            scheme,
            "status",
        ),
        "visibility": get_display_value(
            scheme,
            "visibility",
        ),
        "description": description,
        "source": get_display_value(
            scheme,
            "source",
        ),
        "author": author,
        "owner": owner_text,
        "is_favorite": bool(
            getattr(
                scheme,
                "is_favorite_for_user",
                False,
            )
        ),
    }


# =====================================================
# КЛАВІАТУРИ
# =====================================================


def build_schemes_menu_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Доступні схеми",
                    callback_data=(
                        "schemes_list:"
                        "available:0:1"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🌍 Загальна бібліотека",
                    callback_data=(
                        "schemes_list:"
                        "public:0:1"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="👤 Мої схеми",
                    callback_data=(
                        "schemes_list:"
                        "mine:0:1"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⭐ Обрані",
                    callback_data=(
                        "schemes_list:"
                        "favorite:0:1"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗂 За категоріями",
                    callback_data=(
                        "schemes_categories"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📌 За статусом",
                    callback_data=(
                        "schemes_statuses"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔍 Пошук",
                    callback_data=(
                        "schemes_search"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Головне меню",
                    callback_data="main_menu",
                )
            ],
        ]
    )


def build_options_keyboard(
    options: list[dict],
    mode: str,
) -> InlineKeyboardMarkup:
    rows = []

    for index, option in enumerate(
        options
    ):
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{option['label']} "
                        f"({option['count']})"
                    ),
                    callback_data=(
                        f"schemes_list:"
                        f"{mode}:"
                        f"{index}:"
                        f"1"
                    ),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ До розділу схем",
                callback_data="schemes_menu",
            )
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                text="🏠 Головне меню",
                callback_data="main_menu",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def build_schemes_list_keyboard(
    schemes: list[dict],
    mode: str,
    option_index: int,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    rows = []

    for scheme in schemes:
        favorite_icon = (
            "⭐"
            if scheme["is_favorite"]
            else ""
        )

        visibility_icon = (
            get_visibility_icon(
                scheme["visibility"]
            )
        )

        prefix = " ".join(
            item
            for item in (
                visibility_icon,
                favorite_icon,
            )
            if item
        )

        rows.append(
            [
                InlineKeyboardButton(
                    text=shorten_text(
                        (
                            f"{prefix} "
                            f"{scheme['title']}"
                        ).strip()
                    ),
                    callback_data=(
                        f"scheme_open:"
                        f"{scheme['id']}:"
                        f"{mode}:"
                        f"{option_index}:"
                        f"{page}"
                    ),
                )
            ]
        )

    navigation_row = []

    if page > 1:
        navigation_row.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=(
                    f"schemes_list:"
                    f"{mode}:"
                    f"{option_index}:"
                    f"{page - 1}"
                ),
            )
        )

    navigation_row.append(
        InlineKeyboardButton(
            text=(
                f"{page} / "
                f"{total_pages}"
            ),
            callback_data=(
                "schemes_current_page"
            ),
        )
    )

    if page < total_pages:
        navigation_row.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=(
                    f"schemes_list:"
                    f"{mode}:"
                    f"{option_index}:"
                    f"{page + 1}"
                ),
            )
        )

    rows.append(
        navigation_row
    )

    if mode == "category":
        back_callback = (
            "schemes_categories"
        )
        back_text = (
            "⬅️ До категорій"
        )

    elif mode == "status":
        back_callback = (
            "schemes_statuses"
        )
        back_text = (
            "⬅️ До статусів"
        )

    else:
        back_callback = (
            "schemes_menu"
        )
        back_text = (
            "⬅️ До розділу схем"
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=back_text,
                callback_data=back_callback,
            )
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                text="🏠 Головне меню",
                callback_data="main_menu",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def build_scheme_detail_keyboard(
    scheme_id: int,
    is_favorite: bool,
    mode: str,
    option_index: int,
    page: int,
) -> InlineKeyboardMarkup:
    favorite_text = (
        "⭐ Видалити з обраного"
        if is_favorite
        else "☆ Додати в обране"
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=favorite_text,
                    callback_data=(
                        "scheme_favorite_toggle:"
                        f"{scheme_id}:"
                        f"{mode}:"
                        f"{option_index}:"
                        f"{page}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ До списку",
                    callback_data=(
                        f"schemes_list:"
                        f"{mode}:"
                        f"{option_index}:"
                        f"{page}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📚 До розділу схем",
                    callback_data="schemes_menu",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Головне меню",
                    callback_data="main_menu",
                )
            ],
        ]
    )


def build_scheme_detail_text(
    scheme: dict,
) -> str:
    favorite_text = (
        "⭐ Так"
        if scheme["is_favorite"]
        else "Ні"
    )

    text_parts = [
        (
            "📚 <b>"
            f"{escape(scheme['title'])}"
            "</b>"
        ),
        (
            "Доступність: "
            f"<b>{escape(scheme['visibility'])}</b>"
        ),
        (
            "Власник: "
            f"<b>{escape(scheme['owner'])}</b>"
        ),
        (
            "Категорія: "
            f"<b>{escape(scheme['category'])}</b>"
        ),
        (
            "Складність: "
            f"<b>{escape(scheme['difficulty'])}</b>"
        ),
        (
            "Статус: "
            f"<b>{escape(scheme['status'])}</b>"
        ),
        (
            "Джерело: "
            f"<b>{escape(scheme['source'])}</b>"
        ),
        (
            "У моєму обраному: "
            f"<b>{favorite_text}</b>"
        ),
    ]

    if scheme["author"]:
        text_parts.append(
            (
                "Автор: "
                f"<b>{escape(scheme['author'])}</b>"
            )
        )

    if scheme["description"]:
        text_parts.append(
            (
                "\n📝 <b>Опис</b>\n"
                f"{escape(scheme['description'])}"
            )
        )

    return "\n".join(
        text_parts
    )


# =====================================================
# ВІДОБРАЖЕННЯ ЕКРАНІВ
# =====================================================


async def show_schemes_menu(
    message: Message,
) -> None:
    await safe_edit_message(
        message=message,
        text=(
            "📚 <b>Схеми</b>\n\n"
            "Оберіть потрібний підрозділ:"
        ),
        reply_markup=(
            build_schemes_menu_keyboard()
        ),
    )


async def show_filter_options(
    message: Message,
    field_name: str,
    mode: str,
    title: str,
    telegram_id: int,
) -> None:
    options = await load_filter_options(
        field_name=field_name,
        telegram_id=telegram_id,
    )

    if not options:
        await safe_edit_message(
            message=message,
            text=(
                f"{title}\n\n"
                "У цьому розділі поки "
                "немає доступних схем."
            ),
            reply_markup=(
                build_options_keyboard(
                    [],
                    mode,
                )
            ),
        )
        return

    await safe_edit_message(
        message=message,
        text=(
            f"{title}\n\n"
            "Оберіть потрібний варіант:"
        ),
        reply_markup=(
            build_options_keyboard(
                options,
                mode,
            )
        ),
    )


async def show_schemes_list(
    message: Message,
    mode: str,
    option_index: int,
    page: int,
    telegram_id: int,
) -> None:
    data = await load_schemes_page(
        mode=mode,
        option_index=option_index,
        page=page,
        telegram_id=telegram_id,
    )

    keyboard = (
        build_schemes_list_keyboard(
            schemes=data["schemes"],
            mode=mode,
            option_index=option_index,
            page=data["page"],
            total_pages=data[
                "total_pages"
            ],
        )
    )

    if not data["schemes"]:
        await safe_edit_message(
            message=message,
            text=(
                "📚 <b>"
                f"{escape(data['section_title'])}"
                "</b>\n\n"
                "Схем не знайдено."
            ),
            reply_markup=keyboard,
        )
        return

    text = (
        "📚 <b>"
        f"{escape(data['section_title'])}"
        "</b>\n\n"
        f"Усього схем: "
        f"<b>{data['total_count']}</b>\n"
        f"Сторінка: "
        f"<b>{data['page']} із "
        f"{data['total_pages']}</b>\n\n"
        "Оберіть схему:"
    )

    await safe_edit_message(
        message=message,
        text=text,
        reply_markup=keyboard,
    )


# =====================================================
# ГОЛОВНА КНОПКА
# =====================================================


@router.message(
    F.text == "📚 Схеми"
)
async def schemes_handler(
    message: Message,
) -> None:
    await send_screen(
        message=message,
        text=(
            "📚 <b>Схеми</b>\n\n"
            "Оберіть потрібний підрозділ:"
        ),
        reply_markup=(
            build_schemes_menu_keyboard()
        ),
    )


# =====================================================
# CALLBACK-ОБРОБНИКИ
# =====================================================


@router.callback_query(
    F.data == "schemes_menu"
)
async def schemes_menu_handler(
    callback: CallbackQuery,
) -> None:
    if callback.message is not None:
        await show_schemes_menu(
            callback.message
        )

    await callback.answer()


@router.callback_query(
    F.data == "schemes_categories"
)
async def schemes_categories_handler(
    callback: CallbackQuery,
) -> None:
    if callback.message is not None:
        await show_filter_options(
            message=callback.message,
            field_name="category",
            mode="category",
            title=(
                "🗂 <b>Схеми "
                "за категоріями</b>"
            ),
            telegram_id=(
                callback.from_user.id
            ),
        )

    await callback.answer()


@router.callback_query(
    F.data == "schemes_statuses"
)
async def schemes_statuses_handler(
    callback: CallbackQuery,
) -> None:
    if callback.message is not None:
        await show_filter_options(
            message=callback.message,
            field_name="status",
            mode="status",
            title=(
                "📌 <b>Схеми "
                "за статусом</b>"
            ),
            telegram_id=(
                callback.from_user.id
            ),
        )

    await callback.answer()


@router.callback_query(
    F.data.startswith(
        "schemes_list:"
    )
)
async def schemes_list_handler(
    callback: CallbackQuery,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    try:
        parts = callback.data.split(
            ":"
        )

        mode = parts[1]

        option_index = int(
            parts[2]
        )

        page = int(
            parts[3]
        )

    except (
        IndexError,
        ValueError,
    ):
        await callback.answer(
            "Не вдалося відкрити список.",
            show_alert=True,
        )
        return

    await show_schemes_list(
        message=callback.message,
        mode=mode,
        option_index=option_index,
        page=page,
        telegram_id=(
            callback.from_user.id
        ),
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith(
        "scheme_open:"
    )
)
async def scheme_open_handler(
    callback: CallbackQuery,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    try:
        parts = callback.data.split(
            ":"
        )

        scheme_id = int(
            parts[1]
        )

        mode = parts[2]

        option_index = int(
            parts[3]
        )

        page = int(
            parts[4]
        )

    except (
        IndexError,
        ValueError,
    ):
        await callback.answer(
            "Не вдалося відкрити схему.",
            show_alert=True,
        )
        return

    scheme = await load_scheme_detail(
        scheme_id=scheme_id,
        telegram_id=(
            callback.from_user.id
        ),
    )

    if scheme is None:
        await callback.answer(
            (
                "Схему не знайдено або "
                "у вас немає доступу."
            ),
            show_alert=True,
        )
        return

    await safe_edit_message(
        message=callback.message,
        text=build_scheme_detail_text(
            scheme
        ),
        reply_markup=(
            build_scheme_detail_keyboard(
                scheme_id=scheme_id,
                is_favorite=scheme[
                    "is_favorite"
                ],
                mode=mode,
                option_index=option_index,
                page=page,
            )
        ),
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith(
        "scheme_favorite_toggle:"
    )
)
async def scheme_favorite_toggle_handler(
    callback: CallbackQuery,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    try:
        parts = callback.data.split(
            ":"
        )

        scheme_id = int(
            parts[1]
        )

        mode = parts[2]

        option_index = int(
            parts[3]
        )

        page = int(
            parts[4]
        )

    except (
        IndexError,
        ValueError,
    ):
        await callback.answer(
            "Не вдалося змінити обране.",
            show_alert=True,
        )
        return

    result = await toggle_scheme_favorite(
        scheme_id=scheme_id,
        telegram_id=(
            callback.from_user.id
        ),
    )

    if not result["ok"]:
        await callback.answer(
            result["message"],
            show_alert=True,
        )
        return

    scheme = await load_scheme_detail(
        scheme_id=scheme_id,
        telegram_id=(
            callback.from_user.id
        ),
    )

    if scheme is None:
        await callback.answer(
            (
                "Схему не знайдено або "
                "у вас немає доступу."
            ),
            show_alert=True,
        )
        return

    await safe_edit_message(
        message=callback.message,
        text=build_scheme_detail_text(
            scheme
        ),
        reply_markup=(
            build_scheme_detail_keyboard(
                scheme_id=scheme_id,
                is_favorite=scheme[
                    "is_favorite"
                ],
                mode=mode,
                option_index=option_index,
                page=page,
            )
        ),
    )

    await callback.answer(
        result["message"]
    )


@router.callback_query(
    F.data == "schemes_current_page"
)
async def schemes_current_page_handler(
    callback: CallbackQuery,
) -> None:
    await callback.answer(
        "Це поточна сторінка."
    )