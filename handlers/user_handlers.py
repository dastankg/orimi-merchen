import os
import uuid

from aiogram import Bot, F, Router
from aiogram.enums import ContentType
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from fsms.fsm import UserState
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


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    logger.info(f"/start от {message.from_user.id} ({message.from_user.full_name})")
    await message.answer(
        "👋 Привет! Я бот для загрузки фотографий магазинов.\n\n"
        "Для начала работы, пожалуйста, поделитесь своим контактом, "
        "чтобы я мог проверить ваш номер телефона в системе.",
        reply_markup=get_contact_keyboard(),
    )
    await state.set_state(UserState.unauthorized)


@router.message(Command("help"))
@router.message(F.text == "❓ Помощь")
async def cmd_help(message: Message):
    await message.answer(
        "📋 <b>Инструкция по использованию бота:</b>\n\n"
        "1. Отправьте свой контакт для авторизации\n"
        "2. После успешной авторизации нажмите на кнопку «Загрузить фото»\n"
        "3. Введите название магазина для фотографии\n"
        "4. Отправьте геолокацию для привязки к фотографии\n"
        "5. Выберите тип фотографии\n"
        "6. Загрузите фотографию магазина\n\n"
        "Если у вас возникли проблемы, обратитесь к администратору."
    )


@router.message(Command("profile"))
@router.message(F.text == "👤 Мой профиль")
async def cmd_profile(message: Message, state: FSMContext):
    user = await get_user_profile(message.from_user.id)
    if not user:
        await message.answer(
            "Вы еще не авторизованы. Пожалуйста, поделитесь своим контактом для авторизации.",
            reply_markup=get_contact_keyboard(),
        )
        await state.set_state(UserState.unauthorized)
        return
    await message.answer(
        f"📱 Телефон: {user['agent_number']}",
        reply_markup=get_main_keyboard(),
    )


@router.message(F.content_type == ContentType.CONTACT)
async def handle_contact(message: Message, state: FSMContext):
    contact = message.contact
    phone_number = contact.phone_number
    telegram_id = message.from_user.id
    logger.info(f"Контакт от {telegram_id}: {phone_number}")

    if contact.user_id != telegram_id:
        await message.answer("Пожалуйста, отправьте свой собственный контакт.")
        return

    try:
        agent = await get_agent_by_phone(phone_number)

        await save_user_profile(telegram_id, phone_number)
        await state.update_data(phone=phone_number)
        if agent:
            await state.set_state(UserState.authorized)
            await message.answer(
                "✅ Успешная авторизация!\n\nТеперь вы можете загружать фотографии.",
                reply_markup=get_main_keyboard(),
            )
        else:
            await state.set_state(UserState.unauthorized)
            await message.answer(
                "❌ Ваш номер не найден в нашей системе.\n"
                "Обратитесь к администратору для регистрации вашего магазина."
            )
    except Exception as e:
        logger.error(f"Error in handle_contact: {e}")
        await message.answer(
            "Произошла ошибка при проверке вашего номера. Пожалуйста, попробуйте позже."
        )


@router.message(F.text == "📷 Загрузить фото")
async def handle_upload_photo(message: Message, state: FSMContext):
    user = await get_user_profile(message.from_user.id)
    if not user:
        await message.answer(
            "Для загрузки фото необходимо авторизоваться. Пожалуйста, поделитесь контактом.",
            reply_markup=get_contact_keyboard(),
        )
        await state.set_state(UserState.unauthorized)
        return

    await state.set_state(UserState.waiting_for_shopName)
    await schedule(message)


