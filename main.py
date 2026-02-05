#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎮 AVIATOR PRO - النسخة الاحترافية
نظام تحطم الطائرة مع 50 جولة مختلفة
"""

import os
import asyncio
import random
import sqlite3
import logging
import json
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# ==================== إعدادات النظام ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== البيانات الثابتة ====================
BOT_TOKEN = "8589461643:AAG1tUhcZ5OdJmxmoDlt7KDYsY7jSydjqqQ"
ADMIN_ID = 5848548017  # ضع ID حسابك هنا
BASE_URL = "https://aviator-production-e666.up.railway.app"  # سيتم تحديثه تلقائياً

# تأكد من أن BASE_URL يبدأ بـ https://
if not BASE_URL.startswith('https://'):
    BASE_URL = 'https://' + BASE_URL

# إعدادات اللعبة
BETTING_DURATION = 30  # 30 ثانية للرهان فقط
ROUND_DELAY = 5  # 3 ثواني بين الجولات
BET_OPTIONS = [10, 50, 100, 500, 1000, 5000]
INITIAL_BALANCE = 10  # رصيد بداية لكل مستخدم جديد

# 50 نقطة تحطم مختلفة (مضاعفات)
CRASH_POINTS = [
    0.2, 1.5, 2.0, 0.5, 3.0, 1.9, 2.5, 0.3, 4.0, 1.3,
    2.2, 0.8, 5.0, 1.6, 1.8, 0.6, 2.0, 1.9, 2.2, 0.4,
    6.0, 2.1, 1.5, 0.2, 2.2, 1.3, 3.8, 0.1, 9.0, 2.4,
    4.0, 1.1, 9.0, 2.6, 4.2, 0.7, 16.0, 2.7, 2.5, 0.9,
    2.0, 2.9, 4.8, 1.4, 1.1.0, 3.1, 5.0, 0.0, 2.0, 5.0
]

# ==================== قاعدة البيانات (SQLite) ====================
class Database:
    def __init__(self, db_name="game.db"):
        self.db_name = db_name
        self.init_db()
    
    def init_db(self):
        """تهيئة قاعدة البيانات"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # جدول المستخدمين
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance INTEGER DEFAULT 1000,
                total_wagered INTEGER DEFAULT 0,
                total_won INTEGER DEFAULT 0,
                total_loss INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول المعاملات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                type TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول الجولات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rounds (
                round_id INTEGER PRIMARY KEY AUTOINCREMENT,
                crash_point REAL,
                result TEXT,
                status TEXT DEFAULT 'betting',
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                total_bets INTEGER DEFAULT 0,
                total_amount INTEGER DEFAULT 0
            )
        ''')
        
        # جدول الرهانات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                round_id INTEGER,
                amount INTEGER,
                cashout_multiplier REAL DEFAULT 0,
                win_amount INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                cashout_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ تم تهيئة قاعدة البيانات")
    
    def create_user(self, user_id, username):
        """إنشاء مستخدم جديد"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute(
            'INSERT OR IGNORE INTO users (user_id, username, balance) VALUES (?, ?, ?)',
            (user_id, username, INITIAL_BALANCE)
        )
        
        conn.commit()
        conn.close()
    
    def get_balance(self, user_id):
        """جلب رصيد المستخدم"""
        if user_id == ADMIN_ID:
            return 999999999  # رصيد غير محدود للأدمن
        
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        conn.close()
        return result[0] if result else INITIAL_BALANCE
    
    def update_balance(self, user_id, amount):
        """تحديث رصيد المستخدم"""
        if user_id == ADMIN_ID:
            return 999999999  # الأدمن لا يتغير رصيده
        
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute(
            'UPDATE users SET balance = balance + ? WHERE user_id = ?',
            (amount, user_id)
        )
        
        # تحديث الإحصائيات
        if amount > 0:
            cursor.execute(
                'UPDATE users SET total_won = total_won + ? WHERE user_id = ?',
                (amount, user_id)
            )
        else:
            cursor.execute(
                'UPDATE users SET total_wagered = total_wagered + ? WHERE user_id = ?',
                (abs(amount), user_id)
            )
        
        cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
        new_balance = cursor.fetchone()[0]
        
        conn.commit()
        conn.close()
        return new_balance
    
    def add_transaction(self, user_id, amount, type, description):
        """إضافة معاملة"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute(
            'INSERT INTO transactions (user_id, amount, type, description) VALUES (?, ?, ?, ?)',
            (user_id, amount, type, description)
        )
        
        conn.commit()
        conn.close()
    
    def create_round(self, crash_point):
        """إنشاء جولة جديدة"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute(
            'INSERT INTO rounds (crash_point, status) VALUES (?, ?)',
            (crash_point, 'betting')
        )
        round_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        return round_id
    
    def add_bet(self, user_id, round_id, amount):
        """إضافة رهان"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute(
            'INSERT INTO bets (user_id, round_id, amount, status) VALUES (?, ?, ?, ?)',
            (user_id, round_id, amount, 'active')
        )
        
        cursor.execute(
            'UPDATE rounds SET total_bets = total_bets + 1, total_amount = total_amount + ? WHERE round_id = ?',
            (amount, round_id)
        )
        
        conn.commit()
        conn.close()
    
    def update_round_status(self, round_id, status, result=""):
        """تحديث حالة الجولة"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute(
            'UPDATE rounds SET status = ?, result = ?, end_time = CURRENT_TIMESTAMP WHERE round_id = ?',
            (status, result, round_id)
        )
        
        conn.commit()
        conn.close()
    
    def cashout_bet(self, user_id, round_id, multiplier):
        """صرف الرهان"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # جلب الرهان
        cursor.execute(
            'SELECT id, amount FROM bets WHERE user_id = ? AND round_id = ? AND status = ?',
            (user_id, round_id, 'active')
        )
        bet = cursor.fetchone()
        
        if not bet:
            conn.close()
            return None
        
        bet_id, amount = bet
        win_amount = int(amount * multiplier)
        
        # تحديث الرهان
        cursor.execute(
            '''UPDATE bets SET 
               cashout_multiplier = ?, 
               win_amount = ?, 
               status = ?, 
               cashout_time = CURRENT_TIMESTAMP 
               WHERE id = ?''',
            (multiplier, win_amount, 'cashed', bet_id)
        )
        
        conn.commit()
        conn.close()
        return win_amount
    
    def get_round_bets(self, round_id):
        """جلب رهانات الجولة"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT * FROM bets WHERE round_id = ?',
            (round_id,)
        )
        bets = cursor.fetchall()
        
        conn.close()
        return bets
    
    def get_user_stats(self, user_id):
        """جلب إحصائيات المستخدم"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT total_wagered, total_won, total_loss FROM users WHERE user_id = ?',
            (user_id,)
        )
        stats = cursor.fetchone()
        
        conn.close()
        
        if stats:
            total_wagered, total_won, total_loss = stats
            profit = total_won - total_wagered
            return {
                'total_wagered': total_wagered or 0,
                'total_won': total_won or 0,
                'total_loss': total_loss or 0,
                'profit': profit,
                'total_bets': (total_wagered or 0) // 100  # تقدير
            }
        
        return {'total_wagered': 0, 'total_won': 0, 'total_loss': 0, 'profit': 0, 'total_bets': 0}
    
    def get_leaderboard(self, limit=10):
        """جلب قائمة المتصدرين"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT user_id, username, balance FROM users ORDER BY balance DESC LIMIT ?',
            (limit,)
        )
        leaders = cursor.fetchall()
        
        conn.close()
        return leaders

# إنشاء كائن قاعدة البيانات
db = Database()

# ==================== إدارة الجولات ====================
class GameRound:
    def __init__(self):
        self.round_id = None
        self.crash_point = None
        self.status = "waiting"  # waiting, betting, flying, crashed, finished
        self.start_time = None
        self.betting_end = None
        self.current_multiplier = 1.0
        self.flying_start = None
        self.crash_time = None
        self.active_bets = {}  # user_id: amount
        self.cashed_out = {}  # user_id: {"multiplier": x, "amount": y}
    
    def start_new_round(self):
        """بدء جولة جديدة"""
        # اختيار نقطة تحطم عشوائية من القائمة
        self.crash_point = random.choice(CRASH_POINTS)
        self.round_id = db.create_round(self.crash_point)
        self.status = "betting"
        self.start_time = datetime.now()
        self.betting_end = self.start_time + timedelta(seconds=BETTING_DURATION)
        self.current_multiplier = 1.0
        self.flying_start = None
        self.crash_time = None
        self.active_bets = {}
        self.cashed_out = {}
        
        logger.info(f"🔄 بدأت الجولة #{self.round_id} - نقطة التحطم: {self.crash_point}x")
        return self.round_id
    
    def update(self):
        """تحديث حالة الجولة"""
        now = datetime.now()
        
        if self.status == "betting" and now >= self.betting_end:
            # انتهى وقت الرهان، تبدأ مرحلة الطيران
            self.status = "flying"
            self.flying_start = now
            logger.info(f"✈️ بدأت مرحلة الطيران للجولة #{self.round_id}")
        
        elif self.status == "flying":
            # حساب المضاعف الحالي أثناء الطيران
            if self.flying_start:
                elapsed = (now - self.flying_start).total_seconds()
                
                # حساب المضاعف (يتزايد مع الوقت)
                # سرعة مضاعف واقعية: 0.5x كل ثانية
                self.current_multiplier = 1.0 + (elapsed * 0.5)
                
                # التحقق من الوصول لنقطة التحطم
                if self.current_multiplier >= self.crash_point:
                    self.status = "crashed"
                    self.crash_time = now
                    
                    # تحديث قاعدة البيانات
                    result_text = f"تحطمت عند {self.crash_point}x"
                    db.update_round_status(self.round_id, "crashed", result_text)
                    
                    logger.info(f"💥 تحطمت الجولة #{self.round_id} عند {self.crash_point}x")
                    
                    # معالجة الرهانات المتبقية (خسارة)
                    self.process_crash_results()
    
    def process_crash_results(self):
        """معالجة نتائج التحطم"""
        for user_id, amount in self.active_bets.items():
            if user_id not in self.cashed_out:
                # المستخدم لم يصرف - خسارة كاملة
                db.add_transaction(
                    user_id, 
                    -amount, 
                    "loss", 
                    f"خسارة بسبب تحطم الطائرة عند {self.crash_point}x في الجولة #{self.round_id}"
                )
                
                # تحديث رصيد الخسارة
                conn = sqlite3.connect(db.db_name)
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE users SET total_loss = total_loss + ? WHERE user_id = ?',
                    (amount, user_id)
                )
                conn.commit()
                conn.close()
        
        # بعد 3 ثواني، تبدأ جولة جديدة
        asyncio.create_task(self.start_next_round())
    
    async def start_next_round(self):
        """بدء الجولة التالية"""
        await asyncio.sleep(ROUND_DELAY)
        self.start_new_round()
    
    def get_time_remaining(self):
        """الحصول على الوقت المتبقي"""
        if self.status == "betting" and self.betting_end:
            remaining = (self.betting_end - datetime.now()).total_seconds()
            return max(0, int(remaining))
        return 0
    
    def get_flight_time(self):
        """الحصول على وقت الطيران"""
        if self.status == "flying" and self.flying_start:
            elapsed = (datetime.now() - self.flying_start).total_seconds()
            return max(0, int(elapsed))
        return 0

# إنشاء كائن الجولة
game_round = GameRound()

# ==================== البوت التليجرام ====================
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

@dp.message_handler(commands=['start', 'ابدأ'])
async def cmd_start(message: types.Message):
    """بدء البوت"""
    user_id = message.from_user.id
    username = message.from_user.first_name or "مستخدم"
    
    # إنشاء المستخدم في قاعدة البيانات
    db.create_user(user_id, username)
    
    # جلب الرصيد
    balance = db.get_balance(user_id)
    
    # إنشاء لوحة المفاتيح
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🎮 العب الآن", callback_data="play"),
        InlineKeyboardButton("💰 رصيدي", callback_data="balance")
    )
    keyboard.add(
        InlineKeyboardButton("📤 إرسال رصيد", callback_data="send"),
        InlineKeyboardButton("📊 إحصائيات", callback_data="stats")
    )
    keyboard.add(
        InlineKeyboardButton("🏆 المتصدرين", callback_data="leaderboard"),
        InlineKeyboardButton("❓ المساعدة", callback_data="help")
    )
    
    # رسالة الترحيب
    welcome_text = f"""
🎮 **Aviator Pro** ✈️

مرحباً {username}! 👋

💰 **رصيدك الحالي:** {balance:,} نقطة

⏰ **كل جولة:** {BETTING_DURATION} ثانية للرهان
✈️ **ثم طائرة تصعد حتى تتحطم**
💰 **صرف في الوقت المناسب لتحقيق الربح!**

🎯 **اختر من الأزرار أدناه:**
    """
    
    await message.answer(welcome_text, reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data == 'play')
async def callback_play(callback_query: types.CallbackQuery):
    """زر العب الآن"""
    user_id = callback_query.from_user.id
    game_url = f"{BASE_URL}/game?user_id={user_id}"
    
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        user_id,
        f"🎮 **اضغط على الرابط للعب:**\n\n{game_url}",
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("🎮 افتح اللعبة", url=game_url)
        )
    )

@dp.callback_query_handler(lambda c: c.data == 'balance')
async def callback_balance(callback_query: types.CallbackQuery):
    """زر الرصيد"""
    user_id = callback_query.from_user.id
    balance = db.get_balance(user_id)
    
    balance_text = f"💰 **رصيدك الحالي:** {balance:,} نقطة"
    
    if user_id == ADMIN_ID:
        balance_text += "\n\n👑 **أنت الأدمن - رصيدك غير محدود**"
    
    await bot.answer_callback_query(callback_query.id, balance_text, show_alert=True)

@dp.callback_query_handler(lambda c: c.data == 'send')
async def callback_send(callback_query: types.CallbackQuery):
    """زر إرسال رصيد"""
    user_id = callback_query.from_user.id
    
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        user_id,
        "📤 **لإرسال رصيد:**\n\n"
        "استخدم الأمر:\n"
        "`/send [معرف المستخدم] [المبلغ]`\n\n"
        "**مثال:**\n"
        "`/send 123456789 500`\n\n"
        "💡 **ملاحظات:**\n"
        "• أدخل المعرف أولاً\n"
        "• ثم أدخل المبلغ\n"
        "• الحد الأدنى: 10 نقطة\n"
        "• تأكد من أن لديك رصيد كافي"
    )

@dp.callback_query_handler(lambda c: c.data == 'stats')
async def callback_stats(callback_query: types.CallbackQuery):
    """زر الإحصائيات"""
    user_id = callback_query.from_user.id
    stats = db.get_user_stats(user_id)
    balance = db.get_balance(user_id)
    
    stats_text = f"""
📊 **إحصائياتك:**

💰 **الرصيد:** {balance:,} نقطة
🎯 **الرهانات:** {stats['total_bets']}
📈 **إجمالي المراهن:** {stats['total_wagered']:,}
🏆 **إجمالي الأرباح:** {stats['total_won']:,}
📉 **إجمالي الخسائر:** {stats['total_loss']:,}
💵 **الربح/الخسارة:** {stats['profit']:,}
    """
    
    await bot.answer_callback_query(callback_query.id, stats_text, show_alert=True)

@dp.callback_query_handler(lambda c: c.data == 'leaderboard')
async def callback_leaderboard(callback_query: types.CallbackQuery):
    """زر المتصدرين"""
    leaders = db.get_leaderboard(5)
    
    leaderboard_text = "🏆 **أفضل 5 لاعبين:**\n\n"
    
    for idx, (user_id, username, balance) in enumerate(leaders, 1):
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
        name = username or f"المستخدم {user_id}"
        leaderboard_text += f"{medal} **{name}:** {balance:,} نقطة\n"
    
    await bot.answer_callback_query(callback_query.id, leaderboard_text, show_alert=True)

@dp.callback_query_handler(lambda c: c.data == 'help')
async def callback_help(callback_query: types.CallbackQuery):
    """زر المساعدة"""
    help_text = """
❓ **كيف تلعب Aviator:**

1️⃣ **الرهان:** خلال 30 ثانية، اختر مبلغ الرهان
2️⃣ **الطيران:** بعد 30 ثانية، تبدأ الطائرة في الصعود
3️⃣ **المضاعف:** يزداد كلما ارتفعت الطائرة
4️⃣ **الصرف:** اضغط "صرف الآن" للحصول على المضاعف الحالي
5️⃣ **التحطم:** الطائرة تتحطم عند نقطة عشوائية
6️⃣ **الربح:** إذا صرفت قبل التحطم تربح
7️⃣ **الخسارة:** إذا لم تصرف قبل التحطم تخسر

⚠️ **نصائح:**
• لا تنتظر كثيراً قد تتحطم الطائرة فجأة!
• صرف عندما تشعر أن المضاعف جيد
• العب بمسؤولية
    """
    
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, help_text)

@dp.message_handler(commands=['send', 'ارسال', 'تحويل'])
async def cmd_send(message: types.Message):
    """إرسال رصيد"""
    user_id = message.from_user.id
    parts = message.text.split()
    
    if len(parts) < 3:
        await message.answer(
            "📝 **طريقة الاستخدام:**\n"
            "`/send [معرف المستخدم] [المبلغ]`\n\n"
            "**مثال:**\n"
            "`/send 123456789 500`"
        )
        return
    
    try:
        to_user_id = int(parts[1])
        amount = int(parts[2])
    except ValueError:
        await message.answer("❌ خطأ في البيانات. تأكد من إدخال المعرف أولاً ثم المبلغ")
        return
    
    if amount <= 0:
        await message.answer("❌ المبلغ يجب أن يكون أكبر من صفر")
        return
    
    if amount < 10:
        await message.answer("❌ الحد الأدنى للإرسال هو 10 نقطة")
        return
    
    # التحقق من الرصيد (الأدمن رصيده غير محدود)
    if user_id != ADMIN_ID:
        sender_balance = db.get_balance(user_id)
        if sender_balance < amount:
            await message.answer(f"❌ رصيدك غير كافي. رصيدك: {sender_balance:,}")
            return
    
    if user_id == to_user_id:
        await message.answer("❌ لا يمكنك إرسال الرصيد لنفسك")
        return
    
    # الأدمن لا يخصم منه
    if user_id != ADMIN_ID:
        db.update_balance(user_id, -amount)
        db.add_transaction(user_id, -amount, "send", f"إرسال إلى {to_user_id}")
    
    # إضافة للمستلم
    db.update_balance(to_user_id, amount)
    db.add_transaction(to_user_id, amount, "receive", f"استلام من {user_id}")
    
    await message.answer(
        f"✅ **تم إرسال الرصيد بنجاح**\n\n"
        f"👤 **إلى:** {to_user_id}\n"
        f"💰 **المبلغ:** {amount:,} نقطة\n"
        f"💳 **حالة الرصيد:** تمت العملية"
    )

# ==================== واجهة الويب (FastAPI) ====================
app = FastAPI(title="Aviator Pro", version="1.0.0")

# إضافة CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# HTML واجهة اللعبة
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>✈️ Aviator Pro</title>
    <style>
        :root {
            --primary: #00b4d8;
            --secondary: #0077b6;
            --success: #00ff88;
            --danger: #ff416c;
            --warning: #ffd700;
            --dark: #1a1a2e;
            --darker: #16213e;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        
        body {
            background: linear-gradient(135deg, var(--dark) 0%, var(--darker) 100%);
            min-height: 100vh;
            color: white;
            padding: 15px;
            overflow-x: hidden;
        }
        
        .container {
            max-width: 500px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            border: 1px solid rgba(255,255,255,0.1);
        }
        
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid rgba(255,255,255,0.1);
        }
        
        .logo {
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 22px;
            font-weight: bold;
        }
        
        .logo span {
            font-size: 32px;
            animation: float 3s ease-in-out infinite;
        }
        
        @keyframes float {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-5px); }
        }
        
        .user-info {
            text-align: left;
            font-size: 14px;
            opacity: 0.8;
        }
        
        .balance-card {
            background: linear-gradient(45deg, var(--primary), var(--secondary));
            padding: 15px 25px;
            border-radius: 15px;
            font-weight: bold;
            font-size: 18px;
            text-align: center;
            box-shadow: 0 4px 15px rgba(0, 180, 216, 0.3);
            margin-bottom: 20px;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.02); }
        }
        
        .round-info {
            background: rgba(0,0,0,0.3);
            padding: 20px;
            border-radius: 15px;
            margin: 15px 0;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.1);
        }
        
        .round-id {
            font-size: 16px;
            opacity: 0.8;
            margin-bottom: 10px;
        }
        
        .timer {
            font-size: 36px;
            font-weight: bold;
            margin: 15px 0;
            color: var(--success);
            text-shadow: 0 0 15px var(--success);
            font-family: 'Courier New', monospace;
        }
        
        .round-status {
            font-size: 18px;
            margin: 10px 0;
            color: var(--warning);
        }
        
        .multiplier-info {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 15px;
            padding: 10px 20px;
            background: rgba(0,0,0,0.2);
            border-radius: 10px;
        }
        
        .game-area {
            position: relative;
            height: 300px;
            background: rgba(0, 0, 0, 0.4);
            border-radius: 15px;
            margin: 20px 0;
            overflow: hidden;
            border: 2px solid rgba(255,255,255,0.1);
        }
        
        .sky {
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(to bottom, #0a0a2a, #1a1a4a);
        }
        
        .runway {
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            height: 50px;
            background: linear-gradient(to top, #333, #666);
        }
        
        .runway-lines {
            position: absolute;
            bottom: 25px;
            left: 0;
            right: 0;
            height: 3px;
            background: repeating-linear-gradient(
                90deg,
                transparent,
                transparent 20px,
                var(--warning) 20px,
                var(--warning) 40px
            );
        }
        
        #plane {
            position: absolute;
            bottom: 60px;
            left: 50%;
            transform: translateX(-50%);
            font-size: 50px;
            z-index: 10;
            filter: drop-shadow(0 0 5px rgba(255, 255, 255, 0.7));
            transition: bottom 0.3s ease-out;
        }
        
        .multiplier-display {
            position: absolute;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            font-size: 28px;
            font-weight: bold;
            color: var(--success);
            z-index: 20;
            text-shadow: 0 0 10px var(--success);
            background: rgba(0,0,0,0.5);
            padding: 8px 20px;
            border-radius: 25px;
            border: 2px solid var(--success);
        }
        
        .flight-path {
            position: absolute;
            bottom: 60px;
            left: 50%;
            width: 2px;
            height: 200px;
            background: linear-gradient(to top, rgba(0, 255, 136, 0.3), transparent);
            transform: translateX(-50%);
            z-index: 1;
        }
        
        .crash-point {
            position: absolute;
            top: 60px;
            right: 20px;
            background: rgba(255, 65, 108, 0.2);
            padding: 8px 15px;
            border-radius: 10px;
            border: 1px solid var(--danger);
            font-size: 14px;
        }
        
        .message {
            text-align: center;
            margin: 15px 0;
            padding: 15px;
            border-radius: 10px;
            font-size: 16px;
            min-height: 20px;
            transition: all 0.3s ease;
        }
        
        .success { 
            background: rgba(0, 255, 136, 0.1);
            color: var(--success);
            border: 1px solid var(--success);
        }
        
        .error { 
            background: rgba(255, 68, 68, 0.1);
            color: var(--danger);
            border: 1px solid var(--danger);
        }
        
        .warning { 
            background: rgba(255, 193, 7, 0.1);
            color: var(--warning);
            border: 1px solid var(--warning);
        }
        
        .info { 
            background: rgba(0, 180, 216, 0.1);
            color: var(--primary);
            border: 1px solid var(--primary);
        }
        
        .bet-section {
            margin: 20px 0;
        }
        
        .section-title {
            font-size: 18px;
            margin-bottom: 15px;
            color: var(--primary);
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .bet-amounts {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            margin: 15px 0;
        }
        
        .bet-btn {
            padding: 18px 12px;
            border: none;
            border-radius: 10px;
            background: rgba(255,255,255,0.1);
            color: white;
            font-size: 18px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 5px;
        }
        
        .bet-btn:hover:not(.selected):not(:disabled) {
            background: rgba(255,255,255,0.2);
            transform: translateY(-3px);
        }
        
        .bet-btn.selected {
            background: linear-gradient(45deg, var(--success), #00b09b);
            box-shadow: 0 4px 15px rgba(0, 176, 155, 0.4);
            transform: scale(1.05);
        }
        
        .bet-btn:disabled {
            opacity: 0.3;
            cursor: not-allowed;
        }
        
        .bet-amount {
            font-size: 20px;
        }
        
        .bet-label {
            font-size: 12px;
            opacity: 0.8;
        }
        
        .controls {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin: 20px 0;
        }
        
        .action-btn {
            padding: 20px;
            border: none;
            border-radius: 15px;
            font-size: 18px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }
        
        .bet-action {
            background: linear-gradient(45deg, var(--danger), #ff4b2b);
        }
        
        .bet-action:hover:not(:disabled) {
            background: linear-gradient(45deg, #ff4b2b, var(--danger));
            transform: translateY(-3px);
            box-shadow: 0 5px 20px rgba(255, 65, 108, 0.4);
        }
        
        .cashout-action {
            background: linear-gradient(45deg, var(--success), #00b09b);
        }
        
        .cashout-action:hover:not(:disabled) {
            background: linear-gradient(45deg, #00b09b, var(--success));
            transform: translateY(-3px);
            box-shadow: 0 5px 20px rgba(0, 255, 136, 0.4);
        }
        
        .action-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none !important;
        }
        
        .stats-section {
            background: rgba(0,0,0,0.3);
            padding: 20px;
            border-radius: 10px;
            margin-top: 20px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
            margin-top: 15px;
        }
        
        .stat-item {
            background: rgba(255,255,255,0.05);
            padding: 15px;
            border-radius: 10px;
            text-align: center;
        }
        
        .stat-value {
            font-size: 20px;
            font-weight: bold;
            color: var(--primary);
            margin-top: 8px;
        }
        
        .instructions {
            background: rgba(0,0,0,0.2);
            padding: 20px;
            border-radius: 10px;
            margin-top: 20px;
            font-size: 14px;
            line-height: 1.6;
            border: 1px solid rgba(255,255,255,0.1);
        }
        
        .instructions ul {
            padding-right: 20px;
            margin: 15px 0;
        }
        
        .instructions li {
            margin-bottom: 8px;
        }
        
        @keyframes shake {
            0%, 100% { transform: translateX(-50%); }
            25% { transform: translateX(-52%); }
            75% { transform: translateX(-48%); }
        }
        
        @keyframes crash {
            0% { transform: translateX(-50%) scale(1); }
            50% { transform: translateX(-50%) scale(1.5); }
            100% { transform: translateX(-50%) scale(0); opacity: 0; }
        }
        
        @media (max-width: 600px) {
            .container {
                padding: 15px;
                border-radius: 15px;
            }
            
            .game-area {
                height: 250px;
            }
            
            .timer {
                font-size: 32px;
            }
            
            .action-btn {
                padding: 18px;
                font-size: 16px;
            }
            
            .bet-btn {
                padding: 15px 10px;
                font-size: 16px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- الهيدر -->
        <div class="header">
            <div class="logo">
                <span>✈️</span>
                <div>
                    <div>Aviator Pro</div>
                    <div class="user-info">ID: <span id="user-id">0</span></div>
                </div>
            </div>
            <div class="balance-card" id="balance">
                0 <span>💰</span>
            </div>
        </div>
        
        <!-- معلومات الجولة -->
        <div class="round-info">
            <div class="round-id">الجولة: <span id="round-id">#0</span></div>
            <div class="timer" id="timer">00:00</div>
            <div class="round-status" id="round-status">⏳ جاري التحميل...</div>
            <div class="multiplier-info">
                <div>المضاعف الحالي:</div>
                <div id="current-multiplier">1.00x</div>
            </div>
        </div>
        
        <!-- منطقة اللعبة -->
        <div class="game-area">
            <div class="sky"></div>
            <div class="flight-path"></div>
            <div class="runway">
                <div class="runway-lines"></div>
            </div>
            <div id="plane">✈️</div>
            <div class="multiplier-display" id="multiplier-display">1.00x</div>
            <div class="crash-point" id="crash-point" style="display: none;">
                💥 التحطم عند: <span id="crash-value">0.00x</span>
            </div>
        </div>
        
        <!-- الرسائل -->
        <div class="message" id="message">
            🚀 اختر مبلغ الرهان خلال 30 ثانية!
        </div>
        
        <!-- قسم الرهان -->
        <div class="bet-section">
            <div class="section-title">
                <span>💰</span> اختيار مبلغ الرهان
            </div>
            <div class="bet-amounts" id="bet-amounts">
                <!-- سيتم ملؤها بواسطة JavaScript -->
            </div>
        </div>
        
        <!-- أزرار التحكم -->
        <div class="controls">
            <button class="action-btn bet-action" onclick="placeBet()" id="btn-bet">
                <span>🎯</span> وضع الرهان
            </button>
            <button class="action-btn cashout-action" onclick="cashOut()" id="btn-cashout" disabled>
                <span>💰</span> صرف الآن
            </button>
        </div>
        
        <!-- الإحصائيات -->
        <div class="stats-section">
            <div class="section-title">
                <span>📊</span> إحصائيات الجولة
            </div>
            <div class="stats-grid">
                <div class="stat-item">
                    <div>حالة الجولة</div>
                    <div class="stat-value" id="game-status">انتظار</div>
                </div>
                <div class="stat-item">
                    <div>اللاعبين النشطين</div>
                    <div class="stat-value" id="active-players">0</div>
                </div>
                <div class="stat-item">
                    <div>وقت الطيران</div>
                    <div class="stat-value" id="flight-time">0s</div>
                </div>
                <div class="stat-item">
                    <div>نقطة التحطم</div>
                    <div class="stat-value" id="crash-display">???.??x</div>
                </div>
            </div>
        </div>
        
        <!-- التعليمات -->
        <div class="instructions">
            <div class="section-title">
                <span>📖</span> كيف تلعب
            </div>
            <ul>
                <li>اختر مبلغ الرهان خلال <strong>30 ثانية</strong></li>
                <li>بعد 30 ثانية تبدأ الطائرة في الصعود</li>
                <li>المضاعف يزداد كلما ارتفعت الطائرة</li>
                <li>اضغط "صرف الآن" للحصول على المضاعف الحالي</li>
                <li>الطائرة تتحطم عند نقطة عشوائية</li>
                <li>إذا صرفت قبل التحطم تربح، وإلا تخسر</li>
            </ul>
            <div style="text-align: center; margin-top: 15px; font-size: 12px; opacity: 0.7;">
                ⚠️ الرهان مسؤوليتك. العب بمسؤولية.
            </div>
        </div>
    </div>

    <script>
        // ==================== الإعدادات الأساسية ====================
        const USER_ID = new URLSearchParams(window.location.search).get('user_id') || '0';
        const BASE_URL = window.location.origin;
        const BETTING_TIME = 30;
        
        // ==================== المتغيرات العامة ====================
        let selectedAmount = 0;
        let currentBet = null;
        let currentMultiplier = 1.0;
        let gameStatus = "waiting";
        let timeRemaining = 0;
        let flightTime = 0;
        let crashPoint = 0;
        let isPlaying = false;
        let updateInterval = null;
        let flightInterval = null;
        
        // ==================== تهيئة الصفحة ====================
        function initPage() {
            document.getElementById('user-id').textContent = USER_ID;
            createBetButtons();
            refreshAllData();
            startAutoUpdate();
        }
        
        // ==================== إنشاء أزرار الرهان ====================
        function createBetButtons() {
            const container = document.getElementById('bet-amounts');
            container.innerHTML = '';
            
            const betOptions = [10, 50, 100, 500, 1000, 5000];
            
            betOptions.forEach(amount => {
                const button = document.createElement('button');
                button.className = 'bet-btn';
                button.innerHTML = `
                    <div class="bet-amount">${amount}</div>
                    <div class="bet-label">نقطة</div>
                `;
                button.onclick = () => selectAmount(amount);
                container.appendChild(button);
            });
            
            if (betOptions.length > 0) {
                selectAmount(betOptions[0]);
            }
        }
        
        // ==================== اختيار مبلغ الرهان ====================
        function selectAmount(amount) {
            selectedAmount = amount;
            
            document.querySelectorAll('.bet-btn').forEach(btn => {
                const btnAmount = parseInt(btn.querySelector('.bet-amount').textContent);
                btn.classList.remove('selected');
                if (btnAmount === amount) {
                    btn.classList.add('selected');
                }
            });
            
            updateBetButton();
        }
        
        // ==================== تحديث البيانات ====================
        async function refreshAllData() {
            await Promise.all([
                refreshBalance(),
                refreshGameState()
            ]);
        }
        
        // ==================== جلب الرصيد ====================
        async function refreshBalance() {
            try {
                const response = await fetch(`${BASE_URL}/api/balance/${USER_ID}`);
                const data = await response.json();
                
                if (data.balance !== undefined) {
                    const balanceText = data.is_admin ? '∞ (غير محدود)' : data.balance.toLocaleString();
                    document.getElementById('balance').innerHTML = `${balanceText} <span>💰</span>`;
                }
            } catch (error) {
                console.error('خطأ في جلب الرصيد:', error);
            }
        }
        
        // ==================== جلب حالة اللعبة ====================
        async function refreshGameState() {
            try {
                const response = await fetch(`${BASE_URL}/api/game-state`);
                const data = await response.json();
                
                if (!data) return;
                
                // تحديث المعلومات العامة
                document.getElementById('round-id').textContent = `#${data.round_id || '0'}`;
                document.getElementById('game-status').textContent = 
                    data.status === 'betting' ? 'مراهنة' :
                    data.status === 'flying' ? 'طيران' :
                    data.status === 'crashed' ? 'تحطمت' : 'انتظار';
                
                document.getElementById('active-players').textContent = data.active_players || 0;
                
                // تحديث المضاعف
                currentMultiplier = data.current_multiplier || 1.0;
                document.getElementById('current-multiplier').textContent = currentMultiplier.toFixed(2) + 'x';
                document.getElementById('multiplier-display').textContent = currentMultiplier.toFixed(2) + 'x';
                
                // تحديث نقطة التحطم
                crashPoint = data.crash_point || 0;
                if (crashPoint > 0) {
                    document.getElementById('crash-point').style.display = 'block';
                    document.getElementById('crash-value').textContent = crashPoint.toFixed(2);
                    document.getElementById('crash-display').textContent = crashPoint.toFixed(2) + 'x';
                }
                
                // تحديث المؤقت
                gameStatus = data.status;
                
                if (data.status === 'betting') {
                    timeRemaining = data.time_remaining || 0;
                    document.getElementById('timer').textContent = 
                        timeRemaining.toString().padStart(2, '0') + 's';
                    document.getElementById('round-status').textContent = '⏳ وقت الرهان';
                    
                    // تحديث لون المؤقت
                    const timer = document.getElementById('timer');
                    if (timeRemaining <= 10) {
                        timer.style.color = '#ff416c';
                        timer.style.textShadow = '0 0 15px #ff416c';
                    } else {
                        timer.style.color = '#00ff88';
                        timer.style.textShadow = '0 0 10px #00ff88';
                    }
                    
                } else if (data.status === 'flying') {
                    flightTime = data.flight_time || 0;
                    document.getElementById('timer').textContent = '✈️';
                    document.getElementById('round-status').textContent = '✈️ الطائرة تصعد';
                    document.getElementById('flight-time').textContent = flightTime + 's';
                    
                    // تحديث موقع الطائرة
                    updatePlanePosition();
                    
                } else if (data.status === 'crashed') {
                    document.getElementById('timer').textContent = '💥';
                    document.getElementById('round-status').textContent = '💥 تحطمت الطائرة';
                    document.getElementById('flight-time').textContent = '0s';
                    
                    // تأثير التحطم
                    crashAnimation();
                }
                
                // تحديث أزرار التحكم
                updateBetButton();
                updateCashoutButton();
                
                // تحديث الرسالة
                updateMessage(data.status);
                
            } catch (error) {
                console.error('خطأ في جلب حالة اللعبة:', error);
            }
        }
        
        // ==================== تحديث موقع الطائرة ====================
        function updatePlanePosition() {
            const plane = document.getElementById('plane');
            const gameArea = document.querySelector('.game-area');
            const maxHeight = gameArea.clientHeight - 100;
            
            // حساب الارتفاع بناءً على المضاعف
            const heightPercentage = Math.min(1, (currentMultiplier - 1) / 9);
            const planeHeight = 60 + (heightPercentage * (maxHeight - 60));
            
            plane.style.bottom = `${planeHeight}px`;
            
            // تأثيرات خاصة للمضاعفات العالية
            if (currentMultiplier >= crashPoint * 0.9) {
                // قريب من نقطة التحطم
                plane.style.animation = 'shake 0.3s ease-in-out infinite';
                plane.style.color = '#ff416c';
            } else if (currentMultiplier >= 5) {
                plane.style.filter = 'drop-shadow(0 0 15px #00ff88)';
                plane.style.color = '#00ff88';
                plane.style.animation = 'none';
            } else if (currentMultiplier >= 3) {
                plane.style.filter = 'drop-shadow(0 0 10px #ffd700)';
                plane.style.color = '#ffd700';
                plane.style.animation = 'none';
            } else if (currentMultiplier >= 2) {
                plane.style.filter = 'drop-shadow(0 0 8px #00b4d8)';
                plane.style.color = '#00b4d8';
                plane.style.animation = 'none';
            } else {
                plane.style.filter = 'drop-shadow(0 0 5px #ffffff)';
                plane.style.color = '#ffffff';
                plane.style.animation = 'none';
            }
        }
        
        // ==================== تأثير التحطم ====================
        function crashAnimation() {
            const plane = document.getElementById('plane');
            const multiplierDisplay = document.getElementById('multiplier-display');
            
            // إضافة تأثير التحطم
            plane.style.animation = 'crash 1s forwards';
            multiplierDisplay.style.animation = 'crash 1s forwards';
            multiplierDisplay.style.color = '#ff416c';
            multiplierDisplay.style.borderColor = '#ff416c';
            
            // إرجاع بعد 2 ثانية
            setTimeout(() => {
                plane.style.animation = '';
                multiplierDisplay.style.animation = '';
            }, 2000);
        }
        
        // ==================== تحديث أزرار التحكم ====================
        function updateBetButton() {
            const canBet = gameStatus === 'betting' && selectedAmount > 0 && !isPlaying;
            const btnBet = document.getElementById('btn-bet');
            btnBet.disabled = !canBet;
            
            if (canBet) {
                btnBet.innerHTML = `<span>🎯</span> وضع رهان (${selectedAmount})`;
            } else {
                btnBet.innerHTML = `<span>🎯</span> وضع الرهان`;
            }
        }
        
        function updateCashoutButton() {
            const canCashout = isPlaying && gameStatus === 'flying' && currentMultiplier >= 1.1;
            const btnCashout = document.getElementById('btn-cashout');
            btnCashout.disabled = !canCashout;
            
            if (canCashout && currentBet) {
                const potentialWin = Math.floor(currentBet * currentMultiplier);
                btnCashout.innerHTML = `<span>💰</span> صرف (${potentialWin})`;
            } else {
                btnCashout.innerHTML = `<span>💰</span> صرف الآن`;
            }
        }
        
        // ==================== تحديث الرسالة ====================
        function updateMessage(status) {
            const messageElement = document.getElementById('message');
            
            switch(status) {
                case 'betting':
                    if (timeRemaining <= 10) {
                        messageElement.textContent = `⏰ أسرع! ${timeRemaining} ثانية متبقية للرهان!`;
                        messageElement.className = 'message warning';
                    } else {
                        messageElement.textContent = `🚀 اختر مبلغ الرهان خلال ${timeRemaining} ثانية!`;
                        messageElement.className = 'message info';
                    }
                    break;
                    
                
                    
                case 'crashed':
                    messageElement.textContent = `💥 تحطمت الطائرة عند ${crashPoint.toFixed(2)}x`;
                    messageElement.className = 'message error';
                    break;
                    
                default:
                    messageElement.textContent = '🚀 جاري تحميل اللعبة...';
                    messageElement.className = 'message info';
            }
        }
        
        // ==================== وضع الرهان ====================
        async function placeBet() {
            if (selectedAmount <= 0) {
                showMessage('❌ الرجاء اختيار مبلغ الرهان', 'error');
                return;
            }
            
            if (isPlaying) {
                showMessage('❌ لديك رهان نشط بالفعل', 'error');
                return;
            }
            
            if (gameStatus !== 'betting') {
                showMessage('❌ ليس وقت الرهان الآن', 'error');
                return;
            }
            
            try {
                const response = await fetch(`${BASE_URL}/api/bet`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        user_id: parseInt(USER_ID),
                        amount: selectedAmount
                    })
                });
                
                const data = await response.json();
                
                if (data.error) {
                    showMessage('❌ ' + data.error, 'error');
                    return;
                }
                
                showMessage(`✅ تم وضع رهان ${selectedAmount} نقطة بنجاح!`, 'success');
                isPlaying = true;
                currentBet = selectedAmount;
                
                // تعطيل أزرار الرهان
                document.querySelectorAll('.bet-btn').forEach(btn => {
                    btn.disabled = true;
                });
                
                // تحديث الرصيد
                await refreshBalance();
                updateCashoutButton();
                
            } catch (error) {
                console.error('خطأ في وضع الرهان:', error);
                showMessage('❌ خطأ في الاتصال بالخادم', 'error');
            }
        }
        
        // ==================== صرف الرهان ====================
        async function cashOut() {
            if (!isPlaying) {
                showMessage('❌ ليس لديك رهان نشط', 'error');
                return;
            }
            
            if (currentMultiplier < 1.1) {
                showMessage('❌ انتظر حتى يرتفع المضاعف أكثر', 'warning');
                return;
            }
            
            try {
                const response = await fetch(`${BASE_URL}/api/cashout`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        user_id: parseInt(USER_ID)
                    })
                });
                
                const data = await response.json();
                
                if (data.error) {
                    showMessage('❌ ' + data.error, 'error');
                    return;
                }
                
                showMessage(`🎉 تم الصرف! ربحت ${data.win_amount} نقطة (${currentMultiplier.toFixed(2)}x)`, 'success');
                
                isPlaying = false;
                currentBet = null;
                
                // تفعيل أزرار الرهان
                document.querySelectorAll('.bet-btn').forEach(btn => {
                    btn.disabled = false;
                });
                
                // تحديث الرصيد
                await refreshBalance();
                updateCashoutButton();
                
            } catch (error) {
                console.error('خطأ في الصرف:', error);
                showMessage('❌ خطأ في الاتصال بالخادم', 'error');
            }
        }
        
        // ==================== عرض رسالة ====================
        function showMessage(text, type = 'info') {
            const messageElement = document.getElementById('message');
            messageElement.textContent = text;
            messageElement.className = 'message ' + type;
            
            // إخفاء الرسالة بعد 5 ثواني
            setTimeout(() => {
                if (messageElement.textContent === text) {
                    messageElement.textContent = '';
                    messageElement.className = 'message';
                }
            }, 5000);
        }
        
        // ==================== التحديث التلقائي ====================
        function startAutoUpdate() {
            // تحديث كل ثانية
            if (updateInterval) clearInterval(updateInterval);
            updateInterval = setInterval(() => {
                refreshGameState();
            }, 1000);
            
            // تحديث الرصيد كل 5 ثواني
            setInterval(() => {
                refreshBalance();
            }, 5000);
        }
        
        // ==================== بدء التشغيل ====================
        window.onload = function() {
            initPage();
        };
    </script>
</body>
</html>
'''

