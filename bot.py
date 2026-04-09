import telebot
from telebot import types
import re
import os

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

# Данные пользователей
user_data = {}

# Набор "шрифтов" (Unicode-преобразователи)
FONTS = {
    "Обычный": lambda t: t,
    "Жирный (Eng)": lambda t: "".join([chr(ord(c) + 120211) if 'a' <= c <= 'z' else chr(ord(c) + 120205) if 'A' <= c <= 'Z' else c for c in t]),
    "Курсив (Eng)": lambda t: "".join([chr(ord(c) + 120263) if 'a' <= c <= 'z' else chr(ord(c) + 120257) if 'A' <= c <= 'Z' else c for c in t]),
    "Готический": lambda t: "".join([chr(ord(c) + 120081) if 'a' <= c <= 'z' else chr(ord(c) + 120075) if 'A' <= c <= 'Z' else c for c in t]),
    "Двойной": lambda t: "".join([chr(ord(c) + 120133) if 'a' <= c <= 'z' else chr(ord(c) + 120127) if 'A' <= c <= 'Z' else c for c in t]),
    "Кружочки": lambda t: "".join([chr(ord(c) + 9327) if 'a' <= c <= 'z' else chr(ord(c) + 9333) if 'A' <= c <= 'Z' else c for c in t]),
    "Моно": lambda t: f"`{t}`"
}

def get_main_panel():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add('📝 Установить текст', '👀 Мой текст', '🎨 Выбрать шрифт')
    return markup

def get_fonts_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    for name in FONTS.keys():
        markup.add(types.InlineKeyboardButton(text=name, callback_data=f"font_{name}"))
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Бот готов! Используй панель:", reply_markup=get_main_panel())

@bot.message_handler(func=lambda m: m.text == '🎨 Выбрать шрифт')
def show_fonts(message):
    bot.send_message(message.chat.id, "Выбери стиль текста для ссылок:", reply_markup=get_fonts_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith('font_'))
def handle_font_selection(call):
    font_name = call.data.replace('font_', '')
    user_id = call.message.chat.id
    
    if user_id not in user_data: user_data[user_id] = {'text': '', 'font': 'Обычный'}
    user_data[user_id]['font'] = font_name
    
    example = FONTS[font_name]("BsHelper Пример текста")
    bot.edit_message_text(f"Выбран шрифт: *{font_name}*\nПример: {example}", 
                          call.message.chat.id, call.message.message_id, 
                          parse_mode="Markdown", reply_markup=get_fonts_keyboard())

@bot.message_handler(func=lambda m: m.text == '📝 Установить текст')
def set_text(message):
    msg = bot.send_message(message.chat.id, "Пришли базовый текст:", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, save_text)

def save_text(message):
    user_id = message.chat.id
    if user_id not in user_data: user_data[user_id] = {'text': '', 'font': 'Обычный'}
    user_data[user_id]['text'] = message.text
    bot.send_message(user_id, "✅ Текст сохранен!", reply_markup=get_main_panel())

@bot.message_handler(func=lambda m: m.text == '👀 Мой текст')
def my_text(message):
    data = user_data.get(message.chat.id, {'text': 'Не установлен', 'font': 'Обычный'})
    text = FONTS[data['font']](data['text'])
    bot.send_message(message.chat.id, f"Твой текущий шаблон:\n\n{text}")

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    urls = re.findall(r'(https?://\S+)', message.text)
    if urls:
        data = user_data.get(message.chat.id)
        if not data or not data['text']:
            bot.send_message(message.chat.id, "⚠️ Сначала установи текст!")
            return
        
        # Применяем шрифт к тексту
        styled_text = FONTS[data['font']](data['text'])
        final_msg = f"{styled_text}\n{urls[0]}"
        
        try: bot.delete_message(message.chat.id, message.message_id)
        except: pass
        bot.send_message(message.chat.id, final_msg)

bot.polling(none_stop=True)
