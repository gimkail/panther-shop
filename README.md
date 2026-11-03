# Пантера по выезду — сайт и Telegram-уведомления

Одностраничный магазин на Python (стандартная библиотека) + отправка заказов
в Telegram. Разворачивается на бесплатном тарифе Render.

## Локальный запуск

```powershell
python server.py
```

Откройте http://localhost:8000/shop.html

Для уведомлений заполните `telegram_config.json` (в репозиторий его не кладём)
или задайте переменные окружения:

- `TELEGRAM_BOT_TOKEN` — токен от @BotFather;
- `TELEGRAM_CHAT_ID` — ваш chat_id.

## Деплой на Render

1. Создайте репозиторий на GitHub и загрузите содержимое этой папки.
2. На https://dashboard.render.com нажмите **New + → Blueprint**.
3. Выберите репозиторий — Render прочитает `render.yaml`.
4. Нажмите **Apply**. После первого деплоя откройте сервис → **Environment**
   и добавьте секреты:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
5. Нажмите **Manual Deploy → Deploy latest commit**.

Сайт будет доступен по адресу вида `https://panther-shop.onrender.com/shop.html`.

## Важно

- Бесплатный Render «засыпает» после ~15 минут без запросов; первый заказ
  после сна может открываться дольше обычного.
- Токен бота храните только в Environment Variables, не в коде и не в Git.
- `telegram_config.json` добавлен в `.gitignore`.
