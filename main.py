import os
import logging
import requests
import pytz
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
import openai

# === ЛОГИ ===
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# === API ключи ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWM_API = os.getenv("OWM_API")
EXCHANGE_API_KEY = os.getenv("EXCHANGE_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

openai.api_key = OPENROUTER_API_KEY
openai.api_base = "https://openrouter.ai/api/v1"

# === История городов ===
last_city = {}

# === Смайлики для температуры ===
def temp_emoji(temp):
    if temp <= 0:
        return "🥶"
    elif temp < 20:
        return "🙂"
    else:
        return "🥵"

# === Погода ===
async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if len(context.args) == 0:
        await update.message.reply_text("Введите город: /weather <город>")
        return

    city = " ".join(context.args)
    last_city[chat_id] = city
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OWM_API}&units=metric&lang=ru"
    res = requests.get(url).json()

    if res.get("cod") != 200:
        await update.message.reply_text("Не удалось найти город.")
        return

    sunrise = datetime.utcfromtimestamp(res["sys"]["sunrise"] + res["timezone"]).strftime("%H:%M")
    sunset = datetime.utcfromtimestamp(res["sys"]["sunset"] + res["timezone"]).strftime("%H:%M")
    temp = res["main"]["temp"]
    text = (
        f"Погода в {res['name']} ({res['sys']['country']}): {temp}°C {temp_emoji(temp)}\n"
        f"Ощущается как {res['main']['feels_like']}°C\n"
        f"Влажность: {res['main']['humidity']}%\n"
        f"Давление: {res['main']['pressure']} hPa\n"
        f"Ветер: {res['wind']['speed']} м/с\n"
        f"Осадки: {res['weather'][0]['description']}\n"
        f"Восход: {sunrise}, Закат: {sunset}"
    )
    await update.message.reply_text(text)

# === Прогноз погоды (5 дней) ===
async def forecast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    city = last_city.get(chat_id)
    if not city:
        await update.message.reply_text("Сначала запросите погоду: /weather <город>")
        return

    url = f"https://api.openweathermap.org/data/2.5/forecast?q={city}&appid={OWM_API}&units=metric&lang=ru"
    res = requests.get(url).json()
    if res.get("cod") != "200":
        await update.message.reply_text("Ошибка прогноза.")
        return

    forecast_text = f"Прогноз погоды в {city}:\n"
    for entry in res["list"][:5]:
        dt = entry["dt_txt"]
        temp = entry["main"]["temp"]
        desc = entry["weather"][0]["description"]
        forecast_text += f"{dt}: {temp}°C, {desc}\n"

    await update.message.reply_text(forecast_text)

# === Конвертация валют ===
async def convert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text("Использование: /convert <сумма> <из> <в>")
        return

    amount, from_currency, to_currency = context.args
    try:
        amount = float(amount)
    except ValueError:
        await update.message.reply_text("Неверная сумма.")
        return

    url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_API_KEY}/latest/{from_currency.upper()}"
    res = requests.get(url).json()
    if res.get("result") != "success":
        await update.message.reply_text("Ошибка при получении данных.")
        return

    rate = res["conversion_rates"].get(to_currency.upper())
    if not rate:
        await update.message.reply_text("Валюта не найдена.")
        return

    result = amount * rate
    await update.message.reply_text(f"{amount} {from_currency.upper()} = {result:.2f} {to_currency.upper()}")

# === GPT ===
async def gpt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /gpt <запрос>")
        return

    prompt = " ".join(context.args)
    response = openai.ChatCompletion.create(
        model="openai/gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )
    answer = response["choices"][0]["message"]["content"]
    await update.message.reply_text(answer)

# === Старт ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = ReplyKeyboardMarkup([["Погода"]], resize_keyboard=True)
    await update.message.reply_text("hillow hillow", reply_markup=keyboard)

# === Групповой фильтр ===
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if "погода" in text:
        await update.message.reply_text("Используйте команду: /weather <город>")

# === MAIN ===
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("weather", weather))
    app.add_handler(CommandHandler("forecast", forecast))
    app.add_handler(CommandHandler("convert", convert))
    app.add_handler(CommandHandler("gpt", gpt))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_handler))
    app.run_webhook(listen="0.0.0.0", port=int(os.environ.get("PORT", 5000)),
                    webhook_url=f"{os.getenv('RENDER_EXTERNAL_URL')}/{BOT_TOKEN}")

if __name__ == "__main__":
    main()
