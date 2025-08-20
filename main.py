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

# Хранилище состояний пользователей
user_states = {}

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
    try:
        resp = requests.post(url, headers=headers, json=data, timeout=30)
        if resp.status_code != 200:
            return f"Ошибка Gemini API: {resp.status_code} - {resp.text}"

        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"Произошла ошибка при обращении к Gemini: {str(e)}"

# ======= /start =======
@bot.message_handler(commands=["start"])
def start_handler(message):
    user_id = message.chat.id
    user_states[user_id] = "main_menu"
    bot.send_message(message.chat.id, "Привет! Я бот 🤖\nВыбери действие:", reply_markup=main_menu())

# ======= Погода =======
@bot.message_handler(func=lambda m: m.text == "🌤 Погода")
def ask_city(message):
    user_id = message.chat.id
    user_states[user_id] = "waiting_city"
    bot.send_message(message.chat.id, "Введи название города:")

@bot.message_handler(func=lambda m: m.text == "🤖 ИИ")
def ask_ai(message):
    user_id = message.chat.id
    user_states[user_id] = "waiting_ai_question"
    bot.send_message(message.chat.id, "Задай вопрос ИИ:")

# ======= Обработка запросов погоды =======
@bot.message_handler(func=lambda m: user_states.get(m.chat.id) == "waiting_city")
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
        
        # Парсим данные о погоде
        temp = data["main"]["temp"]
        desc = data["weather"][0]["description"].capitalize()
        humidity = data["main"]["humidity"]
        wind = data["wind"]["speed"]
        sunrise = datetime.utcfromtimestamp(data["sys"]["sunrise"]).strftime('%H:%M')
        sunset = datetime.utcfromtimestamp(data["sys"]["sunset"]).strftime('%H:%M')

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
            f"🌅 Восход: {sunrise}\n"
            f"🌇 Закат: {sunset}"
        )
        
        bot.send_message(chat_id, msg)
        user_states[chat_id] = "main_menu"
        
    except Exception as e:
        bot.send_message(chat_id, f"Произошла ошибка: {str(e)}")
        user_states[chat_id] = "main_menu"

# ======= Обработка запросов к ИИ =======
@bot.message_handler(func=lambda m: user_states.get(m.chat.id) == "waiting_ai_question")
def handle_ai_request(message):
    chat_id = message.chat.id
    question = message.text.strip()
    
    if not question:
        bot.send_message(chat_id, "Вопрос не может быть пустым. Попробуй еще раз:")
        return
    
    bot.send_message(chat_id, "🤖 Думаю...")
    
    try:
        answer = ask_gemini(question)
        bot.send_message(chat_id, f"🤖 Gemini ответ:\n\n{answer}")
        user_states[chat_id] = "main_menu"
        
    except Exception as e:
        bot.send_message(chat_id, f"Произошла ошибка при обработке запроса: {str(e)}")
        user_states[chat_id] = "main_menu"

# ======= Обработка неизвестных команд =======
@bot.message_handler(func=lambda m: True)
def handle_unknown(message):
    chat_id = message.chat.id
    if chat_id not in user_states:
        user_states[chat_id] = "main_menu"
    
    if user_states[chat_id] == "main_menu":
        bot.send_message(chat_id, "Выбери действие из меню:", reply_markup=main_menu())
    else:
        bot.send_message(chat_id, "Не понимаю команду. Выбери действие из меню:", reply_markup=main_menu())
        user_states[chat_id] = "main_menu"
