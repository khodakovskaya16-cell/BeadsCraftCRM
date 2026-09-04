from html import escape

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

from materials.models import Material
from production.models import ProductionOrder
from schemes.models import Scheme, SchemeFavorite
from shop.models import Order
from telegram_bot.utils.navigation import send_screen


router = Router(name="statistics")


# =====================================================
# СТАТУСИ ЗАМОВЛЕНЬ
# =====================================================


ORDER_STATUS_CLASS = getattr(
    Order,
    "Status",
    None,
)

ORDER_STATUS_NEW = getattr(
    ORDER_STATUS_CLASS,
    "NEW",
    "new",
)

ORDER_STATUS_CONFIRMED = getattr(
    ORDER_STATUS_CLASS,
    "CONFIRMED",
    "confirmed",
)

ORDER_STATUS_COMPLETED = getattr(
    ORDER_STATUS_CLASS,
    "COMPLETED",
    "completed",
)

ORDER_STATUS_CANCELLED = getattr(
    ORDER_STATUS_CLASS,
    "CANCELLED",
    "cancelled",
)


# =====================================================
# СТАТУСИ ВИРОБНИЦТВА
# =====================================================


PRODUCTION_STATUS_CLASS = getattr(
    ProductionOrder,
    "Status",
    None,
)

PRODUCTION_STATUS_PLANNED = getattr(
    PRODUCTION_STATUS_CLASS,
    "PLANNED",
    "planned",
)

PRODUCTION_STATUS_IN_PROGRESS = getattr(
    PRODUCTION_STATUS_CLASS,
    "IN_PROGRESS",
    "in_progress",
)

PRODUCTION_STATUS_COMPLETED = getattr(
    PRODUCTION_STATUS_CLASS,
    "COMPLETED",
    "completed",
)

PRODUCTION_STATUS_CANCELLED = getattr(
    PRODUCTION_STATUS_CLASS,
    "CANCELLED",
    "cancelled",
)


# =====================================================
# ДОПОМІЖНІ ФУНКЦІЇ
# =====================================================


def material_is_low_stock(
    material: Material,
) -> bool:
    """
    Перевіряє, чи має матеріал малий запас.

    Працює і для property, і для звичайного поля.
    """

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
    """Безпечно редагує поточний екран бота."""

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
# ЗАВАНТАЖЕННЯ ЗАГАЛЬНОЇ СТАТИСТИКИ
# =====================================================


@sync_to_async(thread_sensitive=True)
def load_general_statistics(
    telegram_id: int,
) -> dict[str, int]:
    """
    Завантажує загальну статистику.

    Кількість обраних схем визначається окремо
    для поточного Telegram-користувача.
    """

    materials = list(
        Material.objects.all()
    )

    low_stock_count = sum(
        1
        for material in materials
        if material_is_low_stock(material)
    )

    active_production = (
        ProductionOrder.objects
        .filter(
            status__in=[
                PRODUCTION_STATUS_PLANNED,
                PRODUCTION_STATUS_IN_PROGRESS,
            ]
        )
        .count()
    )

    favorite_schemes_count = (
        SchemeFavorite.objects
        .filter(
            user__telegram_id=telegram_id,
            user__is_active=True,
        )
        .count()
    )

    return {
        "schemes_total": (
            Scheme.objects.count()
        ),

        "favorite_schemes": (
            favorite_schemes_count
        ),

        "materials_total": (
            len(materials)
        ),

        "low_stock_count": (
            low_stock_count
        ),

        "orders_total": (
            Order.objects.count()
        ),

        "new_orders": (
            Order.objects
            .filter(
                status=ORDER_STATUS_NEW
            )
            .count()
        ),

        "production_total": (
            ProductionOrder.objects.count()
        ),

        "active_production": (
            active_production
        ),
    }


# =====================================================
# СТАТИСТИКА СХЕМ
# =====================================================


