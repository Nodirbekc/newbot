import os
import logging
import requests
import json
import pickle
from datetime import datetime, timedelta
from flask import Flask, request
from telebot import TeleBot, types
import re

# Настройки
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWM_API_KEY = os.environ.get("OWM_API")
GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")

if not all([BOT_TOKEN, OWM_API_KEY, GEMINI_API_KEY, DEEPSEEK_API_KEY, RENDER_URL]):
    raise Exception("Не все переменные окружения заданы")

bot = TeleBot(BOT_TOKEN)
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Константы
MAX_MESSAGES_PER_USER = 50
MAX_HISTORY_DAYS = 7
HISTORY_FILE = "user_dialogs.pkl"

# Структура для хранения сообщений
class DialogMessage:
    def __init__(self, role: str, text: str, ai_model: str = None):
        self.role = role
        self.text = text
        self.timestamp = datetime.now()
        self.ai_model = ai_model  # Какой ИИ ответил
    
    def to_dict(self):
        return {
            "role": self.role,
            "text": self.text,
            "timestamp": self.timestamp.isoformat(),
            "ai_model": self.ai_model
        }

# Загрузка и сохранение истории
user_dialogs = {}
user_states = {}
user_modes = {}  # Режимы пользователей: 'default', 'study', 'coding', 'creative'

def load_dialogs():
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'rb') as f:
                return pickle.load(f)
    except:
        return {}

def save_dialogs():
    try:
        with open(HISTORY_FILE, 'wb') as f:
            pickle.dump(user_dialogs, f)
    except Exception as e:
        logging.error(f"Error saving: {e}")

user_dialogs = load_dialogs()

# ======= AI APIs =======
def ask_deepseek(prompt: str, history: list = None) -> str:
    """DeepSeek API"""
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    messages = [{"role": "system", "content": "Ты полезный и точный ассистент."}]
    
    if history:
        for msg in history[-6:]:  # Последние 6 сообщений для контекста
            messages.append({"role": "user" if msg.role == "user" else "assistant", "content": msg.text})
    
    messages.append({"role": "user", "content": prompt})
    
    data = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2000
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Ошибка DeepSeek: {str(e)}"

def ask_gemini(prompt: str) -> str:
    """Gemini API"""
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY
    }
    
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"Ошибка Gemini: {str(e)}"

# ======= ИНТЕГРАЦИЯ 2: Умный роутер =======
def smart_router(user_id: int, user_query: str) -> tuple:
    """Определяет какой ИИ использовать и в каком режиме"""
    
    # Проверяем явный режим пользователя
    current_mode = user_modes.get(user_id, 'default')
    
    # Ключевые слова для определения лучшего ИИ
    technical_keywords = ["код", "программир", "алгоритм", "математик", "физик", "наук", "технич", "логик"]
    creative_keywords = ["придумай", "создай", "напиши историю", "креатив", "историю", "стих", "рассказ", "сценарий"]
    study_keywords = ["учиться", "урок", "задач", "учеб", "объясни", "как решить", "теория"]
    coding_keywords = ["python", "java", "c++", "функция", "переменн", "баг", "ошибка", "синтаксис"]
    
    query_lower = user_query.lower()
    
    # Определяем режим на основе запроса
    if any(keyword in query_lower for keyword in study_keywords):
        user_modes[user_id] = 'study'
        return 'study', 'deepseek'
    
    if any(keyword in query_lower for keyword in coding_keywords):
        user_modes[user_id] = 'coding'
        return 'coding', 'deepseek'
    
    if any(keyword in query_lower for keyword in creative_keywords):
        user_modes[user_id] = 'creative'
        return 'creative', 'gemini'
    
    if any(keyword in query_lower for keyword in technical_keywords):
        return current_mode, 'deepseek'
    
    # По умолчанию
    return current_mode, 'deepseek'

