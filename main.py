import os
import telebot
import requests
from telebot import types
from flask import Flask, request

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWM_API_KEY = os.getenv("OWM_API")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Команда /start
@bot.message_handler(commands=['start'])
def start_handler(message):
    bot.send_message(message.chat.id, "hillow hillow")
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("Погода"))
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)

# Обработка кнопки "Погода"
@bot.message_handler(func=lambda msg: msg.text == "Погода")
def ask_city(message):
    bot.send_message(message.chat.id, "Информацию о погоде какого города или страны хотите узнать?")
    bot.register_next_step_handler(message, get_weather)

# Получение и отправка погоды
def get_weather(message):
    city = message.text.strip()
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OWM_API_KEY}&units=metric&lang=ru"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        weather = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        feels_like = data["main"]["feels_like"]
        bot.send_message(
            message.chat.id,
            f"🌤 Погода в {city}:\n"
            f"Описание: {weather}\n"
            f"Температура: {temp}°C\n"
            f"Ощущается как: {feels_like}°C"
        )
    else:
        bot.send_message(message.chat.id, "❌ Город не найден. Попробуйте ещё раз.")

# Обработка webhook от Render
@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "ok", 200

# Запуск приложения
if __name__ == "__main__":
    RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
    if not RENDER_EXTERNAL_URL:
        print("❌ Ошибка: переменная окружения RENDER_EXTERNAL_URL не задана.")
        exit(1)

    bot.remove_webhook()
    bot.set_webhook(url=f"{RENDER_EXTERNAL_URL}/{BOT_TOKEN}")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
