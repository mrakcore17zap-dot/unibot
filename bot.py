import os
import re
import asyncio
from datetime import datetime, timedelta
import pytz  # добавил для работы с часовыми поясами

import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask  # для веб-сервера
import threading

# ===== КОНФИГУРАЦИЯ =====
TOKEN = os.getenv("TELEGRAM_TOKEN", "8825040548:AAEzOeCHQT1zHFFPm8lixSd0C8Dwf2QMeI4")
YOUR_CHAT_ID = 1356969534

FACULTY = "1012"
COURSE = "1"
GROUP = "ТП-1-11"

# ===== ФУНКЦИЯ ПАРСИНГА =====
def get_schedule_for_date(date_str: str) -> list:
    url = "https://nmu.nuft.edu.ua/timetable.cgi?n=700"
    payload = {
        'faculty': FACULTY,
        'course': COURSE,
        'group': GROUP,
        'sdate': date_str,
        'edate': date_str,
        'n': '700'
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    try:
        resp = requests.post(url, data=payload, headers=headers, timeout=15)
        resp.encoding = 'windows-1251'
    except Exception as e:
        print(f"Ошибка запроса: {e}")
        return None

    soup = BeautifulSoup(resp.text, 'html.parser')
    day_blocks = soup.find_all('div', class_='col-md-6')
    schedule = []
    for block in day_blocks:
        h4 = block.find('h4')
        if h4 and date_str in h4.get_text():
            table = block.find('table')
            if not table:
                continue
            rows = table.find_all('tr')
            for row in rows:
                tds = row.find_all('td')
                if len(tds) < 3:
                    continue
                content_cell = tds[2]
                if content_cell.get_text(strip=True) == '':
                    continue

                num = tds[0].get_text(strip=True)
                time_raw = tds[1].get_text(strip=True).replace('\n', ' - ')

                zoom_link = None
                link_tag = content_cell.find('a', href=True)
                if link_tag:
                    zoom_link = link_tag['href']

                for br in content_cell.find_all('br'):
                    br.replace_with('\n')
                text = content_cell.get_text(separator='\n')
                lines = [line.strip() for line in text.split('\n') if line.strip()]

                subject = ''
                teacher = ''
                for line in lines:
                    if 'онлайн' in line or 'очно' in line:
                        continue
                    if 'відеоконференсія' in line:
                        continue
                    if 'https://' in line or 'http://' in line:
                        continue
                    if not subject:
                        subject = line
                    else:
                        if teacher:
                            teacher += ', ' + line
                        else:
                            teacher = line

                if not subject and lines:
                    subject = lines[0] if len(lines) > 0 else ''
                if not teacher and len(lines) > 1:
                    teacher = lines[1] if len(lines) > 1 else ''

                schedule.append({
                    'num': num,
                    'time': time_raw,
                    'subject': subject,
                    'teacher': teacher,
                    'zoom': zoom_link
                })
            break

    return schedule if schedule else None

# ===== ФОРМИРОВАНИЕ СООБЩЕНИЯ =====
def format_schedule(schedule: list, date_str: str) -> str:
    if not schedule:
        return f"📅 На {date_str} занятий нет или расписание не найдено."

    try:
        dt = datetime.strptime(date_str, "%d.%m.%Y")
        weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        dow = weekdays[dt.weekday()]
    except:
        dow = ""

    text = f"📅 *{date_str} ({dow})*\n\n"
    for item in schedule:
        text += f"🔹 *{item['num']} пара*  ({item['time']})\n"
        text += f"📖 {item['subject']}\n"
        if item['teacher']:
            text += f"👨‍🏫 {item['teacher']}\n"
        if item['zoom']:
            text += f"🔗 [Zoom-ссылка]({item['zoom']})\n"
        text += "\n"
    return text

# ===== ОБРАБОТЧИКИ КОМАНД =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("📚 Расписание на завтра", callback_data="tomorrow")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Привет! Я твой бот-расписание.\n"
        "Нажми кнопку ниже, чтобы узнать расписание на завтра.\n\n"
        "Также каждый вечер в 20:00 я буду присылать расписание автоматически.",
        reply_markup=reply_markup
    )

async def tomorrow_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Используем Киевское время
    kyiv_tz = pytz.timezone('Europe/Kiev')
    tomorrow = (datetime.now(kyiv_tz) + timedelta(days=1)).strftime("%d.%m.%Y")
    schedule = get_schedule_for_date(tomorrow)
    text = format_schedule(schedule, tomorrow)
    await query.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)

# ===== АВТОМАТИЧЕСКОЕ НАПОМИНАНИЕ =====
async def send_daily_schedule(app: Application):
    kyiv_tz = pytz.timezone('Europe/Kiev')
    tomorrow = (datetime.now(kyiv_tz) + timedelta(days=1)).strftime("%d.%m.%Y")
    schedule = get_schedule_for_date(tomorrow)
    text = format_schedule(schedule, tomorrow)
    await app.bot.send_message(chat_id=YOUR_CHAT_ID, text=text, parse_mode="Markdown", disable_web_page_preview=True)

# ===== ВЕБ-СЕРВЕР ДЛЯ RENDER (чтобы был порт) =====
app_web = Flask(__name__)

@app_web.route('/')
def health_check():
    return "Bot is running!"

def run_web():
    app_web.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))

# ===== ЗАПУСК БОТА =====
def main():
    # Запускаем веб-сервер в отдельном потоке
    thread = threading.Thread(target=run_web)
    thread.daemon = True
    thread.start()

    # Запускаем Telegram-бота
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(tomorrow_callback, pattern="tomorrow"))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_daily_schedule, "cron", hour=20, minute=0, args=[app])
    scheduler.start()

    print("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
