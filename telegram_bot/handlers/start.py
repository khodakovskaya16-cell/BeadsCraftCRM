from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    Message,
    ReplyKeyboardRemove,
    User,
)
from asgiref.sync import sync_to_async

from telegram_bot.handlers.materials import (
    show_materials_menu,
)
from telegram_bot.handlers.orders import (
    show_orders_menu,
)
from telegram_bot.handlers.production import (
    show_production_menu,
)
from telegram_bot.handlers.schemes import (
    show_schemes_menu,
)
from telegram_bot.handlers.statistics import (
    show_statistics_menu,
)
from telegram_bot.keyboards.main_menu import (
    MATERIALS_ALLOWED_ROLES,
    build_main_menu_keyboard,
)
from telegram_bot.models import TelegramUser
from telegram_bot.utils.navigation import send_screen


router = Router(name="start")


MAIN_MENU_TEXT = (
    "🏠 <b>Головне меню BeadsCraft CRM</b>\n\n"
    "Оберіть потрібний розділ:"
)


# =====================================================
# РЕЄСТРАЦІЯ КОРИСТУВАЧА
# =====================================================


@sync_to_async(thread_sensitive=True)
def register_or_update_telegram_user(
    telegram_id: int,
    username: str,
    first_name: str,
    last_name: str,
    language_code: str,
) -> dict:
    """
    Реєструє нового Telegram-користувача
    або оновлює дані наявного.
    """

    telegram_user, created = (
        TelegramUser.objects.update_or_create(
            telegram_id=telegram_id,
            defaults={
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "language_code": language_code,
            },
        )
    )

    return {
        "id": telegram_user.pk,
        "created": created,
        "is_active": telegram_user.is_active,
        "role": telegram_user.role,
        "role_display": (
            telegram_user.get_role_display()
        ),
    }


def get_user_display_name(
    telegram_user: User,
) -> str:
    """Повертає ім’я користувача для привітання."""

    full_name = " ".join(
        part
        for part in (
            telegram_user.first_name,
            telegram_user.last_name,
        )
        if part
    ).strip()

    if full_name:
        return full_name

    if telegram_user.username:
        return f"@{telegram_user.username}"

    return "користувачу"


async def save_telegram_account(
    telegram_account: User,
) -> dict:
    """Зберігає або оновлює Telegram-акаунт."""

    return await register_or_update_telegram_user(
        telegram_id=telegram_account.id,
        username=telegram_account.username or "",
        first_name=telegram_account.first_name or "",
        last_name=telegram_account.last_name or "",
        language_code=(
            telegram_account.language_code or ""
        ),
    )


async def save_current_user(
    message: Message,
) -> dict | None:
    """Зберігає користувача поточного повідомлення."""

    telegram_account = message.from_user

    if telegram_account is None:
        return None

    return await save_telegram_account(
        telegram_account
    )


async def get_callback_user_data(
    callback: CallbackQuery,
) -> dict:
    """Повертає актуальні дані автора callback."""

    return await save_telegram_account(
        callback.from_user
    )


# =====================================================
# ВИДАЛЕННЯ СТАРОЇ НИЖНЬОЇ КЛАВІАТУРИ
# =====================================================


async def remove_old_reply_keyboard(
    message: Message,
) -> None:
    """Прибирає стару нижню ReplyKeyboard."""

    temporary_message = await message.answer(
        text="Оновлення меню…",
        reply_markup=ReplyKeyboardRemove(
            remove_keyboard=True
        ),
    )

    try:
        await temporary_message.delete()
    except TelegramBadRequest:
        pass


# =====================================================
# ТЕКСТ МОЖЛИВОСТЕЙ
# =====================================================


def build_capabilities_text(
    role: str,
) -> str:
    """Формує список можливостей відповідно до ролі."""

    lines = [
        "📚 переглядати та додавати схеми;",
    ]

    if role in MATERIALS_ALLOWED_ROLES:
        lines.append(
            "🧵 вести облік матеріалів і запасів;"
        )

    lines.extend(
        [
            "🛒 формувати замовлення;",
            "⚙️ контролювати виробництво;",
            "📊 переглядати статистику.",
        ]
    )

    return "\n".join(lines)


# =====================================================
# ГОЛОВНЕ МЕНЮ
# =====================================================


async def show_main_menu(
    message: Message,
    role: str,
) -> None:
    """Показує головне меню відповідно до ролі."""

    try:
        await message.edit_text(
            text=MAIN_MENU_TEXT,
            parse_mode="HTML",
            reply_markup=(
                build_main_menu_keyboard(
                    role
                )
            ),
        )

    except TelegramBadRequest as error:
        if (
            "message is not modified"
            not in str(error)
        ):
            raise


async def show_inactive_message(
    message: Message,
) -> None:
    """Повідомляє про неактивний акаунт."""

    await send_screen(
        message=message,
        text=(
            "⛔ <b>Доступ до BeadsCraft CRM "
            "призупинено.</b>\n\n"
            "Ваш обліковий запис неактивний.\n"
            "Зверніться до адміністратора."
        ),
        reply_markup=None,
    )


async def show_materials_access_denied(
    message: Message,
    role: str,
) -> None:
    """Повідомляє про відсутність доступу до складу."""

    try:
        await message.edit_text(
            text=(
                "⛔ <b>Доступ заборонено</b>\n\n"
                "Розділ матеріалів і складу "
                "доступний лише менеджерам "
                "та адміністраторам."
            ),
            parse_mode="HTML",
            reply_markup=(
                build_main_menu_keyboard(
                    role
                )
            ),
        )

    except TelegramBadRequest as error:
        if (
            "message is not modified"
            not in str(error)
        ):
            raise


