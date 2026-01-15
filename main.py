import os
import requests
from flask import Flask, request
from telebot import TeleBot, types

# ===== ENV =====
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWM_API_KEY = os.getenv("OWM_API_KEY")

if not BOT_TOKEN:
    raise Exception("Missing TELEGRAM_BOT_TOKEN")

bot = TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ===== STATES =====
user_states = {}
user_modes = {}

# ===== UI =====
def menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🌤 Погода", "🤖 ИИ")
    kb.add("/study", "/code", "/creative")
    return kb

# ===== WEATHER =====
def get_weather(city):
    if not OWM_API_KEY:
        return "❌ Ключ OpenWeather не задан"

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
        f"🌤 Погода в {city}\n"
        f"🌡 {data['main']['temp']}°C\n"
        f"{data['weather'][0]['description']}\n"
        f"💧 Влажность: {data['main']['humidity']}%\n"
        f"🌬 Ветер: {data['wind']['speed']} м/с"
    )

# ===== COMMANDS =====
@bot.message_handler(commands=["start"])
def start(m):
    user_modes[m.chat.id] = "default"
    user_states[m.chat.id] = "normal"
    bot.send_message(
        m.chat.id,
        "🤖 Учебный бот\n\n"
        "• 🌤 Погода\n"
        "• 🤖 ИИ (демо)\n"
        "• /study — учеба\n"
        "• /code — программирование\n"
        "• /creative — креатив\n",
        reply_markup=menu()
    )

@bot.message_handler(commands=["study"])
def study(m):
    user_modes[m.chat.id] = "study"
    bot.send_message(m.chat.id, "🎓 Режим УЧЁБА включён")

@bot.message_handler(commands=["code"])
def code(m):
    user_modes[m.chat.id] = "code"
    bot.send_message(m.chat.id, "💻 Режим КОД включён")

@bot.message_handler(commands=["creative"])
def creative(m):
    user_modes[m.chat.id] = "creative"
    bot.send_message(m.chat.id, "🎨 Режим КРЕАТИВ включён")

# ===== BUTTONS =====
@bot.message_handler(func=lambda m: m.text == "🌤 Погода")
def ask_city(m):
    user_states[m.chat.id] = "city"
    bot.send_message(m.chat.id, "Введи город:")

@bot.message_handler(func=lambda m: m.text == "🤖 ИИ")
def fake_ai(m):
    bot.send_message(
        m.chat.id,
        "🤖 ИИ временно недоступен.\n"
        "Функция в разработке."
    )

# ===== TEXT HANDLER =====
@bot.message_handler(func=lambda m: True)
def handle(m):
    uid = m.chat.id
    text = m.text

    if user_states.get(uid) == "city":
        user_states[uid] = "normal"
        bot.send_message(uid, get_weather(text))
        return

    mode = user_modes.get(uid, "default")

    if mode == "study":
        bot.send_message(uid, "📘 Учебный режим активен.\nФункция будет добавлена позже.")
    elif mode == "code":
        bot.send_message(uid, "💻 Режим программирования.\nФункция будет добавлена позже.")
    elif mode == "creative":
        bot.send_message(uid, "🎨 Креативный режим.\nФункция будет добавлена позже.")
    else:
        bot.send_message(uid, "ℹ Используй меню или команды.")

# ===== WEB SERVER (для Render) =====
@app.route("/")
def index():
    return "Bot is running"

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = types.Update.de_json(request.data.decode("utf-8"))
    bot.process_new_updates([update])
    return "OK"

# ===== START =====
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
