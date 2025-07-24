import os
import uuid
import aiohttp

from aiogram import Bot, F, Router
from aiogram.enums import ContentType
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from fsms.fsm import UserState
from handlers.constants import POST_TYPE_CHOICES, ORIMI_BRANDS, COMPETITOR_BRANDS
from handlers.utils import (
    check_coordinates,
    download_file,
    get_agent_by_phone,
    get_user_profile,
    save_file_to_post,
    save_post_data,
    save_user_profile,
    schedule, get_store_id_by_name,
)
from keyboards.keyboards import (
    get_back_keyboard,
    get_contact_keyboard,
    get_dmp_brands_keyboard,
    get_location_keyboard,
    get_main_keyboard,
    get_photo_keyboard,
    get_photo_type_keyboard,
)
from services.logger import logger

router = Router()


async def check_auth(message: Message, state: FSMContext) -> bool:
    user_id = message.from_user.id
    logger.info(f"Проверка авторизации для пользователя: {user_id}")

    user = await get_user_profile(user_id)
    if not user:
        logger.warning(f"Пользователь {user_id} не найден в системе")
        await message.answer(
            "Для начала работы необходимо авторизоваться. Поделитесь контактом.",
            reply_markup=get_contact_keyboard(),
        )
        await state.set_state(UserState.unauthorized)
        return False

    try:
        agent = await get_agent_by_phone(user["agent_number"])
        if not agent:
            logger.warning(f"Агент с номером {user['agent_number']} не найден для пользователя {user_id}")
            await message.answer(
                "❌ Ваш номер не найден в системе. Обратитесь к администратору.",
                reply_markup=get_contact_keyboard(),
            )
            await state.set_state(UserState.unauthorized)
            return False

        logger.info(f"Авторизация успешна для пользователя {user_id}, агент: {agent.get('id', 'unknown')}")
    except Exception as e:
        logger.error(f"Ошибка при проверке агента для пользователя {user_id}: {e}")
        await state.set_state(UserState.unauthorized)
        return False

    return True


async def reset_to_main(message: Message, state: FSMContext, error_msg: str = None):
    user_id = message.from_user.id
    logger.info(f"Сброс состояния в главное меню для пользователя {user_id}: {error_msg}")

    if await check_auth(message, state):
        await state.set_state(UserState.authorized)
        await state.update_data(location=None, type_photo=None, shop_name=None,
                                dmp_brand=None, competitor_brand=None)
        msg = error_msg or "Возвращаемся в главное меню."
        logger.info(f"Состояние сброшено для пользователя {user_id}")
        await message.answer(msg, reply_markup=get_main_keyboard())


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_name = message.from_user.full_name
    logger.info(f"Команда /start от пользователя {user_id} ({user_name})")

    await state.clear()
    logger.info(f"Состояние очищено для пользователя {user_id}")

    await message.answer(
        "👋 Привет! Я бот для загрузки фотографий магазинов.\n\n"
        "Для начала работы, пожалуйста, поделитесь своим контактом, "
        "чтобы я мог проверить ваш номер телефона в системе.",
        reply_markup=get_contact_keyboard(),
    )
    await state.set_state(UserState.unauthorized)
    logger.info(f"Пользователь {user_id} переведен в состояние unauthorized")


@router.message(Command("help"))
@router.message(F.text == "❓ Помощь")
async def cmd_help(message: Message):
    user_id = message.from_user.id
    logger.info(f"Команда помощи от пользователя {user_id}")

    await message.answer(
        "📋 <b>Инструкция по использованию бота:</b>\n\n"
        "1. Отправьте свой контакт для авторизации\n"
        "2. После успешной авторизации нажмите на кнопку «🏪 Выбрать маркет»\n"
        "3. Нажмите на название магазина для фотографии\n"
        "4. Нажмите на кнопку геолокации для привязки к фотографии\n"
        "5. Выберите тип фотографии\n"
        "6. Сфотографируйте магазин во внешней камере\n"
        "7. Отправьте фотографию в виде файла\n"
        "8. Загрузите фотографию\n\n"
        "Если у вас возникли проблемы, обратитесь к администратору."
    )


@router.message(Command("profile"))
@router.message(F.text == "👤 Мой профиль")
async def cmd_profile(message: Message, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"Запрос профиля от пользователя {user_id}")

    if not await check_auth(message, state):
        return

    user = await get_user_profile(user_id)
    logger.info(f"Отображение профиля для пользователя {user_id}: {user['agent_number']}")

    await message.answer(
        f"📱 Телефон: {user['agent_number']}",
        reply_markup=get_main_keyboard(),
    )


