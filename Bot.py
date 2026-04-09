import os
import json
import re
import requests

TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
API_URL = f"https://api.telegram.org/bot{TOKEN}"
STATE_FILE = "state.json"

def load_state():
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"offset": 0, "users": {}}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def send_message(chat_id, text, reply_to=None, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(f"{API_URL}/sendMessage", json=payload)

def answer_callback(callback_id, text=None):
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
    requests.post(f"{API_URL}/answerCallbackQuery", json=payload)

def delete_message(chat_id, message_id):
    requests.post(f"{API_URL}/deleteMessage", json={"chat_id": chat_id, "message_id": message_id})

def has_url(text):
    url_pattern = re.compile(r'https?://\S+|www\.\S+')
    return bool(url_pattern.search(text))

def get_main_keyboard():
    return {
        "keyboard": [
            [{"text": "Включить"}, {"text": "Выключить"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

def main():
    state = load_state()
    offset = state.get("offset", 0)
    users = state.get("users", {})

    response = requests.get(f"{API_URL}/getUpdates", params={"offset": offset, "timeout": 30})
    updates = response.json().get("result", [])

    for upd in updates:
        update_id = upd["update_id"]
        offset = update_id + 1

        if "message" in upd:
            msg = upd["message"]
            chat_id = msg["chat"]["id"]
            user_id = str(msg["from"]["id"])
            text = msg.get("text", "")

            user_state = users.get(user_id, {"active": False, "text": "", "awaiting_text": False})

            # Команда /start или первое сообщение — показываем клавиатуру
            if text == "/start":
                send_message(chat_id, "Используйте кнопки для управления ботом.", reply_markup=get_main_keyboard())

            elif text == "/SOn" or text == "Включить":
                user_state["awaiting_text"] = True
                user_state["active"] = False
                users[user_id] = user_state
                send_message(chat_id, "Введите текст, который будет добавляться к вашим сообщениям:", reply_markup=get_main_keyboard())

            elif text == "/SOff" or text == "Выключить":
                user_state["active"] = False
                user_state["awaiting_text"] = False
                users[user_id] = user_state
                send_message(chat_id, "Режим изменения сообщений отключён.", reply_markup=get_main_keyboard())

            elif user_state.get("awaiting_text", False):
                user_state["text"] = text
                user_state["active"] = True
                user_state["awaiting_text"] = False
                users[user_id] = user_state
                send_message(chat_id, f"Текст сохранён: «{text}». Теперь все ваши сообщения будут дополняться им.", reply_markup=get_main_keyboard())

            elif user_state.get("active", False):
                new_text = f"{user_state['text']}\n{text}"
                if has_url(text):
                    keyboard = {
                        "inline_keyboard": [
                            [
                                {"text": "Да", "callback_data": f"mod_yes:{msg['message_id']}"},
                                {"text": "Нет", "callback_data": f"mod_no:{msg['message_id']}"}
                            ]
                        ]
                    }
                    send_message(chat_id, "В сообщении есть ссылка. Изменить его?", reply_to=msg["message_id"], reply_markup=keyboard)
                else:
                    send_message(chat_id, new_text, reply_to=msg["message_id"])

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
            user_state = users.get(user_id)

            if data.startswith("mod_yes:"):
                orig_msg_id = int(data.split(":")[1])
                if user_state and user_state.get("active"):
                    delete_message(chat_id, orig_msg_id)
                    send_message(chat_id, f"{user_state['text']}\n[содержимое удалено]")
                answer_callback(cb_id, "Сообщение изменено")

            elif data.startswith("mod_no:"):
                answer_callback(cb_id, "Изменение отменено")
                delete_message(chat_id, msg["message_id"])

    state["offset"] = offset
    state["users"] = users
    save_state(state)

if __name__ == "__main__":
    main()
