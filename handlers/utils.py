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
    logger.info(f"Получение ID магазина по имени: {name}")
    api_url = f"{os.getenv('WEB_SERVICE_URL')}/api/store-id/{name}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Успешно получен ID магазина для '{name}': {data}")
                    return data
                else:
                    logger.error(
                        f"API запрос не удался со статусом {response.status} для магазина '{name}'"
                    )
                    return None

    except Exception as e:
        logger.error(f"Ошибка в get_store_id_by_name для '{name}': {e}")
        return None


async def get_user_profile(telegram_id: int) -> dict[str, Any] | None:
    logger.info(f"Получение профиля пользователя с telegram_id: {telegram_id}")
    key = f"user:{telegram_id}"

    try:
        data = await redis_client.get(key)
        if data:
            profile = json.loads(data)
            logger.info(f"Профиль пользователя найден: {profile}")
            return profile
        else:
            logger.warning(
                f"Профиль пользователя не найден для telegram_id: {telegram_id}"
            )
            return None
    except Exception as e:
        logger.error(f"Ошибка при получении профиля пользователя {telegram_id}: {e}")
        return None


async def get_agent_by_phone(phone_number: str):
    logger.info(f"Получение агента по номеру телефона: {phone_number}")

    if not phone_number.startswith("+"):
        phone_number = "+" + phone_number
        logger.info(f"Добавлен префикс '+' к номеру: {phone_number}")

    api_url = f"{os.getenv('WEB_SERVICE_URL')}/api/agent/{phone_number}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Агент найден для номера {phone_number}: {data}")
                    return data
                else:
                    logger.error(
                        f"API запрос не удался со статусом {response.status} для номера {phone_number}"
                    )
                    return []
    except Exception as e:
        logger.error(f"Ошибка в get_agent_by_phone для номера {phone_number}: {e}")
        return None


async def save_user_profile(telegram_id: int, phone_number: str) -> bool:
    logger.info(
        f"Сохранение профиля пользователя: telegram_id={telegram_id}, phone={phone_number}"
    )

    if not phone_number.startswith("+"):
        phone_number = "+" + phone_number
        logger.info(f"Добавлен префикс '+' к номеру: {phone_number}")

    key = f"user:{telegram_id}"
    user_data = {"agent_number": phone_number}

    try:
        await redis_client.set(key, json.dumps(user_data))
        logger.info(f"Данные пользователя сохранены в Redis: {user_data}")

        api_url = f"{os.getenv('WEB_SERVICE_URL')}/api/agent/{phone_number}"
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                if response.status == 200:
                    logger.info(f"Агент успешно подтвержден для номера {phone_number}")
                    return True
                else:
                    logger.error(
                        f"API запрос не удался со статусом {response.status} для номера {phone_number}"
                    )
                    return False

    except Exception as e:
        logger.error(f"Ошибка при сохранении профиля пользователя {telegram_id}: {e}")
        return False


