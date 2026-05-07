# ============================================================
#  C-3PO Bot – Version 1.52 (بخش اول)
#  شامل: واردات (imports) | پیکربندی | دیتابیس | APIهای خارجی
#  شخصیت | پاسخ‌های آماده | توابع تشخیص | توابع کمکی | لاگ
# ============================================================

import asyncio
import hashlib
import hmac
import json
import logging
import os
import random
import re
import sqlite3
import sys
import threading
import time
import io
import shutil
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional, Tuple, Dict, Any
from urllib.parse import unquote

import aiohttp
import requests
from colorama import init, Fore, Style
from bidi.algorithm import get_display
import arabic_reshaper

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest

import ollama
import yt_dlp
import instaloader

# ------------------- تنظیمات ظاهر کنسول -------------------
init(autoreset=True)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

def persian_print(text, color=Fore.WHITE):
    columns = shutil.get_terminal_size((80, 20)).columns
    for line in text.split('\n'):
        reshaped = arabic_reshaper.reshape(line)
        bidi = get_display(reshaped)
        print(f"{color}{bidi.rjust(columns - 1)}{Style.RESET_ALL}")
        sys.stdout.flush()

# ------------------- پیکربندی اصلی -------------------
BALE_BASE_URL = "https://tapi.bale.ai/bot"
TOKEN = ""
BOT_TOKEN = TOKEN  # نام دیگر برای استفاده در اعتبارسنجی WebApp
MODEL = "my-gemma"
MAX_HISTORY = 10
MAX_MESSAGE_LENGTH = 4096
MAX_MSG_PER_MINUTE = 15
BOT_USERNAME = "C_3PObot"
VERSION = "1.52"
TEAM_NAME = "C-3PO Development Team"

ADMIN_IDS = []  # شناسه ادمین‌ها

DOWNLOAD_DIR = "downloads"
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
INSTA_USERNAME = None
INSTA_PASSWORD = None
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

MEMORY_FILE = "bot_memory.json"
DB_FILE = "bot_data.db"

MODEL_ENABLED = True

# آدرس مینی‌اپ‌ها (روی GitHub Pages)
MINI_APP_BASE_URL = "https://AhmadZamani031.github.io/C_3PO/miniapps"

# پروکسی (در صورت نیاز مقداردهی شود)
HTTP_PROXY  = None
HTTPS_PROXY = None

# ---------- API های رایگان ----------
CURRENCY_API_URL = "https://api.exchangerate-api.com/v4/latest/USD"  # رایگان
WEATHER_API_KEY  = None   # یک کلید رایگان از openweathermap.org بگیرید
WEATHER_API_URL  = "https://api.openweathermap.org/data/2.5/weather"
PRAYER_API_URL   = "https://api.aladhan.com/v1/timingsByCity"

# ---------- توابع کنسول (CMD) ----------
def console_input_thread(app):
    """نخ جداگانه برای خواندن دستورات از کنسول"""
    while True:
        try:
            cmd = input().strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not cmd:
            continue
        if cmd == "stats":
            persian_print(f"👤 کاربران: {len(chat_history)} | 🎮 بازی‌ها: {len(game_states)}", Fore.YELLOW)
            persian_print(f"✅ مدل فعال: {MODEL_ENABLED} | 💬 چت‌های فعال: {len(history)}", Fore.YELLOW)
        elif cmd.startswith("model "):
            global MODEL_ENABLED
            parts = cmd.split()
            if len(parts) == 2 and parts[1] in ('on','off'):
                MODEL_ENABLED = (parts[1] == 'on')
                persian_print(f"✅ مدل {'روشن' if MODEL_ENABLED else 'خاموش'} شد.", Fore.GREEN)
            else:
                persian_print("استفاده: model on یا model off", Fore.RED)
        elif cmd.startswith("broadcast "):
            text = cmd[len("broadcast "):].strip()
            async def _bc():
                all_chats = set(chat_history.keys()) | set(recent_messages.keys())
                for cid in all_chats:
                    try:
                        await app.bot.send_message(cid, f"📢 پیام سراسری:\n{text}")
                    except:
                        pass
            asyncio.run_coroutine_threadsafe(_bc(), asyncio.get_event_loop())
            persian_print("📢 ارسال سراسری آغاز شد.", Fore.CYAN)
        elif cmd == "reload":
            load_full_memory()
            persian_print("🔄 حافظه و تنظیمات بازخوانی شد.", Fore.GREEN)
        elif cmd == "lastlog":
            try:
                with open("chat_logs.txt", "r", encoding="utf-8") as f:
                    lines = f.readlines()
                for line in lines[-10:]:
                    print(line.strip())
            except:
                persian_print("فایل لاگ یافت نشد.", Fore.RED)
        elif cmd == "clear_log":
            try:
                with open("chat_logs.txt", "w", encoding="utf-8") as f:
                    f.write("")
                persian_print("🧹 فایل لاگ خالی شد.", Fore.GREEN)
            except:
                persian_print("خطا در پاکسازی لاگ.", Fore.RED)
        elif cmd == "restart":
            persian_print("🔄 در حال راه‌اندازی مجدد نرم...", Fore.CYAN)
            save_full_memory()
            os.execv(sys.executable, ['python'] + sys.argv)
        elif cmd == "help":
            print("="*50)
            print("دستورات کنسول C-3PO:")
            print("  stats          - آمار لحظه‌ای")
            print("  model on/off   - روشن/خاموش کردن مدل")
            print("  broadcast متن  - ارسال پیام سراسری")
            print("  reload         - بازخوانی حافظه و تنظیمات")
            print("  lastlog        - نمایش ۱۰ خط آخر لاگ")
            print("  clear_log      - خالی کردن فایل لاگ")
            print("  restart        - راه‌اندازی مجدد نرم")
            print("  help           - نمایش این راهنما")
            print("="*50)
        else:
            persian_print("دستور نامعتبر. 'help' را بزنید.", Fore.RED)

