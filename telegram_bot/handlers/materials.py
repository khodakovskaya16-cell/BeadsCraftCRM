from decimal import Decimal, InvalidOperation
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
from django.db.models import Count

from materials.models import Material
from telegram_bot.keyboards.main_menu import (
    MATERIALS_ALLOWED_ROLES,
    build_main_menu_keyboard,
)
from telegram_bot.models import TelegramUser
from telegram_bot.utils.navigation import send_screen


router = Router(name="materials")

PAGE_SIZE = 5

VALID_LIST_MODES = frozenset(
    {
        "all",
        "low",
        "type",
    }
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

    formatted_value = format(
        decimal_value,
        "f",
    )

    if "." in formatted_value:
        formatted_value = (
            formatted_value
            .rstrip("0")
            .rstrip(".")
        )

    return formatted_value


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


# =====================================================
# ПЕРЕВІРКА ДОСТУПУ
# =====================================================


@sync_to_async(thread_sensitive=True)
def load_telegram_user_access(
    telegram_id: int,
) -> dict | None:
    try:
        telegram_user = (
            TelegramUser.objects.get(
                telegram_id=telegram_id
            )
        )

    except TelegramUser.DoesNotExist:
        return None

    return {
        "role": telegram_user.role,
        "is_active": telegram_user.is_active,
    }


async def validate_materials_callback_access(
    callback: CallbackQuery,
) -> dict | None:
    telegram_user = callback.from_user

    if telegram_user is None:
        await callback.answer(
            "Не вдалося визначити користувача.",
            show_alert=True,
        )
        return None

    user_data = await load_telegram_user_access(
        telegram_user.id
    )

    if user_data is None:
        await callback.answer(
            "Спочатку виконайте команду /start.",
            show_alert=True,
        )
        return None

    if not user_data["is_active"]:
        if isinstance(
            callback.message,
            Message,
        ):
            await safe_edit_message(
                message=callback.message,
                text=(
                    "⛔ <b>Обліковий запис "
                    "деактивовано.</b>\n\n"
                    "Зверніться до адміністратора."
                ),
            )

        await callback.answer(
            "Ваш обліковий запис деактивовано.",
            show_alert=True,
        )
        return None

    if (
        user_data["role"]
        not in MATERIALS_ALLOWED_ROLES
    ):
        if isinstance(
            callback.message,
            Message,
        ):
            await safe_edit_message(
                message=callback.message,
                text=(
                    "⛔ <b>Доступ заборонено</b>\n\n"
                    "Розділ матеріалів доступний "
                    "лише менеджерам та "
                    "адміністраторам."
                ),
                reply_markup=(
                    build_main_menu_keyboard(
                        user_data["role"]
                    )
                ),
            )

        await callback.answer(
            (
                "Розділ матеріалів доступний "
                "лише менеджерам та "
                "адміністраторам."
            ),
            show_alert=True,
        )
        return None

    return user_data


async def validate_materials_message_access(
    message: Message,
) -> dict | None:
    telegram_user = message.from_user

    if telegram_user is None:
        await message.answer(
            "Не вдалося визначити користувача."
        )
        return None

    user_data = await load_telegram_user_access(
        telegram_user.id
    )

    if user_data is None:
        await message.answer(
            "Спочатку виконайте команду /start."
        )
        return None

    if not user_data["is_active"]:
        await message.answer(
            "⛔ Ваш обліковий запис "
            "деактивовано. Зверніться "
            "до адміністратора."
        )
        return None

    if (
        user_data["role"]
        not in MATERIALS_ALLOWED_ROLES
    ):
        await message.answer(
            "⛔ Розділ матеріалів доступний "
            "лише менеджерам та "
            "адміністраторам."
        )
        return None

    return user_data


# =====================================================
# ЗАВАНТАЖЕННЯ ДАНИХ
# =====================================================


@sync_to_async(thread_sensitive=True)
def load_material_types() -> list[dict]:
    queryset = (
        Material.objects
        .exclude(
            material_type__isnull=True
        )
        .values(
            "material_type_id",
            "material_type__name",
        )
        .annotate(
            materials_count=Count("id")
        )
        .order_by(
            "material_type__name"
        )
    )

    material_types = []

    for row in queryset:
        material_types.append(
            {
                "id": row[
                    "material_type_id"
                ],
                "name": str(
                    row[
                        "material_type__name"
                    ]
                    or "Без назви"
                ),
                "count": row[
                    "materials_count"
                ],
            }
        )

    return material_types


@sync_to_async(thread_sensitive=True)
def load_materials_page(
    mode: str,
    material_type_id: int,
    page: int,
) -> dict:
    queryset = (
        Material.objects
        .select_related(
            "material_type"
        )
        .all()
        .order_by(
            "material_type__name",
            "name",
            "color_name",
            "id",
        )
    )

    section_title = "Усі матеріали"

    if mode == "type":
        queryset = queryset.filter(
            material_type_id=(
                material_type_id
            )
        )

        first_material = queryset.first()

        if first_material is not None:
            material_type = getattr(
                first_material,
                "material_type",
                None,
            )

            type_name = (
                str(material_type)
                if material_type
                else "Без типу"
            )

        else:
            type_name = "Тип не знайдено"

        section_title = (
            f"Тип: {type_name}"
        )

    materials_list = list(
        queryset
    )

    if mode == "low":
        materials_list = [
            material
            for material in materials_list
            if material_is_low_stock(
                material
            )
        ]

        section_title = (
            "Матеріали з малим запасом"
        )

    total_count = len(
        materials_list
    )

    if total_count == 0:
        return {
            "materials": [],
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
        min(
            page,
            total_pages,
        ),
    )

    start_index = (
        page - 1
    ) * PAGE_SIZE

    end_index = (
        start_index
        + PAGE_SIZE
    )

    page_materials = materials_list[
        start_index:end_index
    ]

    materials_data = []

    for material in page_materials:
        material_type = getattr(
            material,
            "material_type",
            None,
        )

        type_name = (
            str(material_type)
            if material_type
            else "Без типу"
        )

        color_name = str(
            getattr(
                material,
                "color_name",
                "",
            )
            or ""
        )

        material_name = str(
            getattr(
                material,
                "name",
                "Без назви",
            )
        )

        if color_name:
            full_name = (
                f"{material_name} — "
                f"{color_name}"
            )
        else:
            full_name = material_name

        materials_data.append(
            {
                "id": material.pk,
                "name": full_name,
                "type": type_name,
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
        "materials": materials_data,
        "total_count": total_count,
        "page": page,
        "total_pages": total_pages,
        "section_title": section_title,
    }


@sync_to_async(thread_sensitive=True)
def load_material_detail(
    material_id: int,
) -> dict | None:
    try:
        material = (
            Material.objects
            .select_related(
                "material_type"
            )
            .get(
                pk=material_id
            )
        )

    except Material.DoesNotExist:
        return None

    material_type = getattr(
        material,
        "material_type",
        None,
    )

    type_name = (
        str(material_type)
        if material_type
        else "Без типу"
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
        "type": type_name,
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


def build_materials_menu_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Усі матеріали",
                    callback_data=(
                        "materials_list:"
                        "all:0:1"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚠️ Малий запас",
                    callback_data=(
                        "materials_list:"
                        "low:0:1"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗂 За типом",
                    callback_data=(
                        "materials_types"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔍 Пошук",
                    callback_data=(
                        "materials_search"
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


def build_material_types_keyboard(
    material_types: list[dict],
) -> InlineKeyboardMarkup:
    rows = []

    for material_type in material_types:
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{material_type['name']} "
                        f"({material_type['count']})"
                    ),
                    callback_data=(
                        "materials_list:"
                        "type:"
                        f"{material_type['id']}:"
                        "1"
                    ),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=(
                    "⬅️ До розділу "
                    "матеріалів"
                ),
                callback_data=(
                    "materials_menu"
                ),
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


def build_materials_list_keyboard(
    materials: list[dict],
    mode: str,
    material_type_id: int,
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
                        "material_open:"
                        f"{material['id']}:"
                        f"{mode}:"
                        f"{material_type_id}:"
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
                    "materials_list:"
                    f"{mode}:"
                    f"{material_type_id}:"
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
                "materials_current_page"
            ),
        )
    )

    if page < total_pages:
        navigation_row.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=(
                    "materials_list:"
                    f"{mode}:"
                    f"{material_type_id}:"
                    f"{page + 1}"
                ),
            )
        )

    rows.append(
        navigation_row
    )

    if mode == "type":
        back_text = "⬅️ До типів"
        back_callback = (
            "materials_types"
        )
    else:
        back_text = (
            "⬅️ До розділу матеріалів"
        )
        back_callback = (
            "materials_menu"
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=back_text,
                callback_data=(
                    back_callback
                ),
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


def build_material_detail_keyboard(
    mode: str,
    material_type_id: int,
    page: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ До списку",
                    callback_data=(
                        "materials_list:"
                        f"{mode}:"
                        f"{material_type_id}:"
                        f"{page}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "🧵 До розділу "
                        "матеріалів"
                    ),
                    callback_data=(
                        "materials_menu"
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


# =====================================================
# ВІДОБРАЖЕННЯ ЕКРАНІВ
# =====================================================


async def show_materials_menu(
    message: Message,
) -> None:
    await safe_edit_message(
        message=message,
        text=(
            "🧵 <b>Матеріали</b>\n\n"
            "Оберіть потрібний підрозділ:"
        ),
        reply_markup=(
            build_materials_menu_keyboard()
        ),
    )


async def show_material_types(
    message: Message,
) -> None:
    material_types = (
        await load_material_types()
    )

    if not material_types:
        text = (
            "🗂 <b>Матеріали за типом</b>"
            "\n\n"
            "Типів матеріалів не знайдено."
        )
    else:
        text = (
            "🗂 <b>Матеріали за типом</b>"
            "\n\n"
            "Оберіть потрібний тип:"
        )

    await safe_edit_message(
        message=message,
        text=text,
        reply_markup=(
            build_material_types_keyboard(
                material_types
            )
        ),
    )


async def show_materials_list(
    message: Message,
    mode: str,
    material_type_id: int,
    page: int,
) -> None:
    data = await load_materials_page(
        mode=mode,
        material_type_id=(
            material_type_id
        ),
        page=page,
    )

    keyboard = (
        build_materials_list_keyboard(
            materials=data["materials"],
            mode=mode,
            material_type_id=(
                material_type_id
            ),
            page=data["page"],
            total_pages=(
                data["total_pages"]
            ),
        )
    )

    if not data["materials"]:
        await safe_edit_message(
            message=message,
            text=(
                "🧵 <b>"
                f"{escape(data['section_title'])}"
                "</b>\n\n"
                "Матеріалів не знайдено."
            ),
            reply_markup=keyboard,
        )
        return

    text = (
        "🧵 <b>"
        f"{escape(data['section_title'])}"
        "</b>\n\n"
        f"Усього позицій: "
        f"<b>{data['total_count']}</b>\n"
        f"Сторінка: "
        f"<b>{data['page']} із "
        f"{data['total_pages']}</b>\n\n"
        "Оберіть матеріал:"
    )

    await safe_edit_message(
        message=message,
        text=text,
        reply_markup=keyboard,
    )


# =====================================================
# ТЕКСТОВА КНОПКА
# =====================================================


@router.message(
    F.text == "🧵 Матеріали"
)
async def materials_handler(
    message: Message,
) -> None:
    user_data = (
        await validate_materials_message_access(
            message
        )
    )

    if user_data is None:
        return

    await send_screen(
        message=message,
        text=(
            "🧵 <b>Матеріали</b>\n\n"
            "Оберіть потрібний підрозділ:"
        ),
        reply_markup=(
            build_materials_menu_keyboard()
        ),
    )


# =====================================================
# МЕНЮ МАТЕРІАЛІВ
# =====================================================


@router.callback_query(
    F.data == "materials_menu"
)
async def materials_menu_handler(
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
        await show_materials_menu(
            callback.message
        )

    await callback.answer()


# =====================================================
# ТИПИ МАТЕРІАЛІВ
# =====================================================


@router.callback_query(
    F.data == "materials_types"
)
async def materials_types_handler(
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
        await show_material_types(
            callback.message
        )

    await callback.answer()


# =====================================================
# СПИСОК МАТЕРІАЛІВ
# =====================================================


@router.callback_query(
    F.data.startswith(
        "materials_list:"
    )
)
async def materials_list_handler(
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
            callback.data or ""
        ).split(":")

        mode = parts[1]

        material_type_id = int(
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

    if mode not in VALID_LIST_MODES:
        await callback.answer(
            "Неправильний режим списку.",
            show_alert=True,
        )
        return

    await show_materials_list(
        message=callback.message,
        mode=mode,
        material_type_id=(
            material_type_id
        ),
        page=page,
    )

    await callback.answer()


# =====================================================
# КАРТКА МАТЕРІАЛУ
# =====================================================


@router.callback_query(
    F.data.startswith(
        "material_open:"
    )
)
async def material_open_handler(
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
            callback.data or ""
        ).split(":")

        material_id = int(
            parts[1]
        )

        mode = parts[2]

        material_type_id = int(
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
            "Не вдалося відкрити матеріал.",
            show_alert=True,
        )
        return

    if mode not in VALID_LIST_MODES:
        await callback.answer(
            "Неправильний режим списку.",
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

    if material["is_low_stock"]:
        stock_status = (
            "⚠️ Малий запас"
        )
    else:
        stock_status = (
            "✅ Запас достатній"
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
                f"<b>"
                f"{escape(material['manufacturer'])}"
                f"</b>"
            )
        )

    if material["article"]:
        text_parts.append(
            (
                "Артикул: "
                f"<b>"
                f"{escape(material['article'])}"
                f"</b>"
            )
        )

    if material["color_code"]:
        text_parts.append(
            (
                "Код кольору: "
                f"<b>"
                f"{escape(material['color_code'])}"
                f"</b>"
            )
        )

    await safe_edit_message(
        message=callback.message,
        text="\n".join(
            text_parts
        ),
        reply_markup=(
            build_material_detail_keyboard(
                mode=mode,
                material_type_id=(
                    material_type_id
                ),
                page=page,
            )
        ),
    )

    await callback.answer()


# =====================================================
# ПОТОЧНА СТОРІНКА
# =====================================================


@router.callback_query(
    F.data == "materials_current_page"
)
async def materials_current_page_handler(
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