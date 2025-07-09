from aiogram import Bot
from aiogram.types import BotCommand


async def set_menu(bot: Bot):
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="help", description="Показать инструкцию"),
        BotCommand(command="profile", description="Профиль"),
    ]

    await bot.set_my_commands(commands)
