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
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")

# Проверяем только обязательные переменные
if not BOT_TOKEN or not OWM_API_KEY or not RENDER_URL:
    raise Exception("Не заданы обязательные переменные: BOT_TOKEN, OWM_API, RENDER_EXTERNAL_URL")

bot = TeleBot(BOT_TOKEN)
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Константы
MAX_MESSAGES_PER_USER = 50
MAX_HISTORY_DAYS = 7
HISTORY_FILE = "user_dialogs.pkl"

# Структура для хранения сообщений
class DialogMessage:
    def __init__(self, role: str, text: str, ai_model: str = None):
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

# ======= AI APIs =======
def ask_deepseek(prompt: str, history: list = None) -> str:
    """DeepSeek API"""
    if not DEEPSEEK_API_KEY:
        return ask_gemini(prompt)  # Fallback to Gemini
    
    try:
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        messages = [{"role": "system", "content": "Ты полезный и точный ассистент."}]
        
        if history:
            for msg in history[-6:]:
                role = "user" if msg.role == "user" else "assistant"
                messages.append({"role": role, "content": msg.text})
        
        messages.append({"role": "user", "content": prompt})
        
        data = {
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 2000
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response_data = response.json()
        
        # Безопасное извлечение ответа
        if response_data.get("choices") and len(response_data["choices"]) > 0:
            return response_data["choices"][0].get("message", {}).get("content", "Пустой ответ от DeepSeek")
        else:
            return ask_gemini(prompt)  # Fallback to Gemini
            
    except Exception as e:
        logging.error(f"DeepSeek error: {e}")
        return ask_gemini(prompt)  # Fallback to Gemini

def ask_gemini(prompt: str) -> str:
    """Gemini API"""
    if not GEMINI_API_KEY:
        return "❌ API ключ Gemini не настроен"
    
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
        
        data = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        
        response = requests.post(url, json=data, timeout=30)
        response_data = response.json()
        
        # Логируем ответ для дебага
        logging.info(f"Gemini response: {response_data}")
        
        # Проверяем разные возможные форматы ответа
        if response_data.get("candidates") and len(response_data["candidates"]) > 0:
            candidate = response_data["candidates"][0]
            if "content" in candidate and "parts" in candidate["content"]:
                return candidate["content"]["parts"][0].get("text", "Пустой ответ от Gemini")
        
        # Если нет candidates, проверяем error
        if "error" in response_data:
            return f"❌ Ошибка Gemini: {response_data['error'].get('message', 'Unknown error')}"
            
        return "❌ Не удалось получить ответ от Gemini"
            
    except Exception as e:
        logging.error(f"Gemini error: {e}")
        return f"⚠️ Ошибка Gemini: {str(e)}"

# ======= Умный роутер =======
def smart_router(user_id: int, user_query: str) -> tuple:
    if user_id not in user_modes:
        user_modes[user_id] = 'default'
    
    query_lower = user_query.lower()
    
    technical_keywords = ["код", "программир", "алгоритм", "математик", "физик", "технич", "логик"]
    creative_keywords = ["придумай", "создай", "напиши историю", "креатив", "стих", "рассказ", "сценарий"]
    study_keywords = ["учиться", "урок", "задач", "учеб", "объясни", "как решить", "теория"]
    
    if any(keyword in query_lower for keyword in study_keywords):
        user_modes[user_id] = 'study'
        return 'study', 'deepseek'
    
    if any(keyword in query_lower for keyword in technical_keywords):
        user_modes[user_id] = 'coding'
        return 'coding', 'deepseek'
    
    if any(keyword in query_lower for keyword in creative_keywords):
        user_modes[user_id] = 'creative'
        return 'creative', 'gemini'
    
    return user_modes[user_id], 'deepseek'  # По умолчанию DeepSeek

# ======= Специализированные режимы =======
def study_assistant_mode(query: str, history: list) -> str:
    prompt = f"""Ты экспертный репетитор. Объясняй максимально понятно.
    Вопрос: {query}
    
    Ответь кратко и по делу."""
    return ask_deepseek(prompt, history)

def coding_helper_mode(query: str, history: list) -> str:
    prompt = f"""Ты senior developer. Помоги с кодом.
    Запрос: {query}
    
    Ответь с примером кода."""
    return ask_deepseek(prompt, history)

def creative_mode(query: str) -> str:
    prompt = f"""Ты креативный писатель. Создай что-то интересное.
    Запрос: {query}"""
    return ask_gemini(prompt)

def add_to_dialog(user_id: int, role: str, text: str, ai_model: str = None):
    if user_id not in user_dialogs:
        user_dialogs[user_id] = []
    user_dialogs[user_id].append(DialogMessage(role, text, ai_model))
    if len(user_dialogs[user_id]) > MAX_MESSAGES_PER_USER:
        user_dialogs[user_id] = user_dialogs[user_id][-MAX_MESSAGES_PER_USER:]

def process_message(user_id: int, user_query: str) -> str:
    """Основная функция обработки сообщений"""
    
    # Инициализация если нужно
    if user_id not in user_dialogs:
        user_dialogs[user_id] = []
    if user_id not in user_modes:
        user_modes[user_id] = 'default'
    
    history = user_dialogs[user_id]
    
    # Определяем режим и ИИ
    mode, ai_engine = smart_router(user_id, user_query)
    
    # Сохраняем запрос пользователя
    add_to_dialog(user_id, "user", user_query)
    
    try:
        # Выбираем обработчик based on mode
        if mode == 'study':
            response = study_assistant_mode(user_query, history)
        elif mode == 'coding':
            response = coding_helper_mode(user_query, history)
        elif mode == 'creative':
            response = creative_mode(user_query)
        else:
            # Default processing
            if ai_engine == 'deepseek':
                response = ask_deepseek(user_query, history)
            else:
                response = ask_gemini(user_query)
        
        # Сохраняем ответ
        add_to_dialog(user_id, "assistant", response, ai_engine)
        save_dialogs()
        
        return response
        
    except Exception as e:
        return f"⚠️ Ошибка обработки: {str(e)}"

# ======= Обработка погоды =======
def handle_weather_request(message):
    chat_id = message.chat.id
    city = message.text.strip()
    
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OWM_API_KEY}&units=metric&lang=ru"
    
    try:
        response = requests.get(url)
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
                    "🤖 Привет! Я умный помощник с ИИ!\n"
                    "• 🌤 Погода - узнай погоду\n"
                    "• 🤖 ИИ - задай вопрос\n"
                    "• /study - режим учебы\n"
                    "• /code - режим программирования\n"
                    "• /creative - креативный режим", 
                    reply_markup=main_menu())

