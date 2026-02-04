import os
import asyncio
import random
import aiohttp
import logging
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# ==================== استيراد الإعدادات والوحدات ====================
from config import (
    BOT_TOKEN, ADMIN_ID, BASE_URL, PORT, validate_config,
    ROUND_DURATION, BETTING_DURATION, BET_OPTIONS
)

from database import (
    init_db, get_balance, update_balance, create_user,
    add_transaction, get_user_transactions,
    create_round, add_bet, get_current_round,
    get_round_bets, finish_round, update_round_result,
    set_admin_unlimited_balance, update_bet_result,
    get_user_active_bet, get_all_users, get_user_stats,
    get_round_stats
)

from game_logic import game_manager

# ==================== إعداد التسجيل ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== التحقق من الإعدادات ====================
logger.info("🔧 جاري التحقق من الإعدادات...")
if not validate_config():
    logger.error("❌ تم إيقاف التشغيل بسبب أخطاء في الإعدادات")
    exit(1)

# ==================== إعداد البوت ====================
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
Bot.set_current(bot)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ==================== إعداد Webhook ====================
async def setup_webhook():
    """تعيين Webhook للبوت"""
    try:
        webhook_url = f"{BASE_URL}/webhook"
        logger.info(f"🔗 محاولة تعيين Webhook على: {webhook_url}")
        
        await bot.delete_webhook()
        await bot.set_webhook(
            webhook_url,
            max_connections=100,
            allowed_updates=["message", "callback_query"]
        )
        
        logger.info(f"✅ تم تعيين Webhook بنجاح!")
        
        # إرسال رسالة بدء التشغيل للأدمن
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🚀 <b>البوت يعمل بنجاح!</b>\n\n"
                f"🔗 الرابط: {BASE_URL}\n"
                f"🕐 الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"👑 أنت الأدمن - رصيدك غير محدود"
            )
        except Exception as e:
            logger.warning(f"⚠️  لم يتم إرسال رسالة للأدمن: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في تعيين Webhook: {str(e)}")
        return False

# ==================== أوامر البوت ====================
@dp.message_handler(commands=["start", "play", "ابدأ"])
async def cmd_start(message: types.Message):
    """بدء البوت"""
    try:
        user_id = message.from_user.id
        username = message.from_user.first_name or "اللاعب"
        
        await create_user(user_id, username)
        
        # إذا كان الأدمن، نعطيه رصيد غير محدود
        if user_id == ADMIN_ID:
            await set_admin_unlimited_balance(ADMIN_ID)
        
        balance = await get_balance(user_id)
        
        game_url = f"{BASE_URL}/game?user_id={user_id}"
        
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("🎮 ابدأ اللعب الآن", url=game_url),
            InlineKeyboardButton("📊 إحصائياتي", callback_data="stats")
        )
        
        keyboard.row(
            InlineKeyboardButton("💰 معرفة الرصيد", callback_data="check_balance"),
            InlineKeyboardButton("📤 إرسال رصيد", callback_data="send_balance_menu")
        )
        
        keyboard.row(
            InlineKeyboardButton("📈 ترتيب اللاعبين", callback_data="leaderboard"),
            InlineKeyboardButton("❓ المساعدة", callback_data="help")
        )
        
        welcome_text = f"""
🎉 <b>مرحباً {username}!</b> 

🎮 <b>لعبة Aviator - الرهان الحقيقي!</b>

💰 <b>رصيدك الحالي:</b> <code>{balance if user_id != ADMIN_ID else '∞ (غير محدود)'}</code> نقطة

📊 <b>معلومات النظام:</b>
• الجولة: {ROUND_DURATION} ثانية
• وقت الرهان: {BETTING_DURATION} ثانية
• خيارات الرهان: {', '.join(map(str, BET_OPTIONS))}

🎯 <b>كيف تلعب:</b>
1. اضغط على زر 'ابدأ اللعب'
2. اختر مبلغ الرهان
3. شاهد الطائرة تصعد
4. صرف في الوقت المناسب
5. اربح حسب المضاعف!

<a href="{game_url}">🔗 اضغط هنا للعب مباشرة</a>
        """
        
        await message.answer(welcome_text, reply_markup=keyboard)
        logger.info(f"📨 تم إرسال رسالة start للمستخدم {user_id}")
        
    except Exception as e:
        logger.error(f"❌ خطأ في أمر start: {e}")