@router.message(F.content_type == ContentType.CONTACT)
async def handle_contact(message: Message, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"Получен контакт от пользователя {user_id}")

    current_state = await state.get_state()
    logger.info(f"Текущее состояние пользователя {user_id}: {current_state}")

    if current_state != UserState.unauthorized:
        logger.warning(f"Пользователь {user_id} уже авторизован, контакт проигнорирован")
        await message.answer("Вы уже авторизованы.", reply_markup=get_main_keyboard())
        return

    contact = message.contact
    phone_number = contact.phone_number
    logger.info(f"Номер телефона из контакта: {phone_number}")

    if contact.user_id != user_id:
        logger.warning(f"Пользователь {user_id} отправил чужой контакт")
        await message.answer("Пожалуйста, отправьте свой собственный контакт.")
        return

    try:
        agent = await get_agent_by_phone(phone_number)
        await save_user_profile(user_id, phone_number)
        await state.update_data(phone=phone_number)
        logger.info(f"Профиль сохранен для пользователя {user_id} с номером {phone_number}")

        if agent:
            await state.set_state(UserState.authorized)
            logger.info(f"Пользователь {user_id} успешно авторизован")
            await message.answer(
                "✅ Успешная авторизация!\n\nТеперь вы можете загружать фотографии.",
                reply_markup=get_main_keyboard(),
            )
        else:
            logger.warning(f"Агент с номером {phone_number} не найден в системе")
            await message.answer(
                "❌ Ваш номер не найден в нашей системе.\n"
                "Обратитесь к администратору для регистрации вашего магазина."
            )
    except Exception as e:
        logger.error(f"Ошибка при обработке контакта пользователя {user_id}: {e}")
        await message.answer(
            "Произошла ошибка при проверке вашего номера. Пожалуйста, попробуйте позже."
        )


@router.message(F.text == "🏪 Выбрать маркет")
async def handle_upload_photo(message: Message, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"Запрос загрузки фото от пользователя {user_id}")

    if not await check_auth(message, state):
        return

    current_state = await state.get_state()
    logger.info(f"Текущее состояние при загрузке фото: {current_state}")

    if current_state != UserState.authorized:
        logger.warning(f"Пользователь {user_id} не в авторизованном состоянии")
        await reset_to_main(message, state, "Сначала завершите текущую операцию.")
        return

    await state.set_state(UserState.waiting_for_shopName)
    logger.info(f"Пользователь {user_id} переведен в состояние ожидания названия магазина")
    await schedule(message)


@router.message(UserState.waiting_for_shopName, F.text)
async def handle_shop_name(message: Message, state: FSMContext):
    user_id = message.from_user.id
    shop_name = message.text
    logger.info(f"Получено название магазина от пользователя {user_id}: {shop_name}")

    if not await check_auth(message, state):
        return

    if message.text == "🔙 Назад":
        logger.info(f"Пользователь {user_id} возвращается назад из выбора магазина")
        await reset_to_main(message, state)
        return

    try:
        user = await get_user_profile(user_id)
        phone_number = user["agent_number"]
        if not phone_number.startswith("+"):
            phone_number = f"+{phone_number}"

        url = f"{os.getenv('WEB_SERVICE_URL')}/api/agent-schedule/{phone_number}"
        logger.info(f"Проверка доступных магазинов для пользователя {user_id}: {url}")

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    stores = await response.json()
                    store_names = [store["name"] for store in stores] if stores else []
                    logger.info(f"Доступные магазины для пользователя {user_id}: {store_names}")

                    if message.text not in store_names:
                        logger.warning(f"Пользователь {user_id} выбрал недоступный магазин: {shop_name}")
                        await message.answer(
                            "Пожалуйста, выберите магазин из списка кнопок ниже:",
                            reply_markup=message.reply_markup
                        )
                        return
                else:
                    logger.error(f"Ошибка при получении магазинов для пользователя {user_id}: статус {response.status}")
                    await reset_to_main(message, state, "Ошибка при получении списка магазинов.")
                    return
    except Exception as e:
        logger.error(f"Ошибка при проверке списка магазинов для пользователя {user_id}: {e}")
        await reset_to_main(message, state, "Ошибка при проверке магазина.")
        return

    await state.update_data(shop_name=shop_name)
    await state.set_state(UserState.waiting_for_location)
    logger.info(f"Магазин '{shop_name}' сохранен для пользователя {user_id}, ожидание геолокации")

    await message.answer(
        f"Название магазина '{shop_name}' сохранено.\nТеперь отправьте геолокацию.",
        reply_markup=get_location_keyboard(),
    )