# ======= ИНТЕГРАЦИЯ 3: Специализированные режимы =======
def study_assistant_mode(query: str, history: list) -> str:
    """Режим репетитора"""
    prompt = f"""
    Ты экспертный репетитор с PhD уровнем знаний. Объясняй максимально понятно.
    
    Контекст из предыдущих сообщений: {[msg.text for msg in history[-3:]] if history else 'Нет'}
    
    Вопрос студента: {query}
    
    Ответь строго в формате:
    🎯 ОСНОВНАЯ КОНЦЕПЦИЯ: [1-2 предложения]
    📚 ПОДРОБНОЕ ОБЪЯСНЕНИЕ: [2-3 абзаца]
    🧪 ПРАКТИЧЕСКИЙ ПРИМЕР: [конкретный пример]
    ⚠️ ЧАСТЫЕ ОШИБКИ: [что избегать]
    """
    return ask_deepseek(prompt, history)

def coding_helper_mode(query: str, history: list) -> str:
    """Режим программирования"""
    prompt = f"""
    Ты senior developer с 10+ лет опыта. Давай идеальные решения.
    
    Контекст: {[msg.text for msg in history[-3:]] if history else 'Нет'}
    
    Запрос: {query}
    
    Ответь в формате:
    🔍 АНАЛИЗ ПРОБЛЕМЫ: [в чем суть]
    💻 РЕШЕНИЕ: [код с комментариями]
    📖 ОБЪЯСНЕНИЕ: [почему так работает]
    🚀 АЛЬТЕРНАТИВЫ: [другие подходы]
    """
    return ask_deepseek(prompt, history)

def creative_mode(query: str) -> str:
    """Креативный режим"""
    prompt = f"""
    Ты креативный писатель и художник. Создавай вдохновляющий контент.
    
    Запрос: {query}
    
    Создай что-то уникальное и engaging!
    """
    return ask_gemini(prompt)

# ======= ИНТЕГРАЦИЯ 4: Multi-Agent система =======
def multi_agent_discussion(user_query: str, history: list) -> str:
    """Несколько ИИ агентов обсуждают вопрос"""
    
    # Агент 1: Эксперт
    expert_prompt = f"""
    Как domain expert с глубокими знаниями, дай развернутый ответ:
    {user_query}
    
    Будь максимально точным и профессиональным.
    """
    expert_answer = ask_deepseek(expert_prompt, history)
    
    # Агент 2: Критик
    critic_prompt = f"""
    Проанализируй этот ответ как строгий рецензент:
    {expert_answer}
    
    Найди: 1) Фактические ошибки, 2) Пропущенные важные моменты, 
    3) Сложные для понимания части, 4) Возможные улучшения
    """
    critic_feedback = ask_deepseek(critic_prompt)
    
    # Агент 3: Объяснятель
    explainer_prompt = f"""
    Объясни это понятно для новичка:
    {expert_answer}
    
    Сделай объяснение простым, с аналогиями и примерами.
    """
    explainer_version = ask_deepseek(explainer_prompt)
    
    # Финальный синтезатор
    final_prompt = f"""
    Синтезируй идеальный ответ из трех perspectives:
    
    ЭКСПЕРТ: {expert_answer}
    КРИТИК: {critic_feedback}
    ОБЪЯСНИТЕЛЬ: {explainer_version}
    
    Создай финальный ответ который: точен, полон, и понятен.
    """
    return ask_deepseek(final_prompt)

# ======= Основная обработка =======
def process_message(user_id: int, user_query: str) -> str:
    """Основная функция обработки сообщений"""
    
    # Получаем историю
    history = user_dialogs.get(user_id, [])
    
    # Определяем режим и ИИ
    mode, ai_engine = smart_router(user_id, user_query)
    
    # Сохраняем запрос пользователя
    add_to_dialog(user_id, "user", user_query)
    
    # Выбираем обработчик based on mode
    if mode == 'study':
        response = study_assistant_mode(user_query, history)
    elif mode == 'coding':
        response = coding_helper_mode(user_query, history)
    elif mode == 'creative':
        response = creative_mode(user_query)
    elif "сложн" in user_query.lower() or "обсуди" in user_query.lower():
        response = multi_agent_discussion(user_query, history)
        ai_engine = "multi-agent"
    else:
        # Default processing
        if ai_engine == 'deepseek':
            response = ask_deepseek(user_query, history)
        else:
            response = ask_gemini(user_query)
    
    # Сохраняем ответ
    add_to_dialog(user_id, "assistant", response, ai_engine)
    save_dialogs()
    
    return response

