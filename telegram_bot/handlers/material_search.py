from decimal import Decimal, InvalidOperation
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

from materials.models import Material
from telegram_bot.handlers.materials import (
    build_materials_menu_keyboard,
)
from telegram_bot.handlers.start import (
    save_current_user,
    show_inactive_message,
    show_main_menu,
    show_materials_access_denied,
    validate_callback_user,
)
from telegram_bot.keyboards.main_menu import (
    MATERIALS_ALLOWED_ROLES,
)


router = Router(name="material_search")

PAGE_SIZE = 5

_last_search_by_chat: dict[int, str] = {}
_waiting_search_chats: set[int] = set()
_search_message_by_chat: dict[int, int] = {}


# =====================================================
# ФІЛЬТР ОЧІКУВАННЯ ПОШУКОВОГО ЗАПИТУ
# =====================================================


class WaitingForMaterialSearch(BaseFilter):
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


def format_quantity(value) -> str:
    if value in (None, ""):
        return "0"

    try:
        decimal_value = Decimal(
            str(value)
        )
    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):
        return str(value)

    result = format(
        decimal_value,
        "f",
    )

    if "." in result:
        result = (
            result
            .rstrip("0")
            .rstrip(".")
        )

    return result


def shorten_text(
    text: str,
    max_length: int = 44,
) -> str:
    if len(text) <= max_length:
        return text

    return (
        text[:max_length - 3]
        + "..."
    )


def get_unit_label(
    material: Material,
) -> str:
    display_method = getattr(
        material,
        "get_unit_display",
        None,
    )

    if callable(display_method):
        value = display_method()
    else:
        value = getattr(
            material,
            "unit",
            "",
        )

    return str(value or "")


def material_is_low_stock(
    material: Material,
) -> bool:
    value = getattr(
        material,
        "is_low_stock",
        False,
    )

    if callable(value):
        return bool(value())

    return bool(value)


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
# ПЕРЕВІРКА ДОСТУПУ
# =====================================================


async def validate_materials_callback_access(
    callback: CallbackQuery,
) -> dict | None:
    user_data = await validate_callback_user(
        callback
    )

    if user_data is None:
        return None

    if (
        user_data["role"]
        in MATERIALS_ALLOWED_ROLES
    ):
        return user_data

    if isinstance(
        callback.message,
        Message,
    ):
        clear_search_state(
            callback.message.chat.id,
            clear_query=True,
        )

        await show_materials_access_denied(
            message=callback.message,
            role=user_data["role"],
        )

    await callback.answer(
        text=(
            "Розділ матеріалів доступний "
            "лише менеджерам та адміністраторам."
        ),
        show_alert=True,
    )

    return None


async def validate_materials_message_access(
    message: Message,
) -> dict | None:
    user_data = await save_current_user(
        message
    )

    if user_data is None:
        await message.answer(
            "Не вдалося визначити користувача."
        )
        return None

    if not user_data["is_active"]:
        clear_search_state(
            message.chat.id,
            clear_query=True,
        )

        await show_inactive_message(
            message
        )
        return None

    if (
        user_data["role"]
        not in MATERIALS_ALLOWED_ROLES
    ):
        clear_search_state(
            message.chat.id,
            clear_query=True,
        )

        await message.answer(
            "⛔ Розділ матеріалів доступний "
            "лише менеджерам та адміністраторам."
        )
        return None

    return user_data


# =====================================================
# ЗАВАНТАЖЕННЯ ДАНИХ
# =====================================================


