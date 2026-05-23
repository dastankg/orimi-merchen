import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode

from config.config import load_config
from handlers.user_handlers import router as user_router
from keyboards.menu import set_menu
from services.http_client import close_http_session
from services.logger import logger
from services.notifications import setup_scheduler

config = load_config()
custom_server = TelegramAPIServer.from_base(os.getenv("PROXY_URL"), is_local=True)
session = AiohttpSession(api=custom_server)


async def main():
    logger.info("Starting bot")

    bot = Bot(
        token=config.tg_bot.token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    await set_menu(bot)
    dp = Dispatcher()
    dp.include_router(user_router)
    scheduler = setup_scheduler(bot)
    scheduler.start()
    try:
        logger.info("Bot is starting")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Critical error: {e}")
    finally:
        logger.info("Bot stopped")
        await close_http_session()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
