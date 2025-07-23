import os
import telebot
from flask import Flask, request
import requests
import pytz
from datetime import datetime

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWM_API = os.getenv("OWM_API")
EXCHANGE_API_KEY = os.getenv("EXCHANGE_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ==== История диалогов для ИИ ====
user_histories = {}

# ==== Функции вспомогательные ====
def get_weather(city):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&units=metric&appid={OWM_API}&lang=ru"
    res = requests.get(url)
    if res.status_code != 200:
        return None
    data = res.json()
    sunrise = datetime.utcfromtimestamp(data['sys']['sunrise'] + data['timezone']).strftime('%H:%M')
    sunset = datetime.utcfromtimestamp(data['sys']['sunset'] + data['timezone']).strftime('%H:%M')
    text = (
        f"🏙 Погода в {data['name']}, {data['sys']['country']}\n"
        f"🌡 Температура: {data['main']['temp']}°C (ощущается {data['main']['feels_like']}°C)\n"
        f"💨 Ветер: {data['wind']['speed']} м/с\n"
        f"💧 Влажность: {data['main']['humidity']}%\n"
        f"🌅 Восход: {sunrise}\n"
        f"🌇 Закат: {sunset}\n"
        f"☁ Осадки: {data['weather'][0]['description']}"
    )
    return text

def get_currency_rate(base, target):
    url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_API_KEY}/pair/{base}/{target}"
    r = requests.get(url)
    if r.status_code == 200:
        return r.json().get("conversion_rate")
    return None

def get_crypto_price(crypto, target):
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto.lower()}&vs_currencies={target.lower()}"
    r = requests.get(url)
    if r.status_code == 200:
        return r.json().get(crypto.lower(), {}).get(target.lower())
    return None

def ask_ai(user_id, text):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    messages = user_histories.get(user_id, [])
    messages.append({"role": "user", "content": text})
    payload = {
        "model": "openrouter/gpt-3.5-turbo",
        "messages": messages
    }
    r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
    if r.status_code == 200:
        answer = r.json()['choices'][0]['message']['content']
        messages.append({"role": "assistant", "content": answer})
        user_histories[user_id] = messages[-10:]
        return answer
    return "Ошибка AI."

# ==== Обработчики ====
@bot.message_handler(commands=['start'])
def start_message(message):
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Погода", "Конвертация валют", "ИИ")
    bot.send_message(message.chat.id, "hillow hillow", reply_markup=keyboard)

@bot.message_handler(func=lambda m: m.text == "Погода")
def ask_city(message):
    bot.send_message(message.chat.id, "Информацию о погоде какого города хотите узнать?")

@bot.message_handler(func=lambda m: m.text == "Конвертация валют")
def ask_currency(message):
    bot.send_message(message.chat.id, "Напиши: <СУММА> <ИЗ_ВАЛЮТЫ> в <В_ВАЛЮТУ>\nПример: 10 BTC в USD")

@bot.message_handler(func=lambda m: m.text == "ИИ")
def ask_ai_message(message):
    bot.send_message(message.chat.id, "Напиши вопрос для AI:")

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    text = message.text.strip()

    # Конвертация валют/крипты
    if " в " in text and any(ch.isdigit() for ch in text):
        try:
            amount, from_to = text.split(" ", 1)
            amount = float(amount)
            base, target = from_to.upper().split(" В ")
            # Проверка крипты
            crypto_price = get_crypto_price(base, target)
            if crypto_price:
                bot.send_message(message.chat.id, f"{amount} {base} = {amount * crypto_price} {target}")
                return
            rate = get_currency_rate(base, target)
            if rate:
                bot.send_message(message.chat.id, f"{amount} {base} = {round(amount*rate, 2)} {target}")
            else:
                bot.send_message(message.chat.id, "Не удалось найти валюту.")
        except:
            bot.send_message(message.chat.id, "Формат неправильный. Пример: 10 BTC в USD")
        return

    # Погода
    weather = get_weather(text)
    if weather:
        bot.send_message(message.chat.id, weather)
        return

    # AI
    answer = ask_ai(message.chat.id, text)
    bot.send_message(message.chat.id, answer)

# ==== Webhook ====
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
