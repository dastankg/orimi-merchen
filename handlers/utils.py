import asyncio
import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timedelta
from typing import Any

import aiohttp
import piexif
import pillow_heif
import pytz
from aiogram.types import KeyboardButton, Message
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from asgiref.sync import sync_to_async
from PIL import Image

from config.redis_connect import redis_client
from services.logger import logger


async def get_store_id_by_name(name: str) -> dict[str, Any] | None:
    api_url = f"{os.getenv('WEB_SERVICE_URL')}/api/store-id/{name}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    logger.error(f"API request failed with status {response.status}")
                    return None

    except Exception as e:
        logger.error(f"Error in get_shop_by_phone: {e}")
        return None


async def get_user_profile(telegram_id: int) -> dict[str, Any] | None:
    key = f"user:{telegram_id}"
    data = await redis_client.get(key)
    return json.loads(data) if data else None


async def get_agent_by_phone(phone_number: str):
    if not phone_number.startswith("+"):
        phone_number = "+" + phone_number
    api_url = f"{os.getenv('WEB_SERVICE_URL')}/api/agent/{phone_number}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    logger.error(f"API request failed with status {response.status}")
                    return []
    except Exception as e:
        logger.error(f"Error in get_shop_by_phone: {e}")
        return None


async def save_user_profile(telegram_id: int, phone_number: str) -> bool:
    if not phone_number.startswith("+"):
        phone_number = "+" + phone_number
    key = f"user:{telegram_id}"
    user_data = {"agent_number": phone_number}
    await redis_client.set(key, json.dumps(user_data))
    try:
        api_url = f"{os.getenv('WEB_SERVICE_URL')}/api/agent/{phone_number}"
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                if response.status == 200:
                    return True
                else:
                    logger.error(f"API request failed with status {response.status}")
                    return False

    except Exception as e:
        logger.error(f"Error saving user profile to Redis: {e}")
        return False


async def schedule(message: Message):
    user = await get_user_profile(message.from_user.id)
    phone_number = user["agent_number"]
    if not phone_number.startswith("+"):
        phone_number = f"+{phone_number}"

    url = f"{os.getenv('WEB_SERVICE_URL')}/api/agent-schedule/{phone_number}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 404:
                await message.answer(f"Агент с номером {phone_number} не найден.")
                return

            if response.status != 200:
                await message.answer("Ошибка при получении расписания.")
                return

            stores = await response.json()

    if not stores:
        weekdays = [
            "Понедельник",
            "Вторник",
            "Среда",
            "Четверг",
            "Пятница",
            "Суббота",
            "Воскресенье",
        ]
        today = datetime.now().weekday()
        await message.answer(
            f"На сегодня ({weekdays[today]}) у вас нет назначенных магазинов."
        )
        return

    builder = ReplyKeyboardBuilder()
    for store in stores:
        builder.add(KeyboardButton(text=store["name"]))
    builder.adjust(2)

    await message.answer(
        "Ваши магазины на сегодня:\n\nВыберите магазин:",
        reply_markup=builder.as_markup(resize_keyboard=True),
    )


async def check_coordinates(latitude: float, longitude: float, store: str) -> bool:
    try:
        print(latitude, longitude, store)
        url = f"{os.getenv('WEB_SERVICE_URL')}/api/check-address/{longitude}/{latitude}/{store}/"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning(
                        f"🟡 CheckAddress API returned {resp.status}: {text}"
                    )
                    return False
                resp = await resp.json()
                print(resp)
                if resp["success"]:
                    return True
                return False

    except Exception as e:
        logger.exception(f"❗ Exception in check_coordinates: {e}")
        return False


