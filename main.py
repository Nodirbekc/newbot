import os
import requests
import logging
from datetime import datetime
from flask import Flask, request
import pytz
from telebot import TeleBot, types

# Настройка
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWM_API_KEY = os.getenv("OWM_API")
EXCHANGE_API = os.getenv("EXCHANGE_API_KEY")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

logging.basicConfig(level=logging.INFO)
bot = TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Хранилище состояний для пользователя
user_state = {}  # chat_id: state
user_last_city = {}  # chat_id: last city

# Эмодзи по температуре
def emoji_for_temp(t):
    return "🥶" if t <= 0 else "🥵" if t >= 30 else "😊"

def format_time(ts, tz_name):
    tz = pytz.timezone(tz_name)
    dt = datetime.utcfromtimestamp(ts, pytz.utc).astimezone(tz)
    return dt.strftime('%H:%M')

# ———————————————— Обработчики ————————————————

# /start
@bot.message_handler(commands=['start'])
def cmd_start(msg):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🌤 Погода", "💱 Валюты")
    bot.send_message(msg.chat.id, "hillow hillow", reply_markup=kb)

# Кнопка «Погода»
@bot.message_handler(func=lambda m: m.text == "🌤 Погода")
def select_weather(m):
    user_state[m.chat.id] = "weather_ask"
    bot.send_message(m.chat.id, "В каком городе узнать погоду?")

# Кнопка «Валюты»
@bot.message_handler(func=lambda m: m.text == "💱 Валюты")
def select_currency(m):
    user_state[m.chat.id] = "currency_ask_dir"
    bot.send_message(m.chat.id,
        "Введите направление конверсии в формате: BTC->UZS или USD->KZT")

# Команда /last
@bot.message_handler(commands=['last'])
def cmd_last(msg):
    city = user_last_city.get(msg.chat.id)
    bot.send_message(msg.chat.id,
        f"Последний город: {city}" if city else "Истории нет")

# Общий текст-обработчик
@bot.message_handler(func=lambda m: True)
def all_text_handler(m):
    cid = m.chat.id
    text = m.text.strip()

    state = user_state.get(cid)
    if state == "weather_ask":
        user_last_city[cid] = text
        user_state[cid] = None
        weather = get_weather(text)
        bot.send_message(cid, weather)
        return

    if state == "currency_ask_dir":
        if "->" in text:
            user_state[cid] = ("currency_amount", text)
            bot.send_message(cid, "Введите сумму (только цифры):")
        else:
            bot.send_message(cid,
                "Неверный формат. Пример: BTC->UZS")
        return

    if isinstance(state, tuple) and state[0] == "currency_amount":
        _, direction = state
        parts = direction.upper().split("->")
        base, target = parts[0], parts[1]
        try:
            amount = float(text)
        except:
            bot.send_message(cid, "Нужна цифра, например: 10")
            return
        user_state[cid] = None
        result = convert_currency(base, target, amount)
        bot.send_message(cid, result)
        return

# ———————————————— Функции ————————————————

def get_weather(city):
    url = (f"http://api.openweathermap.org/data/2.5/weather"
           f"?q={city}&appid={OWM_API_KEY}&units=metric&lang=ru")
    res = requests.get(url).json()
    if res.get("cod") != 200:
        return "Город не найден."
    t = res["main"]["temp"]
    emoji = emoji_for_temp(t)
    s = (
        f"{emoji} Погода в {city}:\n"
        f"🌡 {res['main']['temp']}°C (ощущается как {res['main']['feels_like']}°C)\n"
        f"💧 Влажность: {res['main']['humidity']}%\n"
        f"💨 Ветер: {res['wind']['speed']} м/с\n"
        f"🌅 Восход: {format_time(res['sys']['sunrise'], 'Asia/Tashkent')}\n"
        f"🌇 Закат: {format_time(res['sys']['sunset'], 'Asia/Tashkent')}"
    )
    # Прогноз на 3 следующ. времени
    fc = get_forecast(city)
    return s + "\n\n🔮 Прогноз: \n" + fc

def get_forecast(city):
    url = (f"http://api.openweathermap.org/data/2.5/forecast"
           f"?q={city}&appid={OWM_API_KEY}&units=metric&lang=ru")
    res = requests.get(url).json()
    if res.get("cod") != "200":
        return "нет"
    out = ""
    for i, item in enumerate(res["list"][:3]):
        out += (f"{item['dt_txt'][5:16]} — {item['main']['temp']}°C, "
                f"{item['weather'][0]['description']}\n")
    return out

def convert_currency(base, target, amount):
    url = f"{EXCHANGE_API}?from={base}&to={target}&amount={amount}"
    r = requests.get(url).json()
    if not r.get("result") or not r.get("info"):
        return "Ошибка конверсии."
    rate = r["info"]["rate"]
    return f"{amount} {base} = {round(r['result'],4)} {target}\n💱 1 = {rate}"

# ———————————————— Webhook ————————————————

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    bot.process_new_updates([types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "", 200

@app.route("/", methods=["GET"])
def home():
    return "Bot is running", 200

# ———————————————— Запуск ————————————————

if __name__ == "__main__":
    if RENDER_URL:
        bot.remove_webhook()
        bot.set_webhook(url=f"{RENDER_URL}/{BOT_TOKEN}")
    else:
        logging.error("RENDER_EXTERNAL_URL не задан")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",5000)))
