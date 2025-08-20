import os
import logging
import requests
import json
import pickle
from datetime import datetime, timedelta
from flask import Flask, request
from telebot import TeleBot, types
import re

# Настройки
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWM_API_KEY = os.environ.get("OWM_API")
GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY")
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")

if not all([BOT_TOKEN, OWM_API_KEY, GEMINI_API_KEY, RENDER_URL]):
    raise Exception("Не заданы обязательные переменные окружения")

bot = TeleBot(BOT_TOKEN)
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Константы
MAX_MESSAGES_PER_USER = 50
HISTORY_FILE = "user_dialogs.pkl"

# Структура для хранения сообщений
class DialogMessage:
    def __init__(self, role: str, text: str, ai_model: str = "gemini"):
        self.role = role
        self.text = text
        self.timestamp = datetime.now()
        self.ai_model = ai_model

# Загрузка и сохранение истории
def load_dialogs():
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'rb') as f:
                loaded = pickle.load(f)
                return loaded if isinstance(loaded, dict) else {}
    except Exception as e:
        logging.error(f"Error loading dialogs: {e}")
    return {}

def save_dialogs():
    try:
        with open(HISTORY_FILE, 'wb') as f:
            pickle.dump(user_dialogs, f)
    except Exception as e:
        logging.error(f"Error saving dialogs: {e}")

user_dialogs = load_dialogs()
user_states = {}
user_modes = {}

# ======= GEMINI API =======
def ask_gemini(prompt: str) -> str:
    """Gemini API - надежный и проверенный"""
    try:
        # НОВЫЙ правильный endpoint для Gemini
        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
        
        data = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        
        response = requests.post(url, json=data, timeout=30)
        
        if response.status_code != 200:
            return f"❌ Ошибка Gemini API: {response.status_code}"
        
        response_data = response.json()
        
        # Правильное извлечение ответа
        if (response_data.get("candidates") and 
            len(response_data["candidates"]) > 0 and
            "content" in response_data["candidates"][0] and
            "parts" in response_data["candidates"][0]["content"] and
            len(response_data["candidates"][0]["content"]["parts"]) > 0):
            
            return response_data["candidates"][0]["content"]["parts"][0].get("text", "Пустой ответ от Gemini")
        
        return "❌ Не удалось обработать ответ Gemini"
            
    except Exception as e:
        logging.error(f"Gemini error: {e}")
        return f"⚠️ Ошибка Gemini: {str(e)}"

# ======= Умный роутер =======
def smart_router(user_id: int, user_query: str) -> str:
    if user_id not in user_modes:
        user_modes[user_id] = 'default'
    
    query_lower = user_query.lower()
    
    study_keywords = ["учиться", "урок", "задач", "учеб", "объясни", "как решить", "теория", "математик", "физик"]
    coding_keywords = ["код", "программир", "алгоритм", "python", "java", "функция", "баг", "ошибка"]
    creative_keywords = ["придумай", "создай", "напиши историю", "креатив", "стих", "рассказ"]
    
    if any(keyword in query_lower for keyword in study_keywords):
        user_modes[user_id] = 'study'
    elif any(keyword in query_lower for keyword in coding_keywords):
        user_modes[user_id] = 'coding'
    elif any(keyword in query_lower for keyword in creative_keywords):
        user_modes[user_id] = 'creative'
    
    return user_modes[user_id]

# ======= Специализированные режимы =======
def study_assistant_mode(query: str) -> str:
    prompt = f"""Ты экспертный репетитор с PhD уровнем знаний. Объясняй максимально понятно.
    Вопрос: {query}
    
    Ответь в формате:
    🎯 ОСНОВНАЯ КОНЦЕПЦИЯ: [1-2 предложения]
    📚 ПОДРОБНОЕ ОБЪЯСНЕНИЕ: [2-3 абзаца] 
    🧪 ПРАКТИЧЕСКИЙ ПРИМЕР: [конкретный пример]
    ⚠️ ЧАСТЫЕ ОШИБКИ: [что избегать]"""
    return ask_gemini(prompt)

def coding_helper_mode(query: str) -> str:
    prompt = f"""Ты senior developer с 10+ лет опыта. Давай идеальные решения.
    Запрос: {query}
    
    Ответь в формате:
    🔍 АНАЛИЗ ПРОБЛЕМЫ: [в чем суть]
    💻 РЕШЕНИЕ: [код с комментариями]
    📖 ОБЪЯСНЕНИЕ: [почему так работает]
    🚀 АЛЬТЕРНАТИВЫ: [другие подходы]"""
    return ask_gemini(prompt)

def creative_mode(query: str) -> str:
    prompt = f"""Ты креативный писатель и художник. Создавай вдохновляющий контент.
    Запрос: {query}
    
    Создай что-то уникальное и engaging!"""
    return ask_gemini(prompt)

def add_to_dialog(user_id: int, role: str, text: str):
    if user_id not in user_dialogs:
        user_dialogs[user_id] = []
    user_dialogs[user_id].append(DialogMessage(role, text))
    if len(user_dialogs[user_id]) > MAX_MESSAGES_PER_USER:
        user_dialogs[user_id] = user_dialogs[user_id][-MAX_MESSAGES_PER_USER:]