@dp.message_handler(commands=["balance", "رصيدي", "رصيد"])
async def cmd_balance(message: types.Message):
    """عرض الرصيد"""
    try:
        user_id = message.from_user.id
        balance = await get_balance(user_id)
        
        balance_text = f"""
💰 <b>رصيدك الحالي:</b> <code>{balance if user_id != ADMIN_ID else '∞ (غير محدود)'}</code> نقطة
        """
        
        if user_id == ADMIN_ID:
            balance_text += "\n\n👑 <b>أنت الأدمن - رصيدك غير محدود</b>"
        
        await message.answer(balance_text)
        logger.info(f"💰 تم عرض الرصيد للمستخدم {user_id}")
        
    except Exception as e:
        logger.error(f"❌ خطأ في أمر balance: {e}")

@dp.message_handler(commands=["send", "ارسال", "تحويل"])
async def cmd_send(message: types.Message):
    """إرسال رصيد"""
    try:
        user_id = message.from_user.id
        parts = message.text.split()
        
        if len(parts) < 3:
            await message.answer(
                "📝 <b>طريقة الاستخدام:</b>\n"
                "<code>/send معرف_المستخدم المبلغ</code>\n\n"
                "📌 <b>مثال:</b>\n"
                "<code>/send 123456789 100</code>\n\n"
                "💡 <b>ملاحظة:</b>\n"
                "• أدخل المعرف أولاً\n"
                "• ثم أدخل المبلغ\n"
                "• المبلغ يجب أن يكون رقم"
            )
            return
        
        try:
            to_user_id = int(parts[1])
            amount = int(parts[2])
        except (ValueError, IndexError):
            await message.answer("❌ خطأ في البيانات. تأكد من إدخال المعرف أولاً ثم المبلغ")
            return
        
        if amount <= 0:
            await message.answer("❌ المبلغ يجب أن يكون أكبر من صفر")
            return
        
        if amount < 10:
            await message.answer("❌ الحد الأدنى للإرسال هو 10 نقطة")
            return
        
        # الأدمن يمكنه الإرسال دائماً
        if user_id != ADMIN_ID:
            sender_balance = await get_balance(user_id)
            if sender_balance < amount:
                await message.answer(f"❌ رصيدك غير كافي. رصيدك: {sender_balance}")
                return
        
        if user_id == to_user_id:
            await message.answer("❌ لا يمكنك إرسال الرصيد لنفسك")
            return
        
        # الأدمن لا يخصم منه
        if user_id != ADMIN_ID:
            await update_balance(user_id, -amount)
        
        await update_balance(to_user_id, amount)
        
        # إضافة معاملات
        await add_transaction(user_id, -amount, "send", f"إرسال إلى {to_user_id}")
        await add_transaction(to_user_id, amount, "receive", f"استلام من {user_id}")
        
        await message.answer(
            f"✅ <b>تم إرسال الرصيد بنجاح</b>\n\n"
            f"👤 <b>إلى:</b> <code>{to_user_id}</code>\n"
            f"💰 <b>المبلغ:</b> <code>{amount}</code> نقطة\n"
            f"💳 <b>حالة الرصيد:</b> تمت العملية"
        )
        
        logger.info(f"📤 المستخدم {user_id} أرسل {amount} إلى {to_user_id}")
        
    except Exception as e:
        logger.error(f"❌ خطأ في أمر send: {e}")
        await message.answer("❌ حدث خطأ في إرسال الرصيد")

@dp.message_handler(commands=["add", "اضافة", "اعطاء"])
async def cmd_add(message: types.Message):
    """إضافة رصيد (للأدمن فقط)"""
    try:
        if message.from_user.id != ADMIN_ID:
            await message.answer("⛔ غير مصرح لك بهذا الأمر")
            return
        
        parts = message.text.split()
        if len(parts) < 3:
            await message.answer(
                "📝 <b>طريقة الاستخدام:</b>\n"
                "<code>/add معرف_المستخدم المبلغ</code>"
            )
            return
        
        try:
            user_id = int(parts[1])
            amount = int(parts[2])
        except (ValueError, IndexError):
            await message.answer("❌ خطأ في البيانات. تأكد من إدخال المعرف أولاً ثم المبلغ")
            return
        
        if amount <= 0:
            await message.answer("❌ المبلغ يجب أن يكون أكبر من صفر")
            return
        
        old_balance = await get_balance(user_id)
        new_balance = await update_balance(user_id, amount)
        
        # إضافة معاملة
        await add_transaction(user_id, amount, "admin_add", f"إضافة من الأدمن")
        
        await message.answer(
            f"✅ <b>تم إضافة الرصيد</b>\n\n"
            f"👤 <b>المستخدم:</b> <code>{user_id}</code>\n"
            f"➕ <b>المضاف:</b> <code>{amount}</code> نقطة\n"
            f"📊 <b>السابق:</b> <code>{old_balance}</code> نقطة\n"
            f"💰 <b>الجديد:</b> <code>{new_balance}</code> نقطة"
        )
        
        logger.info(f"➕ الأدمن أضف {amount} للمستخدم {user_id}")
        
    except Exception as e:
        logger.error(f"❌ خطأ في أمر add: {e}")
        await message.answer("❌ حدث خطأ في إضافة الرصيد")

