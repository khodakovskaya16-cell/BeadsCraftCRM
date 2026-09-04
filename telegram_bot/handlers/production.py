from html import escape
from math import ceil

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from asgiref.sync import sync_to_async
from django.utils import timezone

from production.models import ProductionOrder
from telegram_bot.utils.navigation import send_screen


router = Router(name="production")

PAGE_SIZE = 5


# =====================================================
# СТАТУСИ
# =====================================================


STATUS_CLASS = getattr(
    ProductionOrder,
    "Status",
    None,
)

STATUS_PLANNED = getattr(
    STATUS_CLASS,
    "PLANNED",
    "planned",
)

STATUS_IN_PROGRESS = getattr(
    STATUS_CLASS,
    "IN_PROGRESS",
    "in_progress",
)

STATUS_COMPLETED = getattr(
    STATUS_CLASS,
    "COMPLETED",
    "completed",
)

STATUS_CANCELLED = getattr(
    STATUS_CLASS,
    "CANCELLED",
    "cancelled",
)


# =====================================================
# ДОПОМІЖНІ ФУНКЦІЇ
# =====================================================


def shorten_text(
    text: str,
    max_length: int = 44,
) -> str:
    if len(text) <= max_length:
        return text

    return text[:max_length - 3] + "..."


def get_status_icon(status: str) -> str:
    icons = {
        str(STATUS_PLANNED): "🗓",
        str(STATUS_IN_PROGRESS): "⚙️",
        str(STATUS_COMPLETED): "✅",
        str(STATUS_CANCELLED): "🚫",
    }

    return icons.get(
        str(status),
        "📌",
    )


def get_status_label(status: str) -> str:
    try:
        field = ProductionOrder._meta.get_field(
            "status"
        )

        choices = dict(
            field.flatchoices
        )

        return str(
            choices.get(
                status,
                status,
            )
        )

    except Exception:
        return str(status)


def format_datetime(value) -> str:
    if value is None:
        return ""

    try:
        return timezone.localtime(
            value
        ).strftime(
            "%d.%m.%Y %H:%M"
        )
    except (TypeError, ValueError):
        return str(value)


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
# ЗАВАНТАЖЕННЯ СПИСКУ
# =====================================================