@router.message(UserState.waiting_for_location, F.content_type == ContentType.LOCATION)
async def handle_location(message: Message, state: FSMContext):
    user_id = message.from_user.id
    latitude = message.location.latitude
    longitude = message.location.longitude
    logger.info(f"Получена геолокация от пользователя {user_id}: lat={latitude}, lng={longitude}")

    if not await check_auth(message, state):
        return

    await state.update_data(
        location={
            "latitude": latitude,
            "longitude": longitude,
        }
    )

    data = await state.get_data()
    shop_name = data.get("shop_name")
    logger.info(f"Проверка координат для пользователя {user_id}, магазин: {shop_name}")

    try:
        check = await check_coordinates(latitude, longitude, shop_name)
        logger.info(f"Результат проверки координат для пользователя {user_id}: {check}")

        if check:
            await state.set_state(UserState.waiting_for_type_photo)
            logger.info(f"Пользователь {user_id} переведен в состояние выбора типа фото")
            await message.answer(
                "📍 Геолокация принята!\n\nТеперь выберите тип фото.",
                reply_markup=get_photo_type_keyboard(),
            )
        else:
            logger.warning(f"Координаты не подтверждены для пользователя {user_id}")
            await reset_to_main(message, state, "Координаты не подтверждены.")
    except Exception as e:
        logger.error(f"Ошибка при проверке координат для пользователя {user_id}: {e}")
        await reset_to_main(message, state, "Ошибка при проверке координат.")


@router.message(UserState.waiting_for_location, F.text == "🔙 Назад")
async def back_from_location(message: Message, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} возвращается назад из геолокации")

    await state.set_state(UserState.waiting_for_shopName)
    await schedule(message)


@router.message(UserState.waiting_for_type_photo, F.text)
async def handle_type_photo(message: Message, state: FSMContext):
    user_id = message.from_user.id
    photo_type = message.text
    logger.info(f"Получен тип фото от пользователя {user_id}: {photo_type}")

    if not await check_auth(message, state):
        return

    if message.text == "🔙 Назад":
        logger.info(f"Пользователь {user_id} возвращается назад из выбора типа фото")
        await state.set_state(UserState.waiting_for_location)
        await message.answer(
            "Возвращаемся к отправке геолокации.",
            reply_markup=get_location_keyboard(),
        )
        return

    if message.text not in POST_TYPE_CHOICES:
        logger.warning(f"Пользователь {user_id} выбрал неверный тип фото: {photo_type}")
        await message.answer(
            "❌ Неверный тип фото!\n"
            "Пожалуйста, выберите один из предложенных вариантов:",
            reply_markup=get_photo_type_keyboard(),
        )
        return

    type_photo = message.text
    await state.update_data(type_photo=type_photo)
    logger.info(f"Тип фото '{type_photo}' сохранен для пользователя {user_id}")

    if "ДМП" in type_photo:
        if "конкурент" in type_photo:
            logger.info(f"Пользователь {user_id} выбрал ДМП конкурента")
            brands_keyboard = await get_dmp_brands_keyboard("competitor")
            await message.answer(
                f"📋 Тип: {type_photo}\n\nВыберите бренд конкурента:",
                reply_markup=brands_keyboard,
            )
            await state.set_state(UserState.waiting_for_competitor_brand)
        else:
            logger.info(f"Пользователь {user_id} выбрал ДМП ОРИМИ")
            brands_keyboard = await get_dmp_brands_keyboard("orimi")
            await message.answer(
                f"📋 Тип: {type_photo}\n\nВыберите бренд ОРИМИ:",
                reply_markup=brands_keyboard,
            )
            await state.set_state(UserState.waiting_for_dmp_brand)
    else:
        await state.set_state(UserState.waiting_for_photo)
        logger.info(f"Пользователь {user_id} переведен в состояние ожидания фото")
        await message.answer(
            f"📋 Тип фото: {type_photo}\n\nТеперь отправьте фото.",
            reply_markup=get_photo_keyboard(),
        )