@dp.message_handler(commands=["stats", "احصائيات", "إحصائيات"])
async def cmd_stats(message: types.Message):
    """عرض إحصائيات المستخدم"""
    try:
        user_id = message.from_user.id
        stats = await get_user_stats(user_id)
        balance = await get_balance(user_id)
        
        stats_text = f"""
📊 <b>إحصائياتك</b>

💰 <b>الرصيد الحالي:</b> <code>{balance if user_id != ADMIN_ID else '∞ (غير محدود)'}</code>

🎯 <b>الأداء العام:</b>
• عدد الرهانات: <code>{stats['total_bets']}</code>
• إجمالي المراهن: <code>{stats['total_wagered']}</code>
• إجمالي الأرباح: <code>{stats['total_wins']}</code>
• أكبر فوز: <code>{stats['biggest_win']}</code>
• الربح/الخسارة: <code>{stats['profit']}</code>

📈 <b>تحليلات:</b>
"""
        
        if stats['total_bets'] > 0:
            win_rate = (stats['total_wins'] / stats['total_wagered'] * 100) if stats['total_wagered'] > 0 else 0
            avg_bet = stats['total_wagered'] / stats['total_bets'] if stats['total_bets'] > 0 else 0
            
            stats_text += f"""
• متوسط الرهان: <code>{avg_bet:.2f}</code>
• نسبة الفوز: <code>{win_rate:.2f}%</code>
"""
        
        if user_id == ADMIN_ID:
            stats_text += "\n👑 <b>أنت الأدمن - إحصائيات غير محدودة</b>"
        
        await message.answer(stats_text)
        
    except Exception as e:
        logger.error(f"❌ خطأ في أمر stats: {e}")
        await message.answer("❌ حدث خطأ في جلب الإحصائيات")

@dp.message_handler(commands=["leaderboard", "ترتيب", "متصدرين"])
async def cmd_leaderboard(message: types.Message):
    """عرض ترتيب اللاعبين"""
    try:
        users = await get_all_users(limit=10)
        
        leaderboard_text = "🏆 <b>أفضل 10 لاعبين</b>\n\n"
        
        for idx, user in enumerate(users, 1):
            user_id = user[0]
            username = user[1] or f"المستخدم {user_id}"
            balance = user[2]
            
            medal = ""
            if idx == 1: medal = "🥇"
            elif idx == 2: medal = "🥈"
            elif idx == 3: medal = "🥉"
            else: medal = f"{idx}."
            
            leaderboard_text += f"{medal} {username}: <code>{balance:,}</code> نقطة\n"
        
        await message.answer(leaderboard_text)
        
    except Exception as e:
        logger.error(f"❌ خطأ في أمر leaderboard: {e}")
        await message.answer("❌ حدث خطأ في جلب الترتيب")

@dp.message_handler(commands=["round", "جولة"])
async def cmd_round(message: types.Message):
    """معلومات الجولة الحالية"""
    try:
        game_state = game_manager.get_game_state()
        
        if not game_state["round_id"]:
            await message.answer("⏳ <b>جاري إعداد الجولة القادمة...</b>")
            return
        
        round_text = f"""
🔄 <b>الجولة #{game_state['round_id']}</b>

⏰ <b>الحالة:</b> {"🕒 وقت الرهان" if game_state['status'] == 'betting' else "✈️ الجولة جارية"}
⏳ <b>الوقت المتبقي:</b> {game_state['remaining_time']} ثانية
🎮 <b>اللاعبين النشطين:</b> {game_state['active_players']}
"""
        
        if game_state['status'] == 'counting':
            round_text += f"""
🎯 <b>المضاعف الحالي:</b> {game_state['current_multiplier']}x
🏆 <b>النتيجة النهائية:</b> {game_state['result'] if game_state['result'] else 'قيد التحديد'}x
"""
        
        await message.answer(round_text)
        
    except Exception as e:
        logger.error(f"❌ خطأ في أمر round: {e}")