@sync_to_async(thread_sensitive=True)
def load_production_page(
    mode: str,
    page: int,
) -> dict:
    queryset = (
        ProductionOrder.objects
        .select_related("scheme")
        .order_by(
            "-created_at",
            "-id",
        )
    )

    section_title = "Усі виробничі завдання"

    if mode != "all":
        queryset = queryset.filter(
            status=mode
        )

        section_title = get_status_label(
            mode
        )

    total_count = queryset.count()

    if total_count == 0:
        return {
            "productions": [],
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

    page_queryset = queryset[
        start_index:end_index
    ]

    production_data = []

    for production_order in page_queryset:
        scheme = getattr(
            production_order,
            "scheme",
            None,
        )

        scheme_title = str(
            getattr(
                scheme,
                "title",
                "Не вказано",
            )
        )

        production_number = str(
            getattr(
                production_order,
                "production_number",
                f"Завдання №{production_order.pk}",
            )
        )

        status = str(
            getattr(
                production_order,
                "status",
                "",
            )
        )

        production_data.append(
            {
                "id": production_order.pk,
                "number": production_number,
                "scheme": scheme_title,
                "quantity": getattr(
                    production_order,
                    "quantity",
                    0,
                ),
                "status": status,
                "status_display": str(
                    production_order.get_status_display()
                ),
                "created_at": format_datetime(
                    getattr(
                        production_order,
                        "created_at",
                        None,
                    )
                ),
            }
        )

    return {
        "productions": production_data,
        "total_count": total_count,
        "page": page,
        "total_pages": total_pages,
        "section_title": section_title,
    }


# =====================================================
# ЗАВАНТАЖЕННЯ КАРТКИ
# =====================================================


@sync_to_async(thread_sensitive=True)
def load_production_detail(
    production_id: int,
) -> dict | None:
    try:
        production_order = (
            ProductionOrder.objects
            .select_related("scheme")
            .get(pk=production_id)
        )

    except ProductionOrder.DoesNotExist:
        return None

    scheme = getattr(
        production_order,
        "scheme",
        None,
    )

    scheme_title = str(
        getattr(
            scheme,
            "title",
            "Не вказано",
        )
    )

    production_number = str(
        getattr(
            production_order,
            "production_number",
            f"Завдання №{production_order.pk}",
        )
    )

    notes = str(
        getattr(
            production_order,
            "notes",
            "",
        )
        or ""
    )

    if len(notes) > 1500:
        notes = notes[:1500] + "..."

    return {
        "id": production_order.pk,
        "number": production_number,
        "scheme": scheme_title,
        "quantity": getattr(
            production_order,
            "quantity",
            0,
        ),
        "status": str(
            getattr(
                production_order,
                "status",
                "",
            )
        ),
        "status_display": str(
            production_order.get_status_display()
        ),
        "created_at": format_datetime(
            getattr(
                production_order,
                "created_at",
                None,
            )
        ),
        "started_at": format_datetime(
            getattr(
                production_order,
                "started_at",
                None,
            )
        ),
        "completed_at": format_datetime(
            getattr(
                production_order,
                "completed_at",
                None,
            )
        ),
        "notes": notes,
    }


# =====================================================
# КЛАВІАТУРА РОЗДІЛУ
# =====================================================


def build_production_menu_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Усі завдання",
                    callback_data=(
                        "production_list:all:1"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗓 Заплановані",
                    callback_data=(
                        "production_list:"
                        f"{STATUS_PLANNED}:1"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ У роботі",
                    callback_data=(
                        "production_list:"
                        f"{STATUS_IN_PROGRESS}:1"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Завершені",
                    callback_data=(
                        "production_list:"
                        f"{STATUS_COMPLETED}:1"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Скасовані",
                    callback_data=(
                        "production_list:"
                        f"{STATUS_CANCELLED}:1"
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
# КЛАВІАТУРА СПИСКУ
# =====================================================


def build_production_list_keyboard(
    productions: list[dict],
    mode: str,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    rows = []

    for production_order in productions:
        status_icon = get_status_icon(
            production_order["status"]
        )

        button_text = (
            f"{status_icon} "
            f"{production_order['number']} — "
            f"{production_order['scheme']}"
        )

        rows.append(
            [
                InlineKeyboardButton(
                    text=shorten_text(
                        button_text
                    ),
                    callback_data=(
                        "production_open:"
                        f"{production_order['id']}:"
                        f"{mode}:"
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
                    "production_list:"
                    f"{mode}:"
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
                "production_current_page"
            ),
        )
    )

    if page < total_pages:
        navigation_row.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=(
                    "production_list:"
                    f"{mode}:"
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
                text=(
                    "⬅️ До розділу виробництва"
                ),
                callback_data="production_menu",
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


# =====================================================
# КЛАВІАТУРА КАРТКИ
# =====================================================


def build_production_detail_keyboard(
    mode: str,
    page: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ До списку",
                    callback_data=(
                        "production_list:"
                        f"{mode}:"
                        f"{page}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "⚙️ До розділу виробництва"
                    ),
                    callback_data="production_menu",
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


async def show_production_menu(
    message: Message,
) -> None:
    await safe_edit_message(
        message=message,
        text=(
            "⚙️ <b>Виробництво</b>\n\n"
            "Оберіть потрібний підрозділ:"
        ),
        reply_markup=(
            build_production_menu_keyboard()
        ),
    )


async def show_production_list(
    message: Message,
    mode: str,
    page: int,
) -> None:
    data = await load_production_page(
        mode=mode,
        page=page,
    )

    keyboard = (
        build_production_list_keyboard(
            productions=data[
                "productions"
            ],
            mode=mode,
            page=data["page"],
            total_pages=data[
                "total_pages"
            ],
        )
    )

    if not data["productions"]:
        await safe_edit_message(
            message=message,
            text=(
                "⚙️ <b>"
                f"{escape(data['section_title'])}"
                "</b>\n\n"
                "Виробничих завдань не знайдено."
            ),
            reply_markup=keyboard,
        )
        return

    text = (
        "⚙️ <b>"
        f"{escape(data['section_title'])}"
        "</b>\n\n"
        f"Усього завдань: "
        f"<b>{data['total_count']}</b>\n"
        f"Сторінка: "
        f"<b>{data['page']} із "
        f"{data['total_pages']}</b>\n\n"
        "Оберіть виробниче завдання:"
    )

    await safe_edit_message(
        message=message,
        text=text,
        reply_markup=keyboard,
    )


# =====================================================
# ГОЛОВНА КНОПКА ТА КОМАНДА
# =====================================================


@router.message(
    F.text == "⚙️ Виробництво"
)
@router.message(
    Command("production")
)
async def production_handler(
    message: Message,
) -> None:
    await send_screen(
        message=message,
        text=(
            "⚙️ <b>Виробництво</b>\n\n"
            "Оберіть потрібний підрозділ:"
        ),
        reply_markup=(
            build_production_menu_keyboard()
        ),
    )


# =====================================================
# CALLBACK: МЕНЮ
# =====================================================


@router.callback_query(
    F.data == "production_menu"
)
async def production_menu_handler(
    callback: CallbackQuery,
) -> None:
    if callback.message is not None:
        await show_production_menu(
            callback.message
        )

    await callback.answer()


# =====================================================
# CALLBACK: СПИСОК
# =====================================================


@router.callback_query(
    F.data.startswith(
        "production_list:"
    )
)
async def production_list_handler(
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

        page = int(
            parts[2]
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

    await show_production_list(
        message=callback.message,
        mode=mode,
        page=page,
    )

    await callback.answer()


# =====================================================
# CALLBACK: КАРТКА
# =====================================================


@router.callback_query(
    F.data.startswith(
        "production_open:"
    )
)
async def production_open_handler(
    callback: CallbackQuery,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    try:
        parts = callback.data.split(
            ":"
        )

        production_id = int(
            parts[1]
        )

        mode = parts[2]

        page = int(
            parts[3]
        )

    except (
        IndexError,
        ValueError,
    ):
        await callback.answer(
            "Не вдалося відкрити завдання.",
            show_alert=True,
        )
        return

    production_order = (
        await load_production_detail(
            production_id
        )
    )

    if production_order is None:
        await callback.answer(
            "Виробниче завдання не знайдено.",
            show_alert=True,
        )
        return

    status_icon = get_status_icon(
        production_order["status"]
    )

    text_parts = [
        (
            f"{status_icon} "
            f"<b>{escape(production_order['number'])}</b>"
        ),
        (
            "Статус: "
            f"<b>{escape(production_order['status_display'])}</b>"
        ),
        (
            "📚 Схема: "
            f"<b>{escape(production_order['scheme'])}</b>"
        ),
        (
            "Кількість виробів: "
            f"<b>{production_order['quantity']}</b>"
        ),
    ]

    if production_order["created_at"]:
        text_parts.append(
            (
                "Створено: "
                f"<b>{escape(production_order['created_at'])}</b>"
            )
        )

    if production_order["started_at"]:
        text_parts.append(
            (
                "Початок роботи: "
                f"<b>{escape(production_order['started_at'])}</b>"
            )
        )

    if production_order["completed_at"]:
        text_parts.append(
            (
                "Завершено: "
                f"<b>{escape(production_order['completed_at'])}</b>"
            )
        )

    if production_order["notes"]:
        text_parts.append(
            (
                "\n📝 <b>Примітка</b>\n"
                f"{escape(production_order['notes'])}"
            )
        )

    await safe_edit_message(
        message=callback.message,
        text="\n".join(
            text_parts
        ),
        reply_markup=(
            build_production_detail_keyboard(
                mode=mode,
                page=page,
            )
        ),
    )

    await callback.answer()


# =====================================================
# CALLBACK: НОМЕР СТОРІНКИ
# =====================================================


@router.callback_query(
    F.data == "production_current_page"
)
async def production_current_page_handler(
    callback: CallbackQuery,
) -> None:
    await callback.answer(
        "Це поточна сторінка."
    )