#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import re
import sys
import time
import traceback
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

import requests

# ---------- Конфигурация ----------
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    print("❌ Ошибка: TELEGRAM_BOT_TOKEN не задан!", file=sys.stderr)
    sys.exit(1)

API_URL = f"https://api.telegram.org/bot{TOKEN}"
STATE_FILE = "state.json"
LOG_FILE = "bot_errors.log"  # Для локальной отладки, в Actions можно выводить в stdout

# URL-регулярка (упрощённая, но охватывает основные случаи)
URL_PATTERN = re.compile(r'(https?://\S+|www\.\S+|tg://\S+)', re.IGNORECASE)

# Эмодзи для клавиатуры
EMOJI_ON = "🟢"
EMOJI_OFF = "🔴"
EMOJI_SETTINGS = "⚙️"
EMOJI_INFO = "ℹ️"
EMOJI_LINK = "🔗"
EMOJI_CHECK = "✅"
EMOJI_CROSS = "❌"

# ---------- Вспомогательные функции ----------
def log_error(message: str, exception: Optional[Exception] = None):
    """Запись ошибки в лог (вывод в stderr для GitHub Actions)."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    error_text = f"[{timestamp}] {message}"
    if exception:
        error_text += f"\n{traceback.format_exc()}"
    print(error_text, file=sys.stderr)
    # Опционально писать в файл, если нужно
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(error_text + "\n")
    except:
        pass

def api_request(method: str, params: Dict[str, Any] = None, files: Dict = None) -> Optional[Dict]:
    """Выполнение запроса к Telegram API с обработкой ошибок."""
    url = f"{API_URL}/{method}"
    try:
        if files:
            resp = requests.post(url, data=params, files=files, timeout=30)
        else:
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
    """Загрузка состояния из файла."""
    default = {
        "offset": 0,
        "users": {},
        "last_update_id": 0,
        "processed_updates": []  # для дебага
    }
    if not os.path.exists(STATE_FILE):
        return default
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Убедимся, что все ключи есть
            for key in default:
                if key not in data:
                    data[key] = default[key]
            return data
    except Exception as e:
        log_error(f"Failed to load state: {e}", e)
        return default

def save_state(state: Dict):
    """Сохранение состояния в файл."""
    try:
        # Ограничим размер processed_updates (опционально)
        if len(state.get("processed_updates", [])) > 100:
            state["processed_updates"] = state["processed_updates"][-50:]
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log_error(f"Failed to save state: {e}", e)

def send_message(chat_id: int, text: str, reply_to: int = None, reply_markup: Dict = None, parse_mode: str = "HTML") -> Optional[Dict]:
    """Отправка сообщения."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True  # чтобы ссылки не мешали
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    return api_request("sendMessage", payload)

def edit_message_text(chat_id: int, message_id: int, text: str, reply_markup: Dict = None, parse_mode: str = "HTML") -> Optional[Dict]:
    """Редактирование текста сообщения."""
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    return api_request("editMessageText", payload)

def answer_callback(callback_id: str, text: str = None, show_alert: bool = False) -> bool:
    """Ответ на callback query."""
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = show_alert
    result = api_request("answerCallbackQuery", payload)
    return result is not None

def delete_message(chat_id: int, message_id: int) -> bool:
    """Удаление сообщения."""
    payload = {"chat_id": chat_id, "message_id": message_id}
    result = api_request("deleteMessage", payload)
    return result is not None

def get_updates(offset: int, timeout: int = 30) -> List[Dict]:
    """Получение обновлений с увеличенным таймаутом."""
    params = {"offset": offset, "timeout": timeout, "allowed_updates": ["message", "callback_query"]}
    return api_request("getUpdates", params) or []

