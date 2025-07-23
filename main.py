import os
import requests
import redis
import telebot
from flask import Flask, request
from datetime import datetime
import pytz

# Токены
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWM_API = os.getenv("OWM_API")
EXCHANGE_API_KEY = os.getenv("EXCHANGE_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Redis для хранения истории ИИ
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST"),
    port=int(os.getenv("REDIS_PORT")),
    password=os.getenv("REDIS_PASSWORD"),
    decode_responses=True
)

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# --- Хранилище состояния пользователей ---
user_state = {}
last_city = {}

# --- Вспомогательные функции ---
def get_conversation_history(user_id):
    key = f"history:{user_id}"
    return redis_client.lrange(key, 0, -1) or []

def add_to_history(user_id, role, content):
    key = f"history:{user_id}"
    redis_client.rpush(key, f"{role}: {content}")
    redis_client.ltrim(key, -20, -1)

def get_weather(city):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OWM_API}&units=metric&lang=ru"
    r = requests.get(url)
    if r.status_code != 200:
        return None
    data = r.json()
    sunrise = datetime.utcfromtimestamp(data['sys']['sunrise'] + data['timezone']).strftime('%H:%M')
    sunset = datetime.utcfromtimestamp(data['sys']['sunset'] + data['timezone']).strftime('%H:%M')
    temp = data['main']['temp']
    if temp <= 0:
        emoji = "🥶"
    elif temp < 20:
        emoji = "🙂"
    else:
        emoji = "🥵"
    return (f"{emoji} Погода в {data['name']} ({data['sys']['country']}):\n"
            f"Температура: {temp}°C (ощущается как {data['main']['feels_like']}°C)\n"
            f"Влажность: {data['main']['humidity']}%\n"
            f"Ветер: {data['wind']['speed']} м/с\n"
            f"Давление: {data['main']['pressure']} hPa\n"
            f"Осадки: {data['weather'][0]['description']}\n"
            f"Восход: {sunrise}  Закат: {sunset}")

def convert_currency(amount, from_currency, to_currency):
    url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_API_KEY}/pair/{from_currency}/{to_currency}/{amount}"
    r = requests.get(url)
    if r.status_code != 200:
        return None
    data = r.json()
    return f"{amount} {from_currency} = {data['conversion_result']} {to_currency}"

def query_ai(user_id, message):
    history = get_conversation_history(user_id)
    context = "\n".join(history) + f"\nUser: {message}\nAI:"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    data = {"model": "openrouter/openai/gpt-3.5-turbo",
            "messages": [{"role": "user", "content": context}]}
    res = requests.post("https://openrouter.ai/api/v1/chat/completions",
                        headers=headers, json=data)
    ai_reply = res.json()["choices"][0]["message"]["content"]
    add_to_history(user_id, "User", message)
    add_to_history(user_id, "AI", ai_reply)
    return ai_reply

# --- Команды ---
@bot.message_handler(commands=['start'])
def start(message):
    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Погода", "Конвертация", "ИИ")
    bot.send_message(message.chat.id, "hillow hillow", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "Погода")
def weather_button(message):
    user_state[message.chat.id] = "weather"
    bot.send_message(message.chat.id, "Информацию о погоде какого города хотите узнать?")

@bot.message_handler(func=lambda m: m.text == "Конвертация")
def convert_button(message):
    user_state[message.chat.id] = "convert"
    bot.send_message(message.chat.id, "Напиши так: <сумма> <из валюты> <в валюту>\nПример: 10 USD UZS")

@bot.message_handler(func=lambda m: m.text == "ИИ")
def ai_button(message):
    user_state[message.chat.id] = "ai"
    bot.send_message(message.chat.id, "Задай свой вопрос ИИ:")

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    state = user_state.get(message.chat.id)
    if state == "weather":
        text = get_weather(message.text)
        if text:
            last_city[message.chat.id] = message.text
            bot.send_message(message.chat.id, text)
        else:
            bot.send_message(message.chat.id, "Не нашёл такой город. Попробуй ещё раз.")
        user_state[message.chat.id] = None

    elif state == "convert":
        try:
            parts = message.text.split()
            amount = float(parts[0])
            from_currency = parts[1].upper()
            to_currency = parts[2].upper()
            res = convert_currency(amount, from_currency, to_currency)
            bot.send_message(message.chat.id, res if res else "Ошибка при конвертации.")
        except:
            bot.send_message(message.chat.id, "Формат: 10 USD UZS")
        user_state[message.chat.id] = None

    elif state == "ai":
        ai_answer = query_ai(message.chat.id, message.text)
        bot.send_message(message.chat.id, ai_answer)
        user_state[message.chat.id] = None

# --- Flask (webhook) ---
@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK", 200

@app.route("/", methods=["GET"])
def index():
    return "Бот работает", 200

# --- Запуск ---
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{os.getenv('RENDER_EXTERNAL_URL')}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
