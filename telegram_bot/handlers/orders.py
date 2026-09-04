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
from django.utils import timezone

from shop.models import Order
from telegram_bot.utils.navigation import send_screen


router = Router(name="orders")

PAGE_SIZE = 5
DETAIL_ITEMS_LIMIT = 10


# =====================================================
# СТАТУСИ
# =====================================================


STATUS_CLASS = getattr(
    Order,
    "Status",
    None,
)

STATUS_NEW = getattr(
    STATUS_CLASS,
    "NEW",
    "new",
)

STATUS_CONFIRMED = getattr(
    STATUS_CLASS,
    "CONFIRMED",
    "confirmed",
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


def format_quantity(value) -> str:
    """
    Перетворює:
    10.00 -> 10
    2.50 -> 2.5
    """

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


def get_status_icon(
    status: str,
) -> str:
    icons = {
        str(STATUS_NEW): "🆕",
        str(STATUS_CONFIRMED): "✅",
        str(STATUS_COMPLETED): "📦",
        str(STATUS_CANCELLED): "🚫",
    }

    return icons.get(
        str(status),
        "🛒",
    )


def get_status_label(
    status: str,
) -> str:
    """
    Отримує назву статусу з choices моделі.
    """

    try:
        field = Order._meta.get_field(
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


def get_item_value(
    item,
    field_name: str,
    default="",
):
    value = getattr(
        item,
        field_name,
        default,
    )

    if callable(value):
        try:
            return value()
        except TypeError:
            return default

    return value


async def safe_edit_message(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """
    Редагує поточний екран Telegram-бота.
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
# ЗАВАНТАЖЕННЯ СПИСКУ ЗАМОВЛЕНЬ
# =====================================================


@sync_to_async(thread_sensitive=True)
def load_orders_page(
    mode: str,
    page: int,
) -> dict:
    queryset = (
        Order.objects
        .select_related(
            "cart",
            "cart__scheme",
        )
        .prefetch_related("items")
        .order_by(
            "-created_at",
            "-id",
        )
    )

    section_title = "Усі замовлення"

    if mode != "all":
        queryset = queryset.filter(
            status=mode
        )

        section_title = (
            get_status_label(mode)
        )

    total_count = queryset.count()

    if total_count == 0:
        return {
            "orders": [],
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

    orders_data = []

    for order in page_queryset:
        cart = getattr(
            order,
            "cart",
            None,
        )

        scheme = getattr(
            cart,
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

        created_at = getattr(
            order,
            "created_at",
            None,
        )

        if created_at is not None:
            created_at_text = (
                timezone.localtime(
                    created_at
                ).strftime(
                    "%d.%m.%Y %H:%M"
                )
            )
        else:
            created_at_text = (
                "Не вказано"
            )

        items = list(
            order.items.all()
        )

        order_number = str(
            getattr(
                order,
                "order_number",
                f"Замовлення №{order.pk}",
            )
        )

        customer_name = str(
            getattr(
                order,
                "customer_name",
                "",
            )
            or "Не вказано"
        )

        orders_data.append(
            {
                "id": order.pk,
                "number": order_number,
                "customer_name": customer_name,
                "scheme": scheme_title,
                "status": str(
                    getattr(
                        order,
                        "status",
                        "",
                    )
                ),
                "status_display": str(
                    order.get_status_display()
                ),
                "created_at": created_at_text,
                "items_count": len(items),
            }
        )

    return {
        "orders": orders_data,
        "total_count": total_count,
        "page": page,
        "total_pages": total_pages,
        "section_title": section_title,
    }


# =====================================================
# ЗАВАНТАЖЕННЯ КАРТКИ ЗАМОВЛЕННЯ
# =====================================================


@sync_to_async(thread_sensitive=True)
def load_order_detail(
    order_id: int,
) -> dict | None:
    try:
        order = (
            Order.objects
            .select_related(
                "cart",
                "cart__scheme",
            )
            .prefetch_related("items")
            .get(pk=order_id)
        )

    except Order.DoesNotExist:
        return None

    cart = getattr(
        order,
        "cart",
        None,
    )

    scheme = getattr(
        cart,
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

    created_at = getattr(
        order,
        "created_at",
        None,
    )

    if created_at is not None:
        created_at_text = (
            timezone.localtime(
                created_at
            ).strftime(
                "%d.%m.%Y %H:%M"
            )
        )
    else:
        created_at_text = (
            "Не вказано"
        )

    all_items = list(
        order.items.all()
    )

    items_data = []

    for item in all_items[
        :DETAIL_ITEMS_LIMIT
    ]:
        material_name = str(
            get_item_value(
                item,
                "material_name",
                "Матеріал",
            )
            or "Матеріал"
        )

        color_name = str(
            get_item_value(
                item,
                "color_name",
                "",
            )
            or ""
        )

        if color_name:
            material_title = (
                f"{material_name} — "
                f"{color_name}"
            )
        else:
            material_title = (
                material_name
            )

        quantity = format_quantity(
            get_item_value(
                item,
                "quantity",
                0,
            )
        )

        unit_label = str(
            get_item_value(
                item,
                "unit_label",
                "",
            )
            or ""
        )

        items_data.append(
            {
                "title": material_title,
                "quantity": quantity,
                "unit": unit_label,
            }
        )

    order_number = str(
        getattr(
            order,
            "order_number",
            f"Замовлення №{order.pk}",
        )
    )

    customer_name = str(
        getattr(
            order,
            "customer_name",
            "",
        )
        or "Не вказано"
    )

    phone = str(
        getattr(
            order,
            "phone",
            "",
        )
        or ""
    )

    email = str(
        getattr(
            order,
            "email",
            "",
        )
        or ""
    )

    return {
        "id": order.pk,
        "number": order_number,
        "customer_name": customer_name,
        "phone": phone,
        "email": email,
        "scheme": scheme_title,
        "status": str(
            getattr(
                order,
                "status",
                "",
            )
        ),
        "status_display": str(
            order.get_status_display()
        ),
        "created_at": created_at_text,
        "items": items_data,
        "items_count": len(
            all_items
        ),
    }


# =====================================================
# КЛАВІАТУРА ГОЛОВНОГО РОЗДІЛУ
# =====================================================


def build_orders_menu_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Усі замовлення",
                    callback_data=(
                        "orders_list:all:1"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🆕 Нові",
                    callback_data=(
                        "orders_list:"
                        f"{STATUS_NEW}:1"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Підтверджені",
                    callback_data=(
                        "orders_list:"
                        f"{STATUS_CONFIRMED}:1"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📦 Виконані",
                    callback_data=(
                        "orders_list:"
                        f"{STATUS_COMPLETED}:1"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Скасовані",
                    callback_data=(
                        "orders_list:"
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


def build_orders_list_keyboard(
    orders: list[dict],
    mode: str,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    rows = []

    for order in orders:
        status_icon = get_status_icon(
            order["status"]
        )

        button_text = (
            f"{status_icon} "
            f"{order['number']} — "
            f"{order['customer_name']}"
        )

        rows.append(
            [
                InlineKeyboardButton(
                    text=shorten_text(
                        button_text
                    ),
                    callback_data=(
                        "order_open:"
                        f"{order['id']}:"
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
                    "orders_list:"
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
                "orders_current_page"
            ),
        )
    )

    if page < total_pages:
        navigation_row.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=(
                    "orders_list:"
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
                    "⬅️ До розділу замовлень"
                ),
                callback_data="orders_menu",
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


def build_order_detail_keyboard(
    mode: str,
    page: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ До списку",
                    callback_data=(
                        "orders_list:"
                        f"{mode}:"
                        f"{page}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "🛒 До розділу замовлень"
                    ),
                    callback_data="orders_menu",
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


async def show_orders_menu(
    message: Message,
) -> None:
    await safe_edit_message(
        message=message,
        text=(
            "🛒 <b>Замовлення</b>\n\n"
            "Оберіть потрібний підрозділ:"
        ),
        reply_markup=(
            build_orders_menu_keyboard()
        ),
    )


async def show_orders_list(
    message: Message,
    mode: str,
    page: int,
) -> None:
    data = await load_orders_page(
        mode=mode,
        page=page,
    )

    keyboard = (
        build_orders_list_keyboard(
            orders=data["orders"],
            mode=mode,
            page=data["page"],
            total_pages=data[
                "total_pages"
            ],
        )
    )

    if not data["orders"]:
        await safe_edit_message(
            message=message,
            text=(
                "🛒 <b>"
                f"{escape(data['section_title'])}"
                "</b>\n\n"
                "Замовлень не знайдено."
            ),
            reply_markup=keyboard,
        )
        return

    text = (
        "🛒 <b>"
        f"{escape(data['section_title'])}"
        "</b>\n\n"
        f"Усього замовлень: "
        f"<b>{data['total_count']}</b>\n"
        f"Сторінка: "
        f"<b>{data['page']} із "
        f"{data['total_pages']}</b>\n\n"
        "Оберіть замовлення:"
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
    F.text == "🛒 Замовлення"
)
async def orders_handler(
    message: Message,
) -> None:
    await send_screen(
        message=message,
        text=(
            "🛒 <b>Замовлення</b>\n\n"
            "Оберіть потрібний підрозділ:"
        ),
        reply_markup=(
            build_orders_menu_keyboard()
        ),
    )


# =====================================================
# CALLBACK: ПОВЕРНЕННЯ ДО МЕНЮ
# =====================================================


@router.callback_query(
    F.data == "orders_menu"
)
async def orders_menu_handler(
    callback: CallbackQuery,
) -> None:
    if callback.message is not None:
        await show_orders_menu(
            callback.message
        )

    await callback.answer()


# =====================================================
# CALLBACK: СПИСОК ЗАМОВЛЕНЬ
# =====================================================


@router.callback_query(
    F.data.startswith(
        "orders_list:"
    )
)
async def orders_list_handler(
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

    await show_orders_list(
        message=callback.message,
        mode=mode,
        page=page,
    )

    await callback.answer()


# =====================================================
# CALLBACK: КАРТКА ЗАМОВЛЕННЯ
# =====================================================


@router.callback_query(
    F.data.startswith(
        "order_open:"
    )
)
async def order_open_handler(
    callback: CallbackQuery,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    try:
        parts = callback.data.split(
            ":"
        )

        order_id = int(
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
            "Не вдалося відкрити замовлення.",
            show_alert=True,
        )
        return

    order = await load_order_detail(
        order_id
    )

    if order is None:
        await callback.answer(
            "Замовлення не знайдено.",
            show_alert=True,
        )
        return

    status_icon = get_status_icon(
        order["status"]
    )

    text_parts = [
        (
            f"{status_icon} "
            f"<b>{escape(order['number'])}</b>"
        ),
        (
            "Статус: "
            f"<b>{escape(order['status_display'])}</b>"
        ),
        (
            "Дата: "
            f"<b>{escape(order['created_at'])}</b>"
        ),
        "",
        (
            "👤 Отримувач: "
            f"<b>{escape(order['customer_name'])}</b>"
        ),
        (
            "📚 Схема: "
            f"<b>{escape(order['scheme'])}</b>"
        ),
    ]

    if order["phone"]:
        text_parts.append(
            (
                "📞 Телефон: "
                f"<b>{escape(order['phone'])}</b>"
            )
        )

    if order["email"]:
        text_parts.append(
            (
                "✉️ Email: "
                f"<b>{escape(order['email'])}</b>"
            )
        )

    if order["items"]:
        text_parts.append(
            "\n🧵 <b>Матеріали</b>"
        )

        for item in order["items"]:
            unit_text = (
                f" {escape(item['unit'])}"
                if item["unit"]
                else ""
            )

            text_parts.append(
                (
                    "• "
                    f"{escape(item['title'])}: "
                    f"<b>{escape(item['quantity'])}"
                    f"{unit_text}</b>"
                )
            )

    else:
        text_parts.append(
            "\nМатеріали не вказані."
        )

    if (
        order["items_count"]
        > DETAIL_ITEMS_LIMIT
    ):
        hidden_count = (
            order["items_count"]
            - DETAIL_ITEMS_LIMIT
        )

        text_parts.append(
            f"… ще позицій: {hidden_count}"
        )

    await safe_edit_message(
        message=callback.message,
        text="\n".join(
            text_parts
        ),
        reply_markup=(
            build_order_detail_keyboard(
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
    F.data == "orders_current_page"
)
async def orders_current_page_handler(
    callback: CallbackQuery,
) -> None:
    await callback.answer(
        "Це поточна сторінка."
    )