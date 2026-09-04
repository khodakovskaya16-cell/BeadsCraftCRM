from typing import Any

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message


# Поточний робочий екран окремо для кожного чату.
_current_screen_by_chat: dict[int, int] = {}

# Постійне головне меню окремо для кожного чату.
_main_menu_by_chat: dict[int, int] = {}


# =====================================================
# БЕЗПЕЧНЕ ВИДАЛЕННЯ ПОВІДОМЛЕНЬ
# =====================================================


async def safe_delete_message(
    bot,
    chat_id: int,
    message_id: int,
) -> None:
    """
    Безпечно видаляє повідомлення Telegram.
    """

    try:
        await bot.delete_message(
            chat_id=chat_id,
            message_id=message_id,
        )
    except TelegramBadRequest:
        pass


async def delete_user_message(
    message: Message,
) -> None:
    """
    Видаляє повідомлення користувача:
    /start, /menu або натиснуту нижню кнопку.
    """

    try:
        await message.delete()
    except TelegramBadRequest:
        pass


# =====================================================
# РОБОЧИЙ ЕКРАН
# =====================================================


async def delete_previous_screen(
    message: Message,
) -> None:
    """
    Видаляє попередній робочий екран,
    але не видаляє головне меню.
    """

    chat_id = message.chat.id

    previous_message_id = (
        _current_screen_by_chat.get(
            chat_id
        )
    )

    if previous_message_id is None:
        return

    await safe_delete_message(
        bot=message.bot,
        chat_id=chat_id,
        message_id=previous_message_id,
    )

    _current_screen_by_chat.pop(
        chat_id,
        None,
    )


async def send_screen(
    message: Message,
    text: str,
    reply_markup: Any = None,
    parse_mode: str | None = "HTML",
) -> Message:
    """
    Створює новий робочий екран.

    Використовується для звичайних
    повідомлень користувача.
    """

    await delete_user_message(
        message
    )

    await delete_previous_screen(
        message
    )

    sent_message = await message.bot.send_message(
        chat_id=message.chat.id,
        text=text,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
    )

    _current_screen_by_chat[
        message.chat.id
    ] = sent_message.message_id

    return sent_message


async def send_callback_screen(
    callback: CallbackQuery,
    text: str,
    reply_markup: Any = None,
    parse_mode: str | None = "HTML",
) -> Message | None:
    """
    Створює робочий екран після натискання
    кнопки постійного головного меню.

    Головне меню при цьому не змінюється
    і не видаляється.
    """

    if callback.message is None:
        return None

    chat_id = callback.message.chat.id

    previous_message_id = (
        _current_screen_by_chat.get(
            chat_id
        )
    )

    if previous_message_id is not None:
        await safe_delete_message(
            bot=callback.bot,
            chat_id=chat_id,
            message_id=previous_message_id,
        )

    sent_message = await callback.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
    )

    _current_screen_by_chat[
        chat_id
    ] = sent_message.message_id

    return sent_message


async def close_current_screen(
    callback: CallbackQuery,
) -> None:
    """
    Закриває робочий екран.
    Постійне головне меню залишається.
    """

    if callback.message is None:
        return

    chat_id = callback.message.chat.id

    current_message_id = (
        _current_screen_by_chat.get(
            chat_id
        )
    )

    if (
        current_message_id
        == callback.message.message_id
    ):
        await safe_delete_message(
            bot=callback.bot,
            chat_id=chat_id,
            message_id=current_message_id,
        )

        _current_screen_by_chat.pop(
            chat_id,
            None,
        )


# =====================================================
# ПОСТІЙНЕ ГОЛОВНЕ МЕНЮ
# =====================================================


async def send_main_menu(
    message: Message,
    text: str,
    reply_markup: Any,
    parse_mode: str | None = "HTML",
) -> Message:
    """
    Створює окреме головне меню
    та закріплює його зверху чату.
    """

    await delete_user_message(
        message
    )

    await delete_previous_screen(
        message
    )

    chat_id = message.chat.id

    previous_menu_id = (
        _main_menu_by_chat.get(
            chat_id
        )
    )

    if previous_menu_id is not None:
        try:
            await message.bot.unpin_chat_message(
                chat_id=chat_id,
                message_id=previous_menu_id,
            )
        except TelegramBadRequest:
            pass

        await safe_delete_message(
            bot=message.bot,
            chat_id=chat_id,
            message_id=previous_menu_id,
        )

    # Прибираємо старі закріплення
    # саме в чаті з цим ботом.
    try:
        await message.bot.unpin_all_chat_messages(
            chat_id=chat_id
        )
    except TelegramBadRequest:
        pass

    menu_message = await message.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
    )

    _main_menu_by_chat[
        chat_id
    ] = menu_message.message_id

    # Закріплюємо головне меню зверху чату.
    try:
        await message.bot.pin_chat_message(
            chat_id=chat_id,
            message_id=menu_message.message_id,
            disable_notification=True,
        )
    except TelegramBadRequest as error:
        print(
            "[MAIN MENU PIN ERROR] "
            f"{type(error).__name__}: {error}"
        )

    return menu_message


# =====================================================
# ЗАПАМ’ЯТОВУВАННЯ ЕКРАНІВ
# =====================================================


def remember_screen(
    message: Message,
) -> None:
    """
    Запам'ятовує повідомлення як робочий екран.
    """

    _current_screen_by_chat[
        message.chat.id
    ] = message.message_id


def forget_screen(
    chat_id: int,
) -> None:
    """
    Забуває робочий екран без видалення.
    """

    _current_screen_by_chat.pop(
        chat_id,
        None,
    )