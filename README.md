# Orimi Merchen Telegram Bot

Telegram-бот для загрузки фотографий магазинов с проверкой геолокации и обработкой изображений.

## 🚀 Быстрый старт

### Требования
- Python 3.12+
- Redis
- Docker (опционально)

### Установка

1. **Клонируйте репозиторий**
```bash
git clone <repository-url>
cd orimi-merchen
```
## Установите зависимости
### С uv (рекомендуется)
uv sync

### Или с pip
pip install -r requirements.txt

### Создайте .env файл
SECRET_KEY=your_telegram_bot_token
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your_redis_password
WEB_SERVICE_URL=https://your-api-server.com

## 🐳 Запуск с 
```
docker compose up --build -d
```