@router.message(UserState.waiting_for_shopName)
async def handle_shop_name(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await state.set_state(UserState.authorized)
        await message.answer(
            "Возвращаемся в главное меню.",
            reply_markup=get_main_keyboard(),
        )
        return

    shop_name = message.text

    await state.update_data(shop_name=shop_name)
    await state.set_state(UserState.waiting_for_location)

    await message.answer(
        f"Название магазина '{shop_name}' сохранено.\nТеперь отправьте геолокацию.",
        reply_markup=get_location_keyboard(),
    )


@router.message(UserState.waiting_for_location, F.content_type == ContentType.LOCATION)
async def handle_location(message: Message, state: FSMContext):
    telegram_id = message.from_user.id
    user = await get_user_profile(telegram_id)

    if not user:
        await message.answer(
            "Для начала работы необходимо авторизоваться. Пожалуйста, поделитесь своим контактом.",
            reply_markup=get_contact_keyboard(),
        )
        await state.set_state(UserState.unauthorized)
        return

    await state.update_data(
        location={
            "latitude": message.location.latitude,
            "longitude": message.location.longitude,
        }
    )
    data = await state.get_data()
    shop_name = data.get("shop_name")
    check = await check_coordinates(
        message.location.latitude, message.location.longitude, shop_name
    )
    if check:
        await state.set_state(UserState.waiting_for_type_photo)

        await message.answer(
            "📍 Геолокация получена!\n\nТеперь выберите тип фото.",
            reply_markup=get_photo_type_keyboard(),
        )
    else:
        await message.answer(
            "Возвращаемся в главное меню.",
            reply_markup=get_main_keyboard(),
        )


@router.message(UserState.waiting_for_location, F.text == "🔙 Назад")
async def back_from_location(message: Message, state: FSMContext):
    await state.set_state(UserState.authorized)
    await message.answer(
        "Возвращаемся в главное меню.",
        reply_markup=get_main_keyboard(),
    )


@router.message(UserState.waiting_for_type_photo, F.text)
async def handle_type_photo(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await state.set_state(UserState.waiting_for_location)
        await message.answer(
            "Возвращаемся к отправке геолокации.",
            reply_markup=get_location_keyboard(),
        )
        return

    type_photo = message.text
    await state.update_data(type_photo=type_photo)

    if "ДМП" in type_photo:
        if "конкурент" in type_photo:
            brands_keyboard = await get_dmp_brands_keyboard("competitor")
            await message.answer(
                f"📋 Тип: {type_photo}\n\nВыберите бренд конкурента:",
                reply_markup=brands_keyboard,
            )
            await state.set_state(UserState.waiting_for_competitor_brand)
        else:
            brands_keyboard = await get_dmp_brands_keyboard("orimi")
            await message.answer(
                f"📋 Тип: {type_photo}\n\nВыберите бренд ОРИМИ:",
                reply_markup=brands_keyboard,
            )
            await state.set_state(UserState.waiting_for_dmp_brand)
    else:
        await state.set_state(UserState.waiting_for_photo)
        await message.answer(
            f"📋 Тип фото: {type_photo}\n\nТеперь выберите тип файла.",
            reply_markup=get_photo_keyboard(),
        )


@router.message(UserState.waiting_for_dmp_brand, F.text)
async def handle_dmp_brand(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await state.set_state(UserState.waiting_for_type_photo)
        await message.answer(
            "Возвращаемся к выбору типа фото.",
            reply_markup=get_photo_type_keyboard(),
        )
        return

    dmp_brand = message.text
    await state.update_data(dmp_brand=dmp_brand)

    # Для обычных брендов ОРИМИ переходим к выбору файла
    await state.set_state(UserState.waiting_for_photo)
    await message.answer(
        f"📋 Выбран бренд ОРИМИ: {dmp_brand}\n\nТеперь выберите тип файла.",
        reply_markup=get_photo_keyboard(),
    )


@router.message(UserState.waiting_for_competitor_brand, F.text)
async def handle_competitor_brand(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await state.set_state(UserState.waiting_for_type_photo)
        await message.answer(
            "Возвращаемся к выбору типа фото.",
            reply_markup=get_photo_type_keyboard(),
        )
        return

    competitor_brand = message.text
    await state.update_data(competitor_brand=competitor_brand)

    # Для конкурентов спрашиваем количество товаров
    await state.set_state(UserState.waiting_for_competitor_count_after_brand)
    await message.answer(
        f"📋 Выбран бренд конкурента: {competitor_brand}\n\n"
        "Введите количество товаров конкурентов:",
        reply_markup=get_back_keyboard(),
    )


@router.message(UserState.waiting_for_competitor_count_after_brand, F.text)
async def handle_competitor_count_after_brand(message: Message, state: FSMContext):
    telegram_id = message.from_user.id
    logger.info(f"Получен файл от user_id={telegram_id}")
    cnt = message.text
    user_profile = await get_user_profile(telegram_id)
    if not user_profile:
        logger.warning(f"Неизвестный пользователь: {telegram_id}")
        await message.answer("Авторизуйтесь.")
        await state.set_state(UserState.unauthorized)
        return
    agent = await get_agent_by_phone(user_profile["agent_number"])
    if not agent:
        logger.warning(f"Магазин не найден: phone={user_profile['agent_number']}")
        await message.answer("Ваш магазин не зарегистрирован.")
        return
    state_data = await state.get_data()
    store = await get_store_id_by_name(state_data["shop_name"])
    if not store:
        logger.warning(f"Магазин не найден: phone={user_profile['agent_number']}")
        await message.answer("Ваш магазин не зарегистрирован.")
        return
    if cnt.isdigit():
        await state.set_state(UserState.authorized)
        # Получаем данные из состояния FSM, а не из профиля пользователя
        data = await state.get_data()
        location = data.get("location", {})
        await save_post_data(
            agent["id"],
            store["id"],
            location.get("latitude"),
            location.get("longitude"),
            data.get("type_photo"),
            data.get("competitor_brand"),  # правильное поле
            cnt,
        )
        await message.answer(
            "Данные успешно сохранены!", reply_markup=get_main_keyboard()
        )
    else:
        await message.answer(
            "Введите число, а не что-то другое:",
            reply_markup=get_back_keyboard(),
        )


@router.message(UserState.waiting_for_photo, F.content_type == ContentType.DOCUMENT)
async def handle_file(message: Message, bot: Bot, state: FSMContext):
    telegram_id = message.from_user.id
    logger.info(f"Получен файл от user_id={telegram_id}")

    try:
        user_profile = await get_user_profile(telegram_id)
        if not user_profile:
            logger.warning(f"Неизвестный пользователь: {telegram_id}")
            await message.answer("Авторизуйтесь.")
            await state.set_state(UserState.unauthorized)
            return

        state_data = await state.get_data()
        location = state_data.get("location")
        type_photo = state_data.get("type_photo")

        if not location:
            logger.info(f"Нет геолокации для user_id={telegram_id}")
            await message.answer("Сначала отправьте геолокацию.")
            await state.set_state(UserState.waiting_for_location)
            return

        agent = await get_agent_by_phone(user_profile["agent_number"])
        if not agent:
            logger.warning(f"Магазин не найден: phone={user_profile['agent_number']}")
            await message.answer("Ваш магазин не зарегистрирован.")
            return
        store = await get_store_id_by_name(state_data["shop_name"])
        if not store:
            logger.warning(f"Магазин не найден: phone={user_profile['agent_number']}")
            await message.answer("Ваш магазин не зарегистрирован.")
            return

        document = message.document
        file_id = document.file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        file_name = (
                document.file_name or f"{uuid.uuid4().hex}{os.path.splitext(file_path)[1]}"
        )

        logger.info(
            f"Загрузка файла от {telegram_id}: file_id={file_id}, path={file_path}, name={file_name}"
        )

        file_url = (
            f"https://api.telegram.org/file/bot{os.getenv('SECRET_KEY')}/{file_path}"
        )
        status_message = await message.answer("⏳ Загрузка файла...")

        try:
            relative_path = await download_file(file_url, file_name)

            await save_file_to_post(
                agent["id"],
                store["id"],
                relative_path,
                latitude=location["latitude"],
                longitude=location["longitude"],
                type_photo=type_photo,
                dmp_type=state_data.get("dmp_brand")
            )

            logger.info(f"Файл сохранен: {file_name}")

            await state.update_data(location=None, type_photo=None)
            await state.set_state(UserState.authorized)

            await bot.edit_message_text(
                "✅ Файл успешно сохранен",
                chat_id=status_message.chat.id,
                message_id=status_message.message_id,
            )

            await message.answer(
                text="Хотите загрузить еще фото?", reply_markup=get_main_keyboard()
            )

        except Exception as e:
            await state.set_state(UserState.authorized)
            error_message = str(e)
            logger.exception(
                f"Ошибка при сохранении файла от {telegram_id}: {error_message}"
            )

            if "более 5 минут назад" in error_message:
                await bot.edit_message_text(
                    "❌ Фото сделано более 5 минут назад. Пожалуйста, сделайте свежее фото.",
                    chat_id=status_message.chat.id,
                    message_id=status_message.message_id,
                )
            elif (
                    "EXIF данные отсутствуют" in error_message
                    or "метаданные отсутствуют" in error_message.lower()
            ):
                await bot.edit_message_text(
                    "❌ Фото не содержит необходимые метаданные (EXIF). Пожалуйста, сделайте фото через камеру телефона.",
                    chat_id=status_message.chat.id,
                    message_id=status_message.message_id,
                )
            else:
                await bot.edit_message_text(
                    "❌ Ошибка при сохранении файла.",
                    chat_id=status_message.chat.id,
                    message_id=status_message.message_id,
                )

    except Exception as e:
        await state.set_state(UserState.authorized)
        logger.exception(f"Ошибка в handle_file от {telegram_id}: {str(e)}")
        await message.answer("❗ Неизвестная ошибка.")


@router.message(UserState.authorized)
async def handle_authorized_commands(message: Message):
    await message.answer(
        "Используйте кнопки меню для навигации.",
        reply_markup=get_main_keyboard(),
    )


@router.message()
async def unknown_message(message: Message, state: FSMContext):
    current_state = await state.get_state()
    user = await get_user_profile(message.from_user.id)

    if not user:
        await message.answer(
            "Для начала работы, пожалуйста, поделитесь своим контактом.",
            reply_markup=get_contact_keyboard(),
        )
        await state.set_state(UserState.unauthorized)
    else:
        if current_state is None:
            await state.set_state(UserState.authorized)

        await message.answer(
            "Используйте кнопки меню для навигации.",
            reply_markup=get_main_keyboard(),
        )