# ---------- Клавиатуры ----------
def get_main_keyboard() -> Dict:
    """Основная Reply-клавиатура с красивыми эмодзи."""
    return {
        "keyboard": [
            [
                {"text": f"{EMOJI_ON} Включить изменение"},
                {"text": f"{EMOJI_OFF} Выключить"}
            ],
            [
                {"text": f"{EMOJI_INFO} Статус"},
                {"text": f"{EMOJI_SETTINGS} Сменить текст"}
            ]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

def get_link_confirmation_keyboard(original_msg_id: int) -> Dict:
    """Инлайн-клавиатура для подтверждения изменения ссылки."""
    return {
        "inline_keyboard": [
            [
                {"text": f"{EMOJI_CHECK} Да, изменить", "callback_data": f"mod_yes:{original_msg_id}"},
                {"text": f"{EMOJI_CROSS} Нет, отмена", "callback_data": f"mod_no:{original_msg_id}"}
            ]
        ]
    }

def get_remove_keyboard_markup() -> Dict:
    """Клавиатура для удаления основной (пустая)."""
    return {"remove_keyboard": True}

# ---------- Обработчики команд и сообщений ----------
def handle_start(chat_id: int, user_id: str, state: Dict):
    """Обработка /start."""
    welcome_text = (
        f"{EMOJI_ON} <b>Бот для автозамены сообщений</b>\n\n"
        f"Используйте кнопки ниже для управления:\n"
        f"• {EMOJI_ON} <b>Включить изменение</b> — ввести текст, который будет добавляться к каждому вашему сообщению.\n"
        f"• {EMOJI_OFF} <b>Выключить</b> — отключить режим изменения.\n"
        f"• {EMOJI_INFO} <b>Статус</b> — показать текущий статус.\n"
        f"• {EMOJI_SETTINGS} <b>Сменить текст</b> — задать новый добавляемый текст.\n\n"
        f"<i>При отправке ссылки бот запросит подтверждение на изменение.</i>"
    )
    send_message(chat_id, welcome_text, reply_markup=get_main_keyboard())

    # Инициализация состояния пользователя, если нет
    users = state.setdefault("users", {})
    if user_id not in users:
        users[user_id] = {
            "active": False,
            "text": "",
            "awaiting_text": False,
            "last_action": datetime.now().isoformat()
        }

def handle_status(chat_id: int, user_id: str, state: Dict):
    """Показать текущий статус пользователя."""
    users = state.get("users", {})
    user = users.get(user_id, {})
    active = user.get("active", False)
    text = user.get("text", "не задан")
    status_emoji = EMOJI_ON if active else EMOJI_OFF
    status_text = f"{status_emoji} <b>Статус бота</b>\n\n"
    status_text += f"Активен: <b>{'Да' if active else 'Нет'}</b>\n"
    if active:
        status_text += f"Добавляемый текст: <code>{text}</code>\n"
    send_message(chat_id, status_text, reply_markup=get_main_keyboard())

def handle_enable(chat_id: int, user_id: str, state: Dict):
    """Активировать режим ожидания ввода текста."""
    users = state.get("users", {})
    user = users.setdefault(user_id, {"active": False, "text": "", "awaiting_text": False})
    user["awaiting_text"] = True
    user["active"] = False
    prompt = f"{EMOJI_SETTINGS} Введите текст, который будет добавляться <b>перед</b> каждым вашим сообщением.\n\nПример: <code>Важно!</code>"
    send_message(chat_id, prompt, reply_markup=get_main_keyboard())

def handle_disable(chat_id: int, user_id: str, state: Dict):
    """Отключить режим изменения."""
    users = state.get("users", {})
    user = users.setdefault(user_id, {"active": False, "text": "", "awaiting_text": False})
    user["active"] = False
    user["awaiting_text"] = False
    send_message(chat_id, f"{EMOJI_OFF} Режим изменения сообщений <b>отключён</b>.", reply_markup=get_main_keyboard())

def handle_change_text(chat_id: int, user_id: str, state: Dict):
    """Принудительно запросить новый текст."""
    users = state.get("users", {})
    user = users.setdefault(user_id, {"active": False, "text": "", "awaiting_text": False})
    user["awaiting_text"] = True
    user["active"] = False
    send_message(chat_id, f"{EMOJI_SETTINGS} Введите <b>новый текст</b> для добавления:", reply_markup=get_main_keyboard())

def handle_new_text(chat_id: int, user_id: str, text: str, state: Dict):
    """Сохранение введённого текста."""
    users = state.get("users", {})
    user = users.setdefault(user_id, {"active": False, "text": "", "awaiting_text": False})
    user["text"] = text.strip()
    user["active"] = True
    user["awaiting_text"] = False
    confirmation = (
        f"{EMOJI_CHECK} Текст сохранён:\n"
        f"<code>{user['text']}</code>\n\n"
        f"Теперь все ваши сообщения будут начинаться с этой строки."
    )
    send_message(chat_id, confirmation, reply_markup=get_main_keyboard())

def process_message_with_modification(chat_id: int, user_id: str, message_id: int, original_text: str, state: Dict):
    """Обработка обычного сообщения в активном режиме."""
    users = state.get("users", {})
    user = users.get(user_id, {})
    if not user.get("active", False):
        return False  # не активно

    prefix = user.get("text", "")
    if not prefix:
        # Если текст пуст, но активен — не изменяем
        return False

    new_text = f"{prefix}\n{original_text}"

    # Проверяем наличие ссылок
    if URL_PATTERN.search(original_text):
        # Запрашиваем подтверждение через инлайн-кнопки
        keyboard = get_link_confirmation_keyboard(message_id)
        # Сохраняем во временное хранилище оригинальный текст? Но callback_data ограничен 64 байтами.
        # Передадим только message_id, текст брать неоткуда, поэтому при подтверждении просто отправим новое сообщение с префиксом.
        # Лучше сохранить оригинальный текст в состоянии пользователя временно.
        user["last_original_text"] = original_text
        user["last_original_msg_id"] = message_id
        state["users"][user_id] = user

        prompt = f"{EMOJI_LINK} В сообщении обнаружена ссылка. Изменить сообщение, добавив ваш текст?"
        send_message(chat_id, prompt, reply_to=message_id, reply_markup=keyboard)
        return True
    else:
        # Отправляем новое сообщение с префиксом (в ответ)
        send_message(chat_id, new_text, reply_to=message_id)
        # Удалять оригинал не будем, это не запрошено
        return True

def process_callback_yes(chat_id: int, user_id: str, original_msg_id: int, callback_id: str, state: Dict):
    """Подтверждение изменения сообщения со ссылкой."""
    users = state.get("users", {})
    user = users.get(user_id, {})
    if not user.get("active", False):
        answer_callback(callback_id, "Режим изменения не активен", show_alert=True)
        return

    prefix = user.get("text", "")
    original_text = user.get("last_original_text", "")
    if not prefix or not original_text:
        answer_callback(callback_id, "Ошибка: отсутствует текст для изменения", show_alert=True)
        return

    new_text = f"{prefix}\n{original_text}"
    # Удаляем оригинальное сообщение
    delete_message(chat_id, original_msg_id)
    # Отправляем новое сообщение с префиксом
    send_message(chat_id, new_text)
    answer_callback(callback_id, "Сообщение изменено!")

    # Очищаем временные данные
    user.pop("last_original_text", None)
    user.pop("last_original_msg_id", None)
    state["users"][user_id] = user

def process_callback_no(chat_id: int, callback_query_msg_id: int, callback_id: str, state: Dict):
    """Отмена изменения."""
    # Удаляем сообщение с запросом подтверждения
    delete_message(chat_id, callback_query_msg_id)
    answer_callback(callback_id, "Изменение отменено")

# ---------- Основной цикл обработки обновлений ----------
def process_updates(state: Dict) -> bool:
    """Обработка всех новых обновлений. Возвращает True, если были обновления."""
    offset = state.get("offset", 0)
    updates = get_updates(offset, timeout=25)  # чуть меньше, чем таймаут GitHub Actions шага

    if not updates:
        return False

    for upd in updates:
        update_id = upd["update_id"]
        # Обновляем offset на следующий
        state["offset"] = max(state["offset"], update_id + 1)

        # Логируем для отладки (можно убрать)
        state.setdefault("processed_updates", []).append({
            "update_id": update_id,
            "timestamp": datetime.now().isoformat()
        })

        try:
            if "message" in upd:
                msg = upd["message"]
                # Пропускаем сообщения без текста (стикеры, фото и т.д.)
                if "text" not in msg:
                    continue

                chat_id = msg["chat"]["id"]
                user_id = str(msg["from"]["id"])
                text = msg["text"].strip()
                message_id = msg["message_id"]

                # Загружаем пользователя из состояния
                users = state.setdefault("users", {})
                user = users.setdefault(user_id, {
                    "active": False,
                    "text": "",
                    "awaiting_text": False
                })

                # Обработка команд и кнопок
                if text == "/start":
                    handle_start(chat_id, user_id, state)

                elif text == "/status" or text == f"{EMOJI_INFO} Статус":
                    handle_status(chat_id, user_id, state)

                elif text == "/enable" or text == f"{EMOJI_ON} Включить изменение":
                    handle_enable(chat_id, user_id, state)

                elif text == "/disable" or text == f"{EMOJI_OFF} Выключить":
                    handle_disable(chat_id, user_id, state)

                elif text == "/change" or text == f"{EMOJI_SETTINGS} Сменить текст":
                    handle_change_text(chat_id, user_id, state)

                elif user.get("awaiting_text", False):
                    # Ожидание ввода нового текста
                    handle_new_text(chat_id, user_id, text, state)

                else:
                    # Обычное сообщение — если активен, модифицируем
                    if user.get("active", False):
                        process_message_with_modification(chat_id, user_id, message_id, text, state)

            elif "callback_query" in upd:
                cb = upd["callback_query"]
                cb_id = cb["id"]
                data = cb["data"]
                msg = cb.get("message")
                if not msg:
                    answer_callback(cb_id)
                    continue

                chat_id = msg["chat"]["id"]
                user_id = str(cb["from"]["id"])
                callback_msg_id = msg["message_id"]

                if data.startswith("mod_yes:"):
                    try:
                        original_msg_id = int(data.split(":")[1])
                    except:
                        answer_callback(cb_id, "Ошибка данных", show_alert=True)
                        continue
                    process_callback_yes(chat_id, user_id, original_msg_id, cb_id, state)

                elif data.startswith("mod_no:"):
                    process_callback_no(chat_id, callback_msg_id, cb_id, state)

                else:
                    answer_callback(cb_id, "Неизвестная команда")

        except Exception as e:
            log_error(f"Error processing update {update_id}: {e}", e)
            # Попытка ответить пользователю об ошибке (если есть chat_id)
            # Не всегда возможно определить chat_id, поэтому пропускаем

    return True

# ---------- Точка входа ----------
def main():
    print(f"🚀 Bot started at {datetime.now().isoformat()}")
    state = load_state()
    # Принудительно сбросим offset, если нужно перехватить все сообщения после долгого простоя
    # Но лучше использовать существующий offset
    # Для отладки можно раскомментировать:
    # state["offset"] = 0

    try:
        has_updates = process_updates(state)
        if not has_updates:
            print("No new updates.")
    except Exception as e:
        log_error("Fatal error in main loop", e)
    finally:
        save_state(state)
        print(f"✅ Bot finished at {datetime.now().isoformat()}")

if __name__ == "__main__":
    main()