def add_to_dialog(user_id: int, role: str, text: str, ai_model: str = None):
    if user_id not in user_dialogs:
        user_dialogs[user_id] = []
    user_dialogs[user_id].append(DialogMessage(role, text, ai_model))
    if len(user_dialogs[user_id]) > MAX_MESSAGES_PER_USER:
        user_dialogs[user_id] = user_dialogs[user_id][-MAX_MESSAGES_PER_USER:]

# ======= Telegram Handlers =======
@bot.message_handler(commands=["start"])
def start_handler(message):
    user_id = message.chat.id
    user_states[user_id] = "main_menu"
    user_modes[user_id] = "default"
    bot.send_message(user_id, 
                    "🤖 Привет! Я умный помощник с несколькими ИИ мозгами!\n"
                    "Выбери режим или просто спроси что-то:", 
                    reply_markup=main_menu())

@bot.message_handler(commands=["mode_study"])
def set_study_mode(message):
    user_id = message.chat.id
    user_modes[user_id] = "study"
    bot.send_message(user_id, "🎓 Режим репетитора активирован! Задавай учебные вопросы.")

@bot.message_handler(commands=["mode_code"])
def set_code_mode(message):
    user_id = message.chat.id
    user_modes[user_id] = "coding"
    bot.send_message(user_id, "💻 Режим программирования активирован! Задавай технические вопросы.")

@bot.message_handler(commands=["mode_creative"])
def set_creative_mode(message):
    user_id = message.chat.id
    user_modes[user_id] = "creative"
    bot.send_message(user_id, "🎨 Креативный режим активирован! Давай творить!")

@bot.message_handler(commands=["multi_ai"])
def multi_ai_mode(message):
    user_id = message.chat.id
    bot.send_message(user_id, "🧠 Multi-Agent режим! Несколько ИИ будут обсуждать твой вопрос.")

@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    user_id = message.chat.id
    user_query = message.text
    
    if user_query in ["🌤 Погода", "🤖 ИИ"]:
        # Обработка кнопок
        if user_query == "🌤 Погода":
            user_states[user_id] = "waiting_city"
            bot.send_message(user_id, "Введи название города:")
        else:
            bot.send_message(user_id, "Задай любой вопрос!")
        return
    
    if user_states.get(user_id) == "waiting_city":
        # Обработка погоды
        handle_weather_request(message)
        return
    
    # Обработка ИИ запросов
    thinking_msg = bot.send_message(user_id, "🤔 Думаю...")
    
    try:
        response = process_message(user_id, user_query)
        
        # Добавляем информацию о использованном ИИ
        last_msg = user_dialogs.get(user_id, [])[-1] if user_dialogs.get(user_id) else None
        ai_info = f" (via {last_msg.ai_model})" if last_msg and last_msg.ai_model else ""
        
        bot.delete_message(user_id, thinking_msg.message_id)
        bot.send_message(user_id, f"{response}{ai_info}")
        
    except Exception as e:
        bot.send_message(user_id, f"⚠️ Ошибка: {str(e)}")

# ======= Кнопки =======
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🌤 Погода"))
    markup.add(types.KeyboardButton("🤖 ИИ"))
    markup.row(types.KeyboardButton("🎓 Режим учебы"), types.KeyboardButton("💻 Режим кода"))
    markup.add(types.KeyboardButton("🎨 Креативный режим"), types.KeyboardButton("🧠 Multi-AI"))
    return markup

# ... остальной код вебхуков и Flask ...

# Запуск
if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(url=RENDER_URL + '/' + BOT_TOKEN)
    app.run(host='0.0.0.0', port=5000)