def check_photo_creation_time(file_path):
    try:
        file_extension = os.path.splitext(file_path.lower())[1]
        user_timezone = pytz.timezone("Asia/Bishkek")

        if file_extension == ".heic":
            metadata = get_heic_metadata(file_path)
            if not metadata:
                logger.warning(f"Метаданные отсутствуют в HEIC файле: {file_path}")
                return False

            date_time_str = None
            for field in ["DateTimeOriginal", "CreateDate"]:
                if field in metadata and metadata[field]:
                    date_time_str = metadata[field]
                    break

            if not date_time_str:
                logger.warning(
                    f"Данные о времени создания отсутствуют в HEIC: {file_path}"
                )
                return False

            match = re.match(
                r"(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})", date_time_str
            )
            if not match:
                logger.warning(f"Неизвестный формат даты в HEIC: {date_time_str}")
                return False

            year, month, day, hour, minute, second = map(int, match.groups())
            photo_time_naive = datetime(year, month, day, hour, minute, second)
            photo_time = user_timezone.localize(photo_time_naive)

            current_time = datetime.now(user_timezone)

            time_diff = current_time - photo_time

            return time_diff <= timedelta(minutes=5)

        else:
            try:
                img = Image.open(file_path)

                if not hasattr(img, "_getexif") or not img._getexif():
                    logger.warning(
                        f"EXIF данные отсутствуют в изображении: {file_path}"
                    )
                    return False

                exif_dict = piexif.load(img.info["exif"])

                if "0th" in exif_dict and piexif.ImageIFD.DateTime in exif_dict["0th"]:
                    date_time_str = exif_dict["0th"][piexif.ImageIFD.DateTime].decode(
                        "utf-8"
                    )
                    photo_time_naive = datetime.strptime(
                        date_time_str, "%Y:%m:%d %H:%M:%S"
                    )
                    photo_time = user_timezone.localize(photo_time_naive)

                    current_time = datetime.now(user_timezone)

                    time_diff = current_time - photo_time

                    return time_diff <= timedelta(minutes=5)
                else:
                    logger.warning(
                        f"Данные о времени создания отсутствуют в EXIF: {file_path}"
                    )
                    return False

            except Exception as e:
                logger.warning(f"Ошибка при чтении EXIF данных: {e}")
                return False

    except Exception as e:
        logger.error(f"Ошибка при проверке времени создания файла: {e}")
        return False


async def download_file(file_url: str, filename: str):
    try:
        os.makedirs("media/shelf", exist_ok=True)
        _, ext = os.path.splitext(filename)
        unique_filename = f"{uuid.uuid4()}{ext}"
        save_path = f"media/shelf/{unique_filename}"
        relative_path = f"shelf/{unique_filename}"

        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as response:
                if response.status != 200:
                    raise Exception(f"Failed to download file: {response.status}")

                with open(save_path, "wb") as f:
                    f.write(await response.read())

        file_extension = os.path.splitext(filename.lower())[1]
        image_extensions = [".jpg", ".jpeg", ".png", ".heic", ".tiff", ".bmp"]

        if any(file_extension == ext for ext in image_extensions):
            is_valid = await sync_to_async(check_photo_creation_time)(save_path)
            if not is_valid:
                if os.path.exists(save_path):
                    os.remove(save_path)
                raise Exception(
                    "Фото не содержит необходимые метаданные или было сделано более 5 минут назад."
                )

            if file_extension in [".heic", ".heif"]:
                new_path = await convert_heic_to_jpeg(save_path)
                relative_path = f"shelf/{os.path.basename(new_path)}"

        return relative_path
    except Exception as e:
        logger.error(f"Error in download_file: {e}")
        raise


