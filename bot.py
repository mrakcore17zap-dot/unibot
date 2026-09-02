import os
import re
from datetime import datetime, timedelta
import pytz
import requests
from bs4 import BeautifulSoup
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import threading

# ===== КОНФИГУРАЦИЯ =====
TOKEN = os.getenv("TELEGRAM_TOKEN", "8778485093:AAEwSgzfZP4HbXZ2eUfoTvKEvBgdw7mhe9A")
YOUR_CHAT_ID = 1356969534
FACULTY = "1012"
COURSE = "1"
GROUP = "ТП-1-11"

# URL твоего бота на Render (измени, если имя другое)
RENDER_URL = "https://unibot-85cq.onrender.com"

# ===== ПАРСИНГ (исправленный) =====
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
        print(f"[ПАРСИНГ] Ошибка запроса: {e}")
        return None

    soup = BeautifulSoup(resp.text, 'html.parser')
    day_blocks = soup.find_all('div', class_='col-md-6')
    schedule = []
    for block in day_blocks:
        h4 = block.find('h4')
        if h4 and date_str in h4.get_text():
            table = block.find('table', class_='table')
            if not table:
                continue
            rows = table.find_all('tr')
            for row in rows:
                tds = row.find_all('td')
                if len(tds) < 3:
                    continue
                if not tds[2].get_text(strip=True):
                    continue
                num = tds[0].get_text(strip=True)
                time_raw = tds[1].get_text(strip=True).replace('\n', ' - ')
                zoom_link = None
                link_tag = tds[2].find('a', href=True)
                if link_tag:
                    zoom_link = link_tag['href']
                cell_text = tds[2].get_text(separator='\n').strip()
                lines = [line.strip() for line in cell_text.split('\n') if line.strip()]
                subject = ''
                teacher = ''
                for line in lines:
                    if 'онлайн' in line or 'очно' in line or 'відеоконференсія' in line or 'https://' in line:
                        continue
                    if not subject:
                        subject = line
                    else:
                        teacher = line if not teacher else teacher + ', ' + line
                if not subject and lines:
                    subject = lines[0]
                if not teacher and len(lines) > 1:
                    teacher = lines[1]
                schedule.append({
                    'num': num,
                    'time': time_raw,
                    'subject': subject,
                    'teacher': teacher,
                    'zoom': zoom_link
                })
            break
    print(f"[ПАРСИНГ] Найдено пар: {len(schedule)}")
    return schedule if schedule else []

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

# ===== ОБРАБОТЧИКИ =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("📚 Расписание на завтра", callback_data="tomorrow")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Привет! Я твой бот-расписание.\n"
        "Нажми кнопку ниже, чтобы узнать расписание на завтра.\n\n"
        "Каждый вечер в 20:00 я буду присылать расписание автоматически.",
        reply_markup=reply_markup
    )

async def tomorrow_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("⏳ Загружаю расписание...")
    kyiv_tz = pytz.timezone('Europe/Kiev')
    tomorrow = (datetime.now(kyiv_tz) + timedelta(days=1)).strftime("%d.%m.%Y")
    schedule = get_schedule_for_date(tomorrow)
    text = format_schedule(schedule, tomorrow)
    await query.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)

# ===== АВТОНАПОМИНАНИЕ (используем asyncio) =====
async def send_daily_schedule(app: Application):
    kyiv_tz = pytz.timezone('Europe/Kiev')
    tomorrow = (datetime.now(kyiv_tz) + timedelta(days=1)).strftime("%d.%m.%Y")
    schedule = get_schedule_for_date(tomorrow)
    text = format_schedule(schedule, tomorrow)
    await app.bot.send_message(chat_id=YOUR_CHAT_ID, text=text, parse_mode="Markdown", disable_web_page_preview=True)

# ===== НАСТРОЙКА WEBHOOK =====
app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(tomorrow_callback, pattern="tomorrow"))

# Планировщик для автоуведомлений
from apscheduler.schedulers.asyncio import AsyncIOScheduler
scheduler = AsyncIOScheduler()
scheduler.add_job(send_daily_schedule, "cron", hour=20, minute=0, args=[app])
scheduler.start()

# ===== FLASK ДЛЯ ПРИЁМА WEBHOOK =====
flask_app = Flask(__name__)

@flask_app.route('/')
def health():
    return "Bot is running!"

@flask_app.route('/webhook', methods=['POST'])
async def webhook():
    """Принимаем обновления от Telegram"""
    json_data = request.get_json(force=True)
    update = Update.de_json(json_data, app.bot)
    await app.process_update(update)
    return "ok"

@flask_app.route('/set_webhook', methods=['GET'])
def set_webhook():
    """Устанавливаем webhook (вызови один раз вручную)"""
    webhook_url = f"{RENDER_URL}/webhook"
    response = requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={webhook_url}")
    return response.json()

# ===== ЗАПУСК =====
if __name__ == "__main__":
    # Удаляем старый webhook (на всякий случай)
    requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")
    # Устанавливаем новый webhook
    webhook_url = f"{RENDER_URL}/webhook"
    requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={webhook_url}")
    print(f"Webhook установлен на {webhook_url}")
    # Запускаем Flask
    flask_app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
