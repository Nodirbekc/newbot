import os
import logging
import requests
import pytz
from datetime import datetime
from flask import Flask, request
from telebot import TeleBot, types
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWM_API_KEY = os.getenv("OWM_API")

if not BOT_TOKEN or not OWM_API_KEY:
    raise Exception("BOT_TOKEN или OWM_API не задан в переменных окружения")

bot = TeleBot(BOT_TOKEN)
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

user_last_city = {}

# Кнопка "Погода"
def weather_button():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn = types.KeyboardButton("🌤 Погода")
    markup.add(btn)
    return markup

# /start
@bot.message_handler(commands=["start"])
def start_handler(message):
    bot.send_message(message.chat.id, "hillow hillow", reply_markup=weather_button())

# Обработка нажатий на кнопку
@bot.message_handler(func=lambda m: m.text == "🌤 Погода")
def ask_city(message):
    bot.send_message(message.chat.id, "Информацию о погоде какого города или страны хотите узнать?")

# Основная логика получения и вывода погоды
@bot.message_handler(func=lambda m: True)
def send_weather(message):
    chat_id = message.chat.id
    city = message.text.strip()
    user_last_city[message.from_user.id] = city

    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OWM_API_KEY}&units=metric&lang=ru"
    forecast_url = f"https://api.openweathermap.org/data/2.5/forecast?q={city}&appid={OWM_API_KEY}&units=metric&lang=ru"

    try:
        r = requests.get(url).json()
        f = requests.get(forecast_url).json()

        if r.get("cod") != 200:
            bot.send_message(chat_id, "Не удалось найти город. Проверьте название.")
            return

        # Текущая погода
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

        # Прогноз на 3 дня (раз в 24 ч, 12:00)
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

# Flask webhook
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    bot.process_new_updates([types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

# Проверка внешнего URL от Render
if __name__ == "__main__":
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if not render_url:
        raise RuntimeError("Ошибка: переменная окружения RENDER_EXTERNAL_URL не задана.")

    bot.remove_webhook()
    bot.set_webhook(url=f"{render_url}/{BOT_TOKEN}")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
