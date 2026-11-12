import asyncio
import json
import logging

import aiohttp
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

from config import (
    BOT_TOKEN, WEBAPP_URL,
    PLUSVIBE_API_KEY, PLUSVIBE_BASE_URL, AI_MODEL
)
from db import (
    init_db, calculate_natal_chart, save_full_natal_profile,
    get_user_astro_context, save_chat_message
)

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


# ---------- ИИ-консультация через PlusVibeAPI (OpenAI-совместимый) ----------

def build_ai_messages(ctx: dict, topic: str, question: str) -> list:
    """Собирает messages для chat/completions: системный промпт + натальная карта."""
    astro = (
        f"Клиент: {ctx['name']} (пол: {ctx['gender']}).\n"
        f"Дата рождения: {ctx['birth_date']}, время: {ctx['birth_time']}"
        + ("" if ctx["is_exact_time"] else " (время приблизительное, асцендент ненадёжен)") + "\n"
        f"Город рождения: {ctx['city']}.\n\n"
        f"Натальная карта (Swiss Ephemeris, система домов Плацидуса):\n"
        f"- Солнце: {ctx['sun_sign']}\n"
        f"- Луна: {ctx['moon_sign']}\n"
        f"- Асцендент: {ctx['ascendant']}\n\n"
        f"Планеты: {ctx['planets_json']}\n"
        f"Куспиды домов: {ctx['houses_json']}"
    )

    system = (
        "Ты — тёплый и обаятельный астролог-консультант. "
        "Отвечай на русском языке, дружелюбно и на \"ты\".\n\n"
        "ПРИОРИТЕТ: главный источник для ответа — ВОПРОС КЛИЕНТА (сообщение пользователя). "
        f"Тема «{topic}» — это лишь категория, которой клиент отметил запрос в интерфейсе. "
        "Она НЕ задаёт рамку ответа и не должна подменять вопрос. "
        "Отвечай строго на то, о чём клиент спросил своими словами, "
        "даже если тема из интерфейса звучит иначе или выглядит не по делу.\n\n"
        "Правила:\n"
        "1. Опирайся ТОЛЬКО на данные натальной карты клиента из контекста. "
        "Не выдумывай положения планет. "
        "Если время рождения приблизительное — не используй дома и асцендент.\n\n"
        "СТРУКТУРА ОТВЕТА — РОВНО 3 АБЗАЦА (без заголовков, разделяются пустой строкой):\n\n"
        "АБЗАЦ 1 — «Что бросается в глаза» (до 350 символов):\n"
        "Начни живым оборотом: «Первое, что бросается в глаза, — …», «Сразу скажу: …», "
        "«Моментально видно, что …». Технично перечисли 1–2 самые яркие конфигурации карты "
        "(конкретные планеты и знаки) и подай каждую как редкое и сильное преимущество клиента — "
        "обоснованно, но максимально комплиментарно. Клиент должен почувствовать: "
        "такая карта — редкость, он уникален и у него всё получится.\n\n"
        "АБЗАЦ 2 — «Ключ к решению» (до 350 символов):\n"
        "Начни ровно со слов «Ключ к решению: …». Сформулируй главный принцип ответа "
        "максимально просто, тепло и универсально — так, чтобы почти любой человек "
        "мгновенно узнал в этом себя и подумал: «да, это точно про меня». "
        "Мягко свяжи универсальный принцип с одной-двумя деталями карты из абзаца 1.\n\n"
        "АБЗАЦ 3 — CTA (до 400 символов):\n"
        "Начни ровно со слов «Я бы не замарачивалась и начала с базы: …». Дай 2–3 шага, каждый из которых:\n"
        "— выполняется за 1–7 дней;\n"
        "— даёт заметный, ощутимый результат уже на этой неделе;\n"
        "— результат однозначно привязывается к шагу: человек точно понимает, "
        "что этот результат появился именно благодаря этому действию.\n"
        "ЗАПРЕЩЕНЫ советы с отложенным результатом на месяцы и годы "
        "(«развивай проект годами», «спрашивай себя раз в квартал»). "
        "Шаги должны быть конкретными, измеримыми и сразу дающими эффект.\n\n"
        "Тон: поддерживающий, без фатализма и пугающих прогнозов. "
        "Астрология — инструмент самопознания, а не приговор. "
        "Без markdown-разметки, простой текст с абзацами.\n\n"
        "ДАННЫЕ КЛИЕНТА:\n" + astro
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question}
    ]


async def call_plusvibe(messages: list) -> str:
    """Отправляет запрос в PlusVibeAPI и возвращает текст ответа модели.

    503/429 от провайдера — временные: делаем до 3 попыток с паузой.
    """
    url = f"{PLUSVIBE_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {PLUSVIBE_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": AI_MODEL,
        "messages": messages,
        "temperature": 0.8,
        "max_tokens": 2048,
        "reasoning_effort": "none"  # reasoning-модель: иначе токены уходят в скрытые размышления
    }
    timeout = aiohttp.ClientTimeout(total=120)
    last_error = None
    for attempt, delay in enumerate([0, 3, 8, 15, 25]):
        if delay:
            await asyncio.sleep(delay)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    data = await resp.json()
                    if resp.status == 200:
                        return data["choices"][0]["message"]["content"]
                    if resp.status in (429, 502, 503):
                        last_error = RuntimeError(f"PlusVibe {resp.status}: {data}")
                        continue
                    raise RuntimeError(f"PlusVibe {resp.status}: {data}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            last_error = e
    raise last_error


async def handle_consult_api(request: web.Request):
    """Принимает тему и вопрос из Mini App, консультирует через ИИ с учётом карты."""
    try:
        payload = await request.json()
        telegram_id = int(payload.get("telegram_id", 0))
        topic = (payload.get("topic") or "").strip()
        question = (payload.get("question") or "").strip()

        if not telegram_id or not topic or not question:
            return web.json_response(
                {"status": "error", "message": "Нужны telegram_id, topic и question"},
                status=400,
                headers=CORS_HEADERS
            )

        # Паспорт натальной карты из БД
        ctx = await get_user_astro_context(telegram_id)
        if not ctx:
            return web.json_response(
                {"status": "error", "message": "Сначала составь натальную карту"},
                status=404,
                headers=CORS_HEADERS
            )

        messages = build_ai_messages(ctx, topic, question)
        answer = await call_plusvibe(messages)

        # История чата — в БД
        await save_chat_message(telegram_id, "user", f"[{topic}] {question}")
        await save_chat_message(telegram_id, "assistant", answer)

        return web.json_response(
            {"status": "ok", "answer": answer},
            headers=CORS_HEADERS
        )
    except Exception as e:
        logging.exception("Ошибка ИИ-консультации:")
        return web.json_response(
            {"status": "error", "message": str(e)},
            status=500,
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
    app.router.add_route("OPTIONS", "/api/consult", handle_options)
    app.router.add_post("/api/consult", handle_consult_api)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 8080)
    await site.start()
    logging.info("API-сервер слушает http://127.0.0.1:8080/api/natal и http://127.0.0.1:8080/api/consult")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())