import os
import logging
import requests
import pickle
from datetime import datetime
from flask import Flask, request
from telebot import TeleBot, types
import google.generativeai as genai

# ================== ENV ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWM_API_KEY = os.environ.get("OWM_API")
GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY")
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")

if not all([BOT_TOKEN, OWM_API_KEY, GEMINI_API_KEY, RENDER_URL]):
    raise Exception("Missing required environment variables")

# ================== INIT ==================
bot = TeleBot(BOT_TOKEN)
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

# ================== CONSTANTS ==================
MAX_MESSAGES_PER_USER = 50
HISTORY_FILE = "user_dialogs.pkl"

# ================== DATA ==================
class DialogMessage:
    def __init__(self, role, text):
        self.role = role
        self.text = text
        self.timestamp = datetime.now()

def load_dialogs():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "rb") as f:
                return pickle.load(f)
        except:
            pass
    return {}

def save_dialogs():
    with open(HISTORY_FILE, "wb") as f:
        pickle.dump(user_dialogs, f)

user_dialogs = load_dialogs()
user_states = {}
user_modes = {}

# ================== GEMINI ==================
def ask_gemini(prompt: str) -> str:
    try:
        response = gemini_model.generate_content(prompt)
        return response.text if response.text else "❌ Empty response from Gemini"
    except Exception as e:
        logging.error(f"Gemini error: {e}")
        return f"❌ Gemini error: {str(e)}"

# ================== ROUTER ==================
def smart_router(user_id, text):
    text = text.lower()
    if any(k in text for k in ["учеб", "задач", "объясни", "математ", "физик"]):
        return "study"
    if any(k in text for k in ["код", "python", "алгоритм", "ошибка"]):
        return "coding"
    if any(k in text for k in ["история", "стих", "креатив"]):
        return "creative"
    return "default"

# ================== MODES ==================
def study_mode(q):
    prompt = f"""
Ты экспертный репетитор.
Ответь структурированно:

Вопрос: {q}

Формат:
- Основная идея
- Подробное объяснение
- Пример
- Частые ошибки
"""
    return ask_gemini(prompt)

def coding_mode(q):
    prompt = f"""
Ты senior developer.
Дай точное решение.

Запрос: {q}

Формат:
- Анализ
- Код
- Объяснение
"""
    return ask_gemini(prompt)

def creative_mode(q):
    return ask_gemini(q)

# ================== CORE ==================
def process_message(user_id, text):
    user_dialogs.setdefault(user_id, []).append(DialogMessage("user", text))
    mode = smart_router(user_id, text)

    if mode == "study":
        reply = study_mode(text)
    elif mode == "coding":
        reply = coding_mode(text)
    elif mode == "creative":
        reply = creative_mode(text)
    else:
        reply = ask_gemini(text)

    user_dialogs[user_id].append(DialogMessage("assistant", reply))
    user_dialogs[user_id] = user_dialogs[user_id][-MAX_MESSAGES_PER_USER:]
    save_dialogs()
    return reply

# ================== WEATHER ==================
def weather(city):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OWM_API_KEY}&units=metric&lang=ru"
    r = requests.get(url, timeout=10).json()
    if r.get("cod") != 200:
        return "❌ Город не найден"
    return (
        f"🌤 {city}\n"
        f"{r['weather'][0]['description'].capitalize()}, {r['main']['temp']}°C\n"
        f"💧 Влажность: {r['main']['humidity']}%\n"
        f"🌬 Ветер: {r['wind']['speed']} м/с"
    )

# ================== TELEGRAM ==================
@bot.message_handler(commands=["start"])
def start(m):
    user_states[m.chat.id] = "menu"
    bot.send_message(
        m.chat.id,
        "🤖 Умный AI-бот\n\n🌤 Погода\n🤖 ИИ",
        reply_markup=menu()
    )

@bot.message_handler(func=lambda m: m.text == "🌤 Погода")
def ask_city(m):
    user_states[m.chat.id] = "city"
    bot.send_message(m.chat.id, "Введи город:")

@bot.message_handler(func=lambda m: m.text == "🤖 ИИ")
def ask_ai(m):
    user_states[m.chat.id] = "ai"
    bot.send_message(m.chat.id, "Задай вопрос:")

@bot.message_handler(func=lambda m: True)
def handle(m):
    uid = m.chat.id

    if user_states.get(uid) == "city":
        bot.send_message(uid, weather(m.text))
        user_states[uid] = "menu"
        return

    bot.send_message(uid, "🤔 Думаю...")
    reply = process_message(uid, m.text)
    bot.send_message(uid, reply[:4000])

def menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🌤 Погода", "🤖 ИИ")
    return kb

# ================== WEBHOOK ==================
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = types.Update.de_json(request.get_data().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK"

@app.route("/")
def index():
    return "Bot is running"

@app.route("/set_webhook")
def set_webhook():
    url = f"{RENDER_URL}/{BOT_TOKEN}"
    bot.remove_webhook()
    bot.set_webhook(url=url)
    return f"Webhook set to {url}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