@dp.message_handler(commands=["help", "مساعدة", "الاوامر"])
async def cmd_help(message: types.Message):
    """عرض المساعدة"""
    try:
        help_text = f"""
🎮 <b>أوامر لعبة Aviator</b>

📋 <b>الأوامر الأساسية:</b>
/start - بدء البوت وعرض رابط اللعبة
/balance - عرض رصيدك
/send معرف مبلغ - إرسال رصيد لمستخدم
/stats - عرض إحصائياتك
/round - حالة الجولة الحالية
/leaderboard - ترتيب أفضل اللاعبين
/help - عرض هذه القائمة

🎯 <b>لعبة الرهان:</b>
• اضغط /start للحصول على رابط اللعبة
• الجولة: {ROUND_DURATION} ثانية
• وقت الرهان: {BETTING_DURATION} ثانية
• خيارات الرهان: {', '.join(map(str, BET_OPTIONS))}

💰 <b>نظام الرصيد:</b>
• ابدأ برصيد 0
• إرسال واستقبال من الآخرين
• الأدمن رصيده غير محدود

⚙️ <b>أوامر الأدمن:</b>
/add معرف مبلغ - إضافة رصيد لمستخدم

📞 <b>الدعم:</b>
تواصل مع الأدمن للمساعدة
        """
        
        await message.answer(help_text)
        
    except Exception as e:
        logger.error(f"❌ خطأ في أمر help: {e}")

# ==================== معالجة Callback ====================
@dp.callback_query_handler(lambda c: c.data in [
    "check_balance", "send_balance_menu", "stats", "leaderboard", "help"
])
async def process_callback(callback_query: types.CallbackQuery):
    """معالجة Callback"""
    try:
        user_id = callback_query.from_user.id
        
        if callback_query.data == "check_balance":
            balance = await get_balance(user_id)
            await bot.answer_callback_query(
                callback_query.id,
                f"💰 رصيدك: {balance if user_id != ADMIN_ID else '∞ (غير محدود)'} نقطة",
                show_alert=True
            )
            
        elif callback_query.data == "send_balance_menu":
            await bot.send_message(
                user_id,
                "📤 <b>لإرسال رصيد:</b>\n\n"
                "استخدم الأمر:\n<code>/send معرف_المستخدم المبلغ</code>\n\n"
                "<b>مثال:</b>\n<code>/send 123456789 500</code>\n\n"
                "⚠️ <b>ملاحظات:</b>\n"
                "1. أدخل المعرف أولاً\n"
                "2. ثم أدخل المبلغ\n"
                "3. الحد الأدنى: 10 نقطة\n"
                "4. تأكد من أن لديك رصيد كافي"
            )
            await bot.answer_callback_query(callback_query.id)
            
        elif callback_query.data == "stats":
            stats = await get_user_stats(user_id)
            balance = await get_balance(user_id)
            
            stats_text = f"""
📊 <b>إحصائياتك:</b>

💰 الرصيد: {balance if user_id != ADMIN_ID else '∞'}
🎯 الرهانات: {stats['total_bets']}
📈 الربح/الخسارة: {stats['profit']}
            """
            
            await bot.answer_callback_query(callback_query.id, stats_text, show_alert=True)
            
        elif callback_query.data == "leaderboard":
            users = await get_all_users(limit=5)
            leaderboard_text = "🏆 أفضل 5 لاعبين:\n\n"
            
            for idx, user in enumerate(users[:5], 1):
                username = user[1] or f"المستخدم {user[0]}"
                balance = user[2]
                leaderboard_text += f"{idx}. {username}: {balance:,}\n"
            
            await bot.answer_callback_query(callback_query.id, leaderboard_text, show_alert=True)
            
        elif callback_query.data == "help":
            await bot.send_message(
                user_id,
                "❓ <b>المساعدة السريعة:</b>\n\n"
                "🎮 للعب: اضغط /start ثم 'ابدأ اللعب'\n"
                "💰 للرصيد: /balance\n"
                "📊 للإحصائيات: /stats\n"
                "🏆 للترتيب: /leaderboard\n"
                "📤 للإرسال: /send معرف مبلغ\n\n"
                "📞 للدعم: تواصل مع الأدمن"
            )
            await bot.answer_callback_query(callback_query.id)
            
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة callback: {e}")

