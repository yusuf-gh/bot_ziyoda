# Telegram Counter Bot (Aiogram v3)

## Что делает
- Автоматически проставляет порядковый номер каждому посту в канале:
  - Текст — редактирует текст, добавляя `#N` сверху
  - Фото/видео/док/гиф/аудио — редактирует caption
  - Альбомы — номер ставится на **первый элемент** группы
  - Типы без подписи (опросы и т.п.) — отправляет отдельное сообщение с номером

## Требования
- Python 3.10+
- Бот добавлен в канал как **админ** с правами *Can Post* и *Can Edit*
- Long polling (без вебхуков/хостинга)

## Установка
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # вставь свой BOT_TOKEN
python main.py