@bot.message_handler(commands=["study", "mode_study"])
def set_study_mode(message):
    user_id = message.chat.id
    user_modes[user_id] = "study"
    bot.send_message(user_id, "🎓 Режим репетитора активирован! Задавай учебные вопросы.")

@bot.message_handler(commands=["code", "mode_code"])
def set_code_mode(message):
    user_id = message.chat.id
    user_modes[user_id] = "coding"
    bot.send_message(user_id, "💻 Режим программирования активирован! Задавай технические вопросы.")

@bot.message_handler(commands=["creative", "mode_creative"])
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
def ask_ai(message):
    user_id = message.chat.id
    user_states[user_id] = "waiting_ai_question"
    bot.send_message(user_id, "Задай вопрос ИИ:")

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
        
        # Добавляем информацию о использованном ИИ
        if user_id in user_dialogs and user_dialogs[user_id]:
            last_msg = user_dialogs[user_id][-1]
            ai_info = f"\n\n🔧 via {last_msg.ai_model}" if last_msg.ai_model else ""
        else:
            ai_info = ""
        
        # Обрезаем если слишком длинное
        if len(response) > 4000:
            response = response[:4000] + "..."
            
        bot.send_message(user_id, f"{response}{ai_info}")
        
    except Exception as e:
        bot.send_message(user_id, f"⚠️ Ошибка: {str(e)}")

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
    return 'Bot is running with multi-AI system!'

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