# ==================== FastAPI Application ====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """إدارة دورة حياة التطبيق"""
    print("=" * 60)
    print("🚀 بدء تشغيل لعبة Aviator...")
    print("=" * 60)
    
    try:
        # تهيئة قاعدة البيانات
        await init_db()
        
        # تعيين رصيد غير محدود للأدمن
        await set_admin_unlimited_balance(ADMIN_ID)
        
        # تعيين Webhook
        await setup_webhook()
        
        # بدء نظام الجولات
        await game_manager.start_new_round()
        asyncio.create_task(game_manager.process_round())
        
        print(f"\n📊 معلومات التشغيل:")
        print(f"🔗 الرابط: {BASE_URL}")
        print(f"🤖 البوت: {BOT_TOKEN[:15]}...")
        print(f"👑 الأدمن: {ADMIN_ID} (رصيد غير محدود)")
        print(f"⏳ مدة الجولة: {ROUND_DURATION} ثانية")
        print(f"⏰ وقت الرهان: {BETTING_DURATION} ثانية")
        print(f"💰 خيارات الرهان: {BET_OPTIONS}")
        print("=" * 60)
        print("✅ التطبيق يعمل بنجاح وجاهز للاستخدام!")
        print("=" * 60)
        
        yield
        
    except Exception as e:
        logger.error(f"❌ خطأ فادح في التشغيل: {e}")
        raise
    
    finally:
        print("\n🛑 إيقاف التطبيق...")
        game_manager.is_running = False

app = FastAPI(
    title="Aviator Game Pro",
    description="لعبة رهان Aviator الاحترافية مع نظام جولات متكامل",
    version="4.0.0",
    lifespan=lifespan
)

# إضافة CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== Webhook Endpoint ====================
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
    game_state = game_manager.get_game_state()
    
    return {
        "app": "Aviator Game Pro v4.0",
        "status": "running",
        "game_state": game_state,
        "admin_id": ADMIN_ID,
        "base_url": BASE_URL
    }

