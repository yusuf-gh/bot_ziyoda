# Бот-посредник: принимает ЛС от владельца и публикует в канал СРАЗУ с номером
# Поддержка: текст, одиночное медиа (photo/video/document/animation/audio), альбомы (caption у первого элемента)

import asyncio
import os
import logging
from collections import defaultdict

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ContentType
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, InputMediaPhoto, InputMediaVideo
from dotenv import load_dotenv

from storage import CounterStore

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")

# --- ENV ---
load_dotenv()
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")  # -100xxxxxxxxxx или @public_channel
OWNER_ID = os.environ.get("OWNER_ID")      # Telegram ID владельца (число)
OWNERS = os.environ.get("OWNERS")          # список id через запятую

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN не задан в .env")
if not CHANNEL_ID:
    raise SystemExit("CHANNEL_ID не задан в .env")

ADMIN_IDS: set[str] = set()
if OWNERS:
    ADMIN_IDS = {s.strip() for s in OWNERS.replace(';', ',').split(',') if s.strip().isdigit()}
elif OWNER_ID:
    # обратная совместимость с единичным владельцем
    try:
        ADMIN_IDS = {str(int(OWNER_ID))}
    except Exception:
        ADMIN_IDS = set()

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- Счётчик ---
counter = CounterStore()

# --- Утилиты ---

def is_admin(message: Message) -> bool:
    """Публиковать могут только id из ADMIN_IDS. Если список пуст — отклоняем."""
    if not ADMIN_IDS:
        return False
    return str(message.from_user.id) in ADMIN_IDS

async def send_numbered_text_to_channel(n: int, text: str):
    head = f"№{n}\n\n"
    await bot.send_message(chat_id=CHANNEL_ID, text=head + (text or ""))

async def send_numbered_media_to_channel(n: int, message: Message):
    head = f"№{n}\n\n"
    caption_src = message.caption or ""
    cap = (head + caption_src)[:1024]

    ct = message.content_type
    if ct == ContentType.PHOTO:
        await bot.send_photo(CHANNEL_ID, photo=message.photo[-1].file_id, caption=cap)
    elif ct == ContentType.VIDEO:
        await bot.send_video(CHANNEL_ID, video=message.video.file_id, caption=cap)
    elif ct == ContentType.DOCUMENT:
        await bot.send_document(CHANNEL_ID, document=message.document.file_id, caption=cap)
    elif ct == ContentType.ANIMATION:
        await bot.send_animation(CHANNEL_ID, animation=message.animation.file_id, caption=cap)
    elif ct == ContentType.AUDIO:
        await bot.send_audio(CHANNEL_ID, audio=message.audio.file_id, caption=cap)
    else:
        await bot.send_message(CHANNEL_ID, text=f"№{n}")

# --- Альбомы (media group) буфер ---
album_buf: dict[str, list[Message]] = defaultdict(list)
album_flush: set[str] = set()

async def flush_album(gid: str):
    await asyncio.sleep(1.2)  # дождаться всех частей альбома
    msgs = album_buf.pop(gid, [])
    album_flush.discard(gid)
    if not msgs:
        return

    msgs.sort(key=lambda m: m.message_id)
    n = await counter.next_number()

    media = []
    for i, m in enumerate(msgs):
        cap = (f"№{n}\n\n{m.caption or ''}" if i == 0 else None)
        if m.content_type == ContentType.PHOTO:
            media.append(InputMediaPhoto(media=m.photo[-1].file_id, caption=(cap[:1024] if cap else None)))
        elif m.content_type == ContentType.VIDEO:
            media.append(InputMediaVideo(media=m.video.file_id, caption=(cap[:1024] if cap else None)))
        # Прочие типы альбомами не отправляем — Telegram ограничивает типы media group

    if media:
        await bot.send_media_group(chat_id=CHANNEL_ID, media=media)

# --- Startup ---
@dp.startup()
async def on_startup():
    await counter.init()
    try:
        for admin_id in ADMIN_IDS:
            await bot.send_message(admin_id, "Бот запущен. Готов публиковать в канал с нумерацией.")
    except TelegramBadRequest:
        pass
    logging.info("Bot started. Counter ready.")

# --- DM handlers ---
@dp.message(F.chat.type == "private", F.text)
async def dm_text(message: Message):
    if not is_admin(message):
        return await message.answer("Недостаточно прав.")
    n = await counter.next_number()
    await send_numbered_text_to_channel(n, message.text)
    await message.answer(f"Ок, отправил в канал №{n}")

@dp.message(F.chat.type == "private", ~F.media_group_id, F.content_type.in_({
    ContentType.PHOTO, ContentType.VIDEO, ContentType.DOCUMENT,
    ContentType.ANIMATION, ContentType.AUDIO
}))
async def dm_single_media(message: Message):
    if not is_admin(message):
        return await message.answer("Недостаточно прав.")
    n = await counter.next_number()
    await send_numbered_media_to_channel(n, message)
    await message.answer(f"Ок, отправил в канал №{n}")

@dp.message(F.chat.type == "private", F.media_group_id)
async def dm_album_part(message: Message):
    if not is_admin(message):
        return await message.answer("Недостаточно прав.")
    gid = message.media_group_id
    album_buf[gid].append(message)
    if gid not in album_flush:
        album_flush.add(gid)
        asyncio.create_task(flush_album(gid))

@dp.message(F.chat.type == "private", F.text.startswith("/start"))
async def dm_start(message: Message):
    await message.answer(
        "Я публикую в канал с нумерацией.\n"
        "Пришли текст/медиа/альбом — я отправлю как пост.\n"
        "Команды: /status, /set <N> (доступно администраторам)"
    )

@dp.message(F.chat.type == "private", F.text.startswith("/status"))
async def dm_status(message: Message):
    if not is_admin(message):
        return await message.answer("Недостаточно прав.")
    await message.answer("Бот запущен. Готов публиковать.")

@dp.message(F.chat.type == "private", F.text.startswith("/admins"))
async def dm_admins(message: Message):
    if not is_admin(message):
        return await message.answer("Недостаточно прав.")
    ids = ", ".join(sorted(ADMIN_IDS)) or "<пусто>"
    await message.answer(f"Администраторы: {ids}")

@dp.message(F.chat.type == "private")
async def dm_set_or_fallback(message: Message):
    # Обрабатываем /set <N> и все прочие нераспознанные DM
    if message.text and message.text.startswith("/set "):
        if not is_admin(message):
            return await message.answer("Недостаточно прав.")
        arg = message.text.split(maxsplit=1)[1].strip()
        if arg.isdigit():
            new_n = int(arg)
            await counter.set_number(new_n)
            return await message.answer(f"Ок, установлен номер на {new_n}")
        return await message.answer("Использование: /set 123")
    await message.answer("Пришли текст/медиа/альбом — я отправлю в канал с номером.")

# --- Entry point ---
async def main():
    # На случай, если раньше стоял вебхук
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())