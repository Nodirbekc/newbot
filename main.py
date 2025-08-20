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
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")

if not BOT_TOKEN or not OWM_API_KEY or not RENDER_URL:
    raise Exception("Не заданы обязательные переменные: BOT_TOKEN, OWM_API, RENDER_EXTERNAL_URL")

bot = TeleBot(BOT_TOKEN)
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Константы
MAX_MESSAGES_PER_USER = 50
HISTORY_FILE = "user_dialogs.pkl"

# Структура для хранения сообщений
class DialogMessage:
    def __init__(self, role: str, text: str):
        self.role = role
        self.text = text
        self.timestamp = datetime.now()

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

# ======= БЕСПЛАТНЫЙ ИИ API =======
def ask_ai(prompt: str) -> str:
    """Бесплатный ИИ через OpenAI-совместимый API"""
    try:
        # Попробуем несколько бесплатных альтернатив
        return ask_openrouter(prompt)  # Основной вариант
        
    except Exception as e:
        logging.error(f"AI error: {e}")
        return "🤖 ИИ временно недоступен. Попробуй позже."

def ask_openrouter(prompt: str) -> str:
    """OpenRouter - бесплатные модели"""
    try:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer free"  # Бесплатный ключ
        }
        
        data = {
            "model": "google/gemini-pro",  # Бесплатная модель
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1000
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        else:
            return ask_fallback(prompt)
            
    except:
        return ask_fallback(prompt)

def ask_fallback(prompt: str) -> str:
    """Резервный вариант - локальная логика"""
    prompt_lower = prompt.lower()
    
    # Простые ответы на частые вопросы
    if any(word in prompt_lower for word in ["привет", "hello", "hi", "здравств"]):
        return "Привет! Чем могу помочь? 😊"
    
    elif any(word in prompt_lower for word in ["как дела", "how are you"]):
        return "У меня все отлично! Готов помочь тебе! 🚀"
    
    elif any(word in prompt_lower for word in ["спасибо", "thanks", "thank you"]):
        return "Всегда рад помочь! Обращайся еще! 👍"
    
    elif any(word in prompt_lower for word in ["погода", "weather"]):
        return "Используй кнопку '🌤 Погода' для информации о погоде!"
    
    # Для остального - заглушка
    return "🤖 Извини, ИИ сервис временно недоступен. Но ты можешь спросить о погоде или попробовать позже!"

# ======= Умный роутер =======
def smart_router(user_id: int, user_query: str) -> str:
    if user_id not in user_modes:
        user_modes[user_id] = 'default'
    
    query_lower = user_query.lower()
    
    study_keywords = ["учиться", "урок", "задач", "учеб", "объясни", "как решить", "теория"]
    coding_keywords = ["код", "программир", "алгоритм", "python", "java", "функция"]
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
    prompt = f"""Ты экспертный репетитор. Объясни понятно:
    {query}
    
    Ответь кратко и информативно."""
    return ask_ai(prompt)

def coding_helper_mode(query: str) -> str:
    prompt = f"""Ты senior developer. Помоги с кодом:
    {query}
    
    Ответь с примером и объяснением."""
    return ask_ai(prompt)

def creative_mode(query: str) -> str:
    prompt = f"""Ты креативный писатель. Создай:
    {query}
    
    Будь креативным!"""
    return ask_ai(prompt)

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
            response = ask_ai(user_query)
        
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
                    "🤖 Привет! Я умный помощник!\n"
                    "• 🌤 Погода - узнай погоду\n"
                    "• 🤖 ИИ - задай вопрос\n"
                    "Работаю на бесплатных технологиях! 🚀", 
                    reply_markup=main_menu())

@bot.message_handler(commands=["study"])
def set_study_mode(message):
    user_id = message.chat.id
    user_modes[user_id] = "study"
    bot.send_message(user_id, "🎓 Режим репетитора активирован!")

@bot.message_handler(commands=["code"])
def set_code_mode(message):
    user_id = message.chat.id
    user_modes[user_id] = "coding"
    bot.send_message(user_id, "💻 Режим программирования активирован!")

@bot.message_handler(commands=["creative"])
def set_creative_mode(message):
    user_id = message.chat.id
    user_modes[user_id] = "creative"
    bot.send_message(user_id, "🎨 Креативный режим активирован!")

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
    return 'Bot is running with free AI!'

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
