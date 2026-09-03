import os
import threading
import time
import requests
from datetime import datetime, timedelta
import pytz
from bs4 import BeautifulSoup
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TOKEN = "8717215414:AAE_EDp-Z240EgXE8KlchuaTciWmbdiCqqw"  # вставь свой токен
YOUR_CHAT_ID = 7191243741

FACULTY = "1012"
COURSE = "1"
GROUP = "ТП-1-11"

# ===== ТЕСТОВАЯ ВЕРСИЯ ПАРСИНГА =====
def get_schedule_for_date(date_str: str) -> list:
    # Вместо реального парсинга возвращаем тестовые данные
    print(f"[ТЕСТ] Запрос для даты {date_str}")
    return [
        {
            'num': '1',
            'time': '08:15 - 09:35',
            'subject': 'Тестовый предмет',
            'teacher': 'Тестовый преподаватель',
            'zoom': 'https://zoom.us/test'
        },
        {
            'num': '2',
            'time': '09:50 - 11:10',
            'subject': 'Ещё тест',
            'teacher': 'Другой преподаватель',
            'zoom': None
        }
    ]

def format_schedule(schedule: list, date_str: str) -> str:
    if not schedule:
        return f"📅 На {date_str} занятий нет."
    try:
        dt = datetime.strptime(date_str, "%d.%m.%Y")
        weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        dow = weekdays[dt.weekday()]
    except:
        dow = ""
    text = f"📅 *{date_str} ({dow})* (ТЕСТ)\n\n"
    for item in schedule:
        text += f"🔹 *{item['num']} пара*  ({item['time']})\n"
        text += f"📖 {item['subject']}\n"
        if item['teacher']:
            text += f"👨‍🏫 {item['teacher']}\n"
        if item['zoom']:
            text += f"🔗 [Zoom-ссылка]({item['zoom']})\n"
        text += "\n"
    return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("📚 Расписание на завтра", callback_data="tomorrow")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Привет! Это тестовая версия.\n"
        "Нажми кнопку, чтобы получить тестовое расписание.",
        reply_markup=reply_markup
    )

async def tomorrow_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("⏳ Генерирую тестовое расписание...")
    kyiv_tz = pytz.timezone('Europe/Kiev')
    tomorrow = (datetime.now(kyiv_tz) + timedelta(days=1)).strftime("%d.%m.%Y")
    schedule = get_schedule_for_date(tomorrow)
    text = format_schedule(schedule, tomorrow)
    await query.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)

async def send_daily_schedule(app: Application):
    kyiv_tz = pytz.timezone('Europe/Kiev')
    tomorrow = (datetime.now(kyiv_tz) + timedelta(days=1)).strftime("%d.%m.%Y")
    schedule = get_schedule_for_date(tomorrow)
    text = format_schedule(schedule, tomorrow)
    await app.bot.send_message(chat_id=YOUR_CHAT_ID, text=text, parse_mode="Markdown", disable_web_page_preview=True)

flask_app = Flask(__name__)

@flask_app.route('/')
def health():
    return "Bot is running!"

def run_flask():
    flask_app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)), debug=False)

def main():
    try:
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")
    except:
        pass
    time.sleep(1)

    thread = threading.Thread(target=run_flask)
    thread.daemon = True
    thread.start()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(tomorrow_callback, pattern="tomorrow"))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_daily_schedule, "cron", hour=20, minute=0, args=[app])
    scheduler.start()

    print("Бот запущен (тестовая версия)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