@sync_to_async(thread_sensitive=True)
def load_schemes_statistics(
    telegram_id: int,
) -> dict:
    """
    Завантажує статистику схем.

    Обране підраховується персонально
    для поточного Telegram-користувача.
    """

    category_field = (
        Scheme._meta.get_field(
            "category"
        )
    )

    status_field = (
        Scheme._meta.get_field(
            "status"
        )
    )

    category_choices = dict(
        category_field.flatchoices
    )

    status_choices = dict(
        status_field.flatchoices
    )

    category_rows = (
        Scheme.objects
        .exclude(category="")
        .values("category")
        .order_by("category")
    )

    category_counts: dict[str, int] = {}

    for row in category_rows:
        value = str(
            row["category"]
        )

        category_counts[value] = (
            category_counts.get(
                value,
                0,
            )
            + 1
        )

    status_rows = (
        Scheme.objects
        .exclude(status="")
        .values("status")
        .order_by("status")
    )

    status_counts: dict[str, int] = {}

    for row in status_rows:
        value = str(
            row["status"]
        )

        status_counts[value] = (
            status_counts.get(
                value,
                0,
            )
            + 1
        )

    categories = []

    for value, count in category_counts.items():
        categories.append(
            {
                "label": str(
                    category_choices.get(
                        value,
                        value,
                    )
                ),
                "count": count,
            }
        )

    statuses = []

    for value, count in status_counts.items():
        statuses.append(
            {
                "label": str(
                    status_choices.get(
                        value,
                        value,
                    )
                ),
                "count": count,
            }
        )

    favorite_schemes_count = (
        SchemeFavorite.objects
        .filter(
            user__telegram_id=telegram_id,
            user__is_active=True,
        )
        .count()
    )

    return {
        "total": (
            Scheme.objects.count()
        ),

        "favorite": (
            favorite_schemes_count
        ),

        "categories": categories,

        "statuses": statuses,
    }


# =====================================================
# СТАТИСТИКА МАТЕРІАЛІВ
# =====================================================


@sync_to_async(thread_sensitive=True)
def load_materials_statistics() -> dict:
    """Завантажує статистику матеріалів."""

    materials = list(
        Material.objects
        .select_related("material_type")
        .all()
    )

    low_stock_count = sum(
        1
        for material in materials
        if material_is_low_stock(material)
    )

    type_counts: dict[str, int] = {}

    for material in materials:
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

        type_counts[type_name] = (
            type_counts.get(
                type_name,
                0,
            )
            + 1
        )

    types = [
        {
            "name": name,
            "count": count,
        }
        for name, count in sorted(
            type_counts.items()
        )
    ]

    return {
        "total": (
            len(materials)
        ),

        "low_stock": (
            low_stock_count
        ),

        "normal_stock": (
            len(materials)
            - low_stock_count
        ),

        "types": types,
    }


# =====================================================
# СТАТИСТИКА ЗАМОВЛЕНЬ
# =====================================================


@sync_to_async(thread_sensitive=True)
def load_orders_statistics() -> dict[str, int]:
    """Завантажує статистику замовлень."""

    return {
        "total": (
            Order.objects.count()
        ),

        "new": (
            Order.objects
            .filter(
                status=ORDER_STATUS_NEW
            )
            .count()
        ),

        "confirmed": (
            Order.objects
            .filter(
                status=ORDER_STATUS_CONFIRMED
            )
            .count()
        ),

        "completed": (
            Order.objects
            .filter(
                status=ORDER_STATUS_COMPLETED
            )
            .count()
        ),

        "cancelled": (
            Order.objects
            .filter(
                status=ORDER_STATUS_CANCELLED
            )
            .count()
        ),
    }


# =====================================================
# СТАТИСТИКА ВИРОБНИЦТВА
# =====================================================


@sync_to_async(thread_sensitive=True)
def load_production_statistics() -> dict[str, int]:
    """Завантажує статистику виробництва."""

    return {
        "total": (
            ProductionOrder.objects.count()
        ),

        "planned": (
            ProductionOrder.objects
            .filter(
                status=(
                    PRODUCTION_STATUS_PLANNED
                )
            )
            .count()
        ),

        "in_progress": (
            ProductionOrder.objects
            .filter(
                status=(
                    PRODUCTION_STATUS_IN_PROGRESS
                )
            )
            .count()
        ),

        "completed": (
            ProductionOrder.objects
            .filter(
                status=(
                    PRODUCTION_STATUS_COMPLETED
                )
            )
            .count()
        ),

        "cancelled": (
            ProductionOrder.objects
            .filter(
                status=(
                    PRODUCTION_STATUS_CANCELLED
                )
            )
            .count()
        ),
    }


