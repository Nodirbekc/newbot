import os
import telebot
from flask import Flask, request
import requests
from datetime import datetime

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWM_API = os.getenv("OWM_API")
EXCHANGE_API_KEY = os.getenv("EXCHANGE_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
user_histories = {}

# === Погода ===
def get_weather(city):
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&units=metric&appid={OWM_API}&lang=ru"
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            return "Ошибка: город не найден или API недоступен."
        data = res.json()
        sunrise = datetime.utcfromtimestamp(data['sys']['sunrise'] + data['timezone']).strftime('%H:%M')
        sunset = datetime.utcfromtimestamp(data['sys']['sunset'] + data['timezone']).strftime('%H:%M')
        return (
            f"🏙 Погода в {data['name']}, {data['sys']['country']}\n"
            f"🌡 Температура: {data['main']['temp']}°C (ощущается {data['main']['feels_like']}°C)\n"
            f"💨 Ветер: {data['wind']['speed']} м/с\n"
            f"💧 Влажность: {data['main']['humidity']}%\n"
            f"🌅 Восход: {sunrise}\n"
            f"🌇 Закат: {sunset}\n"
            f"☁ Осадки: {data['weather'][0]['description'].capitalize()}"
        )
    except:
        return "Ошибка получения погоды."

# === Курсы валют и крипты ===
def get_currency_rate(base, target):
    url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_API_KEY}/pair/{base}/{target}"
    r = requests.get(url, timeout=10)
    if r.status_code == 200 and "conversion_rate" in r.json():
        return r.json()["conversion_rate"]
    return None

def get_crypto_price(crypto, target):
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto.lower()}&vs_currencies={target.lower()}"
    r = requests.get(url, timeout=10)
    if r.status_code == 200:
        return r.json().get(crypto.lower(), {}).get(target.lower())
    return None

def convert_currency(amount, base, target):
    # 1. crypto → fiat
    crypto_to_fiat = get_crypto_price(base, target)
    if crypto_to_fiat:
        return amount * crypto_to_fiat

    # 2. fiat → crypto
    fiat_to_crypto = get_crypto_price(target, base)
    if fiat_to_crypto:
        return amount / fiat_to_crypto

    # 3. fiat → fiat
    rate = get_currency_rate(base, target)
    if rate:
        return amount * rate

    return None

# === Gemini AI ===
def ask_ai(user_id, text):
    if not GEMINI_API_KEY:
        return "Ошибка: ключ Gemini не задан."
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": text}]}]
        }
        headers = {"Content-Type": "application/json"}
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code == 200:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return f"ИИ недоступен (код {r.status_code})."
    except Exception as e:
        return f"Ошибка AI: {str(e)}"

# === Обработчики ===
@bot.message_handler(commands=['start'])
def start_message(message):
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Погода", "Конвертация валют", "ИИ")
    bot.send_message(message.chat.id, "Привет! Что тебя интересует?", reply_markup=keyboard)

@bot.message_handler(func=lambda m: m.text == "Погода")
def ask_city(message):
    bot.send_message(message.chat.id, "Напиши название города:")

@bot.message_handler(func=lambda m: m.text == "Конвертация валют")
def ask_currency(message):
    bot.send_message(message.chat.id, "Формат: <СУММА> <ИЗ_ВАЛЮТЫ> в <В_ВАЛЮТУ>\nПример: 10 BTC в USD")

@bot.message_handler(func=lambda m: m.text == "ИИ")
def ask_ai_message(message):
    bot.send_message(message.chat.id, "Напиши вопрос для ИИ:")

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    text = message.text.strip()

    # --- Конвертация ---
    if " в " in text.lower() and any(ch.isdigit() for ch in text):
        try:
            parts = text.split()
            amount = float(parts[0])
            idx = parts.index("в")
            base = parts[1].upper()
            target = parts[idx+1].upper()
            result = convert_currency(amount, base, target)
            if result is not None:
                bot.send_message(message.chat.id, f"{amount} {base} = {round(result, 6)} {target}")
            else:
                bot.send_message(message.chat.id, "Не удалось найти валюту или криптовалюту.")
        except Exception as e:
            bot.send_message(message.chat.id, f"Ошибка формата: {str(e)}\nПример: 10 BTC в USD")
        return

    # --- Погода ---
    weather = get_weather(text)
    if weather and not weather.startswith("Ошибка"):
        bot.send_message(message.chat.id, weather)
        return

    # --- ИИ ---
    answer = ask_ai(message.chat.id, text)
    bot.send_message(message.chat.id, answer)

# === Webhook ===
@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK", 200

@app.route("/")
def index():
    return "Бот работает", 200

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{os.getenv('RENDER_EXTERNAL_URL')}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