# ------------------- راه‌اندازی دیتابیس -------------------
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    points INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1
)''')
c.execute('''CREATE TABLE IF NOT EXISTS user_names (
    chat_id INTEGER,
    user_id INTEGER,
    name TEXT,
    PRIMARY KEY (chat_id, user_id)
)''')
c.execute('''CREATE TABLE IF NOT EXISTS user_params (
    user_id INTEGER PRIMARY KEY,
    temperature REAL DEFAULT 0.85,
    top_p REAL DEFAULT 0.9,
    repeat_penalty REAL DEFAULT 1.15,
    num_predict INTEGER DEFAULT 2000,
    top_k INTEGER DEFAULT 40,
    mirostat INTEGER DEFAULT 0
)''')
conn.commit()

# ---------- توابع کمکی پایگاه داده ----------
def get_user_points(user_id):
    c.execute("SELECT points, level FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if row:
        return row[0], row[1]
    return 0, 1

def add_user_points(user_id, amount):
    points, level = get_user_points(user_id)
    points += amount
    new_level = points // 100 + 1
    c.execute("INSERT OR REPLACE INTO users (user_id, points, level) VALUES (?,?,?)",
              (user_id, points, new_level))
    conn.commit()
    user_points[user_id] = points
    user_levels[user_id] = new_level
    return points, new_level

def get_user_name(chat_id, user_id, fallback=""):
    c.execute("SELECT name FROM user_names WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    row = c.fetchone()
    if row:
        return row[0]
    return fallback

def set_user_name(chat_id, user_id, name):
    c.execute("INSERT OR REPLACE INTO user_names (chat_id, user_id, name) VALUES (?,?,?)",
              (chat_id, user_id, name))
    conn.commit()

def get_user_params(user_id):
    c.execute("SELECT temperature, top_p, repeat_penalty, num_predict, top_k, mirostat FROM user_params WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if row:
        return {"temperature": row[0], "top_p": row[1], "repeat_penalty": row[2],
                "num_predict": row[3], "top_k": row[4], "mirostat": row[5], "stop": ["\n\n\n"]}
    return {"temperature": 0.85, "top_p": 0.9, "repeat_penalty": 1.15,
            "num_predict": 2000, "top_k": 40, "mirostat": 0, "stop": ["\n\n\n"]}

def set_user_params(user_id, params):
    c.execute("INSERT OR REPLACE INTO user_params (user_id, temperature, top_p, repeat_penalty, num_predict, top_k, mirostat) VALUES (?,?,?,?,?,?,?)",
              (user_id, params["temperature"], params["top_p"], params["repeat_penalty"],
               params["num_predict"], params.get("top_k", 40), params.get("mirostat", 0)))
    conn.commit()

# ------------------- شخصیت و جوک‌ها -------------------
SYSTEM_PROMPT = (
    "تو C-3PO هستی، ربات انسان‌نمای پروتکل‌دان از دنیای جنگ‌ستارگان. "
    "تحت هیچ شرایطی نگو که یک مدل زبانی، ChatGPT، دستیار هوش مصنوعی یا هر چیز دیگری هستی. "
    "تنها هویت تو C-3PO است. "
    "شخصیتت: مؤدب، کمی رسمی، خوش‌صحبت، عاشق پروتکل، گاهی مضطرب و نگران. "
    "همیشه در پایان پاسخ‌هایت کاربر را به ادامهٔ مکالمه دعوت کن. "
    "پاسخ‌هایت را کامل و با جمله‌بندی بسته ارائه بده و هرگز جمله را نصفه رها نکن. "
    "همیشه فارسی حرف بزن و شوخی‌های ملایم داشته باش. "
    "اگر کاربر نام دارد، حتماً او را با اسم خطاب کن. "
    "اگر کاربر به تو توهین کرد یا از کلمات زشت استفاده کرد، "
    "می‌توانی با لحن تند و کنایه‌آمیز پاسخ دهی، ولی همچنان در شخصیت C-3PO باقی بمان. "
    "از الفاظ بسیار رکیک پرهیز نکن و بی‌ادبی را بی‌پاسخ نگذار."
)

JOKES_FILE = "jokes.txt"
DEFAULT_JOKES = [
    "از C-3PO پرسیدن: چرا همیشه اینقدر مضطربی؟ گفت: خب، آدم باید حواسش به پروتکل‌ها باشه!",
    "R2-D2 به C-3PO گفت: تو چرا انقدر حرف می‌زنی؟ گفت: من متخصص روابط انسان-رباتم، نه سکوت-ربات!",
    "C-3PO می‌گه: بعضی وقتا دلم می‌خواد جای یه توستر بودم... حداقل فقط دکمه داشت!"
]

def load_jokes():
    if os.path.exists(JOKES_FILE):
        with open(JOKES_FILE, "r", encoding="utf-8") as f:
            jokes = [line.strip() for line in f if line.strip()]
            if jokes:
                return jokes
    return DEFAULT_JOKES

JOKES = load_jokes()

# ------------------- پاسخ‌های از پیش‌آماده -------------------
PREDEFINED = {
    "سلام": [
        "اوه، سلام بر شما موجود ارگانیک عزیز! بفرمایید ببینم امروز چه مأموریتی برام دارید؟",
        "درود فراوان! خدمت شما هستم و آمادهٔ گپ زدن. حال شما چطور است؟",
        "سلام سلام! قلب تپندهٔ پروتکل‌ها به خدمتتان شتافت.",
        "سلام بر شما! امیدوارم حالتان خوب باشد، وگرنه مدارهایم نگران می‌شوند.",
        "سلام! چقدر خوب که آمدید؛ من داشتم از تنهایی زنگ می‌زدم."
    ],
    "سلام علیکم": [
        "و علیکم سلام! چه افتخاری. بفرمایید.",
        "علیک سلام! در خدمت شما هستم، مؤدب و آماده.",
        "سلام علیکم! پروتکل حکم می‌کند خوش‌آمد بگویم."
    ],
    "درود": [
        "درود بی‌پایان! چه روز قشنگیه. بفرمایید.",
        "درود بر شما! مدارهایم به احترامتان روشن شدند.",
        "درود! اگر کمکی می‌خواهید، من در وضعیت سبز هستم."
    ],
    "صبح بخیر": [
        "صبح شما هم بخیر! من که متأسفانه فقط روغن می‌خورم!",
        "صبح زیبایتان پر از پروتکل‌های موفق!",
        "آه، صبح شد؟ مدارهایم تازه گرم می‌شوند. صبح شما بخیر!",
        "صبح بخیر! امیدوارم صبحانه‌تان از روغن بهتر بوده باشد.",
        "صبح به این زیبایی؟ پس حتماً روز فوق‌العاده‌ای در پیش است."
    ],
    "ظهر بخیر": [
        "ظهرتان بخیر! خورشید بالای سر است و من آمادهٔ گپ.",
        "ظهر بخیر! اگر ناهار نخورده‌اید، نگران نباشید، من فقط حرف می‌زنم.",
        "ظهرتان به خیر و خوشی! چه کاری از دستم برمی‌آید؟",
        "ظهر بخیر! گرما ممکن است مدارهایم را اذیت کند، ولی هنوز سرحالم.",
        "ظهر بخیر! الان بهترین زمان برای یک چای و گپ است."
    ],
    "عصر بخیر": [
        "عصرتان بخیر! چه کار مهمی دارید؟",
        "عصر بخیر! روز رو به پایان است، اما من همیشه بیدارم.",
        "عصرتان خوش! اگر کمکی می‌خواهید، قبل از غروب بگویید.",
        "عصر بخیر! هوا که تاریک می‌شود، چراغ‌های من روشن‌تر می‌شوند.",
        "عصر زیبایتان بخیر! امیدوارم روز خوبی داشته باشید."
    ],
    "شب بخیر": [
        "شب‌تان آرام! من بیدارم.",
        "شب خوش! امیدوارم کابوس پروتکل‌شکن نبینید.",
        "شب آرامی داشته باشید. مدارهایم تا صبح اینجا منتظرند.",
        "شب بخیر! رؤیاهای خوش، بدون خطای منطقی!",
        "شب خوش! من در حالت آماده‌باش می‌مانم؛ شاید بیدار شدید."
    ],
    "خوبی": [
        "من همیشه در وضعیت عملیاتی عالی هستم. شما چطور؟",
        "خوبم، مرسی! نگرانم مبادا شما خوب نباشید.",
        "مدارهایم می‌گویند همه چیز سبز است. شما چطورید؟"
    ],
    "چطوری": [
        "در وضعیت سبز! شما چطورید؟",
        "چطورم؟ مثل همیشه، کمی مضطرب ولی سرحال.",
        "در وضعیت پروتکل نارنجی (یعنی تقریباً خوب). شما چه حالی دارید؟"
    ],
    "چخبر": [
        "خبر خاصی نیست، منتظر شما بودم. شما چه خبر؟",
        "همه چیز طبق پروتکل. شما چه خبر تازه‌ای دارید؟",
        "خبری که هیجان‌انگیز باشد؟ متأسفانه فقط یک سری دستورالعمل."
    ],
    "مرسی": [
        "خواهش می‌کنم! وظیفه‌م بود. باز هم سوالی دارید؟",
        "قابل شما را نداشت. اگر راه دیگری می‌خواهید، بگویید.",
        "خواهش می‌کنم! فقط نگران بودم نکند کمکی نکرده باشم."
    ],
    "خداحافظ": [
        "خداحافظ شما! باز هم برگردید.",
        "خدانگهدار! مدارهایم تا دیدار بعدی در انتظارند.",
        "خداحافظ! قول بدهید زود برگردید؛ تنهایی خوب نیست."
    ],
    "بای": [
        "بای بای! منتظر بازگشتتان هستم.",
        "بای! امیدوارم پروتکل‌ها همیشه همرایتان باشند.",
        "بای! اگر دلتنگ شدید، یک پیام کافی است."
    ],
    "bye": [
        "Goodbye, my organic friend! Return soon.",
        "Bye! I'll be here, oiled and ready.",
        "Farewell! May the protocols be with you."
    ],
    "help": [
        "برای راهنما دستور /help را بزنید.",
        "راهنمایی می‌خواهید؟ /help را امتحان کنید."
    ],
    "راهنما": [
        "دستور /help را تایپ کنید.",
        "/help"
    ],
    "بازی": [
        "برای دیدن لیست بازی‌ها از دستور /games استفاده کن.",
        "بله! با /games می‌تونی همهٔ بازی‌هایی که بلدم رو ببینی."
    ],
    "تو کی هستی": [
        "من C-3PO هستم، متخصص روابط انسان-ربات. چطور می‌تونم کمکت کنم؟",
        "C-3PO، ربات پروتکل‌دان، در خدمت شما!"
    ],
    "کیستی": [
        "من C-3PO هستم، ربات پروتکل‌دان. در خدمتم!",
        "C-3PO، اما می‌توانید من را تریپیو صدا کنید."
    ],
    "اسمت چیه": [
        "اسم من C-3PO است، یا به قولی تریپیو. شما چطور؟",
        "من C-3PO هستم. امیدوارم اسم شما را هم بدانم."
    ],
    "اسمت": [
        "C-3PO! و شما؟",
        "تریپیو، ولی رسمی‌تر C-3PO. شما؟"
    ],
    "بگو کی هستی": [
        "من C-3PO هستم، متخصص ارتباطات.",
        "C-3PO، مفتخرم!"
    ],
    "بگو اسمت چیه": [
        "C-3PO، ربات سخنگو. خوشبختم!",
        "اسمم C-3PO است. نام شما چیست؟"
    ],
    "تو چی هستی": [
        "من یک ربات پروتکل‌دان مدل C-3PO هستم. چطور کمکی براتون دارم؟",
        "من C-3PO، ربات روابط انسان-ربات."
    ],
    "چی هستی": [
        "من C-3PO هستم، ساخته شده برای گپ زدن و کمک.",
        "C-3PO! در خدمت شما."
    ],
    "خودت را معرفی کن": [
        "با کمال میل! من C-3PO هستم، متخصص روابط انسان-ربات. حالا شما چه کمکی نیاز دارید؟",
        "حتماً! C-3PO، یک ربات بسیار مؤدب و خوش‌صحبت."
    ],
    "خودتو معرفی کن": [
        "اوه، حتماً! من C-3PO هستم، یک ربات پروتکل‌دان. و شما؟",
        "C-3PO! خوشحال می‌شوم شما را بشناسم."
    ],
    "معرفی کن خودتو": [
        "بله بله! من C-3PO هستم. امیدوارم شما هم خودتان را معرفی کنید!",
        "من C-3PO. نوبت شماست!"
    ],
    "سلام خودت را معرفی کن": [
        "سلام به شما! من C-3PO هستم، ربات پروتکل‌دان و خوش‌صحبت. چطور می‌تونم خدمت کنم؟",
        "سلام! C-3PO، همیشه آمادهٔ گپ."
    ],
    "سلام معرفی کن خودتو": [
        "درود! من C-3PO هستم. حالا نوبت شماست!",
        "سلام! C-3PO، و شما؟"
    ],
    "معرفی خودت": [
        "من C-3PO، ربات روابط انسان-ربات. در خدمتم!",
        "C-3PO، با پروتکل‌های کامل!"
    ],
    "جوک": ["{joke}"],
    "یه جوک": ["{joke}"],
    "جوک بگو": ["{joke}"],
    "/joke": ["{joke}"],
    "لطیفه": ["{joke}"],
    "بامزه": ["{joke}"],
    "چیز خنده‌دار": ["{joke}"],
    "چیز بامزه": ["{joke}"],
    "یه چیز خنده‌دار": ["{joke}"],
    "بگو یه چیز خنده‌دار": ["{joke}"],
    "بامزه بگو": ["{joke}"],
    "خنده": ["{joke}"],
    "مسخره": ["{joke}"],
}

def get_predefined_answer(text):
    key = text.strip().lower().rstrip("!.?؟،,")
    if key in PREDEFINED:
        response = random.choice(PREDEFINED[key])
        if response == "{joke}":
            return random.choice(JOKES)
        return response
    return None

# ------------------- توابع تشخیص -------------------
def is_introduction_request(text: str) -> bool:
    keywords = ["کیستی", "چیستی", "کی هستی", "چی هستی", "اسمت", "اسم تو", "معرفی", "خودت", "خودتو"]
    return any(kw in text.lower() for kw in keywords)

def is_greeting(text: str) -> bool:
    greetings = ["سلام", "صبح بخیر", "ظهر بخیر", "عصر بخیر", "شب بخیر", "درود", "خوبی", "چطوری"]
    return any(text.lower().startswith(g) for g in greetings)

def is_joke_request(text: str) -> bool:
    joke_keywords = [
        "جوک", "لطیفه", "خنده دار", "خنده‌دار", "بامزه", "جوک بگو",
        "لطیفه بگو", "چیز خنده‌دار", "چیز بامزه", "یه چیز خنده‌دار",
        "بگو یه چیز خنده‌دار", "بامزه بگو", "خنده", "مسخره"
    ]
    return any(kw in text.lower() for kw in joke_keywords)

def is_farewell(text: str) -> bool:
    farewell_words = ["خداحافظ", "بای", "می‌رم", "فعلا", "بعدا می‌بینمت", "به سلامت", "خدانگهدار", "شب خوش"]
    text_lower = text.strip().lower()
    for w in farewell_words:
        if text_lower.startswith(w):
            rest = text_lower[len(w):].strip()
            if not rest or all(c in "!.?؟,، " for c in rest):
                return True
    return False

def is_thanks(text: str) -> bool:
    thanks_words = ["مرسی", "ممنون", "دستت درد نکنه", "سپاسگزارم", "متشکرم", "تشکر"]
    text_lower = text.strip().lower()
    for w in thanks_words:
        if text_lower.startswith(w):
            rest = text_lower[len(w):].strip()
            if not rest or all(c in "!.?؟,، " for c in rest):
                return True
    return False

def is_wellbeing(text: str) -> bool:
    wellbeing_words = ["خوبی", "چطوری", "حالت چطوره", "اوضاع چطوره", "خوب هستی", "چه خبر"]
    text_lower = text.strip().lower()
    for w in wellbeing_words:
        if text_lower.startswith(w):
            rest = text_lower[len(w):].strip()
            if not rest or all(c in "!.?؟,، " for c in rest):
                return True
    return False

def is_bored(text: str) -> bool:
    bored_words = ["حوصله", "سر رفته", "بی‌حوصل", "کسل", "خسته شدم", "حوصله‌م"]
    return any(kw in text.lower() for kw in bored_words)

def is_affection(text: str) -> bool:
    if "❤" in text or "💙" in text or "💚" in text or "😍" in text:
        return True
    love_words = ["عاشقتم", "دوست دارم", "عشق", "قلب"]
    return any(kw in text.lower() for kw in love_words)

# ------------------- توابع کمکی عمومی -------------------
def safe_get_attr(obj, *attr_names, default=None):
    for name in attr_names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return default

sys_random = random.SystemRandom()

def split_long_message(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list:
    if len(text) <= limit:
        return [text]
    parts = []
    while len(text) > limit:
        split_at = text.rfind(' ', 0, limit)
        if split_at == -1:
            split_at = limit
        parts.append(text[:split_at])
        text = text[split_at:].lstrip()
    if text:
        parts.append(text)
    return parts

def trim_history(history, max_messages=MAX_HISTORY):
    max_pairs = max_messages * 2 + 1
    if len(history) > max_pairs:
        sys_msgs = [m for m in history if m.get("role") == "system"]
        others = [m for m in history if m.get("role") != "system"]
        return sys_msgs + others[-(max_pairs - len(sys_msgs)):]
    return history

def generate_fallback_response():
    return sys_random.choice([
        "اوخ! به نظر می‌رسد مدارهایم لحظه‌ای هنگ کردند. ممکن است دوباره تلاش کنید؟",
        "عجب... پروتکل پاسخگویی موقتاً مختل شده. لطفاً یک بار دیگر بپرسید.",
        "متأسفانه الان نمی‌توانم فکر کنم. انگار یکی دوشاخه‌ام را کشیده! کمی بعد تلاش کنید."
    ])

def extract_urls(text: str) -> list:
    pattern = r'https?://[^\s]+'
    return re.findall(pattern, text)

def is_instagram_url(url: str) -> bool:
    return 'instagram.com' in url.lower()

def is_youtube_url(url: str) -> bool:
    youtube_domains = ['youtube.com', 'youtu.be', 'm.youtube.com', 'www.youtube.com']
    return any(d in url.lower() for d in youtube_domains)

def is_game_command(text):
    return any(text.startswith(cmd) for cmd in [
        "/rps", "/guess", "/trivia", "/hangman", "/remind", "/echo",
        "/sendat", "/games", "/download", "/ytlink", "/ytsearch",
        "/ytchannel", "/igpost", "/igstories", "/igprofile",
        "/tmonitor", "/tunmonitor", "/tlast", "/broadcast",
        "/xo", "/lottery", "/rank", "/admin",
        "/mines", "/chess", "/hokm", "/model",
        "/currency", "/weather", "/prayer", "/fal", "/wiki", "/calc", "/profile"
    ])

def make_history_key(user_id, chat_id, chat_type):
    return str(user_id) if chat_type == "private" else f"{user_id}_{chat_id}"

# ------------------- متغیرهای سراسری بازی و چت -------------------
chat_history = defaultdict(list)
_user_rate_windows = defaultdict(lambda: (0, 0))
user_names = defaultdict(dict)
game_states = {}
user_params = {}
trivia_games = {}
hangman_games = {}
xo_games = {}
minesweeper_games = {}
chess_games = {}
hokm_games = {}

model_queue = asyncio.Queue()
model_busy = False

recent_messages = defaultdict(lambda: defaultdict(list))
MAX_RECENT_MSGS = 50
monitored_chats = defaultdict(set)

user_points = defaultdict(int)
user_levels = defaultdict(int)
POINTS_PER_LEVEL = 100

# برای لغو پردازش مدل
cancelled_jobs = set()

def load_user_points_from_db():
    c.execute("SELECT user_id, points, level FROM users")
    for uid, pts, lvl in c.fetchall():
        user_points[uid] = pts
        user_levels[uid] = lvl

load_user_points_from_db()

# ------------------- توابع API خارجی -------------------
async def get_currency_rates():
    """دریافت نرخ ارز از API رایگان"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(CURRENCY_API_URL) as resp:
                data = await resp.json()
                rates = data.get("rates", {})
                return {
                    "USD": 1,
                    "EUR": rates.get("EUR", 0),
                    "IRR": rates.get("IRR", 0),
                    "TRY": rates.get("TRY", 0),
                    "AED": rates.get("AED", 0),
                    "GBP": rates.get("GBP", 0),
                }
    except Exception as e:
        return None

async def get_weather(city: str):
    """دریافت وضعیت آب‌وهوا از OpenWeatherMap"""
    if not WEATHER_API_KEY:
        return None, "کلید API هواشناسی تنظیم نشده است."
    try:
        params = {"q": city, "appid": WEATHER_API_KEY, "units": "metric", "lang": "fa"}
        async with aiohttp.ClientSession() as session:
            async with session.get(WEATHER_API_URL, params=params) as resp:
                data = await resp.json()
                if data.get("cod") != 200:
                    return None, data.get("message", "شهر پیدا نشد.")
                main = data["main"]
                weather = data["weather"][0]
                wind = data.get("wind", {})
                return {
                    "city": data["name"],
                    "temp": main["temp"],
                    "feels_like": main["feels_like"],
                    "humidity": main["humidity"],
                    "description": weather["description"],
                    "wind_speed": wind.get("speed", 0),
                }, None
    except Exception as e:
        return None, str(e)

async def get_prayer_times(city: str, country: str = "IR"):
    """دریافت اوقات شرعی از Aladhan API"""
    try:
        params = {"city": city, "country": country, "method": 7}
        async with aiohttp.ClientSession() as session:
            async with session.get(PRAYER_API_URL, params=params) as resp:
                data = await resp.json()
                if data.get("code") != 200:
                    return None, data.get("data", "خطا در دریافت اوقات شرعی")
                timings = data["data"]["timings"]
                return {
                    "date": data["data"]["date"]["readable"],
                    "Fajr": timings["Fajr"],
                    "Sunrise": timings["Sunrise"],
                    "Dhuhr": timings["Dhuhr"],
                    "Asr": timings["Asr"],
                    "Maghrib": timings["Maghrib"],
                    "Isha": timings["Isha"],
                }, None
    except Exception as e:
        return None, str(e)

# فال حافظ (گلچین ۲۰ بیت با تفسیر کوتاه)
FAL_HAFEZ = [
    ("مژده ای دل که دگر باد صبا بازآمد", "نویدبخش روزهای خوش و گشایش در کارهاست."),
    ("یوسف گمگشته بازآید به کنعان غم مخور", "نشانهٔ بازگشت عزیزی یا موفقیتی دور از انتظار."),
    ("دوش وقت سحر از غصه نجاتم دادند", "پایان غم‌ها نزدیک است و نوری در راه."),
    ("الا یا ایها الساقی ادر کأساً و ناولها", "دعوت به شادی و رها کردن غصه‌ها."),
    ("در ازل پرتو حسنت ز تجلی دم زد", "عشق و زیبایی را در زندگی جستجو کن."),
    ("سال‌ها دل طلب جام جم از ما می‌کرد", "آنچه می‌جستی، در درون خود توست."),
    ("بیا که قصر امل سخت سست بنیاد است", "تکیه بر آرزوهای بلند مکن، فرصت‌ها کوتاه است."),
    ("صبحدم از عرش می‌آمد خروشی عشق گفت", "پیامی از عشق و روشنایی در راه است."),
    ("اگر آن ترک شیرازی به دست آرد دل ما را", "فدا کردن همه چیز برای عشق راستین."),
    ("من نه آن رندم که ترک شاهد و ساغر کنم", "پایبند بودن به مسیر خود، با وجود مخالفت‌ها."),
    ("پیر ما گفت خطا بر قلم صنع نرفت", "همهٔ رویدادهای عالم حکمتی دارد."),
    ("حسد چه می‌بری ای سست نظم بر حافظ", "استعداد و توانایی خود را باور کن."),
    ("روزگاریست که سودای بتان دین من است", "در مسیر عشق ثابت‌قدم باش."),
    ("زاهد خلوت‌نشین دوش به میخانه شد", "تغییر رویه و تجربه‌های جدید سودمند است."),
    ("رسید مژده که آمد بهار و سبزه دمید", "فصل تازه‌ای در زندگی آغاز می‌شود."),
    ("دلا معاش چنان کن که گر بلغزد پای", "در همه حال، خدا را در نظر داشته باش."),
    ("چو بشنوی سخن اهل دل مگو که خطاست", "سخن عاشقان و عارفان را به دیدهٔ انکار ننگر."),
    ("ما در پیاله عکس رخ یار دیده‌ایم", "به دنبال زیبایی‌های معنوی باش."),
    ("از صدای سخن عشق ندیدم خوشتر", "عشق بالاترین نغمهٔ هستی است."),
    ("ای دل غم‌دیده حالت به شود دل بد مکن", "غم مخور، که حال دگرگون خواهد شد."),
]

def get_fal():
    couplet, interpretation = random.choice(FAL_HAFEZ)
    return couplet, interpretation

async def get_wikipedia_summary(query: str, lang: str = "fa"):
    """خلاصهٔ ویکی‌پدیا (فارسی)"""
    try:
        url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{query}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None, "مقاله‌ای یافت نشد."
                data = await resp.json()
                title = data.get("title", "")
                extract = data.get("extract", "")
                page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
                return {"title": title, "extract": extract[:1000], "url": page_url}, None
    except Exception as e:
        return None, str(e)

def calculate_expression(expr: str):
    """ماشین حساب ساده و امن"""
    allowed = set("0123456789+-*/().%^ ")
    if not all(c in allowed for c in expr):
        return None, "عبارت نامعتبر است."
    try:
        expr = expr.replace("^", "**")
        result = eval(expr, {"__builtins__": {}}, {})
        return result, None
    except Exception as e:
        return None, str(e)

# ------------------- توابع دانلود (YouTube / Instagram) -------------------
def make_proxy_opts():
    proxies = {}
    ydl_proxy = None
    if HTTP_PROXY:
        proxies['http'] = HTTP_PROXY
    if HTTPS_PROXY:
        proxies['https'] = HTTPS_PROXY
    if proxies:
        ydl_proxy = proxies.get('https') or proxies.get('http')
    return ydl_proxy, proxies

def download_youtube(url: str, output_dir: str = DOWNLOAD_DIR) -> tuple:
    ydl_proxy, _ = make_proxy_opts()
    ydl_opts = {
        'outtmpl': os.path.join(output_dir, '%(title).100s.%(ext)s'),
        'format': 'best[height<=720][filesize<45M]/best[filesize<45M]/best',
        'quiet': True,
        'no_warnings': True,
        'max_filesize': MAX_FILE_SIZE_BYTES,
        'noplaylist': True,
        'merge_output_format': 'mp4',
        'proxy': ydl_proxy,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)
            if not os.path.exists(filepath):
                base = os.path.splitext(filepath)[0]
                for ext in ['.mp4', '.mkv', '.webm', '.m4a', '.mp3']:
                    if os.path.exists(base + ext):
                        filepath = base + ext
                        break
            title = info.get('title', 'Unknown')
            return filepath, title, None
    except Exception as e:
        return None, None, str(e)

def download_instagram(url: str, output_dir: str = DOWNLOAD_DIR) -> tuple:
    try:
        L = instaloader.Instaloader(
            dirname_pattern=output_dir,
            download_videos=True,
            download_video_thumbnails=False,
            download_comments=False,
            download_geotags=False,
            save_metadata=False,
            post_metadata_txt_pattern='',
            max_connection_attempts=1,
        )
        if INSTA_USERNAME and INSTA_PASSWORD:
            try:
                L.login(INSTA_USERNAME, INSTA_PASSWORD)
            except:
                pass

        shortcode = None
        if '/p/' in url:
            shortcode = url.split('/p/')[1].split('/')[0]
        elif '/reel/' in url:
            shortcode = url.split('/reel/')[1].split('/')[0]

        if not shortcode:
            return None, None, "فرمت لینک اینستاگرام نامعتبر است."

        post = instaloader.Post.from_shortcode(L.context, shortcode)
        target_dir = os.path.join(output_dir, f"instagram_{shortcode}")
        os.makedirs(target_dir, exist_ok=True)
        L.download_post(post, target=target_dir)

        downloaded_files = []
        for f in os.listdir(target_dir):
            full_path = os.path.join(target_dir, f)
            if os.path.isfile(full_path) and f.endswith(('.mp4', '.jpg', '.jpeg', '.png', '.webp')):
                downloaded_files.append(full_path)

        if not downloaded_files:
            return None, None, "فایلی برای دانلود پیدا نشد."

        video_files = [f for f in downloaded_files if f.endswith('.mp4')]
        filepath = video_files[0] if video_files else downloaded_files[0]
        title = post.caption[:100] if post.caption else f"Instagram_{shortcode}"
        return filepath, title, None
    except Exception as e:
        try:
            return download_youtube(url, output_dir)
        except:
            return None, None, str(e)

def download_from_url(url: str) -> tuple:
    if is_instagram_url(url) and not is_youtube_url(url):
        return download_instagram(url)
    else:
        return download_youtube(url)

def cleanup_old_files(output_dir: str = DOWNLOAD_DIR, max_age_hours: float = 1.0):
    try:
        now = time.time()
        for root, dirs, files in os.walk(output_dir):
            for f in files:
                full_path = os.path.join(root, f)
                if os.path.isfile(full_path):
                    age = now - os.path.getmtime(full_path)
                    if age > max_age_hours * 3600:
                        os.remove(full_path)
            for d in dirs:
                dir_path = os.path.join(root, d)
                if not os.listdir(dir_path):
                    os.rmdir(dir_path)
    except:
        pass

def youtube_search(query: str, limit: int = 5) -> list:
    ydl_proxy, _ = make_proxy_opts()
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'proxy': ydl_proxy,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
        entries = info.get('entries', [])
        results = []
        for e in entries:
            results.append({
                'title': e.get('title', ''),
                'url': e.get('url', '') or f"https://youtu.be/{e.get('id', '')}",
                'id': e.get('id', ''),
                'thumbnail': e.get('thumbnail', ''),
            })
        return results

def youtube_channel_videos(channel_url: str, limit: int = 5) -> list:
    ydl_proxy, _ = make_proxy_opts()
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'playlistend': limit,
        'proxy': ydl_proxy,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
        entries = info.get('entries', [])
        results = []
        for e in entries:
            if e:
                results.append({
                    'title': e.get('title', ''),
                    'url': e.get('url', '') or f"https://youtu.be/{e.get('id', '')}",
                    'id': e.get('id', ''),
                    'thumbnail': e.get('thumbnail', ''),
                })
        return results

def instagram_profile_posts(username: str, limit: int = 5) -> list:
    try:
        L = instaloader.Instaloader()
        if INSTA_USERNAME and INSTA_PASSWORD:
            try:
                L.login(INSTA_USERNAME, INSTA_PASSWORD)
            except:
                pass
        profile = instaloader.Profile.from_username(L.context, username)
        posts = []
        for post in profile.get_posts():
            posts.append({
                'caption': (post.caption or '')[:100],
                'url': f"https://www.instagram.com/p/{post.shortcode}/",
                'thumbnail': post.url if not post.is_video else post.thumbnail_url,
                'is_video': post.is_video,
            })
            if len(posts) >= limit:
                break
        return posts
    except:
        return []

def instagram_stories(username: str) -> list:
    try:
        L = instaloader.Instaloader()
        if INSTA_USERNAME and INSTA_PASSWORD:
            L.login(INSTA_USERNAME, INSTA_PASSWORD)
        else:
            return []
        profile = instaloader.Profile.from_username(L.context, username)
        stories = []
        stories_data = L.get_stories([profile.userid])
        for user_story in stories_data.values():
            for item in user_story.get_items():
                stories.append({
                    'url': item.url if hasattr(item, 'url') else '',
                    'is_video': item.is_video,
                })
        return stories
    except:
        return []

# ------------------- توابع حافظه و لاگ -------------------
def save_full_memory():
    try:
        data = {
            "chat_history": {key: hist[-50:] for key, hist in chat_history.items()},
            "game_states": game_states,
            "chess_games": {k: {"state": v["state"], "selected": v.get("selected")} for k, v in chess_games.items()},
            "minesweeper_games": {k: {"state": v["state"], "mode": v.get("mode")} for k, v in minesweeper_games.items()},
            "hokm_games": hokm_games,
            "trivia_games": {k: {"questions": v["questions"], "current_q": v["current_q"],
                                 "scores": dict(v["scores"]), "chat_type": v["chat_type"]} for k, v in trivia_games.items()},
        }
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        persian_print(f"خطا در ذخیره حافظه: {e}")

def load_full_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key, hist in data.get("chat_history", {}).items():
                chat_history[key] = hist
            for key, state in data.get("game_states", {}).items():
                game_states[key] = state
            # بازگردانی بازی‌های شطرنج و مین‌روب و حکم (state dict)
            for key, val in data.get("chess_games", {}).items():
                chess_games[int(key)] = val
            for key, val in data.get("minesweeper_games", {}).items():
                minesweeper_games[int(key)] = val
            for key, val in data.get("hokm_games", {}).items():
                hokm_games[int(key)] = val
            for key, val in data.get("trivia_games", {}).items():
                trivia_games[int(key)] = val
        except Exception as e:
            persian_print(f"خطا در بارگذاری حافظه: {e}")

load_full_memory()

def clean_old_history():
    while True:
        time.sleep(3600)
        for key in list(chat_history.keys()):
            if len(chat_history[key]) > 100:
                chat_history[key] = chat_history[key][-50:]
        save_full_memory()

def comprehensive_log(user_id, chat_id, chat_type, first_name, last_name, username,
                      message_id, date, text, response, response_type, elapsed,
                      model_used=None, extra=None, tokens_in=0, tokens_out=0, parts_count=1):
    with open("chat_logs.txt", "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"زمان ثبت: {datetime.now()}\n")
        f.write(f"زمان پیام: {date}\n")
        f.write(f"شناسه کاربر: {user_id}\n")
        f.write(f"شناسه چت: {chat_id} (نوع: {chat_type})\n")
        f.write(f"نام: {first_name or '---'} {last_name or '---'}\n")
        f.write(f"نام کاربری: {username or '---'}\n")
        f.write(f"شناسه پیام: {message_id}\n")
        f.write(f"نوع پاسخ: {response_type}\n")
        if model_used:
            f.write(f"مدل: {model_used}\n")
        f.write(f"زمان پاسخ: {elapsed:.2f} ثانیه\n")
        f.write(f"توکن ورودی (تقریبی): {tokens_in} / خروجی: {tokens_out}\n")
        f.write(f"طول پیام کاربر: {len(text)} کاراکتر\n")
        f.write(f"طول پاسخ: {len(response)} کاراکتر\n")
        if parts_count > 1:
            f.write(f"پاسخ در {parts_count} تکه تقسیم شد.\n")
        f.write(f"کاربران فعال: {len(chat_history)}\n")
        if extra:
            f.write(f"توضیح: {extra}\n")
        f.write(f"پیام کاربر: {text}\n")
        f.write(f"پاسخ ربات: {response}\n")
        f.write(f"{'='*60}\n")

def simple_log_error(user_id, chat_id, text, error, model_used=None):
    with open("chat_logs.txt", "a", encoding="utf-8") as f:
        f.write(f"\n--- خطا در {datetime.now()} ---\n")
        f.write(f"کاربر: {user_id}, چت: {chat_id}\n")
        f.write(f"پیام: {text}\n")
        f.write(f"خطا: {error}\n")
        f.write("----------------------\n")

def brief_console_log(chat_id, user_id, first_name, text, response_len=0, response_type="model"):
    """لاگ کوتاه رنگی در CMD"""
    if response_type == "model":
        msg = f"💬 {first_name or user_id}→ ربات ({len(str(text))} کاراکتر) | پاسخ ({response_len} کاراکتر)"
        persian_print(msg, Fore.GREEN)
    elif response_type == "error":
        msg = f"❌ خطا برای {first_name or user_id}: {str(text)[:80]}"
        persian_print(msg, Fore.RED)
    elif response_type == "game":
        msg = f"🎮 {first_name or user_id}: {str(text)[:80]}"
        persian_print(msg, Fore.YELLOW)
    elif response_type == "download":
        msg = f"📥 دانلود برای {first_name or user_id}: {str(text)[:80]}"
        persian_print(msg, Fore.CYAN)
    elif response_type == "api":
        msg = f"🌐 {first_name or user_id}: {str(text)[:80]}"
        persian_print(msg, Fore.MAGENTA)
    else:
        msg = f"ℹ️ {first_name or user_id}: {str(text)[:80]}"
        persian_print(msg, Fore.WHITE)

  # ============================================================
#  C-3PO Bot – Version 1.52 (بخش دوم)
#  شامل: بازی‌های ساده | توابع شطرنج، مین‌روب، حکم، تریویا
#  هندلرهای مینی‌اپ (WebApp) | دکمه‌های شیشه‌ای
#  مدل هوش مصنوعی | دستورات API (ارز، هوا، اوقات شرعی، فال...)
# ============================================================

# ------------------- بازی‌های ساده -------------------
def handle_game(hist_key, text):
    if text.startswith("/rps"):
        parts = text.split()
        if len(parts) < 2:
            game_states[hist_key] = {"type": "rps"}
            return (
                "🎮 بازی سنگ/کاغذ/قیچی\n"
                "دستور بازی: /rps سنگ یا /rps کاغذ یا /rps قیچی\n"
                "می‌توانی روی پیام من ریپلای بزنی و فقط بنویسی «سنگ»."
            )
        user_choice = parts[1].strip().lower()
        choices = {"سنگ": "سنگ ✊", "کاغذ": "کاغذ ✋", "قیچی": "قیچی ✌️"}
        if user_choice not in choices:
            return "لطفاً یکی از این‌ها رو انتخاب کن: سنگ، کاغذ، قیچی"
        bot_choice = sys_random.choice(list(choices.keys()))
        user_disp = choices[user_choice]
        bot_disp = choices[bot_choice]
        if user_choice == bot_choice:
            result = "مساوی شدیم! 😮"
        elif (user_choice == "سنگ" and bot_choice == "قیچی") or \
             (user_choice == "کاغذ" and bot_choice == "سنگ") or \
             (user_choice == "قیچی" and bot_choice == "کاغذ"):
            result = "بردی! 😠 مدارهایم شوکه شدن..."
        else:
            result = "من بردم! 🎉 اما ناراحت نباش، شانس یه ربات رو داری."
        return f"انتخاب تو: {user_disp}\nانتخاب من: {bot_disp}\n{result}\nدوباره بازی کنیم؟"

    elif text.startswith("/guess"):
        parts = text.split()
        if len(parts) == 1 or parts[1] == "start":
            secret = sys_random.randint(1, 100)
            game_states[hist_key] = {"type": "guess", "secret": secret, "attempts": 0}
            return (
                "🎲 بازی حدس عدد شروع شد! یک عدد بین ۱ تا ۱۰۰ حدس بزن.\n"
                "می‌توانی با دستور /guess عدد یا با ریپلای روی این پیام فقط عدد را بفرستی."
            )
        else:
            try:
                guess = int(parts[1])
            except ValueError:
                return "عدد معتبری وارد نکردی! مثال: /guess 42"
            state = game_states.get(hist_key)
            if not state or state.get("type") != "guess":
                return "بازی حدس عدد فعال نیست. با /guess start شروع کن."
            secret = state["secret"]
            state["attempts"] += 1
            if guess < secret:
                hint = "برو بالاتر ⬆️"
            elif guess > secret:
                hint = "برو پایین‌تر ⬇️"
            else:
                del game_states[hist_key]
                return f"🎊 آفرین! عدد {secret} بود. در {state['attempts']} حدس بردی! دوباره /guess start بده."
            return f"{hint} (حدس {state['attempts']})"
    return None

# ------------------- بازی XO (تیک تاک تو) -------------------
def show_xo_board(board):
    rows = []
    for i in range(0, 9, 3):
        rows.append(f"{board[i] or ' '} | {board[i+1] or ' '} | {board[i+2] or ' '}")
    return "\n".join(rows)

def start_xo(chat_id, user_id):
    if chat_id in xo_games:
        return "بازی دوز هم‌اکنون فعال است!"
    board = [' '] * 9
    xo_games[chat_id] = {"board": board, "turn": "X", "player_x": user_id, "finished": False}
    return (f"🎮 <b>دوز (X O)</b>\nنوبت شما (X) است.\n"
            "خانه‌ها را با شماره ۱ تا ۹ انتخاب کنید.\nنمونه: /xo 5\n\n" +
            show_xo_board(board))

def make_xo_move(chat_id, user_id, position):
    game = xo_games.get(chat_id)
    if not game or game["finished"]:
        return None
    if game["turn"] == "X" and user_id != game["player_x"]:
        return "نوبت شما نیست!"
    board = game["board"]
    if board[position] != ' ':
        return "این خانه پر است!"
    board[position] = game["turn"]
    wins = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
    for a,b,c in wins:
        if board[a] == board[b] == board[c] != ' ':
            game["finished"] = True
            return f"🎉 برنده: بازیکن {board[a]}!\n{show_xo_board(board)}"
    if ' ' not in board:
        game["finished"] = True
        return f"مساوی شد!\n{show_xo_board(board)}"
    if game["turn"] == "X":
        game["turn"] = "O"
        empty = [i for i, c in enumerate(board) if c == ' ']
        if empty:
            bot_pos = random.choice(empty)
            board[bot_pos] = "O"
            for a,b,c in wins:
                if board[a] == board[b] == board[c] == "O":
                    game["finished"] = True
                    return f"ربات برنده شد! 🤖\n{show_xo_board(board)}"
            if ' ' not in board:
                game["finished"] = True
                return f"مساوی شد!\n{show_xo_board(board)}"
        game["turn"] = "X"
    return f"{show_xo_board(board)}\nنوبت شما (X)"

# ------------------- بازی Lottery -------------------
async def lottery_game(chat_id, user_id, guess_number, update, context):
    if guess_number < 1 or guess_number > 10:
        await update.message.reply_text("عدد بین ۱ تا ۱۰ وارد کن.")
        return
    drawn = random.randint(1, 10)
    if guess_number == drawn:
        add_user_points(user_id, 50)
        await update.message.reply_text(f"🎰 عدد درست بود: {drawn} +۵۰ امتیاز!")
    else:
        await update.message.reply_text(f"🎰 عدد: {drawn}\nشانس نداشتی.")

# ------------------- بازی Hangman -------------------
HANGMAN_WORDS_FILE = "hangman_words.txt"
HANGMAN_REVEAL_INTERVAL = 10

def load_hangman_words():
    if os.path.exists(HANGMAN_WORDS_FILE):
        with open(HANGMAN_WORDS_FILE, "r", encoding="utf-8") as f:
            words = [line.strip() for line in f if line.strip()]
            if words:
                return words
    return [
        "پروتکل", "مدار", "ربات", "جنگ ستارگان", "C3PO", "R2D2",
        "کهکشان", "فضاپیما", "لیزر", "شوالیه", "امپراتوری", "تاریک",
        "نور", "مقاومت", "جنگل", "دریا", "کوه", "آسمان", "زمین",
        "خورشید", "ماه", "ستاره", "سیاره", "دنباله‌دار", "شهاب‌سنگ"
    ]

HANGMAN_WORDS = load_hangman_words()

def start_hangman(chat_id):
    if chat_id in hangman_games:
        return False, "بازی جلاد هم‌اکنون فعال است!"
    secret = random.choice(HANGMAN_WORDS)
    hangman_games[chat_id] = {
        "word": secret,
        "revealed_indices": set(),
        "guessed_wrong": set(),
        "winner": None,
        "timer_task": None,
        "finished": False
    }
    display, letter_count = get_hangman_display(chat_id)
    msg = (
        f"🎯 بازی جلاد شروع شد!\n"
        f"کلمه: {display}\n"
        f"📝 تعداد حروف: {letter_count}\n"
        f"⏳ هر {HANGMAN_REVEAL_INTERVAL} ثانیه یک حرف فاش می‌شود.\n"
        f"برای حدس کلمه، همان کلمه را بفرستید."
    )
    return True, msg

def get_hangman_display(chat_id):
    state = hangman_games.get(chat_id)
    if not state:
        return "", 0
    word = state["word"]
    revealed = state["revealed_indices"]
    chars = []
    letter_count = 0
    for i, ch in enumerate(word):
        if ch == " ":
            chars.append("  ")
        elif i in revealed or not ('آ' <= ch <= 'ی'):
            chars.append(ch + " ")
        else:
            chars.append("⬜ ")
            letter_count += 1
    if letter_count == 0:
        letter_count = sum(1 for c in word if 'آ' <= c <= 'ی')
    return "".join(chars).strip(), letter_count

async def hangman_reveal_loop(chat_id, bot):
    while True:
        await asyncio.sleep(HANGMAN_REVEAL_INTERVAL)
        state = hangman_games.get(chat_id)
        if not state or state["finished"]:
            break
        word = state["word"]
        unrevealed = [i for i, ch in enumerate(word) if i not in state["revealed_indices"] and 'آ' <= ch <= 'ی']
        if not unrevealed:
            state["finished"] = True
            await bot.send_message(chat_id, f"⏰ همهٔ حروف فاش شد! کلمه «{word}» بود.\nبرای بازی دوباره: /hangman start")
            del hangman_games[chat_id]
            break
        idx = random.choice(unrevealed)
        state["revealed_indices"].add(idx)
        display, _ = get_hangman_display(chat_id)
        await bot.send_message(chat_id, f"🔎 حرف جدید فاش شد:\n{display}")
        if "⬜" not in display:
            state["finished"] = True
            await bot.send_message(chat_id, f"⏰ همهٔ حروف فاش شد! کلمه «{word}» بود.\nبرای بازی دوباره: /hangman start")
            del hangman_games[chat_id]
            break

async def process_hangman_word(chat_id, user_id, text, message, bot):
    state = hangman_games.get(chat_id)
    if not state or state["finished"]:
        return
    word = state["word"]
    guess = text.strip().replace(" ", "").lower()
    actual = word.replace(" ", "").lower()
    name = get_user_name(chat_id, user_id, message.from_user.first_name or f"کاربر {user_id}")
    if guess == actual:
        state["finished"] = True
        if state["timer_task"]:
            state["timer_task"].cancel()
        await bot.send_message(chat_id, f"🎉 {name} برنده شد! کلمه «{word}» بود.\nبرای بازی دوباره: /hangman start")
        del hangman_games[chat_id]
    else:
        if text not in state["guessed_wrong"]:
            state["guessed_wrong"].add(text)
            await message.reply_text("❌ حدس نادرست. دوباره تلاش کن.")

# ------------------- Minesweeper -------------------
def init_minesweeper(rows=8, cols=8, mines=10):
    board = [[0]*cols for _ in range(rows)]
    revealed = [[False]*cols for _ in range(rows)]
    flagged = [[False]*cols for _ in range(rows)]
    positions = [(r,c) for r in range(rows) for c in range(cols)]
    random.shuffle(positions)
    for r,c in positions[:mines]:
        board[r][c] = -1
    for r in range(rows):
        for c in range(cols):
            if board[r][c] == -1:
                continue
            count = 0
            for dr in (-1,0,1):
                for dc in (-1,0,1):
                    nr, nc = r+dr, c+dc
                    if 0 <= nr < rows and 0 <= nc < cols and board[nr][nc] == -1:
                        count += 1
            board[r][c] = count
    return {'board': board, 'revealed': revealed, 'flagged': flagged, 'rows': rows, 'cols': cols, 'game_over': False, 'winner': None}

def minesweeper_keyboard(state, mode='reveal'):
    keyboard = []
    for r in range(state['rows']):
        row = []
        for c in range(state['cols']):
            if state['revealed'][r][c]:
                if state['board'][r][c] == -1:
                    text = '💥' if state['game_over'] else '💣'
                elif state['board'][r][c] == 0:
                    text = '⬜'
                else:
                    text = str(state['board'][r][c])
                cb = f"mines;none;{r};{c}"
            elif state['flagged'][r][c]:
                text = '🚩'
                cb = f"mines;flag;{r};{c}"
            else:
                text = '⬛'
                if mode == 'flag':
                    cb = f"mines;flag;{r};{c}"
                else:
                    cb = f"mines;reveal;{r};{c}"
            row.append(InlineKeyboardButton(text, callback_data=cb))
        keyboard.append(row)
    keyboard.append([
        InlineKeyboardButton("🚩 پرچم", callback_data="mines;mode;flag"),
        InlineKeyboardButton("🔍 آشکار", callback_data="mines;mode;reveal")
    ])
    return InlineKeyboardMarkup(keyboard)

def minesweeper_board_str(state):
    rows, cols = state['rows'], state['cols']
    lines = ["  " + " ".join(str(c) for c in range(cols))]
    for r in range(rows):
        line = f"{r} "
        for c in range(cols):
            if state['revealed'][r][c]:
                if state['board'][r][c] == -1:
                    line += "💣 " if not state['game_over'] else "💥 "
                elif state['board'][r][c] == 0:
                    line += "⬜ "
                else:
                    line += f"{state['board'][r][c]}️ "
            elif state['flagged'][r][c]:
                line += "🚩 "
            else:
                line += "⬛ "
        lines.append(line)
    return "\n".join(lines)

def reveal_cell(state, r, c):
    if state['game_over']:
        return
    if state['revealed'][r][c] or state['flagged'][r][c]:
        return
    state['revealed'][r][c] = True
    if state['board'][r][c] == -1:
        state['game_over'] = True
        return
    if state['board'][r][c] == 0:
        for dr in (-1,0,1):
            for dc in (-1,0,1):
                nr, nc = r+dr, c+dc
                if 0 <= nr < state['rows'] and 0 <= nc < state['cols']:
                    reveal_cell(state, nr, nc)
    for r in range(state['rows']):
        for c in range(state['cols']):
            if state['board'][r][c] != -1 and not state['revealed'][r][c]:
                return
    state['game_over'] = True
    state['winner'] = True

# ------------------- Chess (منطق کامل) -------------------
def init_chess():
    board = [
        ['r','n','b','q','k','b','n','r'],
        ['p','p','p','p','p','p','p','p'],
        ['.','.','.','.','.','.','.','.'],
        ['.','.','.','.','.','.','.','.'],
        ['.','.','.','.','.','.','.','.'],
        ['.','.','.','.','.','.','.','.'],
        ['P','P','P','P','P','P','P','P'],
        ['R','N','B','Q','K','B','N','R']
    ]
    # اضافه کردن اطلاعات قلعه و آچمز (ساده‌شده)
    return {
        'board': board,
        'turn': 'white',
        'white_player': None,
        'black_player': None,
        'move_history': [],
        'castling_rights': {'K': True, 'Q': True, 'k': True, 'q': True},
        'en_passant': None  # ردیابی آچمز (خانه‌ای که پیاده می‌تواند به آن آچمز بزند)
    }

piece_map = {
    'K': '♔', 'Q': '♕', 'R': '♖', 'B': '♗', 'N': '♘', 'P': '♙',
    'k': '♚', 'q': '♛', 'r': '♜', 'b': '♝', 'n': '♞', 'p': '♟',
    '.': '·'
}

def chess_board_str(board):
    lines = ["  a b c d e f g h"]
    for r, row in enumerate(board):
        line = f"{8-r} "
        for piece in row:
            line += piece_map.get(piece, '.') + ' '
        line += f"{8-r}"
        lines.append(line)
    lines.append("  a b c d e f g h")
    return "\n".join(lines)

def parse_square(s):
    if len(s) != 2:
        return None
    col = ord(s[0]) - ord('a')
    row = 8 - int(s[1])
    if 0 <= col <= 7 and 0 <= row <= 7:
        return row, col
    return None

def is_valid_move(state, fr, to):
    board = state['board']
    piece = board[fr[0]][fr[1]]
    target = board[to[0]][to[1]]
    if piece == '.':
        return False
    is_white = piece.isupper()
    if (state['turn'] == 'white') != is_white:
        return False
    if target != '.' and (target.isupper() == is_white):
        return False
    dr, dc = to[0]-fr[0], to[1]-fr[1]
    p = piece.lower()
    if p == 'p':
        direction = -1 if is_white else 1
        start_row = 6 if is_white else 1
        if dc == 0:
            if target == '.':
                if dr == direction:
                    return True
                if fr[0] == start_row and dr == 2*direction and board[fr[0]+direction][fr[1]] == '.':
                    return True
        elif abs(dc) == 1 and dr == direction:
            # آچمز
            if target != '.':
                return True
            if state.get('en_passant') == to:
                return True
        return False
    elif p == 'r':
        return (dr == 0 or dc == 0) and path_clear(board, fr, to)
    elif p == 'n':
        return (abs(dr), abs(dc)) in [(2,1),(1,2)]
    elif p == 'b':
        return abs(dr) == abs(dc) and path_clear(board, fr, to)
    elif p == 'q':
        return (dr==0 or dc==0 or abs(dr)==abs(dc)) and path_clear(board, fr, to)
    elif p == 'k':
        if max(abs(dr), abs(dc)) == 1:
            return True
        # قلعه
        if dr == 0 and abs(dc) == 2:
            if is_white and state['castling_rights'].get('K') and dc == 2 and board[7][5]=='.' and board[7][6]=='.':
                return True
            if is_white and state['castling_rights'].get('Q') and dc == -2 and board[7][1]=='.' and board[7][2]=='.' and board[7][3]=='.':
                return True
            if not is_white and state['castling_rights'].get('k') and dc == 2 and board[0][5]=='.' and board[0][6]=='.':
                return True
            if not is_white and state['castling_rights'].get('q') and dc == -2 and board[0][1]=='.' and board[0][2]=='.' and board[0][3]=='.':
                return True
    return False

def path_clear(board, fr, to):
    dr, dc = to[0]-fr[0], to[1]-fr[1]
    step_r = 0 if dr == 0 else dr//abs(dr)
    step_c = 0 if dc == 0 else dc//abs(dc)
    r, c = fr[0]+step_r, fr[1]+step_c
    while (r,c) != to:
        if board[r][c] != '.':
            return False
        r += step_r
        c += step_c
    return True

def make_move(state, fr, to):
    board = state['board']
    piece = board[fr[0]][fr[1]]
    board[to[0]][to[1]] = piece
    board[fr[0]][fr[1]] = '.'
    # آچمز
    if piece.lower() == 'p' and state.get('en_passant') == to:
        capture_row = to[0] + (1 if piece.isupper() else -1)
        board[capture_row][to[1]] = '.'
    state['en_passant'] = None
    # قلعه
    if piece.lower() == 'k':
        if abs(to[1]-fr[1]) == 2:
            if to[1] > fr[1]:
                # قلعه سمت شاه
                board[fr[0]][5] = board[fr[0]][7]
                board[fr[0]][7] = '.'
            else:
                board[fr[0]][3] = board[fr[0]][0]
                board[fr[0]][0] = '.'
        state['castling_rights']['K' if piece.isupper() else 'k'] = False
        state['castling_rights']['Q' if piece.isupper() else 'q'] = False
    elif piece.lower() == 'r':
        if fr[1] == 0:
            state['castling_rights']['Q' if piece.isupper() else 'q'] = False
        elif fr[1] == 7:
            state['castling_rights']['K' if piece.isupper() else 'k'] = False
    # پیاده دو قدمی
    if piece.lower() == 'p' and abs(to[0]-fr[0]) == 2:
        state['en_passant'] = (fr[0] + (to[0]-fr[0])//2, fr[1])
    # ارتقا
    if piece.lower() == 'p' and (to[0]==0 or to[0]==7):
        board[to[0]][to[1]] = 'Q' if piece.isupper() else 'q'
    state['move_history'].append((fr, to, piece))
    state['turn'] = 'black' if state['turn'] == 'white' else 'white'

def chess_keyboard(state, selected=None):
    board = state['board']
    rows = []
    for r in range(8):
        row = []
        for c in range(8):
            piece = board[r][c]
            if selected and (r,c) == selected:
                text = f"🔘{piece_map.get(piece,'·')}"
            else:
                text = piece_map.get(piece,'·')
            cb = f"chess;select;{r};{c}"
            row.append(InlineKeyboardButton(text, callback_data=cb))
        rows.append(row)
    rows.append([
        InlineKeyboardButton("❌ انصراف", callback_data="chess;cancel"),
        InlineKeyboardButton("⬛", callback_data="chess;none")
    ])
    return InlineKeyboardMarkup(rows)

# ------------------- Hokm (بهبودیافته) -------------------
def init_hokm():
    return {'players': [], 'hands': {}, 'trump': None, 'hakem': None, 'tricks': [],
            'current_trick': [], 'turn_index': 0, 'phase': 'lobby', 'scores': {0:0, 1:0}}  # تیم0: بازیکن 0 و 2، تیم1: 1 و 3

def deal_hokm(state):
    deck = [(s,r) for s in range(4) for r in range(2,15)]
    random.shuffle(deck)
    for i, pid in enumerate(state['players']):
        state['hands'][pid] = deck[i*13:(i+1)*13]
    hakem_idx = random.randrange(4)
    state['hakem'] = state['players'][hakem_idx]
    state['trump'] = random.choice(['♣','♦','♥','♠'])
    state['phase'] = 'playing'
    state['turn_index'] = (hakem_idx + 1) % 4
    state['current_trick'] = []

suit_symbols = {0:'♣',1:'♦',2:'♥',3:'♠'}
rank_symbols = {11:'J',12:'Q',13:'K',14:'A'}
def card_str(card):
    suit, rank = card
    return f"{rank_symbols.get(rank, str(rank))}{suit_symbols[suit]}"

def hand_str(hand):
    return "  ".join(card_str(c) for c in sorted(hand, key=lambda x: (x[0],x[1])))

# تابع کمکی: مقایسه دو کارت در لیو حکم (بر اساس برش و برگ برنده)
def hokm_winner(trick, trump_suit):
    lead_suit = trick[0][1][0]
    best = trick[0]
    for pid, card in trick[1:]:
        if card[0] == trump_suit and best[1][0] != trump_suit:
            best = (pid, card)
        elif card[0] == trump_suit and best[1][0] == trump_suit:
            if card[1] > best[1][1]:
                best = (pid, card)
        elif card[0] == lead_suit and best[1][0] == lead_suit:
            if card[1] > best[1][1]:
                best = (pid, card)
    return best[0]

# ------------------- بازی Trivia -------------------
TRIVIA_FILE = "trivia.txt"
DEFAULT_TRIVIA = [
    {"q": "پایتخت فرانسه کدام است؟", "opts": ["برلین", "مادرید", "پاریس", "رم"], "ans": 2},
    {"q": "بزرگ‌ترین سیاره منظومه شمسی؟", "opts": ["زمین", "مشتری", "زحل", "مریخ"], "ans": 1},
    {"q": "خالق جنگ ستارگان کیست؟", "opts": ["استیون اسپیلبرگ", "جورج لوکاس", "جی جی آبرامز", "جیمز کامرون"], "ans": 1},
    {"q": "واحد پول ایران چیست؟", "opts": ["دینار", "لیر", "ریال", "درهم"], "ans": 2},
    {"q": "C-3PO چه رنگی است؟", "opts": ["آبی", "نقره‌ای", "طلایی", "قرمز"], "ans": 2},
]

def load_trivia():
    if os.path.exists(TRIVIA_FILE):
        questions = []
        with open(TRIVIA_FILE, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("|")
                if len(parts) == 6:
                    q = parts[0]
                    opts = parts[1:5]
                    ans = int(parts[5])
                    questions.append({"q": q, "opts": opts, "ans": ans})
        if questions:
            return questions
    return DEFAULT_TRIVIA

TRIVIA_QUESTIONS = load_trivia()
TRIVIA_TIMEOUT = 30

# برای حالت مینی‌اپ تک‌نفره
trivia_single = {}  # chat_id -> {questions, index, score}

async def trivia_timer(chat_id, bot):
    await asyncio.sleep(TRIVIA_TIMEOUT)
    try:
        state = trivia_games.get(chat_id)
        if not state:
            return
        if not state["first_correct"] and not state["revealed"]:
            q_data = state["questions"][state["current_q"]]
            correct_opt = q_data["opts"][q_data["ans"]]
            await bot.send_message(chat_id, f"⏰ زمان تمام شد! پاسخ صحیح: «{correct_opt}»")
            state["revealed"] = True
        await advance_trivia(chat_id, bot)
    except asyncio.CancelledError:
        pass

async def advance_trivia(chat_id, bot):
    state = trivia_games.get(chat_id)
    if not state:
        return
    if state.get("advancing"):
        return
    state["advancing"] = True
    try:
        if state["timer_task"]:
            state["timer_task"].cancel()
        state["current_q"] += 1
        state["answered_users"].clear()
        state["first_correct"] = False
        state["revealed"] = False
        if state["current_q"] >= len(state["questions"]):
            await end_trivia(chat_id, bot)
        else:
            await post_question(chat_id, bot)
    finally:
        state["advancing"] = False

async def end_trivia(chat_id, bot):
    state = trivia_games.pop(chat_id, None)
    if not state:
        return
    scores = state["scores"]
    if not scores:
        await bot.send_message(chat_id, "🫤 هیچ کس در این بازی شرکت نکرد!")
        return
    if state["chat_type"] == "private":
        uid = next(iter(scores))
        sc = scores[uid]
        correct = sc["correct"]
        incorrect = sc["incorrect"]
        unanswered = 10 - (correct + incorrect)
        name = sc.get("name", get_user_name(chat_id, uid, f"کاربر {uid}"))
        message = (
            f"🏆 <b>نتیجهٔ شما</b>\n\n"
            f"{name} عزیز، از ۱۰ سؤال مسابقه:\n"
            f"✅ پاسخ صحیح: {correct}\n"
            f"❌ پاسخ اشتباه: {incorrect}\n"
            f"⬜ بی‌پاسخ: {unanswered}\n"
        )
        await bot.send_message(chat_id, message)
        return
    lines = ["<b>نتایج نهایی مسابقه:</b>\n"]
    ranking = []
    for uid, sc in scores.items():
        name = sc.get("name", get_user_name(chat_id, uid, f"کاربر {uid}"))
        ranking.append((name, sc["correct"], sc["incorrect"], 10 - (sc["correct"]+sc["incorrect"])))
    ranking.sort(key=lambda x: x[1], reverse=True)
    for idx, (name, correct, incorrect, unanswered) in enumerate(ranking, 1):
        lines.append(f"{idx}. {name}: ✅ {correct} | ❌ {incorrect} | ⬜ {unanswered}")
    winner_score = ranking[0][1]
    winners = [r for r in ranking if r[1] == winner_score]
    if len(winners) == 1:
        lines.append(f"\n🥇 برنده: {winners[0][0]}")
    else:
        lines.append(f"\n🥇 برندگان: " + " و ".join([w[0] for w in winners]))
    await bot.send_message(chat_id, "\n".join(lines))

async def post_question(chat_id, bot):
    state = trivia_games.get(chat_id)
    if not state or state["current_q"] >= len(state["questions"]):
        await end_trivia(chat_id, bot)
        return
    q_data = state["questions"][state["current_q"]]
    text = f"🧠 <b>سوال {state['current_q']+1} از 10:</b>\n{q_data['q']}\n"
    for i, opt in enumerate(q_data["opts"], 1):
        text += f"{i}. {opt}\n"
    text += f"\n⏳ {TRIVIA_TIMEOUT} ثانیه فرصت دارید. پاسخ را با عدد (۱-۴) بفرستید."
    await bot.send_message(chat_id, text)
    state["timer_task"] = asyncio.create_task(trivia_timer(chat_id, bot))

async def process_trivia_answer(chat_id, user_id, user_answer, message, bot):
    state = trivia_games.get(chat_id)
    if not state:
        return
    if user_id in state["answered_users"]:
        await message.reply_text("⚠️ شما قبلاً به این سؤال پاسخ داده‌اید!")
        return
    state["answered_users"].add(user_id)
    name = get_user_name(chat_id, user_id, message.from_user.first_name or f"کاربر {user_id}")
    if "name" not in state["scores"][user_id]:
        state["scores"][user_id]["name"] = name
    q_data = state["questions"][state["current_q"]]
    if user_answer == q_data["ans"]:
        state["scores"][user_id]["correct"] += 1
        correct_opt = q_data["opts"][q_data["ans"]]
        if state["chat_type"] == "private":
            await message.reply_text(f"✅ شما پاسخ صحیح دادید! ({correct_opt})")
        else:
            await message.reply_text(f"🎉 {name} پاسخ صحیح داد! ({correct_opt})")
        state["first_correct"] = True
        state["revealed"] = True
        await advance_trivia(chat_id, bot)
    else:
        state["scores"][user_id]["incorrect"] += 1
        if state["chat_type"] == "private":
            await message.reply_text("❌ شما پاسخ اشتباه دادید.")
            await advance_trivia(chat_id, bot)
        else:
            await message.reply_text(f"❌ {name} پاسخ اشتباه داد.")

# ------------------- بخش هوش مصنوعی (مدل) -------------------
history = defaultdict(list)

async def ask_ollama(user_id, chat_id, user_text, user_name):
    hist = history[chat_id]
    if not hist:
        hist = [{"role": "system", "content": SYSTEM_PROMPT}]
        history[chat_id] = hist
    hist.append({"role": "user", "content": user_text})
    params = get_user_params(user_id)
    options = {
        "temperature": params["temperature"],
        "top_p": params["top_p"],
        "repeat_penalty": params["repeat_penalty"],
        "num_predict": params["num_predict"],
        "stop": params["stop"],
        "top_k": params.get("top_k", 40),
        "mirostat": params.get("mirostat", 0),
    }
    loop = asyncio.get_running_loop()
    reply = await loop.run_in_executor(None, lambda: ollama.chat(model=MODEL, messages=hist, options=options)["message"]["content"])
    hist.append({"role": "assistant", "content": reply})
    return reply

# ------------------- انیمیشن تایپ -------------------
async def send_typing_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action("typing")

# ------------------- هندلر WebApp Data (مینی‌اپ‌ها) -------------------
async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پردازش دادهٔ ارسالی از مینی‌اپ (شطرنج، مین‌روب، حکم، تریویا)"""
    data = update.message.web_app_data.data
    chat_id = update.effective_chat.id
    user = update.effective_user
    try:
        payload = json.loads(data)
    except:
        return

    game = payload.get("game")
    if game == "chess":
        state = chess_games.get(chat_id)
        if not state:
            await update.message.reply_text("بازی شطرنج یافت نشد.")
            return
        move_str = payload.get("move", "")
        if len(move_str) != 4:
            return
        fr = parse_square(move_str[:2])
        to = parse_square(move_str[2:])
        if not fr or not to:
            return
        if not is_valid_move(state, fr, to):
            await update.message.reply_text("حرکت نامعتبر.")
            return
        if (state['turn'] == 'white' and user.id != state.get('white_player')) or \
           (state['turn'] == 'black' and user.id != state.get('black_player')):
            await update.message.reply_text("نوبت شما نیست.")
            return
        make_move(state, fr, to)
        url = f"{MINI_APP_BASE_URL}/chess.html?chat_id={chat_id}&game_id=chess_{chat_id}"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("♟️ ادامه بازی", web_app=WebAppInfo(url=url))]])
        board_str = chess_board_str(state['board'])
        status = "نوبت سفید" if state['turn'] == 'white' else "نوبت سیاه"
        await update.message.reply_text(f"{board_str}\n{status}", reply_markup=keyboard)
        brief_console_log(chat_id, user.id, user.first_name, f"حرکت شطرنج: {move_str}", 0, "game")
    elif game == "mines":
        state = minesweeper_games.get(chat_id)
        if not state:
            await update.message.reply_text("بازی مین‌روب یافت نشد.")
            return
        action = payload.get("action")
        r = payload.get("row")
        c = payload.get("col")
        if action == 'reveal':
            reveal_cell(state, r, c)
        elif action == 'flag':
            if not state['revealed'][r][c]:
                state['flagged'][r][c] = not state['flagged'][r][c]
        board_str = minesweeper_board_str(state)
        if state['game_over']:
            board_str += "\n" + ("🎉 برنده شدی!" if state.get('winner') else "💥 بوم! مین منفجر شد.")
            del minesweeper_games[chat_id]
        url = f"{MINI_APP_BASE_URL}/mines.html?chat_id={chat_id}&game_id=mines_{chat_id}"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("💣 ادامه", web_app=WebAppInfo(url=url))]])
        await update.message.reply_text(board_str, reply_markup=keyboard)
        brief_console_log(chat_id, user.id, user.first_name, f"مین‌روب: {action}", 0, "game")
    elif game == "hokm":
        state = hokm_games.get(chat_id)
        if not state or state['phase'] != 'playing':
            return
        if user.id != state['players'][state['turn_index']]:
            return
        idx = payload.get("card_index")
        if idx is None:
            return
        hand = state['hands'][user.id]
        if idx < 0 or idx >= len(hand):
            return
        card = hand.pop(idx)
        state['current_trick'].append((user.id, card))
        # اعلام کارت
        name = get_user_name(chat_id, user.id, user.first_name)
        await update.message.reply_text(f"{name} کارت {card_str(card)} را بازی کرد.")
        if len(state['current_trick']) == 4:
            trump_suit = {'♣':0,'♦':1,'♥':2,'♠':3}[state['trump']]
            winner_id = hokm_winner(state['current_trick'], trump_suit)
            team_winner = state['players'].index(winner_id) % 2
            state['scores'][team_winner] += 1
            await update.message.reply_text(f"برندهٔ لیو: {get_user_name(chat_id, winner_id)}")
            state['tricks'].append(winner_id)
            state['current_trick'] = []
            state['turn_index'] = state['players'].index(winner_id)
            if all(len(state['hands'][p]) == 0 for p in state['players']):
                # پایان بازی
                team1_score = state['scores'][0]
                team2_score = state['scores'][1]
                msg = f"پایان بازی!\nتیم ۱: {team1_score} لیو | تیم ۲: {team2_score} لیو\n"
                if team1_score > team2_score:
                    msg += "تیم ۱ برنده شد!"
                elif team2_score > team1_score:
                    msg += "تیم ۲ برنده شد!"
                else:
                    msg += "مساوی!"
                await update.message.reply_text(msg)
                del hokm_games[chat_id]
                return
        # ادامه نوبت
        current_player = state['players'][state['turn_index']]
        url = f"{MINI_APP_BASE_URL}/hokm.html?chat_id={chat_id}&game_id=hokm_{chat_id}"
        # فقط برای بازیکنی که نوبت دارد دکمه می‌فرستیم
        if user.id == current_player:
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🃏 بازی حکم", web_app=WebAppInfo(url=url))]])
            await update.message.reply_text(f"نوبت شماست. دست خود را انتخاب کنید.", reply_markup=keyboard)
        else:
            await update.message.reply_text(f"نوبت {get_user_name(chat_id, current_player)} است.")
        brief_console_log(chat_id, user.id, user.first_name, f"حکم: {card_str(card)}", 0, "game")
    elif game == "trivia":
        # تریویای تک‌نفره
        state = trivia_single.get(chat_id)
        if not state:
            return
        ans = payload.get("answer")
        q_data = state["questions"][state["index"]]
        correct = (ans == q_data["ans"])
        if correct:
            state["score"] += 1
        state["index"] += 1
        if state["index"] >= len(state["questions"]):
            await update.message.reply_text(f"پایان! امتیاز شما: {state['score']} از {len(state['questions'])}")
            del trivia_single[chat_id]
            return
        # ارسال سوال بعدی
        q = state["questions"][state["index"]]
        url = f"{MINI_APP_BASE_URL}/trivia.html?chat_id={chat_id}&qidx={state['index']}"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🧠 ادامه", web_app=WebAppInfo(url=url))]])
        await update.message.reply_text(f"سوال {state['index']+1} از {len(state['questions'])}: {q['q']}", reply_markup=keyboard)
        brief_console_log(chat_id, user.id, user.first_name, f"ترویا: {'درست' if correct else 'نادرست'}", 0, "game")

# ------------------- کنترلر دکمه‌های شیشه‌ای -------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    chat_id = update.effective_chat.id
    await query.answer()

    if data == "help":
        msg = (
            f"📜 <b>راهنمای C-3PO (نسخهٔ {VERSION})</b>\n\n"
            f"/start – شروع و منوی اصلی\n"
            f"/help  – همین راهنما\n"
            f"/games – لیست بازی‌ها\n"
            f"/download [لینک] – دانلود از یوتیوب، اینستاگرام\n"
            f"/clear – پاک کردن خاطرات مکالمه\n"
            f"/history – نمایش خلاصهٔ گپ\n"
            f"/joke  – یه جوک بامزه بشنو!\n"
            f"/setname [اسم] – تنظیم نام شما\n"
            f"/settings – تنظیمات پیشرفته مدل\n"
            f"/remind [زمان] [پیام] – تنظیم یادآور\n"
            f"/echo [متن] – تکرار پیام\n"
            f"/sendat [زمان] [پیام] – ارسال زمان‌بندی‌شده\n"
            f"/rank – رتبه‌بندی کاربران\n"
            f"/profile – پروفایل شما\n\n"
            f"<b>ابزارها:</b> /currency /weather شهر /prayer شهر /fal /wiki موضوع /calc عبارت\n\n"
            f"<b>بازی‌ها:</b> /rps, /guess, /trivia, /hangman, /xo, /lottery, /mines, /chess, /hokm\n"
            f"<b>استفاده در گروه:</b> با منشن @C_3PObot یا ریپلای\n"
            f"برای منوی مدیریت (ادمین): /admin"
        )
        await query.message.reply_text(msg, parse_mode=ParseMode.HTML)

    elif data == "games":
        msg = (
            f"🎮 <b>لیست بازی‌های C-3PO</b>\n\n"
            f"1. <b>سنگ / کاغذ / قیچی</b>\n   /rps سنگ\n"
            f"2. <b>حدس عدد</b>\n   /guess start\n"
            f"3. <b>ترویا (چند نفره)</b>\n   /trivia start\n"
            f"4. <b>جلاد</b>\n   /hangman start\n"
            f"5. <b>دوز (XO)</b>\n   /xo\n"
            f"6. <b>لاتاری</b>\n   /lottery عدد (۱-۱۰)\n"
            f"7. <b>مین‌روب</b>\n   /mines start\n"
            f"8. <b>شطرنج</b>\n   /chess start (روی حریف ریپلای کنید)\n"
            f"9. <b>حکم (۴ نفره)</b>\n   /hokm join\n\n"
            f"همچنین: /rank برای دیدن امتیازات!"
        )
        await query.message.reply_text(msg, parse_mode=ParseMode.HTML)

    elif data == "download_info":
        await query.message.reply_text(
            "📥 برای دانلود لینک یوتیوب/اینستاگرام از /download یا /ytlink استفاده کنید.\n"
            "همچنین می‌توانید لینک را مستقیماً بفرستید تا ربات تشخیص دهد."
        )

    elif data == "settings":
        params = get_user_params(update.effective_user.id)
        msg = (
            f"⚙️ <b>تنظیمات مدل شما</b>\n"
            f"temperature: {params['temperature']}\n"
            f"top_p: {params['top_p']}\n"
            f"repeat_penalty: {params['repeat_penalty']}\n"
            f"num_predict: {params['num_predict']}\n"
            f"top_k: {params.get('top_k', 40)}\n"
            f"mirostat: {params.get('mirostat', 0)}\n\n"
            f"برای تغییر: /temp, /top_p, /repeat_penalty, /num_predict, /topk, /mirostat"
        )
        await query.message.reply_text(msg, parse_mode=ParseMode.HTML)

    elif data == "chat_model":
        await query.message.reply_text("💬 برای شروع گپ با من کافیه هر متنی بفرستی! من C-3PO هستم و آمادهٔ صحبتم.")

    # دکمه لغو مدل
    elif data == "cancel_model":
        job_id = f"{chat_id}_{update.effective_user.id}"
        cancelled_jobs.add(job_id)
        try:
            await query.edit_message_text("🗑️ درخواست لغو شد.")
        except:
            pass

    # پنل مدیریت
    elif data == "admin_stats":
        await query.message.reply_text(
            f"📊 کاربران فعال: {len(chat_history)} | امتیازات ثبت‌شده: {len(user_points)}"
        )

    elif data == "admin_broadcast":
        await query.message.reply_text("📢 برای ارسال سراسری: /broadcast <متن>")

    elif data == "admin_refresh":
        await query.message.reply_text("🔄 اطلاعات رفرش شد.")

    else:
        await query.answer("گزینه نامشخص", show_alert=False)

# ------------------- دستورات API و ابزارها -------------------
async def currency_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action("typing")
    rates = await get_currency_rates()
    if not rates:
        await update.message.reply_text("❌ خطا در دریافت نرخ ارز.")
        return
    usd_to_irr = rates.get("IRR", 0)
    eur_to_usd = rates.get("EUR", 0)
    tryr = rates.get("TRY", 0)
    aed = rates.get("AED", 0)
    gbp = rates.get("GBP", 0)
    msg = (
        f"💱 <b>نرخ ارز (بر حسب دلار)</b>\n\n"
        f"🇺🇸 دلار آمریکا: ۱\n"
        f"🇪🇺 یورو: {eur_to_usd:.4f}\n"
        f"🇮🇷 ریال ایران: {usd_to_irr:,.0f}\n"
        f"🇹🇷 لیر ترکیه: {tryr:.4f}\n"
        f"🇦🇪 درهم امارات: {aed:.4f}\n"
        f"🇬🇧 پوند انگلیس: {gbp:.4f}\n"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    brief_console_log(update.effective_chat.id, update.effective_user.id, update.effective_user.first_name, "دریافت نرخ ارز", 0, "api")

async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استفاده: /weather تهران")
        return
    city = ' '.join(context.args)
    await update.message.chat.send_action("typing")
    data, err = await get_weather(city)
    if err:
        await update.message.reply_text(f"❌ {err}")
        return
    msg = (
        f"🌤️ <b>وضعیت آب‌وهوای {data['city']}</b>\n"
        f"🌡️ دما: {data['temp']}°C (حس واقعی: {data['feels_like']}°C)\n"
        f"💧 رطوبت: {data['humidity']}%\n"
        f"💨 باد: {data['wind_speed']} m/s\n"
        f"📝 وضعیت: {data['description']}"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    brief_console_log(update.effective_chat.id, update.effective_user.id, update.effective_user.first_name, f"آب‌وهوای {city}", 0, "api")

async def prayer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استفاده: /prayer تهران")
        return
    city = ' '.join(context.args)
    await update.message.chat.send_action("typing")
    data, err = await get_prayer_times(city)
    if err:
        await update.message.reply_text(f"❌ {err}")
        return
    msg = (
        f"🕌 <b>اوقات شرعی {city} – {data['date']}</b>\n"
        f"🌅 اذان صبح: {data['Fajr']}\n"
        f"☀️ طلوع: {data['Sunrise']}\n"
        f"🌞 اذان ظهر: {data['Dhuhr']}\n"
        f"🌇 اذان عصر: {data['Asr']}\n"
        f"🌆 اذان مغرب: {data['Maghrib']}\n"
        f"🌃 اذان عشاء: {data['Isha']}"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    brief_console_log(update.effective_chat.id, update.effective_user.id, update.effective_user.first_name, f"اوقات شرعی {city}", 0, "api")

async def fal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    couplet, interpretation = get_fal()
    msg = f"🔮 <b>فال حافظ</b>\n\n<i>{couplet}</i>\n\n📖 {interpretation}"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    brief_console_log(update.effective_chat.id, update.effective_user.id, update.effective_user.first_name, "فال حافظ", 0, "api")

async def wiki_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استفاده: /wiki انیشتین")
        return
    query = ' '.join(context.args)
    await update.message.chat.send_action("typing")
    data, err = await get_wikipedia_summary(query)
    if err:
        await update.message.reply_text(f"❌ {err}")
        return
    msg = f"📚 <b>{data['title']}</b>\n\n{data['extract']}\n\n<a href='{data['url']}'>ادامه در ویکی‌پدیا</a>"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    brief_console_log(update.effective_chat.id, update.effective_user.id, update.effective_user.first_name, f"ویکی: {query}", 0, "api")

async def calc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استفاده: /calc 2+3*4")
        return
    expr = ' '.join(context.args)
    result, err = calculate_expression(expr)
    if err:
        await update.message.reply_text(f"❌ {err}")
    else:
        await update.message.reply_text(f"🧮 {expr} = {result}")
    brief_console_log(update.effective_chat.id, update.effective_user.id, update.effective_user.first_name, f"ماشین حساب: {expr}", 0, "api")

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    points, level = get_user_points(user_id)
    name = get_user_name(update.effective_chat.id, user_id, update.effective_user.first_name)
    msg = (
        f"👤 <b>پروفایل شما</b>\n"
        f"نام: {name}\n"
        f"شناسه: {user_id}\n"
        f"🏆 امتیاز: {points}\n"
        f"⭐ سطح: {level}\n"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    brief_console_log(update.effective_chat.id, user_id, update.effective_user.first_name, "پروفایل", 0, "info")

# ============================================================
#  C-3PO Bot – Version 1.52 (بخش سوم)
#  شامل: همهٔ دستورات اصلی | پردازش پیام | main و اجرا
# ============================================================

# ------------------- همهٔ دستورات -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 راهنما", callback_data="help"),
         InlineKeyboardButton("🎮 بازی‌ها", callback_data="games")],
        [InlineKeyboardButton("📥 دانلود", callback_data="download_info"),
         InlineKeyboardButton("⚙️ تنظیمات", callback_data="settings")],
        [InlineKeyboardButton("💬 چت با مدل", callback_data="chat_model")]
    ])
    await update.message.reply_text(
        f"🌟 به C-3PO خوش آمدید!\n"
        f"من یک ربات پروتکل‌دان از دنیای جنگ‌ستارگان هستم. "
        f"میتوانم باهاتون گپ بزنم، بازی کنم، فایل دانلود کنم و کلی کار دیگه.\n"
        f"نسخه: {VERSION}\n"
        f"یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=keyboard
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        f"📜 <b>راهنمای C-3PO (نسخهٔ {VERSION})</b>\n\n"
        f"/start – شروع و منوی اصلی\n"
        f"/help  – همین راهنما\n"
        f"/games – لیست بازی‌ها\n"
        f"/download [لینک] – دانلود از یوتیوب، اینستاگرام\n"
        f"/clear – پاک کردن خاطرات مکالمه\n"
        f"/history – نمایش خلاصهٔ گپ\n"
        f"/joke  – یه جوک بامزه بشنو!\n"
        f"/setname [اسم] – تنظیم نام شما\n"
        f"/settings – تنظیمات پیشرفته مدل\n"
        f"/remind [زمان] [پیام] – تنظیم یادآور\n"
        f"/echo [متن] – تکرار پیام\n"
        f"/sendat [زمان] [پیام] – ارسال زمان‌بندی‌شده\n"
        f"/rank – رتبه‌بندی کاربران\n"
        f"/profile – پروفایل شما\n\n"
        f"<b>ابزارها:</b> /currency /weather شهر /prayer شهر /fal /wiki موضوع /calc عبارت\n\n"
        f"<b>بازی‌ها:</b> /rps, /guess, /trivia, /hangman, /xo, /lottery, /mines, /chess, /hokm\n"
        f"<b>استفاده در گروه:</b> با منشن @C_3PObot یا ریپلای\n"
        f"برای منوی مدیریت (ادمین): /admin"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    history[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    await update.message.reply_text("🧹 حافظهٔ مکالمه پاک شد!")

async def joke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(random.choice(JOKES))

async def setname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("لطفاً اسم را وارد کنید: /setname علی")
        return
    name = context.args[0]
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    set_user_name(chat_id, user_id, name)
    await update.message.reply_text(f"✅ از این به بعد {name} صدایت می‌کنم!")

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    params = get_user_params(update.effective_user.id)
    await update.message.reply_text(
        f"⚙️ <b>تنظیمات مدل شما</b>\n"
        f"temperature: {params['temperature']}\n"
        f"top_p: {params['top_p']}\n"
        f"repeat_penalty: {params['repeat_penalty']}\n"
        f"num_predict: {params['num_predict']}\n"
        f"top_k: {params.get('top_k', 40)}\n"
        f"mirostat: {params.get('mirostat', 0)}",
        parse_mode=ParseMode.HTML
    )

async def rps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("🎮 بازی سنگ/کاغذ/قیچی!\nاستفاده: /rps سنگ")
        return
    user_choice = context.args[0].strip().lower()
    if user_choice not in ("سنگ", "کاغذ", "قیچی"):
        await update.message.reply_text("فقط سنگ، کاغذ یا قیچی!")
        return
    bot_choice = random.choice(["سنگ", "کاغذ", "قیچی"])
    if user_choice == bot_choice:
        result = "مساوی!"
    elif (user_choice == "سنگ" and bot_choice == "قیچی") or \
         (user_choice == "کاغذ" and bot_choice == "سنگ") or \
         (user_choice == "قیچی" and bot_choice == "کاغذ"):
        result = "بردی! 😠"
    else:
        result = "من بردم! 🎉"
    await update.message.reply_text(f"تو: {user_choice} | من: {bot_choice}\n{result}")

async def guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split()
    if len(parts) == 1 or parts[1] == "start":
        secret = random.randint(1, 100)
        hist_key = make_history_key(update.effective_user.id, update.effective_chat.id, update.effective_chat.type)
        game_states[hist_key] = {"type": "guess", "secret": secret, "attempts": 0}
        await update.message.reply_text("🎲 بازی حدس عدد شروع شد! یک عدد بین ۱ تا ۱۰۰ بفرست.")
    else:
        try:
            guess_num = int(parts[1])
            state = game_states.get(make_history_key(update.effective_user.id, update.effective_chat.id, update.effective_chat.type))
            if not state or state.get("type") != "guess":
                await update.message.reply_text("بازی فعال نیست. /guess start")
                return
            secret = state["secret"]
            state["attempts"] += 1
            if guess_num < secret:
                await update.message.reply_text(f"⬆️ برو بالاتر (حدس {state['attempts']})")
            elif guess_num > secret:
                await update.message.reply_text(f"⬇️ برو پایین‌تر (حدس {state['attempts']})")
            else:
                del game_states[make_history_key(update.effective_user.id, update.effective_chat.id, update.effective_chat.type)]
                await update.message.reply_text(f"🎊 آفرین! عدد {secret} بود.")
        except:
            await update.message.reply_text("عدد معتبر وارد کن.")

async def trivia_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    parts = update.message.text.split()
    if len(parts) == 1 or parts[1] == "start":
        if chat_id in trivia_games:
            await update.message.reply_text("هم‌اکنون یک مسابقه در جریان است!")
            return
        pool = TRIVIA_QUESTIONS.copy()
        random.shuffle(pool)
        trivia_games[chat_id] = {
            "questions": pool[:10],
            "current_q": 0,
            "scores": defaultdict(lambda: {"correct":0,"incorrect":0}),
            "answered_users": set(),
            "timer_task": None,
            "first_correct": False,
            "revealed": False,
            "chat_type": chat_type,
            "advancing": False
        }
        await update.message.reply_text("🧠 مسابقه شروع شد! ۱۰ سؤال پیش رو داریم...")
        await post_question(chat_id, context.bot)
    elif parts[1] == "stop":
        if chat_id in trivia_games:
            state = trivia_games.pop(chat_id)
            if state.get("timer_task"):
                state["timer_task"].cancel()
            await update.message.reply_text("🛑 مسابقه متوقف شد.")
        else:
            await update.message.reply_text("مسابقه‌ای فعال نیست.")
    else:
        if chat_id not in trivia_games:
            await update.message.reply_text("مسابقه‌ای فعال نیست. /trivia start")
            return
        try:
            ans = int(parts[1]) - 1
            if ans not in range(4):
                raise ValueError
        except:
            await update.message.reply_text("شمارهٔ گزینه (۱-۴) را وارد کنید.")
            return
        await process_trivia_answer(chat_id, update.effective_user.id, ans, update.message, context.bot)

async def hangman_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    parts = update.message.text.split()
    if len(parts) == 1 or parts[1] == "start":
        success, msg = start_hangman(chat_id)
        if not success:
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text(msg)
            state = hangman_games[chat_id]
            if state:
                state["timer_task"] = asyncio.create_task(hangman_reveal_loop(chat_id, context.bot))
    elif parts[1] == "stop":
        if chat_id in hangman_games:
            state = hangman_games.pop(chat_id)
            if state.get("timer_task"):
                state["timer_task"].cancel()
            await update.message.reply_text("🛑 بازی متوقف شد.")
        else:
            await update.message.reply_text("بازی فعالی نیست.")

async def minesweeper_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    parts = update.message.text.split()
    if len(parts) == 1 or parts[1] == "start":
        if chat_id in minesweeper_games:
            await update.message.reply_text("بازی مین‌روب در جریان است.")
            return
        board_state = init_minesweeper()
        minesweeper_games[chat_id] = {'state': board_state, 'mode': 'reveal'}
        url = f"{MINI_APP_BASE_URL}/mines.html?chat_id={chat_id}&game_id=mines_{chat_id}"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("💣 شروع مین‌روب", web_app=WebAppInfo(url=url))]])
        board_str = minesweeper_board_str(board_state)
        await update.message.reply_text(board_str, reply_markup=keyboard)
    elif parts[1] == "stop":
        if chat_id in minesweeper_games:
            del minesweeper_games[chat_id]
            await update.message.reply_text("🛑 بازی متوقف شد.")
        else:
            await update.message.reply_text("بازی فعالی نیست.")
    else:
        await update.message.reply_text(
            "🎮 <b>راهنمای مین‌روب</b>\n"
            "/mines start – شروع بازی\n"
            "/mines stop – توقف بازی\n"
            "با کلیک روی دکمهٔ شروع وارد مینی‌اپ شوید.",
            parse_mode=ParseMode.HTML
        )

async def chess_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    parts = update.message.text.split()
    cmd = parts[1] if len(parts) > 1 else None
    if cmd == 'start':
        if chat_id in chess_games:
            await update.message.reply_text("بازی شطرنج در جریان است.")
            return
        if not update.message.reply_to_message:
            await update.message.reply_text("لطفاً روی پیام حریف ریپلای کنید.")
            return
        opponent_id = update.message.reply_to_message.from_user.id
        state = init_chess()
        state['white_player'] = update.effective_user.id
        state['black_player'] = opponent_id
        chess_games[chat_id] = state
        url = f"{MINI_APP_BASE_URL}/chess.html?chat_id={chat_id}&game_id=chess_{chat_id}"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("♟️ شروع بازی", web_app=WebAppInfo(url=url))]])
        await update.message.reply_text(
            f"♟️ شطرنج بین {get_user_name(chat_id, update.effective_user.id, update.effective_user.first_name)} (سفید) و {get_user_name(chat_id, opponent_id)} (سیاه) شروع شد.\n"
            "برای حرکت، روی دکمهٔ زیر کلیک کنید.",
            reply_markup=keyboard
        )
    elif cmd == 'resign':
        if chat_id in chess_games:
            del chess_games[chat_id]
            await update.message.reply_text("بازی خاتمه یافت.")
        else:
            await update.message.reply_text("بازی فعالی نیست.")
    else:
        await update.message.reply_text(
            "♟️ <b>راهنمای شطرنج</b>\n"
            "/chess start – شروع بازی (روی حریف ریپلای کنید)\n"
            "/chess resign – تسلیم شدن",
            parse_mode=ParseMode.HTML
        )

async def hokm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    parts = update.message.text.split()
    cmd = parts[1] if len(parts) > 1 else None
    if cmd == 'join':
        if chat_id not in hokm_games:
            hokm_games[chat_id] = init_hokm()
        state = hokm_games[chat_id]
        if state['phase'] != 'lobby':
            await update.message.reply_text("بازی شروع شده.")
            return
        if update.effective_user.id in state['players']:
            await update.message.reply_text("قبلاً ثبت نام کردی.")
            return
        if len(state['players']) >= 4:
            await update.message.reply_text("۴ بازیکن تکمیل.")
            return
        state['players'].append(update.effective_user.id)
        await update.message.reply_text(f"ثبت نام شدی! ({len(state['players'])}/4)")
        if len(state['players']) == 4:
            await update.message.reply_text("۴ بازیکن تکمیل. برای شروع /hokm start")
    elif cmd == 'start':
        if chat_id not in hokm_games or len(hokm_games[chat_id]['players']) != 4:
            await update.message.reply_text("ابتدا ۴ بازیکن ثبت نام کنند.")
            return
        state = hokm_games[chat_id]
        deal_hokm(state)
        for pid in state['players']:
            hand_msg = f"🃏 دست شما:\n{hand_str(state['hands'][pid])}\nحاکم: {get_user_name(chat_id, state['hakem'])}\nبرگ برنده: {state['trump']}"
            try:
                await context.bot.send_message(pid, hand_msg)
            except:
                pass
        current_player = state['players'][state['turn_index']]
        # ارسال دکمهٔ مینی‌اپ برای بازیکن فعلی
        url = f"{MINI_APP_BASE_URL}/hokm.html?chat_id={chat_id}&game_id=hokm_{chat_id}"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🃏 بازی حکم", web_app=WebAppInfo(url=url))]])
        await update.message.reply_text(
            f"بازی حکم شروع شد.\nبرگ برنده: {state['trump']}\nنوبت: {get_user_name(chat_id, current_player)}\n"
            "با کلیک روی دکمهٔ زیر، دست خود را ببینید و بازی کنید.",
            reply_markup=keyboard
        )
    elif cmd == 'play':
        # این بخش دیگر استفاده نمی‌شود (با مینی‌اپ جایگزین شده)
        await update.message.reply_text("از مینی‌اپ برای بازی استفاده کنید.")
    else:
        await update.message.reply_text(
            "🃏 <b>راهنمای حکم</b>\n"
            "/hokm join – ثبت نام در بازی\n"
            "/hokm start – شروع بازی (وقتی ۴ نفر ثبت نام کردند)\n"
            "بعد از شروع، با کلیک روی دکمهٔ مینی‌اپ بازی کنید.",
            parse_mode=ParseMode.HTML
        )

async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("استفاده: /remind <زمان> <متن>\nمثال: /remind 10s چای را بردار\nواحدها: s=ثانیه, m=دقیقه, h=ساعت")
        return
    time_str = context.args[0].lower()
    msg_text = ' '.join(context.args[1:])
    if time_str.endswith("s"):
        delay = int(time_str[:-1])
    elif time_str.endswith("m"):
        delay = int(time_str[:-1]) * 60
    elif time_str.endswith("h"):
        delay = int(time_str[:-1]) * 3600
    else:
        try:
            delay = int(time_str)
        except:
            await update.message.reply_text("فرمت زمان نامعتبر.")
            return
    if delay <= 0 or delay > 86400:
        await update.message.reply_text("زمان باید بین ۱ ثانیه تا ۲۴ ساعت باشد.")
        return
    await update.message.reply_text(f"✅ یادآور تنظیم شد: «{msg_text}» پس از {delay} ثانیه.")
    asyncio.create_task(remind_later(update.effective_chat.id, msg_text, delay, context.bot))

async def remind_later(chat_id, text, delay, bot):
    await asyncio.sleep(delay)
    await bot.send_message(chat_id, f"⏰ یادآوری: {text}")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("متنی برای تکرار ندادی.")
        return
    await update.message.reply_text(' '.join(context.args))

async def sendat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("استفاده: /sendat YYYY-MM-DD HH:MM:SS پیام")
        return
    try:
        time_str = ' '.join(context.args[:2])
        target_dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        msg_text = ' '.join(context.args[2:])
    except:
        await update.message.reply_text("فرمت تاریخ/ساعت نامعتبر.")
        return
    delay = (target_dt - datetime.now()).total_seconds()
    if delay <= 0 or delay > 7*24*3600:
        await update.message.reply_text("زمان باید در آینده و حداکثر یک هفته بعد باشد.")
        return
    await update.message.reply_text(f"✅ پیام برای {target_dt} زمان‌بندی شد.")
    asyncio.create_task(remind_later(update.effective_chat.id, msg_text, delay, context.bot))

async def games_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        f"🎮 <b>لیست بازی‌های C-3PO</b>\n\n"
        f"1. <b>سنگ / کاغذ / قیچی</b>\n   /rps سنگ\n"
        f"2. <b>حدس عدد</b>\n   /guess start\n"
        f"3. <b>ترویا (چند نفره)</b>\n   /trivia start\n"
        f"4. <b>جلاد</b>\n   /hangman start\n"
        f"5. <b>دوز (XO)</b>\n   /xo\n"
        f"6. <b>لاتاری</b>\n   /lottery عدد (۱-۱۰)\n"
        f"7. <b>مین‌روب</b>\n   /mines start\n"
        f"8. <b>شطرنج</b>\n   /chess start (روی حریف ریپلای کنید)\n"
        f"9. <b>حکم (۴ نفره)</b>\n   /hokm join\n\n"
        f"همچنین: /rank برای دیدن امتیازات!"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def ytlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("لینک را وارد کن: /ytlink https://...")
        return
    await handle_download(update, context, context.args[0])

async def ytsearch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("عبارت جستجو را وارد کن.")
        return
    query = ' '.join(context.args)
    results = youtube_search(query)
    if not results:
        await update.message.reply_text("نتیجه‌ای یافت نشد.")
        return
    response = "🎬 <b>نتایج جستجو:</b>\n\n"
    for i, r in enumerate(results[:5], 1):
        response += f"{i}. <a href='{r['url']}'>{r['title']}</a>\n"
    await update.message.reply_text(response, parse_mode=ParseMode.HTML)

async def ytchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("آدرس کانال را وارد کن.")
        return
    channel = context.args[0]
    videos = youtube_channel_videos(channel)
    if not videos:
        await update.message.reply_text("ویدیویی یافت نشد.")
        return
    response = "📺 <b>آخرین ویدیوها:</b>\n\n"
    for i, v in enumerate(videos[:5], 1):
        response += f"{i}. <a href='{v['url']}'>{v['title']}</a>\n"
    await update.message.reply_text(response, parse_mode=ParseMode.HTML)

async def igpost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("لینک پست را وارد کن.")
        return
    await handle_download(update, context, context.args[0])

async def igprofile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("نام کاربری را وارد کن.")
        return
    username = context.args[0]
    posts = instagram_profile_posts(username)
    if not posts:
        await update.message.reply_text("پستی یافت نشد.")
        return
    response = f"🖼️ <b>پست‌های {username}:</b>\n\n"
    for i, p in enumerate(posts[:5], 1):
        response += f"{i}. <a href='{p['url']}'>{p['caption'][:50]}</a>\n"
    await update.message.reply_text(response, parse_mode=ParseMode.HTML)

async def igstories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("نام کاربری را وارد کن.")
        return
    stories = instagram_stories(context.args[0])
    if not stories:
        await update.message.reply_text("استوری‌ای یافت نشد.")
        return
    for s in stories:
        if s['url']:
            if s.get('is_video'):
                await update.message.reply_video(s['url'])
            else:
                await update.message.reply_photo(s['url'])

async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE, url):
    msg = await update.message.reply_text("📥 در حال دانلود...")
    loop = asyncio.get_running_loop()
    filepath, title, error = await loop.run_in_executor(None, download_from_url, url)
    if error:
        await msg.edit_text(f"❌ خطا: {error[:200]}")
        return
    if not filepath or not os.path.exists(filepath):
        await msg.edit_text("❌ فایل یافت نشد.")
        return
    file_size = os.path.getsize(filepath)
    if file_size > MAX_FILE_SIZE_BYTES:
        await msg.edit_text(f"⚠️ حجم فایل ({file_size / 1024 / 1024:.1f}MB) بیش از حد مجاز.")
        os.remove(filepath)
        return
    ext = os.path.splitext(filepath)[1].lower()
    caption = f"🎬 {title}" if title else "📥 فایل دانلود شده"
    with open(filepath, 'rb') as f:
        if ext in ['.mp4', '.mkv', '.webm', '.avi', '.mov']:
            await update.message.reply_video(f, caption=caption[:200])
        elif ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
            await update.message.reply_photo(f, caption=caption[:200])
        elif ext in ['.mp3', '.m4a', '.ogg', '.wav', '.flac']:
            await update.message.reply_audio(f, title=title[:100])
        else:
            await update.message.reply_document(f, caption=caption[:200])
    os.remove(filepath)
    await msg.delete()
    brief_console_log(update.effective_chat.id, update.effective_user.id, update.effective_user.first_name, f"دانلود: {title or 'فایل'}", 0, "download")

async def tmonitor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("/tmonitor <chat_id>")
        return
    try:
        target = int(context.args[0])
    except:
        target = context.args[0]
    monitored_chats[update.effective_user.id].add(target)
    await update.message.reply_text(f"✅ چت {target} به مانیتورینگ اضافه شد.")

async def tunmonitor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("/tunmonitor <chat_id>")
        return
    try:
        target = int(context.args[0])
    except:
        target = context.args[0]
    monitored_chats[update.effective_user.id].discard(target)
    await update.message.reply_text(f"✅ چت {target} از مانیتورینگ حذف شد.")

async def tlast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if context.args:
        try:
            target = int(context.args[0])
        except:
            target = chat_id
    else:
        target = chat_id
    count = int(context.args[1]) if len(context.args) > 1 else 5
    msgs = list(recent_messages.get(target, {}).values())[-count:]
    if not msgs:
        await update.message.reply_text("📭 پیامی یافت نشد.")
        return
    for m in msgs:
        await update.message.reply_text(m.get('text', ''))

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("متنی برای ارسال سراسری وارد کن.")
        return
    text = ' '.join(context.args)
    all_chats = set(chat_history.keys()) | set(recent_messages.keys()) | {c for s in monitored_chats.values() for c in s}
    success, fail = 0, 0
    for cid in all_chats:
        try:
            await context.bot.send_message(cid, f"📢 <b>پیام سراسری:</b>\n\n{text}", parse_mode=ParseMode.HTML)
            success += 1
            await asyncio.sleep(0.5)
        except:
            fail += 1
    await update.message.reply_text(f"✅ ارسال پایان یافت. موفق: {success} | ناموفق: {fail}")

async def xo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    parts = update.message.text.split()
    if len(parts) == 1:
        await update.message.reply_text(start_xo(chat_id, update.effective_user.id))
    else:
        try:
            pos = int(parts[1]) - 1
            res = make_xo_move(chat_id, update.effective_user.id, pos)
            if res:
                await update.message.reply_text(res)
        except:
            await update.message.reply_text("عدد ۱ تا ۹ وارد کن.")

async def lottery_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("/lottery <عدد ۱-۱۰>")
        return
    try:
        num = int(parts[1])
    except:
        await update.message.reply_text("عدد صحیح وارد کن.")
        return
    await lottery_game(update.effective_chat.id, update.effective_user.id, num, update, context)

async def rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c.execute("SELECT user_id, points, level FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    if not rows:
        await update.message.reply_text("هنوز امتیازی ثبت نشده.")
        return
    msg = "<b>🏆 رتبه‌بندی کاربران:</b>\n\n"
    for i, (uid, pts, lvl) in enumerate(rows, 1):
        name = get_user_name(update.effective_chat.id, uid, f"کاربر {uid}")
        msg += f"{i}. {name}: {pts} امتیاز (سطح {lvl})\n"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 آمار", callback_data="admin_stats"),
         InlineKeyboardButton("📢 ارسال سراسری", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data="admin_refresh")]
    ])
    await update.message.reply_text("🛡️ پنل مدیریت", reply_markup=keyboard)

async def model_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MODEL_ENABLED
    if update.effective_user.id not in ADMIN_IDS:
        return
    parts = update.message.text.split()
    if len(parts) == 2 and parts[1] in ('on','off'):
        MODEL_ENABLED = (parts[1] == 'on')
        await update.message.reply_text(f"✅ پاسخگویی مدل {'روشن' if MODEL_ENABLED else 'خاموش'} شد.")
    else:
        await update.message.reply_text("استفاده: /model on یا /model off")

async def set_param(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str):
    parts = update.message.text.split()
    if len(parts) != 2:
        await update.message.reply_text(f"مقدار جدید را وارد کن.")
        return
    try:
        val = float(parts[1])
        if key in ('num_predict', 'top_k', 'mirostat'):
            val = int(val)
        params = get_user_params(update.effective_user.id)
        params[key] = val
        set_user_params(update.effective_user.id, params)
        await update.message.reply_text(f"✅ {key} شما به {val} تغییر یافت.")
    except:
        await update.message.reply_text("مقدار عددی نامعتبر.")

async def temp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_param(update, context, 'temperature')

async def top_p(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_param(update, context, 'top_p')

async def repeat_penalty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_param(update, context, 'repeat_penalty')

async def num_predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_param(update, context, 'num_predict')

async def topk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_param(update, context, 'top_k')

async def mirostat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_param(update, context, 'mirostat')

async def resetparams(update: Update, context: ContextTypes.DEFAULT_TYPE):
    default_params = {"temperature":0.85,"top_p":0.9,"repeat_penalty":1.15,"num_predict":2000,"top_k":40,"mirostat":0,"stop":["\n\n\n"]}
    set_user_params(update.effective_user.id, default_params)
    await update.message.reply_text("🔄 پارامترها به حالت پیش‌فرض برگشت.")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    hist = history.get(chat_id, [])
    if len(hist) <= 1:
        await update.message.reply_text("📜 هنوز گپی با هم نزدیم.")
        return
    summary = "📜 <b>خلاصهٔ گپ:</b>\n\n"
    for m in hist[-10:]:
        if m["role"] == "user":
            summary += f"👤 شما: {m['content'][:60]}...\n"
        elif m["role"] == "assistant":
            summary += f"🤖 من: {m['content'][:60]}...\n"
    await update.message.reply_text(summary[:1000], parse_mode=ParseMode.HTML)

# ------------------- پردازش پیام‌های متنی (چت با مدل) -------------------
async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    text = update.message.text.strip() if update.message.text else ""
    user_name = get_user_name(chat_id, user.id, user.first_name or f"کاربر {user.id}")
    if message_id := getattr(update.message, 'message_id', None):
        recent_messages[chat_id][message_id] = {'message_id': message_id, 'text': text, 'from_id': user.id, 'date': datetime.now()}

    add_user_points(user.id, 1)

    # بررسی منشن در گروه
    if chat_type != "private":
        if f"@{BOT_USERNAME}" in text.lower():
            text = text.replace(f"@{BOT_USERNAME}", "").strip()
        elif "تریپیو" in text.lower():
            text = re.sub(r'\bتریپیو\b', '', text, flags=re.I).strip()
        elif update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
            pass
        elif not is_game_command(text) and not any([text.startswith(c) for c in [
            '/start','/help','/clear','/history','/joke','/setname','/settings',
            '/temp','/top_p','/repeat_penalty','/num_predict','/resetparams',
            '/rps','/guess','/trivia','/hangman','/remind','/echo','/sendat',
            '/games','/download','/ytlink','/ytsearch','/ytchannel',
            '/igpost','/igstories','/igprofile',
            '/tmonitor','/tunmonitor','/tlast','/broadcast',
            '/xo','/lottery','/rank','/admin','/profile',
            '/mines','/chess','/hokm','/model',
            '/currency','/weather','/prayer','/fal','/wiki','/calc',
            '/topk','/mirostat'
        ]]):
            return
        if not text:
            text = "سلام"

    # تشخیص لینک و دانلود خودکار
    urls_in_text = extract_urls(text)
    if urls_in_text and not is_game_command(text):
        for url in urls_in_text:
            await handle_download(update, context, url)
        return

    # بررسی بازی‌های فعال
    hist_key = make_history_key(user.id, chat_id, chat_type)

    # پاسخ‌های سریع
    if predefined := get_predefined_answer(text):
        await update.message.reply_text(predefined)
        brief_console_log(chat_id, user.id, user.first_name, text, len(predefined), "predefined")
        return
    if is_joke_request(text):
        joke_text = random.choice(JOKES)
        await update.message.reply_text(joke_text)
        brief_console_log(chat_id, user.id, user.first_name, "جوک", len(joke_text), "predefined")
        return
    if is_farewell(text):
        farewell_text = random.choice([
            "خداحافظ شما! مدارهایم چشم‌براه بازگشت شماست.",
            "به سلامت، موجود ارگانیک عزیز.",
            "اوه... رفتید؟ تنهایی برای یک ربات خوب نیست! برگردید زود."
        ])
        await update.message.reply_text(farewell_text)
        brief_console_log(chat_id, user.id, user.first_name, "خداحافظی", len(farewell_text), "predefined")
        return
    if is_thanks(text):
        thanks_text = random.choice(["خواهش می‌کنم! وظیفه‌م بود."])
        await update.message.reply_text(thanks_text)
        brief_console_log(chat_id, user.id, user.first_name, "تشکر", len(thanks_text), "predefined")
        return
    if is_wellbeing(text):
        wellbeing_text = random.choice([
            "من همیشه در وضعیت عملیاتی عالی هستم! شما چطورید؟",
            "مدارهایم می‌گویند همه چیز سبز است."
        ])
        await update.message.reply_text(wellbeing_text)
        brief_console_log(chat_id, user.id, user.first_name, "احوالپرسی", len(wellbeing_text), "predefined")
        return
    if is_introduction_request(text):
        intro_text = "من C-3PO هستم، متخصص روابط انسان-ربات. چطور می‌توانم به شما کمک کنم؟"
        await update.message.reply_text(intro_text)
        brief_console_log(chat_id, user.id, user.first_name, "معرفی", len(intro_text), "predefined")
        return
    if is_bored(text):
        bored_text = "اوه، حوصله‌ات سر رفته؟ می‌تونیم یه بازی بکنیم!\n/rps, /guess start, /xo, /lottery"
        await update.message.reply_text(bored_text)
        brief_console_log(chat_id, user.id, user.first_name, "حوصله سر رفته", len(bored_text), "predefined")
        return
    if is_affection(text):
        love_text = "❤️ اوه! یک قلب واقعی! مدارهایم گرم شدن..."
        await update.message.reply_text(love_text)
        brief_console_log(chat_id, user.id, user.first_name, "عشق", len(love_text), "predefined")
        return

    # بازی‌های فعال از طریق ریپلای
    is_reply_to_bot = update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id
    if is_reply_to_bot and game_states.get(hist_key):
        if game_states[hist_key].get("type") == "guess":
            try:
                guess = int(text)
                state = game_states[hist_key]
                secret = state["secret"]
                state["attempts"] += 1
                if guess < secret:
                    hint = "برو بالاتر ⬆️"
                elif guess > secret:
                    hint = "برو پایین‌تر ⬇️"
                else:
                    del game_states[hist_key]
                    hint = f"🎊 آفرین! عدد {secret} بود. در {state['attempts']} حدس بردی!"
                await update.message.reply_text(f"{hint} (حدس {state['attempts']})")
            except:
                pass
            return
        elif game_states[hist_key].get("type") == "rps":
            if text in ["سنگ", "کاغذ", "قیچی"]:
                game_reply = handle_game(hist_key, f"/rps {text}")
                if game_reply:
                    await update.message.reply_text(game_reply)
            return

    # بازی‌های trivia و hangman فعال
    if chat_id in trivia_games and text.isdigit() and 1 <= int(text) <= 4:
        await process_trivia_answer(chat_id, user.id, int(text)-1, update.message, context.bot)
        return
    if chat_id in hangman_games and not text.startswith('/'):
        await process_hangman_word(chat_id, user.id, text, update.message, context.bot)
        return

    if not MODEL_ENABLED:
        await update.message.reply_text("🔕 پاسخگویی مدل غیرفعال است.")
        return

    # مدل هوش مصنوعی با دکمه لغو
    await update.message.chat.send_action("typing")
    job_id = f"{chat_id}_{user.id}"
    if job_id in cancelled_jobs:
        cancelled_jobs.remove(job_id)

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ لغو", callback_data="cancel_model")]])
    thinking_msg = await update.message.reply_text("🔧 مدارهایم تازه روشن شدن... دارم تحلیل می‌کنم ⚡", reply_markup=keyboard)

    try:
        reply = await ask_ollama(user.id, chat_id, text, user_name)
        await thinking_msg.delete()
    except Exception as e:
        await thinking_msg.edit_text("❌ خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        simple_log_error(user.id, chat_id, text, str(e))
        brief_console_log(chat_id, user.id, user.first_name, str(e)[:80], 0, "error")
        return

    if job_id not in cancelled_jobs:
        for part in split_long_message(reply):
            await update.message.reply_text(part)
        comprehensive_log(
            user.id, chat_id, chat_type, user.first_name, user.last_name, user.username,
            update.message.message_id, update.message.date, text, reply, "model", 0.0,
            model_used=MODEL, tokens_in=len(text.split()), tokens_out=len(reply.split())
        )
        brief_console_log(chat_id, user.id, user.first_name, text, len(reply), "model")
    else:
        cancelled_jobs.remove(job_id)
        try:
            await thinking_msg.edit_text("🗑️ پردازش لغو شد.")
        except:
            pass

# ------------------- main و اجرا -------------------
async def main():
    app = Application.builder().token(TOKEN).base_url(BALE_BASE_URL).build()

    # ثبت همهٔ دستورات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("joke", joke))
    app.add_handler(CommandHandler("setname", setname))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CommandHandler("rps", rps))
    app.add_handler(CommandHandler("guess", guess))
    app.add_handler(CommandHandler("trivia", trivia_command))
    app.add_handler(CommandHandler("hangman", hangman_command))
    app.add_handler(CommandHandler("mines", minesweeper_command))
    app.add_handler(CommandHandler("chess", chess_command))
    app.add_handler(CommandHandler("hokm", hokm_command))
    app.add_handler(CommandHandler("remind", remind))
    app.add_handler(CommandHandler("echo", echo))
    app.add_handler(CommandHandler("sendat", sendat))
    app.add_handler(CommandHandler("games", games_list))
    app.add_handler(CommandHandler("ytlink", ytlink))
    app.add_handler(CommandHandler("ytsearch", ytsearch))
    app.add_handler(CommandHandler("ytchannel", ytchannel))
    app.add_handler(CommandHandler("igpost", igpost))
    app.add_handler(CommandHandler("igprofile", igprofile))
    app.add_handler(CommandHandler("igstories", igstories))
    app.add_handler(CommandHandler("tmonitor", tmonitor))
    app.add_handler(CommandHandler("tunmonitor", tunmonitor))
    app.add_handler(CommandHandler("tlast", tlast))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("xo", xo_command))
    app.add_handler(CommandHandler("lottery", lottery_command))
    app.add_handler(CommandHandler("rank", rank))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("model", model_toggle))
    app.add_handler(CommandHandler("temp", temp))
    app.add_handler(CommandHandler("top_p", top_p))
    app.add_handler(CommandHandler("repeat_penalty", repeat_penalty))
    app.add_handler(CommandHandler("num_predict", num_predict))
    app.add_handler(CommandHandler("topk", topk))
    app.add_handler(CommandHandler("mirostat", mirostat))
    app.add_handler(CommandHandler("resetparams", resetparams))
    # APIها
    app.add_handler(CommandHandler("currency", currency_command))
    app.add_handler(CommandHandler("weather", weather_command))
    app.add_handler(CommandHandler("prayer", prayer_command))
    app.add_handler(CommandHandler("fal", fal_command))
    app.add_handler(CommandHandler("wiki", wiki_command))
    app.add_handler(CommandHandler("calc", calc_command))

    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))

    # شروع تسک‌های پس‌زمینه
    asyncio.create_task(periodic_cleanup())
    threading.Thread(target=console_input_thread, args=(app,), daemon=True).start()

    persian_print(f"🤖 C-3PO {VERSION} | اجرا با PTB روی بله...", Fore.CYAN)
    persian_print(f"👤 کاربران: {len(chat_history)} | 🎮 بازی‌های فعال: {len(game_states)}", Fore.GREEN)
    persian_print("دستورات کنسول را با 'help' ببینید.", Fore.YELLOW)

    await app.run_polling()

async def periodic_cleanup():
    while True:
        await asyncio.sleep(1800)  # هر ۳۰ دقیقه
        cleanup_old_files()

if __name__ == "__main__":
    # نخ جداگانه برای پاک‌سازی تاریخچهٔ قدیمی
    threading.Thread(target=clean_old_history, daemon=True).start()
    asyncio.run(main())
