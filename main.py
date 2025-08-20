import os
import logging
import requests
from datetime import datetime
from flask import Flask, request
from telebot import TeleBot, types
from dotenv import load_dotenv

# Загружаем .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWM_API_KEY = os.getenv("OWM_API")  # ключ OpenWeatherMap
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")  # ключ Gemini
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

if not BOT_TOKEN or not OWM_API_KEY or not GEMINI_API_KEY or not RENDER_URL:
    raise Exception("Не заданы переменные окружения BOT_TOKEN, OWM_API, GOOGLE_API_KEY, RENDER_EXTERNAL_URL")

bot = TeleBot(BOT_TOKEN)
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ======= КНОПКИ =======
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🌤 Погода"))
    markup.add(types.KeyboardButton("🤖 ИИ"))
    return markup


# ======= Gemini =======
def ask_gemini(prompt: str) -> str:
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY
    }
    data = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ]
    }
    resp = requests.post(url, headers=headers, json=data)
    if resp.status_code != 200:
        return f"Ошибка Gemini API: {resp.status_code} - {resp.text}"

    try:
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return str(resp.json())


# ======= /start =======
@bot.message_handler(commands=["start"])
def start_handler(message):
    bot.send_message(message.chat.id, "Привет! Я бот 🤖\nВыбери действие:", reply_markup=main_menu())


# ======= Погода =======
@bot.message_handler(func=lambda m: m.text == "🌤 Погода")
def ask_city(message):
    bot.send_message(message.chat.id, "Введи название города:")


@bot.message_handler(func=lambda m: m.text == "🤖 ИИ")
def ask_ai(message):
    bot.send_message(message.chat.id, "Задай вопрос ИИ:")


# ======= Логика сообщений =======
@bot.message_handler(func=lambda m: True)
def handle_message(message):
    chat_id = message.chat.id
    text = message.text.strip()

    # Если пользователь хочет погоду
    if text and not text.startswith("/") and not text in ["🌤 Погода", "🤖 ИИ"]:
        # Пробуем сначала как город (погода)
        url = f"https://api.openweathermap.org/data/2.5/weather?q={text}&appid={OWM_API_KEY}&units=metric&lang=ru"
        forecast_url = f"https://api.openweathermap.org/data/2.5/forecast?q={text}&appid={OWM_API_KEY}&units=metric&lang=ru"

        try:
            r = requests.get(url).json()
            f = requests.get(forecast_url).json()

            if r.get("cod") != 200:
                # Если город не найден — пробуем как вопрос к ИИ
                answer = ask_gemini(text)
                bot.send_message(chat_id, f"🤖 Gemini ответ:\n{answer}")
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
                f"Погода в {text} сейчас:\n"
                f"{emoji} {desc}\n"
                f"🌡 Температура: {temp}°C\n"
                f"💧 Влажность: {humidity}%\n"
                f"🌬 Ветер: {wind} м/с\
