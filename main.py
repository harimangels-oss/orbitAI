import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    ReplyKeyboardRemove
)

BOT_TOKEN = "8434981608:AAEZ0V7P4tlXnOHJJcBUiSP0cj6Zth3m74w"
WEBAPP_URL = "https://peppy-pika-ec901d.netlify.app"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

WELCOME_TEXT = (
    "Получи бесплатный разбор твоей натальной карты ✨\n\n"
    "- ИИ составит твою личную натальную карту.\n"
    "- На основе вашей натальной карты проконсультирует вас по выбранному запросу.\n"
    "- В конце поделись своими впечатлениями и получи подарок."
)

@dp.message(CommandStart())
async def cmd_start(message: Message):
    # Создаём кнопку прямо под сообщением с картинкой
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
    await message.answer_photo(
        photo=photo,
        caption=WELCOME_TEXT,
        reply_markup=kb
    )

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())