@app.get("/game")
async def game_page(request: Request):
    """صفحة اللعبة"""
    user_id = request.query_params.get("user_id", "0")
    
    try:
        # قراءة ملف HTML
        with open("static/index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
    except FileNotFoundError:
        return HTMLResponse("<h1>🎮 Aviator Game</h1><p>ملف اللعبة غير موجود</p>")
    
    # استبدال المتغيرات
    replacements = {
        "{BASE_URL}": BASE_URL,
        "{USER_ID}": str(user_id),
        "{BET_OPTIONS}": str(BET_OPTIONS),
        "{ROUND_DURATION}": str(ROUND_DURATION),
        "{BETTING_DURATION}": str(BETTING_DURATION)
    }
    
    for key, value in replacements.items():
        html_content = html_content.replace(key, value)
    
    return HTMLResponse(content=html_content)

@app.get("/api/round")
async def api_round():
    """معلومات الجولة الحالية"""
    game_state = game_manager.get_game_state()
    
    now = datetime.now()
    betting_time_left = 0
    
    if game_state["status"] == "betting":
        betting_time_left = game_state["remaining_time"]
    
    response = {
        "round_id": game_state["round_id"],
        "status": game_state["status"],
        "result": game_state["result"],
        "current_multiplier": game_state["current_multiplier"],
        "remaining_time": game_state["remaining_time"],
        "betting_time_left": betting_time_left,
        "can_bet": game_state["status"] == "betting",
        "active_players": game_state["active_players"]
    }
    
    return response

@app.get("/api/balance/{user_id}")
async def api_balance(user_id: int):
    """جلب الرصيد"""
    try:
        balance = await get_balance(user_id)
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
        
        # الأدمن يمكنه الرهان دائماً
        if user_id != ADMIN_ID:
            balance = await get_balance(user_id)
            if balance < amount:
                return JSONResponse(
                    {"error": "رصيد غير كافي", "balance": balance}, 
                    status_code=400
                )
        
        # وضع الرهان
        bet_placed = await game_manager.place_bet(user_id, amount)
        
        if not bet_placed:
            return JSONResponse({"error": "فشل في وضع الرهان"}, status_code=400)
        
        # خصم المبلغ (الأدمن لا يخصم منه)
        if user_id != ADMIN_ID:
            await update_balance(user_id, -amount)
        
        # إضافة معاملة
        await add_transaction(
            user_id, 
            -amount, 
            "bet", 
            f"رهان على الجولة #{game_manager.current_round.round_id}"
        )
        
        return {
            "success": True,
            "message": f"تم وضع رهان {amount}",
            "round_id": game_manager.current_round.round_id,
            "remaining_time": game_manager.current_round.remaining_time
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
        
        # صرف الرهان
        win_amount = await game_manager.cashout_bet(user_id)
        
        if win_amount is None:
            return JSONResponse({"error": "ليس لديك رهان نشط"}, status_code=400)
        
        # تحديث الرصيد (الأدمن لا يتغير رصيده)
        if user_id != ADMIN_ID:
            await update_balance(user_id, win_amount)
        
        # إضافة معاملة
        await add_transaction(
            user_id,
            win_amount,
            "win",
            f"فوز بمضاعف {game_manager.current_round.current_multiplier}x"
        )
        
        return {
            "success": True,
            "win_amount": win_amount,
            "multiplier": game_manager.current_round.current_multiplier,
            "message": f"تم الصرف بمضاعف {game_manager.current_round.current_multiplier}x"
        }
        
    except Exception as e:
        logger.error(f"❌ خطأ في الصرف: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/multiplier")
async def api_multiplier():
    """جلب المضاعف الحالي للجولة"""
    try:
        game_state = game_manager.get_game_state()
        
        return {
            "multiplier": game_state["current_multiplier"],
            "status": game_state["status"],
            "result": game_state["result"],
            "round_id": game_state["round_id"]
        }
        
    except Exception as e:
        logger.error(f"❌ خطأ في جلب المضاعف: {e}")
        return {"multiplier": 1.0, "error": str(e)}

@app.get("/api/user/{user_id}/stats")
async def api_user_stats(user_id: int):
    """جلب إحصائيات المستخدم"""
    try:
        stats = await get_user_stats(user_id)
        balance = await get_balance(user_id)
        
        return {
            "balance": balance,
            "is_admin": user_id == ADMIN_ID,
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"❌ خطأ في جلب إحصائيات المستخدم: {e}")
        return {"error": str(e)}, 500

@app.get("/api/leaderboard")
async def api_leaderboard(limit: int = 10):
    """جلب ترتيب اللاعبين"""
    try:
        users = await get_all_users(limit)
        
        leaderboard = []
        for idx, user in enumerate(users, 1):
            leaderboard.append({
                "rank": idx,
                "user_id": user[0],
                "username": user[1] or f"المستخدم {user[0]}",
                "balance": user[2],
                "is_admin": user[3]
            })
        
        return {"leaderboard": leaderboard}
        
    except Exception as e:
        logger.error(f"❌ خطأ في جلب الترتيب: {e}")
        return {"error": str(e)}, 500

# ==================== Admin APIs ====================
@app.get("/admin/stats")
async def admin_stats(api_key: str = ""):
    """إحصائيات الأدمن"""
    try:
        # التحقق من المفتاح (استخدم ADMIN_ID كمفتاح بسيط)
        if api_key != str(ADMIN_ID):
            return JSONResponse({"error": "غير مصرح"}, status_code=403)
        
        # جلب إحصائيات النظام
        users = await get_all_users()
        total_users = len(users)
        total_balance = sum(user[2] for user in users if user[0] != ADMIN_ID)
        
        game_state = game_manager.get_game_state()
        
        return {
            "system_stats": {
                "total_users": total_users,
                "total_balance": total_balance,
                "current_round": game_state["round_id"],
                "game_status": game_state["status"],
                "active_players": game_state["active_players"]
            },
            "top_users": [
                {
                    "user_id": user[0],
                    "username": user[1] or f"المستخدم {user[0]}",
                    "balance": user[2],
                    "is_admin": user[3]
                }
                for user in users[:5]
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ خطأ في جلب إحصائيات الأدمن: {e}")
        return {"error": str(e)}, 500

# ==================== نقطة الدخول ====================
if __name__ == "__main__":
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=PORT,
        log_level="info"
    )