# =====================================================
# КЛАВІАТУРИ
# =====================================================


def build_statistics_menu_keyboard(
) -> InlineKeyboardMarkup:
    """Створює головне меню статистики."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Загальна",
                    callback_data=(
                        "statistics_general"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📚 Схеми",
                    callback_data=(
                        "statistics_schemes"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧵 Матеріали",
                    callback_data=(
                        "statistics_materials"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛒 Замовлення",
                    callback_data=(
                        "statistics_orders"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ Виробництво",
                    callback_data=(
                        "statistics_production"
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


def build_statistics_back_keyboard(
) -> InlineKeyboardMarkup:
    """Створює клавіатуру повернення."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=(
                        "⬅️ До розділу статистики"
                    ),
                    callback_data="statistics_menu",
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
# ВІДОБРАЖЕННЯ МЕНЮ
# =====================================================


async def show_statistics_menu(
    message: Message,
) -> None:
    """Показує головне меню статистики."""

    await safe_edit_message(
        message=message,
        text=(
            "📊 <b>Статистика</b>\n\n"
            "Оберіть потрібний підрозділ:"
        ),
        reply_markup=(
            build_statistics_menu_keyboard()
        ),
    )


# =====================================================
# ГОЛОВНА КНОПКА ТА КОМАНДА
# =====================================================


@router.message(
    F.text == "📊 Статистика"
)
@router.message(
    Command("statistics")
)
async def statistics_handler(
    message: Message,
) -> None:
    """Відкриває розділ статистики."""

    await send_screen(
        message=message,
        text=(
            "📊 <b>Статистика</b>\n\n"
            "Оберіть потрібний підрозділ:"
        ),
        reply_markup=(
            build_statistics_menu_keyboard()
        ),
    )


# =====================================================
# CALLBACK: ПОВЕРНЕННЯ ДО МЕНЮ
# =====================================================


@router.callback_query(
    F.data == "statistics_menu"
)
async def statistics_menu_handler(
    callback: CallbackQuery,
) -> None:
    """Повертає користувача до меню статистики."""

    if callback.message is not None:
        await show_statistics_menu(
            callback.message
        )

    await callback.answer()


# =====================================================
# CALLBACK: ЗАГАЛЬНА СТАТИСТИКА
# =====================================================


@router.callback_query(
    F.data == "statistics_general"
)
async def statistics_general_handler(
    callback: CallbackQuery,
) -> None:
    """Показує загальну статистику."""

    if callback.message is None:
        await callback.answer()
        return

    data = await load_general_statistics(
        telegram_id=callback.from_user.id,
    )

    text = (
        "📊 <b>Загальна статистика</b>\n\n"

        "📚 <b>Схеми</b>\n"
        f"Усього: "
        f"<b>{data['schemes_total']}</b>\n"
        f"Мої обрані: "
        f"<b>{data['favorite_schemes']}</b>\n\n"

        "🧵 <b>Матеріали</b>\n"
        f"Усього позицій: "
        f"<b>{data['materials_total']}</b>\n"
        f"Малий запас: "
        f"<b>{data['low_stock_count']}</b>\n\n"

        "🛒 <b>Замовлення</b>\n"
        f"Усього: "
        f"<b>{data['orders_total']}</b>\n"
        f"Нові: "
        f"<b>{data['new_orders']}</b>\n\n"

        "⚙️ <b>Виробництво</b>\n"
        f"Усього завдань: "
        f"<b>{data['production_total']}</b>\n"
        f"Активні: "
        f"<b>{data['active_production']}</b>"
    )

    await safe_edit_message(
        message=callback.message,
        text=text,
        reply_markup=(
            build_statistics_back_keyboard()
        ),
    )

    await callback.answer()


# =====================================================
# CALLBACK: СТАТИСТИКА СХЕМ
# =====================================================


