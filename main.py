# Бот-админ канала: ловит channel_post, добавляет порядковый номер.
# Поддерживает: текст, медиа (caption), альбомы (нумерует только первый элемент).
# Типы без подписи (poll/voice chat) — отправляем отдельным сообщением с номером.

import asyncio
import os
from collections import defaultdict
from pathlib import Path

from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ContentType
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message
from dotenv import load_dotenv

from storage import CounterStore

# --- ENV ---
load_dotenv()
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN не задан в .env")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- Счётчик ---
counter = CounterStore()

album_buffer: dict[str, list[tuple[int, int]]] = defaultdict(list)
album_flushing: set[str] = set() 


def prefix(n: int) -> str:
    return f"#{n}"


async def safe_edit_text(message: Message, new_text: str):
    try:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=message.message_id,
            text=new_text,
        )
    except TelegramBadRequest as e:
        print("edit_message_text:", e)
        await bot.send_message(chat_id=message.chat.id, text=new_text)

async def safe_edit_caption(message: Message, new_caption: str):
    try:
        await bot.edit_message_caption(
            chat_id=message.chat.id,
            message_id=message.message_id,
            caption=new_caption[:1024],  
        )
    except TelegramBadRequest as e:
        print("edit_message_caption:", e)
        await bot.send_message(chat_id=message.chat.id, text=new_caption.split("\n\n", 1)[0])

# --- Handlers ---

@dp.startup()
async def on_startup():
    await counter.init()
    print("Bot started. Counter ready.")

@dp.channel_post(F.media_group_id)  
async def on_album_part(message: Message):
    gid = message.media_group_id
    album_buffer[gid].append((message.chat.id, message.message_id))

    if gid not in album_flushing:
        album_flushing.add(gid)
        asyncio.create_task(flush_album_after_delay(gid))

async def flush_album_after_delay(gid: str):
    await asyncio.sleep(1.2)
    items = album_buffer.pop(gid, [])
    album_flushing.discard(gid)
    if not items:
        return

    items.sort(key=lambda x: x[1])
    first_chat_id, first_msg_id = items[0]
    n = await counter.next_number()
    cap = prefix(n)

    try:
        await bot.edit_message_caption(
            chat_id=first_chat_id,
            message_id=first_msg_id,
            caption=cap
        )
    except TelegramBadRequest as e:
        print("album edit error:", e)
        await bot.send_message(chat_id=first_chat_id, text=cap)

@dp.channel_post(~F.media_group_id) 
async def on_single_post(message: Message):
    n = await counter.next_number()
    head = prefix(n)
    double_nl = "\n\n"

    if message.content_type == ContentType.TEXT:
        new_text = f"{head}{double_nl}{message.text or ''}"
        await safe_edit_text(message, new_text)
        return

    # Медиа (caption-able)
    if message.content_type in {
        ContentType.PHOTO, ContentType.VIDEO, ContentType.DOCUMENT,
        ContentType.ANIMATION, ContentType.AUDIO, ContentType.VOICE, ContentType.VIDEO_NOTE
    }:
        new_caption = f"{head}{double_nl}{message.caption or ''}".strip()
        await safe_edit_caption(message, new_caption)
        return

    await bot.send_message(chat_id=message.chat.id, text=head)


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())