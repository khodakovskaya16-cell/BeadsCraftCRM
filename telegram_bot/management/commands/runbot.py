import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from dotenv import load_dotenv

from telegram_bot.handlers.material_search import (
    router as material_search_router,
)
from telegram_bot.handlers.materials import (
    router as materials_router,
)
from telegram_bot.handlers.orders import (
    router as orders_router,
)
from telegram_bot.handlers.production import (
    router as production_router,
)
from telegram_bot.handlers.scheme_search import (
    router as scheme_search_router,
)
from telegram_bot.handlers.schemes import (
    router as schemes_router,
)
from telegram_bot.handlers.start import (
    router as start_router,
)
from telegram_bot.handlers.statistics import (
    router as statistics_router,
)


class Command(BaseCommand):
    help = "Запускає Telegram-бота BeadsCraft CRM"

    def handle(self, *args, **options) -> None:
        env_path = settings.BASE_DIR / ".env"
        load_dotenv(env_path)

        token = os.getenv(
            "TELEGRAM_BOT_TOKEN",
            "",
        ).strip()

        if not token:
            raise CommandError(
                "Не знайдено TELEGRAM_BOT_TOKEN у файлі .env"
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Запуск Telegram-бота BeadsCraft CRM..."
            )
        )

        try:
            asyncio.run(
                self.run_bot(token)
            )
        except KeyboardInterrupt:
            self.stdout.write(
                self.style.WARNING(
                    "Telegram-бот зупинено."
                )
            )

    async def run_bot(
        self,
        token: str,
    ) -> None:
        bot = Bot(
            token=token
        )

        dispatcher = Dispatcher()

        # Головне меню та реєстрація користувача
        dispatcher.include_router(start_router)

        # Схеми
        dispatcher.include_router(schemes_router)
        dispatcher.include_router(scheme_search_router)

        # Матеріали
        dispatcher.include_router(materials_router)
        dispatcher.include_router(material_search_router)

         # Замовлення, виробництво, статистика
        dispatcher.include_router(orders_router)
        dispatcher.include_router(production_router)
        dispatcher.include_router(statistics_router)

        # Команди, які відображаються
        # в системному меню Telegram.
        await bot.set_my_commands(
            [
                BotCommand(
                    command="start",
                    description="Запустити BeadsCraft CRM",
                ),
                BotCommand(
                    command="menu",
                    description="Показати головне меню",
                ),
                BotCommand(
                    command="production",
                    description="Відкрити виробництво",
                ),
                BotCommand(
                    command="statistics",
                    description="Відкрити статистику",
                ),
            ]
        )

        await bot.delete_webhook(
            drop_pending_updates=True
        )

        try:
            await dispatcher.start_polling(
                bot
            )
        finally:
            await bot.session.close()