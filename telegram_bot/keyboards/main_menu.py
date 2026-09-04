from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)


ROLE_CUSTOMER = "customer"
ROLE_MANAGER = "manager"
ROLE_ADMIN = "admin"


MATERIALS_ALLOWED_ROLES = frozenset(
    {
        ROLE_MANAGER,
        ROLE_ADMIN,
    }
)


def build_main_menu_keyboard(
    role: str,
) -> InlineKeyboardMarkup:
    """
    Створює головне меню відповідно до ролі.

    Адміністратор і менеджер бачать матеріали.
    Клієнт не бачить розділ матеріалів.
    """

    first_row = [
        InlineKeyboardButton(
            text="📚 Схеми",
            callback_data="main_schemes",
        )
    ]

    if role in MATERIALS_ALLOWED_ROLES:
        first_row.append(
            InlineKeyboardButton(
                text="🧵 Матеріали",
                callback_data="main_materials",
            )
        )

    rows = [
        first_row,
        [
            InlineKeyboardButton(
                text="🛒 Замовлення",
                callback_data="main_orders",
            ),
            InlineKeyboardButton(
                text="⚙️ Виробництво",
                callback_data="main_production",
            ),
        ],
        [
            InlineKeyboardButton(
                text="📊 Статистика",
                callback_data="main_statistics",
            ),
        ],
    ]

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )