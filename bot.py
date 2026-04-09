import telebot
from telebot import types
import re
import os

# Получаем токен из секретов GitHub
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

# Хранилище текстов в оперативной памяти
user_texts = {}

# Функция создания красивой панели управления
def get_panel():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_set = types.KeyboardButton('📝 Установить текст')
    btn_show = types.KeyboardButton('👀 Мой текст')
    markup.add(btn_set, btn_show)
    return markup

@bot.message_handler(commands=['start'])
def start_bot(message):
    bot.send_message(
        message.chat.id,
        "👋 Привет! Я помогу тебе быстро оформлять ссылки.\n\n"
        "Нажми на кнопку ниже, чтобы задать текст, который я буду прикреплять к каждой ссылке.",
        reply_markup=get_panel()
    )

@bot.message_handler(func=lambda message: message.text == '👀 Мой текст')
def show_current_text(message):
    current_text = user_texts.get(message.chat.id, "❌ Текст еще не установлен.")
    bot.send_message(message.chat.id, f"Твой текущий шаблон:\n\n`{current_text}`", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == '📝 Установить текст')
def ask_for_text(message):
    msg = bot.send_message(
        message.chat.id, 
        "Пришли мне текст (например: *Крутые подарки по этой ссылке*):",
        parse_mode="Markdown",
        reply_markup=types.ReplyKeyboardRemove()
    )
    bot.register_next_step_handler(msg, save_base_text)

def save_base_text(message):
    user_texts[message.chat.id] = message.text
    bot.send_message(
        message.chat.id, 
        "✅ Готово! Теперь просто присылай мне любую ссылку.", 
        reply_markup=get_panel()
    )

@bot.message_handler(func=lambda message: True)
def process_links(message):
    # Регулярное выражение для поиска ссылок
    urls = re.findall(r'(https?://\S+)', message.text)
    
    if urls:
        url = urls[0]
        base_text = user_texts.get(message.chat.id)
        
        if not base_text:
            bot.send_message(message.chat.id, "⚠️ Сначала установи текст через панель!")
            return
            
        # Формируем итоговый пост
        final_message = f"{base_text}\n{url}"
        
        # Пытаемся удалить старое сообщение (нужны права админа в группах)
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
            
        bot.send_message(message.chat.id, final_message)

if __name__ == '__main__':
    print("Бот успешно запущен!")
    bot.polling(none_stop=True)
