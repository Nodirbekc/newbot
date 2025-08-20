import os
import logging
import requests
from datetime import datetime
from flask import Flask, request
from telebot import TeleBot, types
from dotenv import load_dotenv
import google.genai as genai  # Gemini

# Загружаем .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWM_API_KEY = os.getenv("OWM_API")
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")

if not BOT_TOKEN or not OWM_API_KEY or not GEMINI_API_KEY:
    raise Exception("BOT_TOKEN, OWM_API или GOOGLE_API_KEY не заданы в переменных окружения")

# Инициализация
bot = TeleBot(BOT_TOKEN)
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Клиент Gemini
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# Память о городах
user_last_city = {}

# Кнопки
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🌤 Погода"))
    markup.add(types.KeyboardButton("🤖 ИИ"))
    return markup

# /start
@bot.message_handler(commands=["start"])
def start_handler(message):
    bot.send_message(message.chat.id, "Привет! Я бот 🤖\nВыбери действие:", reply_markup=main_menu())

# Обработка кнопки Погода
@bot.message_handler(func=lambda m: m.text == "🌤 Погода")
def ask_city(message):
    bot.send_message(message.chat.id, "Информацию о погоде какого города хотите узнать?")

# Обработка кнопки ИИ
@bot.message_handler(func=lambda m: m.text == "🤖 ИИ")
def ask_ai(message):
    bot.send_message(message.chat.id, "Задай мне вопрос, и я отвечу с помощью Gemini!")

# Обработка сообщений
@bot.message_handler(func=lambda m: True)
def main_handler(message):
    chat_id = message.chat.id
    text = message.text.strip()

    # Если пользователь до этого нажал "ИИ"
    if text.lower().startswith("ai ") or text.startswith("ИИ") or text.startswith("🤖"):
        question = text.replace("ИИ", "").replace("🤖", "").replace("ai", "").strip()
        if not question:
            bot.send_message(chat_id, "Напиши свой вопрос после слова 'ИИ'.")
            return
        try:
            resp = gemini_client.models.generate_content(
                model="gemini-1.5-flash",
                contents=question
            )
            answer = resp.text if hasattr(resp, "text") else str(resp)
            bot.send_message(chat_id, f"Ответ Gemini:\n{answer}")
        except Exception as e:
            logging.exception(e)
            bot.send_message(chat_id, "Ошибка при обращении к Gemini API.")
        return

    # Обработка как город для погоды
    city = text
    user_last_city[message.from_user.id] = city

    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OWM_API_KEY}&units=metric&lang=ru"
    forecast_url = f"https://api.openweathermap.org/data/2.5/forecast?q={city}&appid={OWM_API_KEY}&units=metric&lang=ru"

    try:
        r = requests.get(url).json()
        f = requests.get(forecast_url).json()

        if r.get("cod") != 200:
            bot.send_message(chat_id, "Не удалось найти город. Проверьте название.")
            return

        temp = r["main"]["temp"]
        desc = r["weather"][0]["description"].capitalize()
        humidity = r["main"]["humidity"]
        wind = r["wind"]["speed"]
        sunrise = datetime.utcfromtimestamp(r["sys"]["sunrise"]).strftime('%H:%M')
        sunset = datetime.utcfromtimestamp(r["sys"]["sunset"]).strftime('%H:%M')

        emoji = "🙂"
        if temp <= 0:
            emoji = "🥶"
        elif temp >= 30:
            emoji = "🥵"

        msg = (
            f"Погода в {city} сейчас:\n"
            f"{emoji} {desc}\n"
            f"🌡 Температура: {temp}°C\n"
            f"💧 Влажность: {humidity}%\n"
            f"🌬 Ветер: {wind} м/с\n"
            f"🌅 Восход: {sunrise} UTC\n"
            f"🌇 Закат: {sunset} UTC\n\n"
            f"📅 Прогноз на ближайшие дни:\n"
        )

        days_added = set()
        for item in f["list"]:
            dt = datetime.utcfromtimestamp(item["dt"])
            if dt.hour == 12 and dt.date() not in days_added:
                day_str = dt.strftime("%d.%m")
                temp_day = item["main"]["temp"]
                description = item["weather"][0]["description"].capitalize()
                pop = item.get("pop", 0)
                chance = f"{int(pop * 100)}%"
                msg += f"📆 {day_str}: {description}, {temp_day}°C, осадки: {chance}\n"
                days_added.add(dt.date())
                if len(days_added) >= 3:
                    break

        bot.send_message(chat_id, msg)

    except Exception as e:
        logging.exception(e)
        bot.send_message(chat_id, "Произошла ошибка при получении данных о погоде.")

# --- Render root (чтобы не было 404) ---
@app.route("/", methods=["GET"])
def index():
    return "Бот работает!", 200

# --- Webhook ---
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    bot.process_new_updates([types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

if __name__ == "__main__":
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if not render_url:
        raise RuntimeError("Ошибка: переменная окружения RENDER_EXTERNAL_URL не задана.")

    bot.remove_webhook()
    bot.set_webhook(url=f"{render_url}/{BOT_TOKEN}")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
