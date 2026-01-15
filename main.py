import os
import logging
import requests
from flask import Flask, request
from telebot import TeleBot, types

# ===== ENV =====
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
OWM_API_KEY = os.getenv("OWM_API_KEY")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

if not TELEGRAM_BOT_TOKEN or not GOOGLE_API_KEY or not RENDER_EXTERNAL_URL:
    raise Exception("Missing required environment variables")

# ===== TELEGRAM =====
bot = TeleBot(TELEGRAM_BOT_TOKEN)
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ===== GEMINI (ПРАВИЛЬНО) =====
import google.genai as genai

genai.configure(api_key=GOOGLE_API_KEY)
MODEL_NAME = "gemini-1.5-flash-latest"

def ask_gemini(prompt: str) -> str:
    try:
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logging.error(e)
        return f"❌ Gemini error: {e}"

# ===== STATES =====
user_modes = {}
user_states = {}

# ===== ROUTER =====
def route_mode(uid, text):
    text = text.lower()
    if uid not in user_modes:
        user_modes[uid] = "default"

    if any(k in text for k in ["мат", "физ", "задач", "объясни"]):
        user_modes[uid] = "study"
    elif any(k in text for k in ["код", "python", "ошибка", "алгоритм"]):
        user_modes[uid] = "code"
    elif any(k in text for k in ["стих", "придумай", "креатив"]):
        user_modes[uid] = "creative"

    return user_modes[uid]

# ===== MODES =====
def study_mode(q):
    return ask_gemini(
        f"Ты преподаватель. Объясни по шагам:\n{q}"
    )

def code_mode(q):
    return ask_gemini(
        f"Ты senior developer. Дай решение с кодом:\n{q}"
    )

def creative_mode(q):
    return ask_gemini(
        f"Создай креативный текст:\n{q}"
    )

# ===== WEATHER =====
def get_weather(city):
    if not OWM_API_KEY:
        return "❌ OpenWeather API key не задан"

    r = requests.get(
        "https://api.openweathermap.org/data/2.5/weather",
        params={
            "q": city,
            "appid": OWM_API_KEY,
            "units": "metric",
            "lang": "ru"
        },
        timeout=10
    )
    data = r.json()

    if data.get("cod") != 200:
        return "❌ Город не найден"

    return (
        f"🌤 {city}\n"
        f"🌡 {data['main']['temp']}°C\n"
        f"{data['weather'][0]['description']}"
    )

# ===== UI =====
def menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🌤 Погода", "🤖 ИИ")
    kb.add("/study", "/code", "/creative")
    return kb

# ===== HANDLERS =====
@bot.message_handler(commands=["start"])
def start(m):
    user_modes[m.chat.id] = "default"
    user_states[m.chat.id] = "normal"
    bot.send_message(m.chat.id, "Gemini AI Bot", reply_markup=menu())

@bot.message_handler(func=lambda m: m.text == "🌤 Погода")
def ask_city(m):
    user_states[m.chat.id] = "city"
    bot.send_message(m.chat.id, "Введи город:")

@bot.message_handler(func=lambda m: True)
def handle(m):
    uid = m.chat.id
    text = m.text

    if user_states.get(uid) == "city":
        user_states[uid] = "normal"
        bot.send_message(uid, get_weather(text))
        return

    mode = route_mode(uid, text)

    if mode == "study":
        ans = study_mode(text)
    elif mode == "code":
        ans = code_mode(text)
    elif mode == "creative":
        ans = creative_mode(text)
    else:
        ans = ask_gemini(text)

    bot.send_message(uid, ans[:4000])

# ===== WEBHOOK =====
@app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def webhook():
    update = types.Update.de_json(request.data.decode("utf-8"))
    bot.process_new_updates([update])
    return "OK"

@app.route("/set_webhook")
def set_webhook():
    bot.remove_webhook()
    url = f"{RENDER_EXTERNAL_URL}/{TELEGRAM_BOT_TOKEN}"
    bot.set_webhook(url)
    return f"Webhook set: {url}"

@app.route("/")
def index():
    return "Bot is running"

# ===== START =====
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