async def validate_callback_user(
    callback: CallbackQuery,
) -> dict | None:
    """
    Перевіряє, чи активний користувач callback.

    Повертає дані активного користувача.
    """

    user_data = await get_callback_user_data(
        callback
    )

    if user_data["is_active"]:
        return user_data

    if isinstance(
        callback.message,
        Message,
    ):
        await show_inactive_message(
            callback.message
        )

    await callback.answer(
        text="Ваш обліковий запис неактивний.",
        show_alert=True,
    )

    return None


# =====================================================
# КОМАНДА /START
# =====================================================


@router.message(CommandStart())
async def start_handler(
    message: Message,
) -> None:
    """Запускає бота і реєструє користувача."""

    telegram_account = message.from_user

    if telegram_account is None:
        await message.answer(
            "Не вдалося визначити користувача Telegram."
        )
        return

    user_data = await save_current_user(
        message
    )

    if user_data is None:
        await message.answer(
            "Не вдалося зареєструвати користувача."
        )
        return

    if not user_data["is_active"]:
        await show_inactive_message(
            message
        )
        return

    await remove_old_reply_keyboard(
        message
    )

    display_name = escape(
        get_user_display_name(
            telegram_account
        )
    )

    if user_data["created"]:
        greeting = (
            f"👋 <b>Вітаю, {display_name}!</b>\n\n"
            "Ваш профіль успішно створено."
        )
    else:
        greeting = (
            f"👋 <b>З поверненням, "
            f"{display_name}!</b>"
        )

    capabilities_text = (
        build_capabilities_text(
            user_data["role"]
        )
    )

    text = (
        f"{greeting}\n\n"
        "Це персональний помічник "
        "<b>BeadsCraft CRM</b>.\n\n"
        "Тут можна:\n"
        f"{capabilities_text}\n\n"
        f"Ваша роль: "
        f"<b>{escape(user_data['role_display'])}</b>\n\n"
        "Оберіть потрібний розділ:"
    )

    await send_screen(
        message=message,
        text=text,
        reply_markup=(
            build_main_menu_keyboard(
                user_data["role"]
            )
        ),
    )


# =====================================================
# КОМАНДА /MENU
# =====================================================


@router.message(Command("menu"))
async def menu_handler(
    message: Message,
) -> None:
    """Показує персональне головне меню."""

    user_data = await save_current_user(
        message
    )

    if user_data is None:
        await message.answer(
            "Не вдалося визначити користувача."
        )
        return

    if not user_data["is_active"]:
        await show_inactive_message(
            message
        )
        return

    await remove_old_reply_keyboard(
        message
    )

    await send_screen(
        message=message,
        text=MAIN_MENU_TEXT,
        reply_markup=(
            build_main_menu_keyboard(
                user_data["role"]
            )
        ),
    )


# =====================================================
# CALLBACK: ГОЛОВНЕ МЕНЮ
# =====================================================


@router.callback_query(
    F.data == "main_menu"
)
async def main_menu_callback(
    callback: CallbackQuery,
) -> None:
    """Повертає користувача до його головного меню."""

    user_data = await validate_callback_user(
        callback
    )

    if user_data is None:
        return

    if isinstance(
        callback.message,
        Message,
    ):
        await show_main_menu(
            message=callback.message,
            role=user_data["role"],
        )

    await callback.answer()


# =====================================================
# CALLBACK: СХЕМИ
# =====================================================


@router.callback_query(
    F.data == "main_schemes"
)
async def main_schemes_callback(
    callback: CallbackQuery,
) -> None:
    """Відкриває розділ схем."""

    user_data = await validate_callback_user(
        callback
    )

    if user_data is None:
        return

    if isinstance(
        callback.message,
        Message,
    ):
        await show_schemes_menu(
            callback.message
        )

    await callback.answer()


# =====================================================
# CALLBACK: МАТЕРІАЛИ
# =====================================================


@router.callback_query(
    F.data == "main_materials"
)
async def main_materials_callback(
    callback: CallbackQuery,
) -> None:
    """Відкриває склад лише дозволеним ролям."""

    user_data = await validate_callback_user(
        callback
    )

    if user_data is None:
        return

    if (
        user_data["role"]
        not in MATERIALS_ALLOWED_ROLES
    ):
        if isinstance(
            callback.message,
            Message,
        ):
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
# CALLBACK: ЗАМОВЛЕННЯ
# =====================================================


@router.callback_query(
    F.data == "main_orders"
)
async def main_orders_callback(
    callback: CallbackQuery,
) -> None:
    """Відкриває розділ замовлень."""

    user_data = await validate_callback_user(
        callback
    )

    if user_data is None:
        return

    if isinstance(
        callback.message,
        Message,
    ):
        await show_orders_menu(
            callback.message
        )

    await callback.answer()


# =====================================================
# CALLBACK: ВИРОБНИЦТВО
# =====================================================


@router.callback_query(
    F.data == "main_production"
)
async def main_production_callback(
    callback: CallbackQuery,
) -> None:
    """Відкриває розділ виробництва."""

    user_data = await validate_callback_user(
        callback
    )

    if user_data is None:
        return

    if isinstance(
        callback.message,
        Message,
    ):
        await show_production_menu(
            callback.message
        )

    await callback.answer()


# =====================================================
# CALLBACK: СТАТИСТИКА
# =====================================================


@router.callback_query(
    F.data == "main_statistics"
)
async def main_statistics_callback(
    callback: CallbackQuery,
) -> None:
    """Відкриває розділ статистики."""

    user_data = await validate_callback_user(
        callback
    )

    if user_data is None:
        return

    if isinstance(
        callback.message,
        Message,
    ):
        await show_statistics_menu(
            callback.message
        )

    await callback.answer()