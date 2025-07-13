import os

import aiohttp
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from services.logger import logger


async def send_daily_plans_post_request():
    api_url = f"{os.getenv('WEB_SERVICE_URL')}/api/daily-plans/"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url) as response:
                if response.status == 201:
                    data = await response.json()
                    logger.info(f"Daily plans created successfully: {data}")
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to create daily plans. Status: {response.status}, Response: {error_text}")
    except Exception as e:
        logger.error(f"Error while posting daily plans: {e}")


def setup_scheduler(bot):
    scheduler = AsyncIOScheduler(timezone=pytz.timezone("Asia/Bishkek"))



    scheduler.add_job(
        send_daily_plans_post_request,
        CronTrigger(hour="17", minute="30"),
    )

    logger.info("Планировщик настроен для ежемесячных уведомлений и ежедневной отправки планов")
    return scheduler