@router.message(UserState.waiting_for_dmp_brand, F.text)
async def handle_dmp_brand(message: Message, state: FSMContext):
    user_id = message.from_user.id
    brand = message.text
    logger.info(f"Получен бренд ОРИМИ от пользователя {user_id}: {brand}")

    if not await check_auth(message, state):
        return

    if message.text == "🔙 Назад":
        logger.info(f"Пользователь {user_id} возвращается назад из выбора бренда ОРИМИ")
        await state.set_state(UserState.waiting_for_type_photo)
        await message.answer(
            "Возвращаемся к выбору типа фото.",
            reply_markup=get_photo_type_keyboard(),
        )
        return

    if message.text not in ORIMI_BRANDS:
        logger.warning(f"Пользователь {user_id} выбрал неверный бренд ОРИМИ: {brand}")
        brands_keyboard = await get_dmp_brands_keyboard("orimi")
        await message.answer(
            "❌ Неверный бренд!\n"
            "Пожалуйста, выберите один из предложенных брендов ОРИМИ:",
            reply_markup=brands_keyboard,
        )
        return

    dmp_brand = message.text
    await state.update_data(dmp_brand=dmp_brand)
    await state.set_state(UserState.waiting_for_photo)
    logger.info(f"Бренд ОРИМИ '{dmp_brand}' сохранен для пользователя {user_id}")

    await message.answer(
        f"📋 Выбран бренд ОРИМИ: {dmp_brand}\n\nТеперь отправьте фото.",
        reply_markup=get_photo_keyboard(),
    )


@router.message(UserState.waiting_for_competitor_brand, F.text)
async def handle_competitor_brand(message: Message, state: FSMContext):
    user_id = message.from_user.id
    brand = message.text
    logger.info(f"Получен бренд конкурента от пользователя {user_id}: {brand}")

    if not await check_auth(message, state):
        return

    if message.text == "🔙 Назад":
        logger.info(f"Пользователь {user_id} возвращается назад из выбора бренда конкурента")
        await state.set_state(UserState.waiting_for_type_photo)
        await message.answer(
            "Возвращаемся к выбору типа фото.",
            reply_markup=get_photo_type_keyboard(),
        )
        return

    if message.text not in COMPETITOR_BRANDS:
        logger.warning(f"Пользователь {user_id} выбрал неверный бренд конкурента: {brand}")
        brands_keyboard = await get_dmp_brands_keyboard("competitor")
        await message.answer(
            "❌ Неверный бренд!\n"
            "Пожалуйста, выберите один из предложенных брендов конкурентов:",
            reply_markup=brands_keyboard,
        )
        return

    competitor_brand = message.text
    await state.update_data(competitor_brand=competitor_brand)
    await state.set_state(UserState.waiting_for_competitor_count_after_brand)
    logger.info(f"Бренд конкурента '{competitor_brand}' сохранен для пользователя {user_id}")

    await message.answer(
        f"📋 Выбран бренд конкурента: {competitor_brand}\n\n"
        "Введите количество ДМП конкурентов:",
        reply_markup=get_back_keyboard(),
    )


@router.message(UserState.waiting_for_competitor_count_after_brand, F.text)
async def handle_competitor_count_after_brand(message: Message, state: FSMContext):
    user_id = message.from_user.id
    count_text = message.text
    logger.info(f"Получено количество товаров конкурентов от пользователя {user_id}: {count_text}")

    if not await check_auth(message, state):
        return

    if message.text == "🔙 Назад":
        logger.info(f"Пользователь {user_id} возвращается назад из ввода количества")
        await state.set_state(UserState.waiting_for_competitor_brand)
        brands_keyboard = await get_dmp_brands_keyboard("competitor")
        await message.answer(
            "Возвращаемся к выбору бренда конкурента.",
            reply_markup=brands_keyboard,
        )
        return

    cnt = message.text

    if not cnt.isdigit():
        logger.warning(f"Пользователь {user_id} ввел некорректное количество: {cnt}")
        await message.answer(
            "Введите число, а не что-то другое:",
            reply_markup=get_back_keyboard(),
        )
        return

    try:
        user_profile = await get_user_profile(user_id)
        agent = await get_agent_by_phone(user_profile["agent_number"])
        state_data = await state.get_data()
        store = await get_store_id_by_name(state_data["shop_name"])

        logger.info(
            f"Сохранение данных конкурента для пользователя {user_id}: агент={agent.get('id')}, магазин={store.get('id') if store else None}, количество={cnt}")

        if not store:
            logger.error(f"Магазин '{state_data['shop_name']}' не найден для пользователя {user_id}")
            await reset_to_main(message, state, "Магазин не зарегистрирован.")
            return

        location = state_data.get("location", {})
        result = await save_post_data(
            agent["id"],
            store["id"],
            location.get("latitude"),
            location.get("longitude"),
            state_data.get("type_photo"),
            state_data.get("competitor_brand"),
            cnt,
        )

        logger.info(f"Результат сохранения данных конкурента для пользователя {user_id}: {result}")
        await reset_to_main(message, state, "Данные успешно сохранены!")

    except Exception as e:
        logger.error(f"Ошибка при сохранении данных конкурента для пользователя {user_id}: {e}")
        await reset_to_main(message, state, "Ошибка при сохранении данных.")


