import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo
)

from config import BOT_TOKEN, WEBAPP_URL
from db import init_db, calculate_natal_chart, save_full_natal_profile

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

WELCOME_TEXT = (
    "Получи бесплатный разбор твоей натальной карты ✨\n\n"
    "- ИИ составит твою личную натальную карту.\n"
    "- На основе вашей натальной карты проконсультирует вас по выбранному запросу.\n"
    "- В конце поделись своими впечатлениями и получи подарок."
)

# Настройка CORS, чтобы Mini App с Netlify мог отправлять запросы на локальный сервер
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


async def handle_options(request: web.Request):
    return web.Response(status=204, headers=CORS_HEADERS)


async def handle_natal_api(request: web.Request):
    """Принимает данные из Mini App, считает карту через pyswisseph и сохраняет в БД."""
    try:
        payload = await request.json()

        # 1. Считаем натальную карту через Swiss Ephemeris
        chart_data = calculate_natal_chart(
            birth_date=payload["birthDate"],
            birth_time=payload["birthTime"],
            is_exact_time=not payload.get("unknownTime", False),
            lat=float(payload.get("latitude", 55.7558)),
            lon=float(payload.get("longitude", 37.6173)),
            tz_offset=float(payload.get("tzOffset", 3.0))
        )

        # 2. Сохраняем все данные в SQLite (astro.db)
        user_id = await save_full_natal_profile(payload, chart_data)
        logging.info(f"Натальная карта сохранена в БД! user_id={user_id}")

        return web.json_response(
            {"status": "ok", "user_id": user_id, "chart": chart_data},
            headers=CORS_HEADERS
        )
    except Exception as e:
        logging.exception("Ошибка при расчёте и сохранении карты:")
        return web.json_response(
            {"status": "error", "message": str(e)},
            status=400,
            headers=CORS_HEADERS
        )


@dp.message(CommandStart())
async def cmd_start(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✨ Составить натальную карту",
                    web_app=WebAppInfo(url=WEBAPP_URL)
                )
            ]
        ]
    )
    photo = FSInputFile("1.png")
    await message.answer_photo(photo=photo, caption=WELCOME_TEXT, reply_markup=kb)


async def main():
    logging.basicConfig(level=logging.INFO)

    # Создаём таблицы в БД
    await init_db()
    logging.info("База данных astro.db готова к работе.")

    # Запускаем API-сервер на порту 8080 для приёма данных из Mini App
    app = web.Application()
    app.router.add_route("OPTIONS", "/api/natal", handle_options)
    app.router.add_post("/api/natal", handle_natal_api)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 8080)
    await site.start()
    logging.info("API-сервер слушает http://127.0.0.1:8080/api/natal")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())