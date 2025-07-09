from aiogram.types import (
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def get_contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📷 Загрузить фото"),
                KeyboardButton(text="👤 Мой профиль"),
                KeyboardButton(text="❓ Помощь"),
            ],
        ],
        resize_keyboard=True,
    )


def get_location_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Отправить геолокацию", request_location=True)],
            [KeyboardButton(text="🔙 Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_back_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔙 Назад")],
        ],
        resize_keyboard=True,
    )


def get_photo_type_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="РМП_чай_ДО")],
            [KeyboardButton(text="РМП_чай_ПОСЛЕ")],
            [KeyboardButton(text="РМП_кофе_ДО")],
            [KeyboardButton(text="РМП_кофе_ПОСЛЕ")],
            [KeyboardButton(text="ДМП_ОРИМИ КР")],
            [KeyboardButton(text="ДМП_конкурент")],
            [KeyboardButton(text="🔙 Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_photo_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔙 Назад")],
        ],
        resize_keyboard=True,
    )


async def get_dmp_brands_keyboard(brand_type: str) -> ReplyKeyboardMarkup:
    """
    Создает клавиатуру для выбора брендов ДМП

    Args:
        brand_type: "orimi" для брендов ОРИМИ или "competitor" для конкурентов

    Returns:
        ReplyKeyboardMarkup: Клавиатура с кнопками брендов
    """

    if brand_type == "orimi":
        # Бренды ОРИМИ
        brands = [
            "Tess",
        ]
    elif brand_type == "competitor":
        # Бренды конкурентов
        brands = [
            "Beta",
        ]
    else:
        # Если передан неизвестный тип, возвращаем пустую клавиатуру
        brands = []

    # Создаем кнопки
    buttons = []
    for brand in brands:
        buttons.append([KeyboardButton(text=brand)])

    # Добавляем кнопку "Назад"
    buttons.append([KeyboardButton(text="🔙 Назад")])

    keyboard = ReplyKeyboardMarkup(
        keyboard=buttons, resize_keyboard=True, one_time_keyboard=True
    )

    return keyboard
