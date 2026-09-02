import os
import asyncio
import re
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ===== КОНФИГУРАЦИЯ =====
TOKEN = "8825040548:AAEzOeCHQT1zHFFPm8lixSd0C8Dwf2QMeI4"  # вставь свой токен от @BotFather
YOUR_CHAT_ID = 1356969534  # вставь свой Telegram ID (узнай у @userinfobot)

# Параметры твоей группы (можно захардкодить или потом сделать через /setgroup)
FACULTY = "1012"      # Навчально-науковий інститут економіки і управління
COURSE = "1"          # твой курс
GROUP = "ТП-1-11"     # твоя группа

# ===== ИНИЦИАЛИЗАЦИЯ БОТА =====
bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# ===== КЛАВИАТУРА =====
keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📚 Расписание на завтра", callback_data="tomorrow")]
])

# ===== ФУНКЦИЯ ПАРСИНГА =====
def get_schedule_for_date(date_str: str) -> list:
    """
    Получает расписание на указанную дату (в формате дд.мм.гггг).
    Возвращает список занятий: [{'num': '1', 'time': '08:15-09:35', 'subject': '...', 'teacher': '...', 'zoom': 'https://...'}, ...]
    """
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
        resp.encoding = 'windows-1251'  # сайт использует эту кодировку
    except Exception as e:
        print(f"Ошибка запроса: {e}")
        return None

    soup = BeautifulSoup(resp.text, 'html.parser')
    # Ищем блок с нужной датой
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
                # Проверяем, что ячейка с содержанием не пустая (не содержит только пробелы)
                content_cell = tds[2]
                if content_cell.get_text(strip=True) == '':
                    continue  # пустая пара

                num = tds[0].get_text(strip=True)
                time_raw = tds[1].get_text(strip=True).replace('\n', ' - ')
                # Извлекаем предмет, преподавателя и ссылку на Zoom
                # Используем BeautifulSoup для поиска
                # Сначала ищем ссылку на Zoom
                zoom_link = None
                link_tag = content_cell.find('a', href=True)
                if link_tag:
                    zoom_link = link_tag['href']

                # Получаем весь текст, разбиваем по <br>
                # Заменяем <br> на разделитель, чтобы потом легко парсить
                for br in content_cell.find_all('br'):
                    br.replace_with('\n')
                text = content_cell.get_text(separator='\n')
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                # Пример lines: ['онлайн', 'Основи підприємництва (ПрС)', 'доцент Бергер А.Д.', 'відеоконференсія', 'https://us04web.zoom.us/j/...']
                # Ищем строку, которая содержит "онлайн" или "очно" – пропускаем
                subject = ''
                teacher = ''
                for line in lines:
                    if 'онлайн' in line or 'очно' in line:
                        continue
                    if 'відеоконференсія' in line:
                        continue
                    if 'https://' in line or 'http://' in line:
                        continue
                    # если строка не содержит подсказок, то это либо предмет, либо преподаватель
                    # обычно предмет идёт первым, преподаватель вторым
                    if not subject:
                        subject = line
                    else:
                        # если уже есть subject, то добавляем в teacher
                        if teacher:
                            teacher += ', ' + line
                        else:
                            teacher = line

                # Если не удалось выделить subject/teacher, используем всю строку
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
            break  # нашли нужный день

    return schedule if schedule else None

# ===== ФОРМИРОВАНИЕ СООБЩЕНИЯ =====
def format_schedule(schedule: list, date_str: str) -> str:
    if not schedule:
        return f"📅 На {date_str} занятий нет или расписание не найдено."

    # Определяем день недели
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
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "👋 Привет! Я твой бот-расписание.\n"
        "Нажми кнопку ниже, чтобы узнать расписание на завтра.\n\n"
        "Также каждый вечер в 20:00 я буду присылать расписание автоматически.",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data == "tomorrow")
async def show_tomorrow(callback: types.CallbackQuery):
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")
    schedule = get_schedule_for_date(tomorrow)
    text = format_schedule(schedule, tomorrow)
    await callback.message.answer(text, parse_mode="Markdown", disable_web_page_preview=True)
    await callback.answer()

# ===== АВТОМАТИЧЕСКОЕ НАПОМИНАНИЕ =====
async def send_daily_schedule():
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")
    schedule = get_schedule_for_date(tomorrow)
    text = format_schedule(schedule, tomorrow)
    await bot.send_message(chat_id=YOUR_CHAT_ID, text=text, parse_mode="Markdown", disable_web_page_preview=True)

# Запуск планировщика – каждый день в 20:00
scheduler.add_job(send_daily_schedule, "cron", hour=20, minute=0)
scheduler.start()

# ===== ЗАПУСК БОТА =====
async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())