def process_message(user_id: int, user_query: str) -> str:
    """Основная функция обработки сообщений"""
    
    if user_id not in user_dialogs:
        user_dialogs[user_id] = []
    if user_id not in user_modes:
        user_modes[user_id] = 'default'
    
    # Сохраняем запрос пользователя
    add_to_dialog(user_id, "user", user_query)
    
    try:
        # Определяем режим
        mode = smart_router(user_id, user_query)
        
        # Выбираем обработчик
        if mode == 'study':
            response = study_assistant_mode(user_query)
        elif mode == 'coding':
            response = coding_helper_mode(user_query)
        elif mode == 'creative':
            response = creative_mode(user_query)
        else:
            response = ask_gemini(user_query)
        
        # Сохраняем ответ
        add_to_dialog(user_id, "assistant", response)
        save_dialogs()
        
        return response
        
    except Exception as e:
        logging.error(f"Process message error: {e}")
        return "🤖 Упс! Произошла ошибка. Попробуй еще раз."

# ======= Обработка погоды =======
def handle_weather_request(message):
    chat_id = message.chat.id
    city = message.text.strip()
    
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OWM_API_KEY}&units=metric&lang=ru"
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("cod") != 200:
            bot.send_message(chat_id, f"Город '{city}' не найден. Попробуй еще раз:")
            return
        
        temp = data["main"]["temp"]
        desc = data["weather"][0]["description"].capitalize()
        humidity = data["main"]["humidity"]
        wind = data["wind"]["speed"]

        msg = (
            f"Погода в {city} сейчас:\n"
            f"🌡 {desc}, {temp}°C\n"
            f"💧 Влажность: {humidity}%\n"
            f"🌬 Ветер: {wind} м/с"
        )
        
        bot.send_message(chat_id, msg)
        user_states[chat_id] = "main_menu"
        
    except Exception as e:
        bot.send_message(chat_id, f"Ошибка погоды: {str(e)}")
        user_states[chat_id] = "main_menu"

# ======= Telegram Handlers =======
@bot.message_handler(commands=["start"])
def start_handler(message):
    user_id = message.chat.id
    user_states[user_id] = "main_menu"
    user_modes[user_id] = "default"
    if user_id not in user_dialogs:
        user_dialogs[user_id] = []
    
    bot.send_message(user_id, 
                    "🤖 Привет! Я умный помощник на Gemini AI!\n"
                    "• 🌤 Погода - узнай погоду\n"
                    "• 🤖 ИИ - задай любой вопрос\n"
                    "• /study - режим учебы\n"
                    "• /code - режим программирования\n"
                    "• /creative - креативный режим\n\n"
                    "🔥 Работаю на Gemini - самом надежном ИИ!", 
                    reply_markup=main_menu())

@bot.message_handler(commands=["study"])
def set_study_mode(message):
    user_id = message.chat.id
    user_modes[user_id] = "study"
    bot.send_message(user_id, "🎓 Режим репетитора активирован! Задавай учебные вопросы.")

@bot.message_handler(commands=["code"])
def set_code_mode(message):
    user_id = message.chat.id
    user_modes[user_id] = "coding"
    bot.send_message(user_id, "💻 Режим программирования активирован! Задавай технические вопросы.")

@bot.message_handler(commands=["creative"])
def set_creative_mode(message):
    user_id = message.chat.id
    user_modes[user_id] = "creative"
    bot.send_message(user_id, "🎨 Креативный режим активирован! Давай творить!")

@bot.message_handler(func=lambda m: m.text == "🌤 Погода")
def ask_city(message):
    user_id = message.chat.id
    user_states[user_id] = "waiting_city"
    bot.send_message(user_id, "Введи название города:")

@bot.message_handler(func=lambda m: m.text == "🤖 ИИ")
def ask_ai_command(message):
    user_id = message.chat.id
    user_states[user_id] = "waiting_ai_question"
    bot.send_message(user_id, "Задай любой вопрос:")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id) == "waiting_city")
def weather_handler(message):
    handle_weather_request(message)

@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    user_id = message.chat.id
    user_query = message.text
    
    if user_states.get(user_id) == "waiting_city":
        handle_weather_request(message)
        return
    
    thinking_msg = bot.send_message(user_id, "🤔 Думаю...")
    
    try:
        response = process_message(user_id, user_query)
        bot.delete_message(user_id, thinking_msg.message_id)
        
        if len(response) > 4000:
            response = response[:4000] + "..."
            
        bot.send_message(user_id, response)
        
    except Exception as e:
        logging.error(f"Handle message error: {e}")
        bot.send_message(user_id, "🤖 Упс! Что-то пошло не так. Попробуй еще раз.")

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🌤 Погода"))
    markup.add(types.KeyboardButton("🤖 ИИ"))
    return markup

# ======= Webhook handlers =======
@app.route('/' + BOT_TOKEN, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return 'OK'

@app.route('/')
def index():
    return 'Bot is running with Gemini AI!'

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    webhook_url = f"{RENDER_URL}/{BOT_TOKEN}"
    bot.remove_webhook()
    result = bot.set_webhook(url=webhook_url)
    return f"Webhook set to {webhook_url}: {result}"

if __name__ == '__main__':
    print("Starting bot...")
    print(f"Webhook URL: {RENDER_URL}/{BOT_TOKEN}")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