# ==================== Webhook للبوت ====================
@app.post("/webhook")
async def telegram_webhook(request: Request):
    """استقبال تحديثات Telegram"""
    try:
        Bot.set_current(bot)
        update_data = await request.json()
        await dp.process_update(types.Update(**update_data))
        return {"ok": True}
    except Exception as e:
        logger.error(f"❌ خطأ في Webhook: {e}")
        return {"ok": False, "error": str(e)}, 500

# ==================== API Endpoints ====================
@app.get("/")
async def home():
    """الصفحة الرئيسية"""
    return {
        "app": "Aviator Pro v1.0",
        "status": "running",
        "round_id": game_round.round_id,
        "game_status": game_round.status,
        "crash_point": game_round.crash_point,
        "base_url": BASE_URL,
        "admin_id": ADMIN_ID
    }

@app.get("/game")
async def game_page(request: Request):
    """صفحة اللعبة"""
    user_id = request.query_params.get("user_id", "0")
    
    # استبدال المتغيرات في HTML
    html_content = HTML_TEMPLATE.replace(
        "const USER_ID = new URLSearchParams(window.location.search).get('user_id') || '0';",
        f"const USER_ID = '{user_id}';"
    )
    
    html_content = html_content.replace("const BASE_URL = window.location.origin;", 
                                       f"const BASE_URL = '{BASE_URL}';")
    
    return HTMLResponse(content=html_content)

