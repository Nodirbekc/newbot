import os
import telebot
from flask import Flask, request
import requests
import pytz
from datetime import datetime, timedelta

# === API ключи из Render ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWM_API = os.getenv("OWM_API")
EXCHANGE_API_KEY = os.getenv("EXCHANGE_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Хранилище истории
user_last_city = {}

# === Клавиатура ===
def main_keyboard():
    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Погода", "Курс", "ИИ")
    return kb

# === Команда /start ===
@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(message.chat.id, "hillow hillow", reply_markup=main_keyboard())

# === Погода ===
@bot.message_handler(func=lambda m: m.text == "Погода")
def weather_request(message):
    bot.send_message(message.chat.id, "Информацию о погоде какого города или страны хотите узнать?")

@bot.message_handler(func=lambda m: m.text not in ["Погода", "Курс", "ИИ"] and message_has_weather_context(m))
def weather_response(message):
    city = message.text.strip()
    user_last_city[message.from_user.id] = city
    send_weather_info(message.chat.id, city)

def message_has_weather_context(message):
    return user_last_city.get(message.from_user.id, None) is None or message.text.lower() not in ["курс", "ии"]

def send_weather_info(chat_id, city):
    url = f"https://api.openweathermap.org/data/2.5/forecast?q={city}&units=metric&lang=ru&appid={OWM_API}"
    res = requests.get(url)
    if res.status_code != 200:
        bot.send_message(chat_id, "Не нашёл такой город. Попробуй ещё раз.")
        return
    data = res.json()
    current = data["list"][0]
    temp = current["main"]["temp"]
    feels = current["main"]["feels_like"]
    wind = current["wind"]["speed"]
    desc = current["weather"][0]["description"]
    humidity = current["main"]["humidity"]

    emoji = "🥶" if temp < 0 else "😎" if temp > 30 else "🙂"
    text = (f"{emoji} Погода в {data['city']['name']} ({data['city']['country']}):\n"
            f"Температура: {temp}°C (ощущается как {feels}°C)\n"
            f"Ветер: {wind} м/с\n"
            f"Осадки: {desc}\n"
            f"Влажность: {humidity}%\n\n"
            "Прогноз на 3 дня:\n")
    for i in range(1, 4):
        day = data["list"][i*8]
        date = datetime.utcfromtimestamp(day["dt"]) + timedelta(hours=data["city"]["timezone"]/3600)
        text += f"- {date.strftime('%d.%m %H:%M')}: {day['main']['temp']}°C, {day['weather'][0]['description']}\n"
    bot.send_message(chat_id, text)

# === Конвертация валют ===
@bot.message_handler(func=lambda m: m.text == "Курс")
def ask_currency(message):
    bot.send_message(message.chat.id, "Напиши валюту и во что перевести (например: `10 BTC USD` или `100 USD UZS`).")

@bot.message_handler(func=lambda m: len(m.text.split()) == 3 and m.text not in ["Погода", "ИИ"])
def convert_currency(message):
    try:
        amount, from_cur, to_cur = message.text.upper().split()
        amount = float(amount)
        url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_API_KEY}/pair/{from_cur}/{to_cur}/{amount}"
        r = requests.get(url)
        data = r.json()
        if r.status_code == 200 and data["result"] == "success":
            result = data["conversion_result"]
            bot.send_message(message.chat.id, f"{amount} {from_cur} = {result} {to_cur}")
        else:
            bot.send_message(message.chat.id, "Ошибка при конвертации валют.")
    except:
        bot.send_message(message.chat.id, "Формат: `10 BTC USD`")

# === Чат с ИИ ===
@bot.message_handler(func=lambda m: m.text == "ИИ")
def ask_ai(message):
    bot.send_message(message.chat.id, "Задай вопрос ИИ:")

@bot.message_handler(func=lambda m: user_last_city.get(m.from_user.id) and m.text not in ["Погода", "Курс", "ИИ"])
def ai_answer(message):
    query = message.text.strip()
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "model": "openai/gpt-3.5-turbo",
        "messages": [{"role": "user", "content": query}]
    }
    res = requests.post("https://openrouter.ai/api/v1/chat/completions", json=body, headers=headers)
    if res.status_code == 200:
        ans = res.json()["choices"][0]["message"]["content"]
        bot.send_message(message.chat.id, ans)
    else:
        bot.send_message(message.chat.id, "Ошибка при запросе к ИИ.")

# === Webhook ===
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK", 200

@app.route("/")
def index():
    return "Бот работает", 200

# === Запуск ===
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{os.getenv('RENDER_EXTERNAL_URL')}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
