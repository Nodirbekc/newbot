import os
import requests
import logging
from datetime import datetime
from flask import Flask, request
import pytz
from telebot import TeleBot, types

TOKEN = os.getenv("BOT_TOKEN")
OWM_API_KEY = os.getenv("OWM_API")
EXCHANGE_API_KEY = os.getenv("EXCHANGE_API_KEY")  # добавь в Render

bot = TeleBot(TOKEN)
app = Flask(__name__)
user_last_city = {}

logging.basicConfig(level=logging.INFO)

# --- Кнопки ---
def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton("🌤 Погода"), types.KeyboardButton("💱 Курсы валют"))
    return markup

# --- Эмодзи по температуре ---
def get_temp_emoji(temp):
    if temp <= 0:
        return "🥶"
    elif temp >= 30:
        return "🥵"
    else:
        return "😊"

# --- Преобразование времени ---
def format_time(timestamp, timezone_str):
    tz = pytz.timezone(timezone_str)
    dt = datetime.utcfromtimestamp(timestamp).replace(tzinfo=pytz.utc).astimezone(tz)
    return dt.strftime('%H:%M')

# --- Старт ---
@bot.message_handler(commands=["start"])
def start_handler(message):
    bot.send_message(
        message.chat.id,
        "hillow hillow!\nВыберите действие:",
        reply_markup=get_main_keyboard()
    )

# --- Обработка кнопок ---
@bot.message_handler(func=lambda msg: msg.text == "🌤 Погода")
def ask_city(message):
    bot.send_message(message.chat.id, "Введите город для прогноза погоды:")

@bot.message_handler(func=lambda msg: msg.text == "💱 Курсы валют")
def ask_currency_type(message):
    bot.send_message(message.chat.id, "Введите валюту (например: USD, EUR, BTC):")

# --- Погода ---
def get_weather(city):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OWM_API_KEY}&units=metric&lang=ru"
    res = requests.get(url).json()

    if res.get("cod") != 200:
        return "Город не найден."

    name = res["name"]
    temp = res["main"]["temp"]
    weather = res["weather"][0]["description"]
    humidity = res["main"]["humidity"]
    wind_speed = res["wind"]["speed"]
    sunrise = res["sys"]["sunrise"]
    sunset = res["sys"]["sunset"]
    emoji = get_temp_emoji(temp)
    timezone_offset = res["timezone"]
    timezone_name = pytz.timezone("Asia/Tashkent")  # или по желанию

    sunrise_local = format_time(sunrise, "Asia/Tashkent")
    sunset_local = format_time(sunset, "Asia/Tashkent")

    return (
        f"📍 {name}\n"
        f"🌡 Температура: {temp}°C {emoji}\n"
        f"☁ Погода: {weather}\n"
        f"💧 Влажность: {humidity}%\n"
        f"💨 Ветер: {wind_speed} м/с\n"
        f"🌅 Восход: {sunrise_local}\n"
        f"🌇 Закат: {sunset_local}"
    )

# --- Курс валют ---
def get_exchange(currency_code):
    try:
        url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_API_KEY}/latest/{currency_code.upper()}"
        res = requests.get(url).json()
        if res["result"] != "success":
            return "Ошибка получения курса."
        rates = res["conversion_rates"]
        return (
            f"💱 1 {currency_code.upper()}:\n"
            f"🇺🇿 UZS: {rates['UZS']}\n"
            f"🇷🇺 RUB: {rates['RUB']}\n"
            f"🇰🇿 KZT: {rates['KZT']}\n"
            f"🇺🇸 USD: {rates['USD']}\n"
            f"🇪🇺 EUR: {rates['EUR']}"
        )
    except:
        return "Ошибка при получении данных."

# --- Обработка сообщений ---
@bot.message_handler(func=lambda msg: True, content_types=["text"])
def general_handler(message):
    text = message.text.strip()

    # Проверка погоды
    if user_last_city.get(message.from_user.id) == "awaiting_city":
        user_last_city[message.from_user.id] = text
        bot.send_message(message.chat.id, get_weather(text))
        return

    # Проверка курса валют
    if user_last_city.get(message.from_user.id) == "awaiting_currency":
        user_last_city[message.from_user.id] = None
        bot.send_message(message.chat.id, get_exchange(text))
        return

    # Установка ожидания
    if text.lower() in ["погода", "🌤 погода"]:
        user_last_city[message.from_user.id] = "awaiting_city"
        bot.send_message(message.chat.id, "Введите город:")
    elif text.lower() in ["курс", "💱 курсы валют"]:
        user_last_city[message.from_user.id] = "awaiting_currency"
        bot.send_message(message.chat.id, "Введите валюту (например USD, BTC):")

    # История
    elif text.lower() == "история":
        last = user_last_city.get(message.from_user.id)
        bot.send_message(message.chat.id, f"Ваш последний запрос: {last}")
    elif "погода" in text.lower():
        city = text.split("погода")[-1].strip()
        bot.send_message(message.chat.id, get_weather(city))
    elif "курс" in text.lower():
        code = text.split("курс")[-1].strip()
        bot.send_message(message.chat.id, get_exchange(code))

# --- Webhook ---
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    bot.process_new_updates([types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

@app.route("/", methods=["GET"])
def index():
    return "Bot is running!"

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{os.environ.get('RENDER_EXTERNAL_URL')}/{TOKEN}")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