@router.message(UserState.waiting_for_photo, F.content_type == ContentType.DOCUMENT)
async def handle_file(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"Получен файл от пользователя {user_id}")

    if not await check_auth(message, state):
        return

    try:
        user_profile = await get_user_profile(user_id)
        state_data = await state.get_data()
        location = state_data.get("location")
        type_photo = state_data.get("type_photo")
        shop_name = state_data.get("shop_name")

        logger.info(f"Данные для обработки файла пользователя {user_id}: магазин={shop_name}, тип={type_photo}")

        if not location:
            logger.warning(f"Отсутствует геолокация для пользователя {user_id}")
            await state.set_state(UserState.waiting_for_location)
            await message.answer("Сначала отправьте геолокацию.")
            return

        agent = await get_agent_by_phone(user_profile["agent_number"])
        store = await get_store_id_by_name(shop_name)

        logger.info(
            f"Найден агент {agent.get('id')} и магазин {store.get('id') if store else None} для пользователя {user_id}")

        if not store:
            logger.error(f"Магазин '{shop_name}' не зарегистрирован для пользователя {user_id}")
            await reset_to_main(message, state, "Магазин не зарегистрирован.")
            return

        document = message.document
        file_id = document.file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        file_name = (
                document.file_name or f"{uuid.uuid4().hex}{os.path.splitext(file_path)[1]}"
        )

        file_url = f"https://api.telegram.org/file/bot{os.getenv('SECRET_KEY')}/{file_path}"
        logger.info(f"Обработка файла для пользователя {user_id}: {file_name}, размер: {document.file_size}")

        status_message = await message.answer("⏳ Загрузка файла...")

        try:
            relative_path = await download_file(file_url, file_name)
            logger.info(f"Файл успешно скачан для пользователя {user_id}: {relative_path}")

            result = await save_file_to_post(
                agent["id"],
                store["id"],
                relative_path,
                latitude=location["latitude"],
                longitude=location["longitude"],
                type_photo=type_photo,
                dmp_type=state_data.get("dmp_brand")
            )

            logger.info(f"Результат сохранения файла для пользователя {user_id}: {result}")

            await bot.edit_message_text(
                "✅ Файл успешно сохранен",
                chat_id=status_message.chat.id,
                message_id=status_message.message_id,
            )

            await reset_to_main(message, state)
            await message.answer("Хотите загрузить еще фото?", reply_markup=get_main_keyboard())

        except Exception as e:
            error_message = str(e)
            logger.error(f"Ошибка при обработке файла пользователя {user_id}: {error_message}")


            error_text = "❌ Фото сделано более 10 минут назад. Сделайте свежее фото."

            await bot.edit_message_text(
                error_text,
                chat_id=status_message.chat.id,
                message_id=status_message.message_id,
            )
            await reset_to_main(message, state)

    except Exception as e:
        logger.error(f"Критическая ошибка при обработке файла пользователя {user_id}: {e}")
        await reset_to_main(message, state, "❗ Неизвестная ошибка.")


@router.message(UserState.authorized)
async def handle_authorized_commands(message: Message, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"Обработка команды в авторизованном состоянии от пользователя {user_id}: {message.text}")

    if not await check_auth(message, state):
        return

    await message.answer(
        "Используйте кнопки меню для навигации.",
        reply_markup=get_main_keyboard(),
    )


@router.message()
async def unknown_message(message: Message, state: FSMContext):
    user_id = message.from_user.id
    current_state = await state.get_state()
    logger.info(f"Неизвестное сообщение от пользователя {user_id} в состоянии {current_state}: {message.text}")

    if current_state and current_state != UserState.unauthorized and current_state != UserState.authorized:
        if await check_auth(message, state):
            logger.info(f"Операция прервана для пользователя {user_id}, возврат в главное меню")
            await reset_to_main(message, state, "Операция прервана. Используйте кнопки меню.")
        return

    if await check_auth(message, state):
        await state.set_state(UserState.authorized)
        logger.info(f"Пользователь {user_id} переведен в авторизованное состояние")
        await message.answer(
            "Используйте кнопки меню для навигации.",
            reply_markup=get_main_keyboard(),
        )
    else:
        logger.info(f"Неавторизованный пользователь {user_id} получил запрос на контакт")
        await message.answer(
            "Для начала работы поделитесь контактом.",
            reply_markup=get_contact_keyboard(),
        )