from html import escape
from math import ceil

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from asgiref.sync import sync_to_async
from django.db.models import Q

from schemes.models import Scheme
from telegram_bot.handlers.schemes import (
    annotate_user_favorite,
    build_scheme_detail_text,
    build_schemes_menu_keyboard,
    get_accessible_schemes_queryset,
    toggle_scheme_favorite,
)
from telegram_bot.handlers.start import (
    show_main_menu,
    validate_callback_user,
)


router = Router(name="scheme_search")

PAGE_SIZE = 5
SEARCH_PROMPT_PREFIX = "🔍 Пошук схеми"

# Останній пошуковий запит окремо для кожного чату.
_last_search_by_chat: dict[int, str] = {}

# Чати, у яких бот очікує введення пошукового запиту.
_waiting_search_chats: set[int] = set()

# ID повідомлення, яке використовується як екран пошуку.
_search_message_by_chat: dict[int, int] = {}


# =====================================================
# ФІЛЬТР ОЧІКУВАННЯ ПОШУКОВОГО ЗАПИТУ
# =====================================================


class WaitingForSchemeSearch(BaseFilter):
    async def __call__(
        self,
        message: Message,
    ) -> bool:
        return (
            message.chat.id
            in _waiting_search_chats
        )


# =====================================================
# ДОПОМІЖНІ ФУНКЦІЇ
# =====================================================


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


def get_display_value(
    scheme: Scheme,
    field_name: str,
) -> str:
    display_method = getattr(
        scheme,
        f"get_{field_name}_display",
        None,
    )

    if callable(display_method):
        value = display_method()
    else:
        value = getattr(
            scheme,
            field_name,
            None,
        )

    if value in (None, ""):
        return "Не вказано"

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


def clear_search_state(
    chat_id: int,
    clear_query: bool = False,
) -> None:
    _waiting_search_chats.discard(
        chat_id
    )

    _search_message_by_chat.pop(
        chat_id,
        None,
    )

    if clear_query:
        _last_search_by_chat.pop(
            chat_id,
            None,
        )


async def safe_edit_message(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
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


async def edit_message_by_id(
    message: Message,
    message_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=message_id,
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
# ЗАВАНТАЖЕННЯ РЕЗУЛЬТАТІВ ПОШУКУ
# =====================================================


@sync_to_async(thread_sensitive=True)
def load_search_page(
    query: str,
    page: int,
    telegram_id: int,
) -> dict:
    queryset = (
        get_accessible_schemes_queryset(
            telegram_id
        )
        .filter(
            Q(title__icontains=query)
            | Q(author__icontains=query)
            | Q(description__icontains=query)
            | Q(subcategory__icontains=query)
            | Q(tags__name__icontains=query)
        )
        .select_related("owner")
        .distinct()
    )

    queryset = (
        annotate_user_favorite(
            queryset,
            telegram_id,
        )
        .order_by(
            "-is_favorite_for_user",
            "title",
            "id",
        )
    )

    total_count = queryset.count()

    if total_count == 0:
        return {
            "schemes": [],
            "total_count": 0,
            "page": 1,
            "total_pages": 1,
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

    schemes = []

    for scheme in queryset[
        start_index:end_index
    ]:
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
        "owner": owner_text,
        "author": str(
            getattr(
                scheme,
                "author",
                "",
            )
            or ""
        ),
        "description": description,
        "source": get_display_value(
            scheme,
            "source",
        ),
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


def build_search_prompt_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ До розділу схем",
                    callback_data=(
                        "scheme_search_cancel"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Головне меню",
                    callback_data=(
                        "scheme_search_main_menu"
                    ),
                )
            ],
        ]
    )