@sync_to_async(thread_sensitive=True)
def load_material_search_page(
    query: str,
    page: int,
) -> dict:
    queryset = (
        Material.objects
        .select_related("material_type")
        .filter(
            Q(name__icontains=query)
            | Q(color_name__icontains=query)
            | Q(color_code__icontains=query)
            | Q(article__icontains=query)
            | Q(manufacturer__icontains=query)
            | Q(
                material_type__name__icontains=query
            )
        )
        .order_by(
            "material_type__name",
            "name",
            "color_name",
            "id",
        )
    )

    total_count = queryset.count()

    if total_count == 0:
        return {
            "materials": [],
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

    materials = []

    for material in queryset[
        start_index:end_index
    ]:
        color_name = str(
            getattr(
                material,
                "color_name",
                "",
            )
            or ""
        )

        name = str(
            getattr(
                material,
                "name",
                "Без назви",
            )
        )

        if color_name:
            full_name = (
                f"{name} — {color_name}"
            )
        else:
            full_name = name

        materials.append(
            {
                "id": material.pk,
                "name": full_name,
                "quantity": format_quantity(
                    getattr(
                        material,
                        "quantity_in_stock",
                        0,
                    )
                ),
                "unit": get_unit_label(
                    material
                ),
                "is_low_stock": (
                    material_is_low_stock(
                        material
                    )
                ),
            }
        )

    return {
        "materials": materials,
        "total_count": total_count,
        "page": page,
        "total_pages": total_pages,
    }


@sync_to_async(thread_sensitive=True)
def load_material_detail(
    material_id: int,
) -> dict | None:
    try:
        material = (
            Material.objects
            .select_related("material_type")
            .get(pk=material_id)
        )
    except Material.DoesNotExist:
        return None

    material_type = getattr(
        material,
        "material_type",
        None,
    )

    return {
        "id": material.pk,
        "name": str(
            getattr(
                material,
                "name",
                "Без назви",
            )
        ),
        "type": (
            str(material_type)
            if material_type
            else "Без типу"
        ),
        "manufacturer": str(
            getattr(
                material,
                "manufacturer",
                "",
            )
            or ""
        ),
        "article": str(
            getattr(
                material,
                "article",
                "",
            )
            or ""
        ),
        "color_name": str(
            getattr(
                material,
                "color_name",
                "",
            )
            or ""
        ),
        "color_code": str(
            getattr(
                material,
                "color_code",
                "",
            )
            or ""
        ),
        "quantity": format_quantity(
            getattr(
                material,
                "quantity_in_stock",
                0,
            )
        ),
        "minimum": format_quantity(
            getattr(
                material,
                "minimum_stock",
                0,
            )
        ),
        "unit": get_unit_label(
            material
        ),
        "is_low_stock": (
            material_is_low_stock(
                material
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
                    text=(
                        "⬅️ До розділу матеріалів"
                    ),
                    callback_data=(
                        "material_search_cancel"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Головне меню",
                    callback_data=(
                        "material_search_main_menu"
                    ),
                )
            ],
        ]
    )


def build_results_keyboard(
    materials: list[dict],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    rows = []

    for material in materials:
        status_icon = (
            "⚠️"
            if material["is_low_stock"]
            else "✅"
        )

        button_text = (
            f"{status_icon} "
            f"{material['name']} — "
            f"{material['quantity']} "
            f"{material['unit']}"
        )

        rows.append(
            [
                InlineKeyboardButton(
                    text=shorten_text(
                        button_text
                    ),
                    callback_data=(
                        "material_search_open:"
                        f"{material['id']}:"
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
                    "material_search_page:"
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
                "material_search_current_page"
            ),
        )
    )

    if page < total_pages:
        navigation_row.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=(
                    "material_search_page:"
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
                callback_data="materials_search",
            )
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                text=(
                    "⬅️ До розділу матеріалів"
                ),
                callback_data="materials_menu",
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


def build_empty_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔍 Спробувати ще раз",
                    callback_data="materials_search",
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "⬅️ До розділу матеріалів"
                    ),
                    callback_data="materials_menu",
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


def build_detail_keyboard(
    page: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ До результатів",
                    callback_data=(
                        "material_search_page:"
                        f"{page}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔍 Новий пошук",
                    callback_data="materials_search",
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "🧵 До розділу матеріалів"
                    ),
                    callback_data="materials_menu",
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
# ВІДОБРАЖЕННЯ ЕКРАНІВ
# =====================================================


async def show_search_prompt(
    callback: CallbackQuery,
) -> None:
    if not isinstance(
        callback.message,
        Message,
    ):
        return

    chat_id = callback.message.chat.id

    _waiting_search_chats.add(
        chat_id
    )

    _search_message_by_chat[
        chat_id
    ] = callback.message.message_id

    await safe_edit_message(
        message=callback.message,
        text=(
            "🔍 <b>Пошук матеріалу</b>\n\n"
            "Введіть назву, тип, колір, "
            "артикул або виробника.\n\n"
            "Наприклад: <i>жовтий</i>\n\n"
            "Після введення повідомлення "
            "буде видалено."
        ),
        reply_markup=(
            build_search_prompt_keyboard()
        ),
    )


async def show_search_results(
    message: Message,
    chat_id: int,
    page: int,
) -> None:
    query = _last_search_by_chat.get(
        chat_id
    )

    if not query:
        await safe_edit_message(
            message=message,
            text=(
                "🔍 <b>Пошук матеріалів</b>\n\n"
                "Пошуковий запит більше "
                "не зберігається."
            ),
            reply_markup=(
                build_empty_keyboard()
            ),
        )
        return

    data = await load_material_search_page(
        query=query,
        page=page,
    )

    if not data["materials"]:
        await safe_edit_message(
            message=message,
            text=(
                "🔍 <b>Результати пошуку</b>\n\n"
                "За запитом "
                f"«<b>{escape(query)}</b>» "
                "матеріалів не знайдено."
            ),
            reply_markup=(
                build_empty_keyboard()
            ),
        )
        return

    text = (
        "🔍 <b>Результати пошуку матеріалів</b>\n\n"
        f"Запит: <b>{escape(query)}</b>\n"
        f"Знайдено позицій: "
        f"<b>{data['total_count']}</b>\n"
        f"Сторінка: "
        f"<b>{data['page']} із "
        f"{data['total_pages']}</b>\n\n"
        "Оберіть матеріал:"
    )

    await safe_edit_message(
        message=message,
        text=text,
        reply_markup=(
            build_results_keyboard(
                materials=data["materials"],
                page=data["page"],
                total_pages=data[
                    "total_pages"
                ],
            )
        ),
    )


# =====================================================
# ПОЧАТОК ПОШУКУ
# =====================================================


@router.callback_query(
    F.data == "materials_search"
)
async def materials_search_handler(
    callback: CallbackQuery,
) -> None:
    user_data = (
        await validate_materials_callback_access(
            callback
        )
    )

    if user_data is None:
        return

    await show_search_prompt(
        callback
    )

    await callback.answer()


# =====================================================
# ВВЕДЕННЯ ПОШУКОВОГО ЗАПИТУ
# =====================================================


@router.message(
    WaitingForMaterialSearch(),
    F.text,
)
async def material_search_query_handler(
    message: Message,
) -> None:
    user_data = (
        await validate_materials_message_access(
            message
        )
    )

    if user_data is None:
        return

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
                "🔍 <b>Пошук матеріалу</b>\n\n"
                "Введіть щонайменше "
                "<b>2 символи</b>.\n\n"
                "Наприклад: <i>жовтий</i>"
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

    data = await load_material_search_page(
        query=query,
        page=1,
    )

    if not data["materials"]:
        await edit_message_by_id(
            message=message,
            message_id=search_message_id,
            text=(
                "🔍 <b>Результати пошуку</b>\n\n"
                "За запитом "
                f"«<b>{escape(query)}</b>» "
                "матеріалів не знайдено."
            ),
            reply_markup=(
                build_empty_keyboard()
            ),
        )
        return

    text = (
        "🔍 <b>Результати пошуку матеріалів</b>\n\n"
        f"Запит: <b>{escape(query)}</b>\n"
        f"Знайдено позицій: "
        f"<b>{data['total_count']}</b>\n"
        f"Сторінка: "
        f"<b>1 із {data['total_pages']}</b>\n\n"
        "Оберіть матеріал:"
    )

    await edit_message_by_id(
        message=message,
        message_id=search_message_id,
        text=text,
        reply_markup=(
            build_results_keyboard(
                materials=data["materials"],
                page=1,
                total_pages=data[
                    "total_pages"
                ],
            )
        ),
    )


# =====================================================
# СКАСУВАННЯ ПОШУКУ
# =====================================================


@router.callback_query(
    F.data == "material_search_cancel"
)
async def material_search_cancel_handler(
    callback: CallbackQuery,
) -> None:
    user_data = (
        await validate_materials_callback_access(
            callback
        )
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

        await safe_edit_message(
            message=callback.message,
            text=(
                "🧵 <b>Матеріали</b>\n\n"
                "Оберіть потрібний підрозділ:"
            ),
            reply_markup=(
                build_materials_menu_keyboard()
            ),
        )

    await callback.answer()


# =====================================================
# ПОВЕРНЕННЯ ДО ГОЛОВНОГО МЕНЮ
# =====================================================


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


# =====================================================
# ПЕРЕМИКАННЯ СТОРІНОК
# =====================================================


@router.callback_query(
    F.data.startswith(
        "material_search_page:"
    )
)
async def material_search_page_handler(
    callback: CallbackQuery,
) -> None:
    user_data = (
        await validate_materials_callback_access(
            callback
        )
    )

    if user_data is None:
        return

    if not isinstance(
        callback.message,
        Message,
    ):
        await callback.answer()
        return

    try:
        page = int(
            str(callback.data).split(":")[1]
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
    )

    await callback.answer()


# =====================================================
# ВІДКРИТТЯ МАТЕРІАЛУ
# =====================================================


@router.callback_query(
    F.data.startswith(
        "material_search_open:"
    )
)
async def material_search_open_handler(
    callback: CallbackQuery,
) -> None:
    user_data = (
        await validate_materials_callback_access(
            callback
        )
    )

    if user_data is None:
        return

    if not isinstance(
        callback.message,
        Message,
    ):
        await callback.answer()
        return

    try:
        parts = str(
            callback.data
        ).split(":")

        material_id = int(
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
            "Не вдалося відкрити матеріал.",
            show_alert=True,
        )
        return

    material = await load_material_detail(
        material_id
    )

    if material is None:
        await callback.answer(
            "Матеріал не знайдено.",
            show_alert=True,
        )
        return

    stock_status = (
        "⚠️ Малий запас"
        if material["is_low_stock"]
        else "✅ Запас достатній"
    )

    title = material["name"]

    if material["color_name"]:
        title += (
            f" — {material['color_name']}"
        )

    text_parts = [
        (
            "🧵 <b>"
            f"{escape(title)}"
            "</b>"
        ),
        (
            "Тип: "
            f"<b>{escape(material['type'])}</b>"
        ),
        (
            "Залишок: "
            f"<b>{escape(material['quantity'])} "
            f"{escape(material['unit'])}</b>"
        ),
        (
            "Мінімальний запас: "
            f"<b>{escape(material['minimum'])} "
            f"{escape(material['unit'])}</b>"
        ),
        (
            "Стан: "
            f"<b>{stock_status}</b>"
        ),
    ]

    if material["manufacturer"]:
        text_parts.append(
            (
                "Виробник: "
                f"<b>{escape(material['manufacturer'])}</b>"
            )
        )

    if material["article"]:
        text_parts.append(
            (
                "Артикул: "
                f"<b>{escape(material['article'])}</b>"
            )
        )

    if material["color_code"]:
        text_parts.append(
            (
                "Код кольору: "
                f"<b>{escape(material['color_code'])}</b>"
            )
        )

    await safe_edit_message(
        message=callback.message,
        text="\n".join(
            text_parts
        ),
        reply_markup=(
            build_detail_keyboard(
                page
            )
        ),
    )

    await callback.answer()


# =====================================================
# ПОТОЧНА СТОРІНКА
# =====================================================


@router.callback_query(
    F.data == "material_search_current_page"
)
async def material_search_current_page_handler(
    callback: CallbackQuery,
) -> None:
    user_data = (
        await validate_materials_callback_access(
            callback
        )
    )

    if user_data is None:
        return

    await callback.answer(
        "Це поточна сторінка."
    )