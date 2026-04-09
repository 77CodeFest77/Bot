#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import re
import sys
import traceback
from datetime import datetime
from typing import Dict, Any, Optional, List

import requests

# ---------- Конфигурация ----------
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    print("❌ Ошибка: TELEGRAM_BOT_TOKEN не задан!", file=sys.stderr)
    sys.exit(1)

API_URL = f"https://api.telegram.org/bot{TOKEN}"
STATE_FILE = "state.json"

# Сброс offset больше не требуется, бот уже получил все сообщения
RESET_OFFSET = False

URL_PATTERN = re.compile(r'(https?://\S+|www\.\S+|tg://\S+)', re.IGNORECASE)

EMOJI_ON = "🟢"
EMOJI_OFF = "🔴"
EMOJI_SETTINGS = "⚙️"
EMOJI_INFO = "ℹ️"
EMOJI_LINK = "🔗"
EMOJI_CHECK = "✅"
EMOJI_CROSS = "❌"

# ---------- Вспомогательные функции ----------
def log_error(message: str, exception: Optional[Exception] = None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    error_text = f"[{timestamp}] {message}"
    if exception:
        error_text += f"\n{traceback.format_exc()}"
    print(error_text, file=sys.stderr)

def api_request(method: str, params: Dict[str, Any] = None) -> Optional[Dict]:
    url = f"{API_URL}/{method}"
    try:
        resp = requests.post(url, json=params, timeout=30)
        data = resp.json()
        if not data.get("ok"):
            log_error(f"Telegram API error: {data.get('description')}")
            return None
        return data.get("result")
    except Exception as e:
        log_error(f"Request failed for {method}: {e}", e)
        return None

def load_state() -> Dict:
    default = {"offset": 0, "users": {}}
    if not os.path.exists(STATE_FILE):
        return default
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for key in default:
                if key not in data:
                    data[key] = default[key]
            return data
    except Exception as e:
        log_error(f"Failed to load state: {e}", e)
        return default

def save_state(state: Dict):
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log_error(f"Failed to save state: {e}", e)

def send_message(chat_id: int, text: str, reply_to: int = None, reply_markup: Dict = None, parse_mode: str = "HTML") -> Optional[Dict]:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    return api_request("sendMessage", payload)

def answer_callback(callback_id: str, text: str = None, show_alert: bool = False) -> bool:
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = show_alert
    return api_request("answerCallbackQuery", payload) is not None

def delete_message(chat_id: int, message_id: int) -> bool:
    return api_request("deleteMessage", {"chat_id": chat_id, "message_id": message_id}) is not None

def get_updates(offset: int, timeout: int = 25) -> List[Dict]:
    params = {"offset": offset, "timeout": timeout, "allowed_updates": ["message", "callback_query"]}
    return api_request("getUpdates", params) or []

# ---------- Клавиатуры ----------
def get_main_keyboard() -> Dict:
    return {
        "keyboard": [
            [{"text": f"{EMOJI_ON} Включить изменение"}, {"text": f"{EMOJI_OFF} Выключить"}],
            [{"text": f"{EMOJI_INFO} Статус"}, {"text": f"{EMOJI_SETTINGS} Сменить текст"}]
        ],
        "resize_keyboard": True
    }

def get_link_confirmation_keyboard(original_msg_id: int) -> Dict:
    return {
        "inline_keyboard": [
            [
                {"text": f"{EMOJI_CHECK} Да, изменить", "callback_data": f"mod_yes:{original_msg_id}"},
                {"text": f"{EMOJI_CROSS} Нет, отмена", "callback_data": f"mod_no:{original_msg_id}"}
            ]
        ]
    }

# ---------- Логика обработки ----------
def handle_start(chat_id: int, user_id: str, state: Dict):
    welcome = (
        f"{EMOJI_ON} <b>Бот для автозамены сообщений</b>\n\n"
        f"• {EMOJI_ON} <b>Включить изменение</b> — задать добавляемый текст.\n"
        f"• {EMOJI_OFF} <b>Выключить</b> — отключить режим.\n"
        f"• {EMOJI_INFO} <b>Статус</b> — текущий статус.\n"
        f"• {EMOJI_SETTINGS} <b>Сменить текст</b> — изменить добавляемую строку.\n\n"
        f"<i>При отправке ссылки бот запросит подтверждение.</i>"
    )
    send_message(chat_id, welcome, reply_markup=get_main_keyboard())
    state.setdefault("users", {}).setdefault(user_id, {"active": False, "text": "", "awaiting_text": False})

def process_update(upd: Dict, state: Dict):
    if "message" in upd:
        msg = upd["message"]
        if "text" not in msg:
            return
        chat_id = msg["chat"]["id"]
        user_id = str(msg["from"]["id"])
        text = msg["text"].strip()
        msg_id = msg["message_id"]

        users = state.setdefault("users", {})
        user = users.setdefault(user_id, {"active": False, "text": "", "awaiting_text": False})

        if text == "/start":
            handle_start(chat_id, user_id, state)
        elif text in ("/status", f"{EMOJI_INFO} Статус"):
            active = user.get("active", False)
            status_text = f"{EMOJI_ON if active else EMOJI_OFF} <b>Статус</b>\nАктивен: <b>{'Да' if active else 'Нет'}</b>"
            if active:
                status_text += f"\nТекст: <code>{user.get('text', '')}</code>"
            send_message(chat_id, status_text, reply_markup=get_main_keyboard())
        elif text in ("/enable", f"{EMOJI_ON} Включить изменение"):
            user["awaiting_text"] = True
            user["active"] = False
            send_message(chat_id, f"{EMOJI_SETTINGS} Введите текст для добавления:", reply_markup=get_main_keyboard())
        elif text in ("/disable", f"{EMOJI_OFF} Выключить"):
            user["active"] = False
            user["awaiting_text"] = False
            send_message(chat_id, f"{EMOJI_OFF} Режим изменения отключён.", reply_markup=get_main_keyboard())
        elif text in ("/change", f"{EMOJI_SETTINGS} Сменить текст"):
            user["awaiting_text"] = True
            user["active"] = False
            send_message(chat_id, f"{EMOJI_SETTINGS} Введите новый текст:", reply_markup=get_main_keyboard())
        elif user.get("awaiting_text", False):
            user["text"] = text
            user["active"] = True
            user["awaiting_text"] = False
            send_message(chat_id, f"{EMOJI_CHECK} Текст сохранён: <code>{text}</code>", reply_markup=get_main_keyboard())
        elif user.get("active", False):
            prefix = user.get("text", "")
            if prefix:
                new_text = f"{prefix}\n{text}"
                if URL_PATTERN.search(text):
                    user["last_original_text"] = text
                    user["last_original_msg_id"] = msg_id
                    kb = get_link_confirmation_keyboard(msg_id)
                    send_message(chat_id, f"{EMOJI_LINK} Обнаружена ссылка. Изменить сообщение?", reply_to=msg_id, reply_markup=kb)
                else:
                    send_message(chat_id, new_text, reply_to=msg_id)

    elif "callback_query" in upd:
        cb = upd["callback_query"]
        cb_id = cb["id"]
        data = cb["data"]
        msg = cb.get("message")
        if not msg:
            answer_callback(cb_id)
            return
        chat_id = msg["chat"]["id"]
        user_id = str(cb["from"]["id"])
        cb_msg_id = msg["message_id"]

        users = state.get("users", {})
        user = users.get(user_id, {})

        if data.startswith("mod_yes:"):
            try:
                orig_msg_id = int(data.split(":")[1])
            except:
                answer_callback(cb_id, "Ошибка данных", show_alert=True)
                return
            if user.get("active") and "last_original_text" in user:
                prefix = user.get("text", "")
                orig_text = user["last_original_text"]
                new_text = f"{prefix}\n{orig_text}"
                delete_message(chat_id, orig_msg_id)
                send_message(chat_id, new_text)
                answer_callback(cb_id, "Сообщение изменено!")
                user.pop("last_original_text", None)
                user.pop("last_original_msg_id", None)
            else:
                answer_callback(cb_id, "Нет данных для изменения", show_alert=True)
        elif data.startswith("mod_no:"):
            delete_message(chat_id, cb_msg_id)
            answer_callback(cb_id, "Изменение отменено")

# ---------- Главный цикл ----------
def main():
    print(f"🚀 Bot started at {datetime.now().isoformat()}")
    state = load_state()

    if RESET_OFFSET:
        print("⚠️ Сброс offset = 0 (однократно)")
        state["offset"] = 0

    offset_before = state.get("offset", 0)
    updates = get_updates(offset_before, timeout=20)
    print(f"📬 Получено обновлений: {len(updates)} (offset был {offset_before})")

    for upd in updates:
        try:
            process_update(upd, state)
            state["offset"] = max(state["offset"], upd["update_id"] + 1)
        except Exception as e:
            log_error(f"Ошибка обработки update {upd.get('update_id')}: {e}", e)

    save_state(state)
    print(f"✅ Бот завершён. Новый offset = {state.get('offset')}")

if __name__ == "__main__":
    main()