@app.get("/api/game-state")
async def api_game_state():
    """حالة اللعبة الحالية"""
    game_round.update()
    
    return {
        "round_id": game_round.round_id,
        "status": game_round.status,
        "crash_point": game_round.crash_point,
        "current_multiplier": game_round.current_multiplier,
        "time_remaining": game_round.get_time_remaining(),
        "flight_time": game_round.get_flight_time(),
        "active_players": len(game_round.active_bets)
    }

@app.get("/api/balance/{user_id}")
async def api_balance(user_id: int):
    """جلب الرصيد"""
    try:
        balance = db.get_balance(user_id)
        return {"balance": balance, "is_admin": user_id == ADMIN_ID}
    except Exception as e:
        logger.error(f"❌ خطأ في جلب الرصيد: {e}")
        return {"balance": 0, "error": str(e)}

@app.post("/api/bet")
async def api_bet(request: Request):
    """وضع رهان"""
    try:
        data = await request.json()
        user_id = int(data.get("user_id", 0))
        amount = int(data.get("amount", 0))
        
        if not user_id or not amount:
            return JSONResponse({"error": "بيانات ناقصة"}, status_code=400)
        
        if amount not in BET_OPTIONS:
            return JSONResponse({"error": "مبلغ رهان غير صالح"}, status_code=400)
        
        if game_round.status != "betting":
            return JSONResponse({"error": "ليس وقت الرهان الآن"}, status_code=400)
        
        # الأدمن لا يمكنه الرهان
        if user_id == ADMIN_ID:
            return JSONResponse({"error": "الأدمن لا يمكنه الرهان"}, status_code=400)
        
        # التحقق من الرصيد
        balance = db.get_balance(user_id)
        if balance < amount:
            return JSONResponse(
                {"error": "رصيد غير كافي", "balance": balance}, 
                status_code=400
            )
        
        # وضع الرهان
        game_round.active_bets[user_id] = amount
        
        # إضافة الرهان إلى قاعدة البيانات
        db.add_bet(user_id, game_round.round_id, amount)
        
        # خصم المبلغ
        db.update_balance(user_id, -amount)
        
        # إضافة معاملة
        db.add_transaction(
            user_id, 
            -amount, 
            "bet", 
            f"رهان على الجولة #{game_round.round_id}"
        )
        
        return {
            "success": True,
            "message": f"تم وضع رهان {amount}",
            "round_id": game_round.round_id,
            "new_balance": balance - amount
        }
        
    except Exception as e:
        logger.error(f"❌ خطأ في وضع الرهان: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/cashout")