def build_search_results_keyboard(
    schemes: list[dict],
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
                        "scheme_search_open:"
                        f"{scheme['id']}:"
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
                    "scheme_search_page:"
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
                "scheme_search_current_page"
            ),
        )
    )

    if page < total_pages:
        navigation_row.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=(
                    "scheme_search_page:"
                    f"{page + 1}"
                ),
            )
        )

    rows.append(
        navigation_row
    )

    rows.append(
        [
            InlineKeyboardButton(
                text="🔍 Новий пошук",
                callback_data="schemes_search",
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


def build_search_empty_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔍 Спробувати ще раз",
                    callback_data="schemes_search",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ До розділу схем",
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


def build_search_detail_keyboard(
    scheme_id: int,
    is_favorite: bool,
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
                        "scheme_search_favorite:"
                        f"{scheme_id}:"
                        f"{page}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ До результатів",
                    callback_data=(
                        "scheme_search_page:"
                        f"{page}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔍 Новий пошук",
                    callback_data="schemes_search",
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


# =====================================================
# ПОКАЗ ПОШУКОВОГО ПОЛЯ
# =====================================================


async def show_search_prompt(
    callback: CallbackQuery,
) -> None:
    if callback.message is None:
        return

    chat_id = (
        callback.message.chat.id
    )

    _waiting_search_chats.add(
        chat_id
    )

    _search_message_by_chat[
        chat_id
    ] = callback.message.message_id

    await safe_edit_message(
        message=callback.message,
        text=(
            "🔍 <b>Пошук схеми</b>\n\n"
            "Введіть назву, автора, опис, "
            "підкатегорію або тег.\n\n"
            "Наприклад: <i>браслет</i>\n\n"
            "Після введення повідомлення "
            "буде видалено."
        ),
        reply_markup=(
            build_search_prompt_keyboard()
        ),
    )


# =====================================================
# ПОКАЗ РЕЗУЛЬТАТІВ
# =====================================================


async def show_search_results(
    message: Message,
    chat_id: int,
    page: int,
    telegram_id: int,
) -> None:
    query = _last_search_by_chat.get(
        chat_id
    )

    if not query:
        await safe_edit_message(
            message=message,
            text=(
                "🔍 <b>Пошук завершено</b>\n\n"
                "Пошуковий запит більше "
                "не зберігається."
            ),
            reply_markup=(
                build_search_empty_keyboard()
            ),
        )
        return

    data = await load_search_page(
        query=query,
        page=page,
        telegram_id=telegram_id,
    )

    if not data["schemes"]:
        await safe_edit_message(
            message=message,
            text=(
                "🔍 <b>Результати пошуку</b>\n\n"
                "За запитом "
                f"«<b>{escape(query)}</b>» "
                "доступних схем не знайдено."
            ),
            reply_markup=(
                build_search_empty_keyboard()
            ),
        )
        return

    text = (
        "🔍 <b>Результати пошуку</b>\n\n"
        f"Запит: <b>{escape(query)}</b>\n"
        f"Знайдено схем: "
        f"<b>{data['total_count']}</b>\n"
        f"Сторінка: "
        f"<b>{data['page']} із "
        f"{data['total_pages']}</b>\n\n"
        "Оберіть схему:"
    )

    await safe_edit_message(
        message=message,
        text=text,
        reply_markup=(
            build_search_results_keyboard(
                schemes=data["schemes"],
                page=data["page"],
                total_pages=data[
                    "total_pages"
                ],
            )
        ),
    )


# =====================================================
# ОБРОБНИКИ ПОШУКУ
# =====================================================


@router.callback_query(
    F.data == "scheme_search_main_menu"
)
async def scheme_search_main_menu_handler(
    callback: CallbackQuery,
) -> None:
    user_data = await validate_callback_user(
        callback
    )

    if user_data is None:
        return

    if isinstance(
        callback.message,
        Message,
    ):
        clear_search_state(
            callback.message.chat.id
        )

        await show_main_menu(
            message=callback.message,
            role=user_data["role"],
        )

    await callback.answer()

@router.message(
    WaitingForSchemeSearch(),
    F.text,
)
async def scheme_search_query_handler(
    message: Message,
) -> None:
    chat_id = message.chat.id

    query = str(
        message.text or ""
    ).strip()

    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    search_message_id = (
        _search_message_by_chat.get(
            chat_id
        )
    )

    if search_message_id is None:
        clear_search_state(
            chat_id
        )
        return

    if len(query) < 2:
        await edit_message_by_id(
            message=message,
            message_id=search_message_id,
            text=(
                "🔍 <b>Пошук схеми</b>\n\n"
                "Введіть щонайменше "
                "<b>2 символи</b>.\n\n"
                "Наприклад: <i>браслет</i>"
            ),
            reply_markup=(
                build_search_prompt_keyboard()
            ),
        )
        return

    query = query[:100]

    _last_search_by_chat[
        chat_id
    ] = query

    clear_search_state(
        chat_id
    )

    telegram_account = message.from_user

    if telegram_account is None:
        return

    data = await load_search_page(
        query=query,
        page=1,
        telegram_id=telegram_account.id,
    )

    if not data["schemes"]:
        await edit_message_by_id(
            message=message,
            message_id=search_message_id,
            text=(
                "🔍 <b>Результати пошуку</b>\n\n"
                "За запитом "
                f"«<b>{escape(query)}</b>» "
                "доступних схем не знайдено."
            ),
            reply_markup=(
                build_search_empty_keyboard()
            ),
        )
        return

    text = (
        "🔍 <b>Результати пошуку</b>\n\n"
        f"Запит: <b>{escape(query)}</b>\n"
        f"Знайдено схем: "
        f"<b>{data['total_count']}</b>\n"
        f"Сторінка: "
        f"<b>1 із {data['total_pages']}</b>\n\n"
        "Оберіть схему:"
    )

    await edit_message_by_id(
        message=message,
        message_id=search_message_id,
        text=text,
        reply_markup=(
            build_search_results_keyboard(
                schemes=data["schemes"],
                page=1,
                total_pages=data[
                    "total_pages"
                ],
            )
        ),
    )


@router.callback_query(
    F.data == "scheme_search_cancel"
)
async def scheme_search_cancel_handler(
    callback: CallbackQuery,
) -> None:
    if callback.message is not None:
        clear_search_state(
            callback.message.chat.id
        )

        await safe_edit_message(
            message=callback.message,
            text=(
                "📚 <b>Схеми</b>\n\n"
                "Оберіть потрібний підрозділ:"
            ),
            reply_markup=(
                build_schemes_menu_keyboard()
            ),
        )

    await callback.answer()


@router.callback_query(
    F.data == "material_search_main_menu"
)
async def material_search_main_menu_handler(
    callback: CallbackQuery,
) -> None:
    user_data = await validate_callback_user(
        callback
    )

    if user_data is None:
        return

    if isinstance(
        callback.message,
        Message,
    ):
        clear_search_state(
            callback.message.chat.id
        )

        await show_main_menu(
            message=callback.message,
            role=user_data["role"],
        )

    await callback.answer()

@router.callback_query(
    F.data.startswith(
        "scheme_search_page:"
    )
)
async def scheme_search_page_handler(
    callback: CallbackQuery,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    try:
        page = int(
            callback.data.split(":")[1]
        )

    except (
        IndexError,
        ValueError,
    ):
        await callback.answer(
            "Неправильний номер сторінки.",
            show_alert=True,
        )
        return

    await show_search_results(
        message=callback.message,
        chat_id=callback.message.chat.id,
        page=page,
        telegram_id=(
            callback.from_user.id
        ),
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith(
        "scheme_search_open:"
    )
)
async def scheme_search_open_handler(
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

        page = int(
            parts[2]
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
            build_search_detail_keyboard(
                scheme_id=scheme_id,
                is_favorite=scheme[
                    "is_favorite"
                ],
                page=page,
            )
        ),
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith(
        "scheme_search_favorite:"
    )
)
async def scheme_search_favorite_handler(
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

        page = int(
            parts[2]
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
            build_search_detail_keyboard(
                scheme_id=scheme_id,
                is_favorite=scheme[
                    "is_favorite"
                ],
                page=page,
            )
        ),
    )

    await callback.answer(
        result["message"]
    )


@router.callback_query(
    F.data == "scheme_search_current_page"
)
async def scheme_search_current_page_handler(
    callback: CallbackQuery,
) -> None:
    await callback.answer(
        "Це поточна сторінка."
    )