@router.callback_query(
    F.data == "statistics_schemes"
)
async def statistics_schemes_handler(
    callback: CallbackQuery,
) -> None:
    """Показує статистику схем."""

    if callback.message is None:
        await callback.answer()
        return

    data = await load_schemes_statistics(
        telegram_id=callback.from_user.id,
    )

    text_parts = [
        "📚 <b>Статистика схем</b>",
        "",
        (
            "Усього схем: "
            f"<b>{data['total']}</b>"
        ),
        (
            "Моїх обраних схем: "
            f"<b>{data['favorite']}</b>"
        ),
    ]

    if data["categories"]:
        text_parts.append(
            "\n🗂 <b>За категоріями</b>"
        )

        for category in data["categories"]:
            text_parts.append(
                (
                    "• "
                    f"{escape(category['label'])}: "
                    f"<b>{category['count']}</b>"
                )
            )

    if data["statuses"]:
        text_parts.append(
            "\n📌 <b>За статусами</b>"
        )

        for status in data["statuses"]:
            text_parts.append(
                (
                    "• "
                    f"{escape(status['label'])}: "
                    f"<b>{status['count']}</b>"
                )
            )

    await safe_edit_message(
        message=callback.message,
        text="\n".join(text_parts),
        reply_markup=(
            build_statistics_back_keyboard()
        ),
    )

    await callback.answer()


# =====================================================
# CALLBACK: СТАТИСТИКА МАТЕРІАЛІВ
# =====================================================


@router.callback_query(
    F.data == "statistics_materials"
)
async def statistics_materials_handler(
    callback: CallbackQuery,
) -> None:
    """Показує статистику матеріалів."""

    if callback.message is None:
        await callback.answer()
        return

    data = await load_materials_statistics()

    text_parts = [
        "🧵 <b>Статистика матеріалів</b>",
        "",
        (
            "Усього позицій: "
            f"<b>{data['total']}</b>"
        ),
        (
            "Запас достатній: "
            f"<b>{data['normal_stock']}</b>"
        ),
        (
            "Малий запас: "
            f"<b>{data['low_stock']}</b>"
        ),
    ]

    if data["types"]:
        text_parts.append(
            "\n🗂 <b>За типами</b>"
        )

        for material_type in data["types"]:
            text_parts.append(
                (
                    "• "
                    f"{escape(material_type['name'])}: "
                    f"<b>{material_type['count']}</b>"
                )
            )

    await safe_edit_message(
        message=callback.message,
        text="\n".join(text_parts),
        reply_markup=(
            build_statistics_back_keyboard()
        ),
    )

    await callback.answer()


# =====================================================
# CALLBACK: СТАТИСТИКА ЗАМОВЛЕНЬ
# =====================================================


@router.callback_query(
    F.data == "statistics_orders"
)
async def statistics_orders_handler(
    callback: CallbackQuery,
) -> None:
    """Показує статистику замовлень."""

    if callback.message is None:
        await callback.answer()
        return

    data = await load_orders_statistics()

    text = (
        "🛒 <b>Статистика замовлень</b>\n\n"
        f"Усього замовлень: "
        f"<b>{data['total']}</b>\n\n"
        f"🆕 Нові: "
        f"<b>{data['new']}</b>\n"
        f"✅ Підтверджені: "
        f"<b>{data['confirmed']}</b>\n"
        f"📦 Виконані: "
        f"<b>{data['completed']}</b>\n"
        f"🚫 Скасовані: "
        f"<b>{data['cancelled']}</b>"
    )

    await safe_edit_message(
        message=callback.message,
        text=text,
        reply_markup=(
            build_statistics_back_keyboard()
        ),
    )

    await callback.answer()


# =====================================================
# CALLBACK: СТАТИСТИКА ВИРОБНИЦТВА
# =====================================================


@router.callback_query(
    F.data == "statistics_production"
)
async def statistics_production_handler(
    callback: CallbackQuery,
) -> None:
    """Показує статистику виробництва."""

    if callback.message is None:
        await callback.answer()
        return

    data = await load_production_statistics()

    text = (
        "⚙️ <b>Статистика виробництва</b>\n\n"
        f"Усього завдань: "
        f"<b>{data['total']}</b>\n\n"
        f"📝 Заплановано: "
        f"<b>{data['planned']}</b>\n"
        f"🔄 У роботі: "
        f"<b>{data['in_progress']}</b>\n"
        f"✅ Завершено: "
        f"<b>{data['completed']}</b>\n"
        f"🚫 Скасовано: "
        f"<b>{data['cancelled']}</b>"
    )

    await safe_edit_message(
        message=callback.message,
        text=text,
        reply_markup=(
            build_statistics_back_keyboard()
        ),
    )

    await callback.answer()