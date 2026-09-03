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

TOKEN = "8717215414:AAE_EDp-Z240EgXE8KlchuaTciWmbdiCqqw"  # вставь свой работающий токен
YOUR_CHAT_ID = 7191243741

FACULTY = "1012"
COURSE = "1"
GROUP = "ТП-1-11"

# ===== РЕАЛЬНЫЙ ПАРСИНГ С ОТЛАДКОЙ =====
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

    print(f"[ОТЛАДКА] Отправляем запрос на {url} с payload={payload}")

    try:
        resp = requests.post(url, data=payload, headers=headers, timeout=15)
        resp.encoding = 'windows-1251'
        print(f"[ОТЛАДКА] Статус ответа: {resp.status_code}")
        print(f"[ОТЛАДКА] Первые 500 символов ответа:\n{resp.text[:500]}")
    except Exception as e:
        print(f"[ОТЛАДКА] Ошибка запроса: {e}")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    day_blocks = soup.find_all('div', class_='col-md-6')
    print(f"[ОТЛАДКА] Найдено блоков col-md-6: {len(day_blocks)}")

    schedule = []
    for block in day_blocks:
        h4 = block.find('h4')
        if h4:
            print(f"[ОТЛАДКА] Заголовок блока: {h4.get_text().strip()}")
        if h4 and date_str in h4.get_text():
            print(f"[ОТЛАДКА] Нашли блок с датой {date_str}")
            table = block.find('table', class_='table')
            if not table:
                print("[ОТЛАДКА] Внутри блока нет таблицы")
                continue
            rows = table.find_all('tr')
            print(f"[ОТЛАДКА] В таблице {len(rows)} строк")
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
                    if any(x in line for x in ['онлайн', 'очно', 'відеоконференсія', 'https://']):
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
    else:
        print(f"[ОТЛАДКА] Блок с датой {date_str} не найден")

    print(f"[ОТЛАДКА] Итоговое расписание: {schedule}")
    return schedule

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("📚 Расписание на завтра", callback_data="tomorrow")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Привет! Я твой бот-расписание.\n"
        "Нажми кнопку, чтобы узнать расписание на завтра.\n\n"
        "Каждый вечер в 20:00 я буду присылать расписание.",
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
        print("Webhook удалён")
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

    print("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
