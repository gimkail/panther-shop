#!/usr/bin/env python3
"""Мини-сервер сайта с уведомлениями о заказах в Telegram.

Запуск:
    python server.py

Сайт:
    http://localhost:8000/shop.html

Настройка Telegram:
    заполните token и chat_id в telegram_config.json
    (подробности — в TELEGRAM.md).
"""

import html
import json
import os
import random
import re
import sys
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
SITE_DIR = ROOT / "site"
CONFIG_PATH = ROOT / "telegram_config.json"
DEFAULT_API_BASE = "https://api.telegram.org"


class NotConfigured(RuntimeError):
    """Telegram ещё не настроен."""


def load_telegram_config():
    """Читает токен и chat_id из переменных окружения или telegram_config.json."""
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()

    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Не удалось прочитать telegram_config.json: {exc}") from exc

        if isinstance(cfg, dict):
            token = token or str(cfg.get("token") or "").strip()
            chat_id = chat_id or str(cfg.get("chat_id") or "").strip()

    return token, chat_id


def send_telegram(text):
    token, chat_id = load_telegram_config()
    if not token or ":" not in token or not chat_id:
        raise NotConfigured(
            "Telegram не настроен: заполните token и chat_id в telegram_config.json "
            "и перезапустите сервер."
        )

    api_base = (os.environ.get("TELEGRAM_API_BASE") or DEFAULT_API_BASE).rstrip("/")
    url = f"{api_base}/bot{token}/sendMessage"
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=15) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = ""
        try:
            body = json.loads(exc.read().decode("utf-8"))
            detail = body.get("description") or ""
        except Exception:
            pass
        raise RuntimeError(f"Telegram отклонил сообщение: {detail or exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Нет связи с Telegram: {exc.reason}") from exc

    if not body.get("ok"):
        raise RuntimeError(body.get("description") or "Telegram вернул ошибку")


def rubles(amount):
    return f"{amount:,}".replace(",", " ") + " ₽"


USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


def normalize_username(value):
    raw = str(value or "").strip().lstrip("@")
    return "@" + raw if USERNAME_RE.fullmatch(raw) else ""


def build_message(order_id, items, total, username):
    handle = username.lstrip("@")
    lines = [
        f"🟣 <b>Новый заказ {order_id}</b>",
        f"🕒 {datetime.now():%d.%m.%Y %H:%M}",
        f'👤 Связаться: <a href="https://t.me/{html.escape(handle, quote=True)}">{html.escape(username)}</a>',
        "",
    ]
    for name, qty, price in items:
        safe_name = html.escape(name, quote=False)
        lines.append(f"• {safe_name} × {qty} — {rubles(qty * price)}")
    lines += ["", f"<b>Итого: {rubles(total)}</b>"]
    return "\n".join(lines)


def parse_order(data):
    """Проверяет заказ и возвращает позиции, сумму и Telegram-юзернейм."""
    if not isinstance(data, dict):
        raise ValueError("Неверный формат заказа")

    username = normalize_username(data.get("username"))
    if not username:
        raise ValueError(
            "Укажите корректный Telegram-юзернейм: 5–32 символа, буквы, цифры и _"
        )

    raw_items = data.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Корзина пуста")
    if len(raw_items) > 50:
        raise ValueError("Слишком много позиций в заказе")

    items = []
    total = 0
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ValueError("Неверная позиция заказа")

        name = str(raw.get("name") or "").strip()
        qty = raw.get("qty")
        price = raw.get("price")

        if not name or len(name) > 120:
            raise ValueError("Неверное название товара")
        if isinstance(qty, bool) or not isinstance(qty, int) or not 1 <= qty <= 99:
            raise ValueError("Неверное количество товара")
        if isinstance(price, bool) or not isinstance(price, int) or not 0 <= price <= 1_000_000:
            raise ValueError("Неверная цена товара")

        items.append((name, qty, price))
        total += qty * price

    return items, total, username


class SiteHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE_DIR), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        # Корень ведёт на магазин, а не на старую страницу index.html.
        if self.path.split("?")[0] in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/shop.html")
            self.end_headers()
            return
        super().do_GET()

    def do_POST(self):
        if self.path.split("?")[0] != "/api/order":
            self.send_json(404, {"ok": False, "error": "Страница не найдена"})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > 50_000:
            self.send_json(400, {"ok": False, "error": "Пустой или слишком большой запрос"})
            return

        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            items, total, username = parse_order(data)
        except (ValueError, UnicodeDecodeError) as exc:
            self.send_json(400, {"ok": False, "error": str(exc)})
            return

        order_id = "VP-" + str(random.randint(1000, 99999))
        message = build_message(order_id, items, total, username)

        try:
            send_telegram(message)
        except NotConfigured as exc:
            print(f"[order] {order_id}: Telegram is not configured", flush=True)
            self.send_json(503, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:
            print(f"[order] {order_id}: Telegram error: {exc}", flush=True)
            self.send_json(502, {"ok": False, "error": str(exc)})
            return

        print(
            f"[order] {order_id}: sent to Telegram, total={total}, items={len(items)}",
            flush=True,
        )
        self.send_json(200, {"ok": True, "orderId": order_id, "total": total})

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Не засоряем консоль строкой на каждый запрос.
        pass


def main():
    host = os.environ.get("HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("PORT", "8000"))
    except ValueError:
        print("PORT должен быть числом", file=sys.stderr)
        return 1

    server = ThreadingHTTPServer((host, port), SiteHandler)

    try:
        token, chat_id = load_telegram_config()
        configured = bool(token and ":" in token and chat_id)
    except Exception as exc:
        configured = False
        print(f"[config] {exc}", flush=True)

    print(f"Site: http://{host}:{port}/shop.html", flush=True)
    print(
        "Telegram: " + ("configured" if configured else "NOT configured (see TELEGRAM.md)"),
        flush=True,
    )
    print("Press Ctrl+C to stop.", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