def get_heic_metadata(file_path):
    try:
        try:
            subprocess.run(["exiftool", "-ver"], capture_output=True, check=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            logger.error(
                "ExifTool не установлен. Установите с помощью 'sudo dnf install perl-Image-ExifTool'"
            )
            return None

        result = subprocess.run(
            ["exiftool", "-json", "-DateTimeOriginal", "-CreateDate", file_path],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            logger.error(f"Ошибка при выполнении exiftool: {result.stderr}")
            return None

        metadata = json.loads(result.stdout)
        if not metadata or len(metadata) == 0:
            return None

        return metadata[0]
    except Exception as e:
        logger.error(f"Ошибка при чтении метаданных HEIC: {e}")
        return None


async def convert_heic_to_jpeg(heic_path):
    try:
        if not heic_path.lower().endswith((".heic", ".heif")):
            return heic_path

        jpeg_path = os.path.splitext(heic_path)[0] + ".jpg"

        try:
            pillow_heif.register_heif_opener()
            with Image.open(heic_path) as img:
                img.convert("RGB").save(jpeg_path, "JPEG", quality=95, optimize=True)

            logger.info(
                f"HEIC конвертирован через pillow-heif: {heic_path} -> {jpeg_path}"
            )

        except (ImportError, Exception) as e:
            logger.warning(f"Pillow-heif не сработал: {e}. Пробуем ImageMagick...")

            cmd = ["convert", heic_path, jpeg_path]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Неизвестная ошибка"
                raise Exception(f"ImageMagick failed: {error_msg}") from None

        if not os.path.exists(jpeg_path):
            raise Exception(f"Не удалось создать JPEG файл: {jpeg_path}")

        if os.path.getsize(jpeg_path) == 0:
            raise Exception("Созданный JPEG файл пустой")

        if os.path.exists(heic_path):
            os.remove(heic_path)
            logger.info(f"Удален оригинальный HEIC файл: {heic_path}")

        return jpeg_path

    except Exception as e:
        logger.error(f"Ошибка в convert_heic_to_jpeg: {e}")
        raise


async def save_file_to_post(
        id,
        store_id,
        relative_path,
        latitude=None,
        longitude=None,
        type_photo=None,
        dmp_type=None,
):
    try:
        file_path = f"media/{relative_path}"
        # Изменен URL на PhotoPost endpoint
        api_url = f"{os.getenv('WEB_SERVICE_URL')}/api/photo-posts/create/"

        # Данные для PhotoPost (убран shop_id, добавлены поля для PhotoPost)
        data = {
            "agent": id,
            "store": store_id,
            "post_type": type_photo,
            "latitude": latitude,
            "longitude": longitude,
            "dmp_type": dmp_type,
        }

        # Дополнительные поля для PhotoPost можно добавить при необходимости
        # "dmp_type": ...,
        # "dmp_count": ...,
        # "brand_name": ...,
        # "brand_count": ...,

        logger.info(f"Отправка файла: {file_path}")
        logger.info(f"Данные: {data}")

        async with aiohttp.ClientSession() as session:
            with open(file_path, "rb") as image_file:
                form_data = aiohttp.FormData()
                for key, value in data.items():
                    if value is not None:
                        form_data.add_field(key, str(value))

                form_data.add_field(
                    "image", image_file, filename=os.path.basename(file_path)
                )

                async with session.post(api_url, data=form_data) as response:
                    response_text = await response.text()

                    if os.path.exists(file_path):
                        os.remove(file_path)

                    if response.status == 201:
                        logger.info("Файл успешно загружен")
                        return {
                            "success": True,
                            "data": json.loads(response_text)
                            if response_text
                            else None,
                        }
                    else:
                        logger.error(
                            f"Ошибка при создании поста. Статус: {response.status}, Ответ: {response_text}"
                        )
                        return {
                            "success": False,
                            "status": response.status,
                            "error": response_text,
                        }

    except Exception as e:
        logger.error(f"Ошибка в save_file_to_post: {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        return {"success": False, "error": str(e)}


async def save_post_data(id,
                         store_id,
                         latitude=None, longitude=None, type_photo=None, brand_name=None, dmp_count=None
                         ):
    try:
        api_url = f"{os.getenv('WEB_SERVICE_URL')}/api/photo-posts/create/"

        data = {
            "agent": id,
            "store": store_id,
            "post_type": type_photo,
            "latitude": latitude,
            "longitude": longitude,
            "dmp_type": brand_name,  # изменено с dmp_type на brand_name
            "dmp_count": dmp_count,
        }

        # Убираем None значения
        data = {k: v for k, v in data.items() if v is not None}

        logger.info(f"Отправка данных: {data}")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                    api_url, json=data, headers={"Content-Type": "application/json"}
            ) as response:
                response_text = await response.text()

                if response.status == 201:
                    logger.info("Данные успешно сохранены")
                    return {
                        "success": True,
                        "data": json.loads(response_text) if response_text else None,
                    }
                else:
                    logger.error(
                        f"Ошибка при создании поста. Статус: {response.status}, Ответ: {response_text}"
                    )
                    return {
                        "success": False,
                        "status": response.status,
                        "error": response_text,
                    }

    except Exception as e:
        logger.error(f"Error saving post data: {e}")
        return {"success": False, "error": str(e)}