async def api_cashout(request: Request):
    """صرف الرهان"""
    try:
        data = await request.json()
        user_id = int(data.get("user_id", 0))
        
        if not user_id:
            return JSONResponse({"error": "بيانات ناقصة"}, status_code=400)
        
        if user_id not in game_round.active_bets:
            return JSONResponse({"error": "ليس لديك رهان نشط"}, status_code=400)
        
        if game_round.status != "flying":
            return JSONResponse({"error": "الطائرة لا تطير الآن"}, status_code=400)
        
        # صرف الرهان
        win_amount = db.cashout_bet(user_id, game_round.round_id, game_round.current_multiplier)
        
        if not win_amount:
            return JSONResponse({"error": "خطأ في الصرف"}, status_code=400)
        
        # تحديث الرصيد
        db.update_balance(user_id, win_amount)
        
        # إضافة معاملة
        db.add_transaction(
            user_id,
            win_amount,
            "win",
            f"صرف بمضاعف {game_round.current_multiplier}x في الجولة #{game_round.round_id}"
        )
        
        # إضافة للجولة
        game_round.cashed_out[user_id] = {
            "multiplier": game_round.current_multiplier,
            "amount": win_amount
        }
        
        return {
            "success": True,
            "win_amount": win_amount,
            "multiplier": game_round.current_multiplier,
            "message": f"تم الصرف بمضاعف {game_round.current_multiplier}x"
        }
        
    except Exception as e:
        logger.error(f"❌ خطأ في الصرف: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/stats/{user_id}")
