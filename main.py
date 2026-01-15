import os
import logging
import telebot
from flask import Flask
import threading

import google.generativeai as genai

# =======================
# ENV VARIABLES
# =======================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not BOT_TOKEN:
    raise Exception("BOT_TOKEN is missing")

if not GOOGLE_API_KEY:
    raise Exception("GOOGLE_API_KEY is missing")

# =======================
# LOGGING
# =======================

logging.basicConfig(level=logging.INFO)

# =======================
# TELEGRAM BOT
# =======================

bot = telebot.TeleBot(BOT_TOKEN)

# =======================
# GEMINI CONFIG
# =======================

genai.configure(api_key=GOOGLE_API_KEY)
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

def ask_gemini(prompt: str) -> str:
    try:
        response = gemini_model.generate_content(prompt)
        if response and response.text:
            return response.text
        return "❌ Пустой ответ от Gemini"
    except Exception as e:
        logging.error(f"Gemini error: {e}")
        return f"❌ Gemini error: {str(e)}"

# =======================
# BOT HANDLERS
# =======================

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(
        message,
        "Привет! 🤖\n\n"
        "Я бот с ИИ (Gemini).\n"
        "Просто напиши сообщение — я отвечу."
    )

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_text = message.text
    bot.send_chat_action(message.chat.id, "typing")
    answer = ask_gemini(user_text)
    bot.reply_to(message, answer)

# =======================
# FLASK (FOR RENDER)
# =======================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# =======================
# START
# =======================

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    logging.info("Bot started")
    bot.infinity_polling(skip_pending=True)