async def schedule(message: Message):
    logger.info(f"Получение расписания для пользователя: {message.from_user.id}")

    user = await get_user_profile(message.from_user.id)
    if not user:
        logger.error(f"Профиль пользователя не найден: {message.from_user.id}")
        await message.answer("Ошибка: профиль пользователя не найден.")
        return

    phone_number = user["agent_number"]
    if not phone_number.startswith("+"):
        phone_number = f"+{phone_number}"
        logger.info(f"Добавлен префикс '+' к номеру: {phone_number}")

    url = f"{os.getenv('WEB_SERVICE_URL')}/api/agent-schedule/{phone_number}"
    logger.info(f"Запрос расписания по URL: {url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 404:
                    logger.warning(f"Агент с номером {phone_number} не найден")
                    await message.answer(f"Агент с номером {phone_number} не найден.")
                    return

                if response.status != 200:
                    logger.error(
                        f"Ошибка при получении расписания: статус {response.status}"
                    )
                    await message.answer("Ошибка при получении расписания.")
                    return

                stores = await response.json()
                logger.info(
                    f"Получено расписание для агента {phone_number}: {len(stores)} магазинов"
                )
    except Exception as e:
        logger.error(f"Ошибка при запросе расписания для {phone_number}: {e}")
        await message.answer("Ошибка при получении расписания.")
        return

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
        logger.info(f"Нет назначенных магазинов на сегодня ({weekdays[today]})")
        await message.answer(
            f"На сегодня ({weekdays[today]}) у вас нет назначенных магазинов."
        )
        return

    builder = ReplyKeyboardBuilder()
    for store in stores:
        builder.add(KeyboardButton(text=store["name"]))

    builder.add(KeyboardButton(text="🔙 Назад"))
    builder.adjust(2)

    logger.info(f"Отправка клавиатуры с {len(stores)} магазинами")
    await message.answer(
        "Ваши магазины на сегодня:\n\nВыберите магазин:",
        reply_markup=builder.as_markup(resize_keyboard=True, one_time_keyboard=True),
    )


async def check_coordinates(latitude, longitude, shop_name):
    logger.info(
        f"Проверка координат: lat={latitude}, lng={longitude}, shop={shop_name}"
    )

    try:
        url = f"{os.getenv('WEB_SERVICE_URL')}/api/check-address/{longitude}/{latitude}/{shop_name}/"
        logger.info(f"Запрос проверки координат: {url}")

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    success = data.get("success", False)
                    distance = data.get("distance")

                    logger.info(
                        f"Результат проверки координат: success={success}, distance={distance}"
                    )
                    return success
                else:
                    error_text = await response.text()
                    logger.error(
                        f"Ошибка проверки координат: статус {response.status}, ответ: {error_text}"
                    )
                    return False

    except Exception as e:
        logger.error(f"Исключение при проверке координат: {e}")
        return False


def check_photo_creation_time(file_path):
    logger.info(f"Проверка времени создания фото: {file_path}")

    try:
        file_extension = os.path.splitext(file_path.lower())[1]
        user_timezone = pytz.timezone("Asia/Bishkek")
        logger.info(f"Расширение файла: {file_extension}")

        if file_extension == ".heic":
            logger.info("Обработка HEIC файла")
            metadata = get_heic_metadata(file_path)
            if not metadata:
                logger.warning(f"Метаданные отсутствуют в HEIC файле: {file_path}")
                return False

            date_time_str = None
            for field in ["DateTimeOriginal", "CreateDate"]:
                if field in metadata and metadata[field]:
                    date_time_str = metadata[field]
                    logger.info(f"Найдено поле времени {field}: {date_time_str}")
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

            logger.info(
                f"HEIC: время фото={photo_time}, текущее время={current_time}, разница={time_diff}"
            )
            result = time_diff <= timedelta(minutes=10)
            logger.info(f"Результат проверки времени HEIC: {result}")
            return result

        else:
            logger.info("Обработка обычного изображения")
            try:
                img = Image.open(file_path)

                if not img.info.get("exif"):
                    logger.warning(
                        f"EXIF данные отсутствуют в изображении: {file_path}"
                    )
                    return False

                exif_dict = piexif.load(img.info["exif"])
                date_time_str = None

                if (
                    "Exif" in exif_dict
                    and piexif.ExifIFD.DateTimeOriginal in exif_dict["Exif"]
                ):
                    date_time_str = exif_dict["Exif"][
                        piexif.ExifIFD.DateTimeOriginal
                    ].decode("utf-8")
                    logger.info(
                        f"Найдено DateTimeOriginal в Exif секции: {date_time_str}"
                    )

                elif (
                    "Exif" in exif_dict
                    and piexif.ExifIFD.DateTimeDigitized in exif_dict["Exif"]
                ):
                    date_time_str = exif_dict["Exif"][
                        piexif.ExifIFD.DateTimeDigitized
                    ].decode("utf-8")
                    logger.info(
                        f"Найдено DateTimeDigitized в Exif секции: {date_time_str}"
                    )

                elif (
                    "0th" in exif_dict and piexif.ImageIFD.DateTime in exif_dict["0th"]
                ):
                    date_time_str = exif_dict["0th"][piexif.ImageIFD.DateTime].decode(
                        "utf-8"
                    )
                    logger.info(f"Найдено DateTime в 0th секции: {date_time_str}")

                if not date_time_str:
                    logger.warning(
                        f"Данные о времени создания отсутствуют в EXIF: {file_path}"
                    )
                    return False

                photo_time_naive = datetime.strptime(date_time_str, "%Y:%m:%d %H:%M:%S")
                photo_time = user_timezone.localize(photo_time_naive)

                current_time = datetime.now(user_timezone)
                time_diff = current_time - photo_time

                logger.info(
                    f"EXIF: время фото={photo_time}, текущее время={current_time}, разница={time_diff}"
                )
                result = time_diff <= timedelta(minutes=10)
                logger.info(f"Результат проверки времени EXIF: {result}")
                return result

            except Exception as e:
                logger.warning(f"Ошибка при чтении EXIF данных: {e}")
                return False

    except Exception as e:
        logger.error(f"Ошибка при проверке времени создания файла: {e}")
        return False


async def download_file(file_url: str, filename: str):
    logger.info(f"Скачивание файла: {file_url} -> {filename}")

    try:
        os.makedirs("media/shelf", exist_ok=True)
        _, ext = os.path.splitext(filename)
        unique_filename = f"{uuid.uuid4()}{ext}"
        save_path = f"media/shelf/{unique_filename}"
        relative_path = f"shelf/{unique_filename}"

        logger.info(f"Сохранение файла по пути: {save_path}")

        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as response:
                if response.status != 200:
                    logger.error(f"Ошибка скачивания файла: статус {response.status}")
                    raise Exception(f"Failed to download file: {response.status}")

                with open(save_path, "wb") as f:
                    content = await response.read()
                    f.write(content)
                    logger.info(f"Файл успешно скачан, размер: {len(content)} байт")

        file_extension = os.path.splitext(filename.lower())[1]
        image_extensions = [".jpg", ".jpeg", ".png", ".heic", ".tiff", ".bmp"]

        if any(file_extension == ext for ext in image_extensions):
            logger.info(f"Проверка изображения с расширением: {file_extension}")
            is_valid = await sync_to_async(check_photo_creation_time)(save_path)

            if not is_valid:
                logger.error("Фото не прошло проверку времени создания")
                if os.path.exists(save_path):
                    os.remove(save_path)
                    logger.info(f"Удален невалидный файл: {save_path}")
                raise Exception(
                    "Фото не содержит необходимые метаданные или было сделано более 10 минут назад."
                )

            if file_extension in [".heic", ".heif"]:
                logger.info("Конвертация HEIC в JPEG")
                new_path = await convert_heic_to_jpeg(save_path)
                relative_path = f"shelf/{os.path.basename(new_path)}"
                logger.info(f"Файл сконвертирован: {relative_path}")

        logger.info(f"Файл успешно обработан: {relative_path}")
        return relative_path

    except Exception as e:
        logger.error(f"Ошибка в download_file: {e}")
        raise


def get_heic_metadata(file_path):
    logger.info(f"Получение метаданных HEIC: {file_path}")

    try:
        try:
            subprocess.run(["exiftool", "-ver"], capture_output=True, check=True)
            logger.info("ExifTool найден и работает")
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
            logger.warning(f"Пустые метаданные для файла: {file_path}")
            return None

        logger.info(f"Метаданные HEIC успешно получены: {metadata[0]}")
        return metadata[0]

    except Exception as e:
        logger.error(f"Ошибка при чтении метаданных HEIC: {e}")
        return None


async def convert_heic_to_jpeg(heic_path):
    logger.info(f"Конвертация HEIC в JPEG: {heic_path}")

    try:
        if not heic_path.lower().endswith((".heic", ".heif")):
            logger.info("Файл не является HEIC, пропуск конвертации")
            return heic_path

        jpeg_path = os.path.splitext(heic_path)[0] + ".jpg"
        logger.info(f"Целевой путь JPEG: {jpeg_path}")

        try:
            pillow_heif.register_heif_opener()
            with Image.open(heic_path) as img:
                img.convert("RGB").save(jpeg_path, "JPEG", quality=95, optimize=True)
            logger.info(
                f"HEIC успешно конвертирован через pillow-heif: {heic_path} -> {jpeg_path}"
            )

        except (ImportError, Exception) as e:
            logger.warning(f"Pillow-heif не сработал: {e}. Пробуем ImageMagick...")

            cmd = ["convert", heic_path, jpeg_path]
            logger.info(f"Команда ImageMagick: {' '.join(cmd)}")

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Неизвестная ошибка"
                logger.error(f"ImageMagick failed: {error_msg}")
                raise Exception(f"ImageMagick failed: {error_msg}") from None

            logger.info("HEIC успешно конвертирован через ImageMagick")

        if not os.path.exists(jpeg_path):
            logger.error(f"Не удалось создать JPEG файл: {jpeg_path}")
            raise Exception(f"Не удалось создать JPEG файл: {jpeg_path}")

        if os.path.getsize(jpeg_path) == 0:
            logger.error("Созданный JPEG файл пустой")
            raise Exception("Созданный JPEG файл пустой")

        if os.path.exists(heic_path):
            os.remove(heic_path)
            logger.info(f"Удален оригинальный HEIC файл: {heic_path}")

        logger.info(f"Конвертация HEIC завершена успешно: {jpeg_path}")
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
    logger.info(
        f"Сохранение файла в пост: id={id}, store_id={store_id}, path={relative_path}"
    )
    logger.info(
        f"Параметры: lat={latitude}, lng={longitude}, type={type_photo}, dmp_type={dmp_type}"
    )

    try:
        file_path = f"media/{relative_path}"
        api_url = f"{os.getenv('WEB_SERVICE_URL')}/api/photo-posts/create/"
        logger.info(f"API URL: {api_url}")

        data = {
            "agent": id,
            "store": store_id,
            "post_type": type_photo,
            "latitude": latitude,
            "longitude": longitude,
            "dmp_type": dmp_type,
        }

        logger.info(f"Отправка файла: {file_path}")
        logger.info(f"Данные запроса: {data}")

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
                    logger.info(
                        f"Ответ API: статус={response.status}, текст={response_text}"
                    )

                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"Удален временный файл: {file_path}")

                    if response.status == 201:
                        logger.info("Файл успешно загружен в пост")
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
            logger.info(f"Удален файл после ошибки: {file_path}")
        return {"success": False, "error": str(e)}


async def save_post_data(
    id,
    store_id,
    latitude=None,
    longitude=None,
    type_photo=None,
    brand_name=None,
    dmp_count=None,
):
    logger.info(f"Сохранение данных поста: id={id}, store_id={store_id}")
    logger.info(
        f"Параметры: lat={latitude}, lng={longitude}, type={type_photo}, brand={brand_name}, count={dmp_count}"
    )

    try:
        api_url = f"{os.getenv('WEB_SERVICE_URL')}/api/photo-posts/create/"
        logger.info(f"API URL: {api_url}")

        data = {
            "agent": id,
            "store": store_id,
            "post_type": type_photo,
            "latitude": latitude,
            "longitude": longitude,
            "dmp_type": brand_name,
            "dmp_count": dmp_count,
        }

        data = {k: v for k, v in data.items() if v is not None}
        logger.info(f"Отправка данных (без None): {data}")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_url, json=data, headers={"Content-Type": "application/json"}
            ) as response:
                response_text = await response.text()
                logger.info(
                    f"Ответ API: статус={response.status}, текст={response_text}"
                )

                if response.status == 201:
                    logger.info("Данные поста успешно сохранены")
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
        logger.error(f"Ошибка в save_post_data: {e}")
        return {"success": False, "error": str(e)}