async def api_stats(user_id: int):
    """إحصائيات المستخدم"""
    try:
        stats = db.get_user_stats(user_id)
        balance = db.get_balance(user_id)
        
        return {
            "balance": balance,
            "is_admin": user_id == ADMIN_ID,
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"❌ خطأ في جلب الإحصائيات: {e}")
        return {"error": str(e)}, 500

@app.get("/api/leaderboard")
async def api_leaderboard():
    """قائمة المتصدرين"""
    try:
        leaders = db.get_leaderboard()
        
        leaderboard = []
        for idx, (user_id, username, balance) in enumerate(leaders, 1):
            leaderboard.append({
                "rank": idx,
                "user_id": user_id,
                "username": username or f"المستخدم {user_id}",
                "balance": balance,
                "is_admin": user_id == ADMIN_ID
            })
        
        return {"leaderboard": leaderboard}
        
    except Exception as e:
        logger.error(f"❌ خطأ في جلب المتصدرين: {e}")
        return {"error": str(e)}, 500

# ==================== إدارة دورة الحياة ====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """إدارة دورة حياة التطبيق"""
    print("=" * 60)
    print("🚀 بدء تشغيل Aviator Pro...")
    print("=" * 60)
    
    try:
        # بدء الجولة الأولى
        game_round.start_new_round()
        
        # تعيين Webhook
        try:
            webhook_url = f"{BASE_URL}/webhook"
            await bot.delete_webhook()
            await bot.set_webhook(
                webhook_url,
                max_connections=100,
                allowed_updates=["message", "callback_query"]
            )
            logger.info(f"✅ تم تعيين Webhook على: {webhook_url}")
        except Exception as e:
            logger.error(f"⚠️ خطأ في تعيين Webhook: {e}")
        
        print(f"\n📊 معلومات التشغيل:")
        print(f"🔗 الرابط: {BASE_URL}")
        print(f"🤖 البوت: {BOT_TOKEN[:15]}...")
        print(f"👑 الأدمن: {ADMIN_ID} (رصيد غير محدود)")
        print(f"⏰ وقت الرهان: {BETTING_DURATION} ثانية")
        print(f"💰 خيارات الرهان: {BET_OPTIONS}")
        print(f"✈️ نقاط التحطم: 50 نقطة مختلفة")
        print("=" * 60)
        print("✅ التطبيق يعمل بنجاح وجاهز للاستخدام!")
        print("=" * 60)
        
        yield
        
    except Exception as e:
        logger.error(f"❌ خطأ فادح في التشغيل: {e}")
        raise
    
    finally:
        print("\n🛑 إيقاف التطبيق...")

# تعيين lifespan للتطبيق
app.router.lifespan_context = lifespan

# ==================== نقطة الدخول ====================
if __name__ == "__main__":
    # تشغيل التطبيق
    port = int(os.environ.get("PORT", 8000))
    
    # تحديث BASE_URL إذا كان على Railway
    if "railway.app" in os.environ.get("RAILWAY_PUBLIC_DOMAIN", ""):
        BASE_URL = f"https://{os.environ['RAILWAY_PUBLIC_DOMAIN']}"
        logger.info(f"🔗 تم تحديث BASE_URL إلى: {BASE_URL}")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        log_level="info"
    )