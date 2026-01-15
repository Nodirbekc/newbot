import os
import logging
import requests
from flask import Flask, request
from telebot import TeleBot, types
from datetime import datetime

# ====== ENV ======
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
OWM_API_KEY = os.getenv("OWM_API_KEY")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

if not TELEGRAM_BOT_TOKEN or not GOOGLE_API_KEY or not RENDER_EXTERNAL_URL:
    raise Exception("Missing required environment variables")

# ====== TELEGRAM ======
bot = TeleBot(TELEGRAM_BOT_TOKEN)
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ====== GEMINI (НОВЫЙ SDK) ======
from google import genai
client = genai.Client(api_key=GOOGLE_API_KEY)

GEMINI_MODEL = "gemini-1.5-flash-latest"

def ask_gemini(prompt: str) -> str:
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        logging.error(f"Gemini error: {e}")
        return f"❌ Gemini error: {e}"

# ====== USER STATES ======
user_modes = {}     # default / study / code / creative
user_states = {}    # waiting_city / normal

# ====== SMART ROUTER ======
def route_mode(user_id: int, text: str):
    text = text.lower()
    if user_id not in user_modes:
        user_modes[user_id] = "default"

    if any(k in text for k in ["мат", "физ", "задач", "объясни", "теория"]):
        user_modes[user_id] = "study"
    elif any(k in text for k in ["код", "python", "ошибка", "функц", "алгоритм"]):
        user_modes[user_id] = "code"
    elif any(k in text for k in ["стих", "история", "придумай", "креатив"]):
        user_modes[user_id] = "creative"

    return user_modes[user_id]

# ====== MODES ======
def study_mode(q: str):
    prompt = f"""
Ты профессиональный преподаватель.
Объясняй чётко и по шагам.

Формат:
🎯 КОНЦЕПЦИЯ
📘 ОБЪЯСНЕНИЕ
🧪 ПРИМЕР
⚠️ ОШИБКИ

Вопрос: {q}
"""
    return ask_gemini(prompt)

def code_mode(q: str):
    prompt = f"""
Ты senior developer.
Дай корректное решение.

Формат:
🔍 АНАЛИЗ
💻 КОД
📖 ПОЯСНЕНИЕ

Запрос: {q}
"""
    return ask_gemini(prompt)

def creative_mode(q: str):
    return ask_gemini(f"Создай креативный и оригинальный текст:\n{q}")

# ====== WEATHER ======
def get_weather(city: str) -> str:
    if not OWM_API_KEY:
        return "❌ OpenWeather API key не задан"

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": OWM_API_KEY,
        "units": "metric",
        "lang": "ru"
    }

    r = requests.get(url, params=params, timeout=10)
    data = r.json()

    if data.get("cod") != 200:
        return f"❌ Город '{city}' не найден"

    return (
        f"🌤 Погода в {city}\n"
        f"🌡 {data['main']['temp']}°C\n"
        f"☁ {data['weather'][0]['description']}\n"
        f"💧 Влажность: {data['main']['humidity']}%\n"
        f"🌬 Ветер: {data['wind']['speed']} м/с"
    )

# ====== UI ======
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🌤 Погода", "🤖 ИИ")
    kb.add("/study", "/code", "/creative")
    return kb

# ====== HANDLERS ======
@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.chat.id
    user_modes[user_id] = "default"
    user_states[user_id] = "normal"

    bot.send_message(
        user_id,
        "🤖 Gemini AI Bot\n\n"
        "• 🌤 Погода\n"
        "• 🤖 ИИ\n"
        "• /study — учеба\n"
        "• /code — программирование\n"
        "• /creative — креатив\n",
        reply_markup=main_menu()
    )

@bot.message_handler(commands=["study"])
def set_study(message):
    user_modes[message.chat.id] = "study"
    bot.send_message(message.chat.id, "🎓 Режим УЧЁБА включён")

@bot.message_handler(commands=["code"])
def set_code(message):
    user_modes[message.chat.id] = "code"
    bot.send_message(message.chat.id, "💻 Режим КОД включён")

@bot.message_handler(commands=["creative"])
def set_creative(message):
    user_modes[message.chat.id] = "creative"
    bot.send_message(message.chat.id, "🎨 КРЕАТИВНЫЙ режим включён")

@bot.message_handler(func=lambda m: m.text == "🌤 Погода")
def ask_city(message):
    user_states[message.chat.id] = "waiting_city"
    bot.send_message(message.chat.id, "Введи город:")

@bot.message_handler(func=lambda m: m.text == "🤖 ИИ")
def ai_prompt(message):
    bot.send_message(message.chat.id, "Задай вопрос:")

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    user_id = message.chat.id
    text = message.text

    if user_states.get(user_id) == "waiting_city":
        user_states[user_id] = "normal"
        bot.send_message(user_id, get_weather(text))
        return

    mode = route_mode(user_id, text)

    if mode == "study":
        answer = study_mode(text)
    elif mode == "code":
        answer = code_mode(text)
    elif mode == "creative":
        answer = creative_mode(text)
    else:
        answer = ask_gemini(text)

    bot.send_message(user_id, answer[:4000])

# ====== WEBHOOK ======
@app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def webhook():
    update = types.Update.de_json(request.get_data().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK"

@app.route("/")
def index():
    return "Bot is running"

@app.route("/set_webhook")
def set_webhook():
    bot.remove_webhook()
    url = f"{RENDER_EXTERNAL_URL}/{TELEGRAM_BOT_TOKEN}"
    bot.set_webhook(url=url)
    return f"Webhook set: {url}"

# ====== START ======
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
