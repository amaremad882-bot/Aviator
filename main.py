import os
import asyncio
import random
import logging
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# ==================== استيراد الإعدادات والوحدات ====================
from config import (
    BOT_TOKEN, ADMIN_ID, BASE_URL, PORT, validate_config,
    ROUND_DURATION, BETTING_DURATION, BET_OPTIONS,
    HTML_TEMPLATE
)

from database import (
    init_db, get_balance, update_balance, create_user,
    add_transaction, get_user_transactions,
    create_round, add_bet, get_current_round,
    get_round_bets, finish_round, update_round_result,
    set_admin_unlimited_balance, update_bet_result,
    get_user_active_bet, get_all_users, get_user_stats
)

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

# ==================== حالة الجولة ====================
class GameRound:
    def __init__(self):
        self.round_id = None
        self.start_time = None
        self.betting_end = None
        self.round_end = None
        self.result = None
        self.status = "waiting"
        self.current_multiplier = 1.0
        self.remaining_time = 0
        self.active_bets = {}

    def update_timer(self):
        """تحديث المؤقت"""
        if not self.start_time:
            return
        
        now = datetime.now()
        
        if self.status == "betting" and self.betting_end:
            self.remaining_time = max(0, int((self.betting_end - now).total_seconds()))
        elif self.status == "counting" and self.round_end:
            self.remaining_time = max(0, int((self.round_end - now).total_seconds()))
            
            # حساب المضاعف الحالي أثناء مرحلة العد
            if self.result and self.betting_end:
                elapsed = (now - self.betting_end).total_seconds()
                total_counting = ROUND_DURATION - BETTING_DURATION
                
                if elapsed <= total_counting:
                    progress = min(1.0, elapsed / total_counting)
                    self.current_multiplier = self.calculate_multiplier(progress)
    
    def calculate_multiplier(self, progress: float) -> float:
        """حساب المضاعف بناءً على التقدم"""
        if not self.result:
            return 1.0
        
        # منحنى مضاعف واقعي
        if progress < 0.3:
            multiplier = 1.0 + (self.result - 1.0) * (progress / 0.3) * 0.5
        elif progress < 0.7:
            multiplier = 1.0 + (self.result - 1.0) * (0.5 + (progress - 0.3) / 0.4 * 0.4)
        else:
            multiplier = 1.0 + (self.result - 1.0) * (0.9 + (progress - 0.7) / 0.3 * 0.1)
        
        return round(min(multiplier, self.result), 2)
    
    def generate_result(self) -> float:
        """توليد نتيجة عشوائية للجولة"""
        rand = random.random()
        
        if rand < 0.3:  # 30% مضاعف منخفض
            result = random.uniform(1.1, 2.0)
        elif rand < 0.6:  # 30% مضاعف متوسط
            result = random.uniform(2.0, 5.0)
        elif rand < 0.85:  # 25% مضاعف عالي
            result = random.uniform(5.0, 8.0)
        elif rand < 0.95:  # 10% مضاعف عالي جداً
            result = random.uniform(8.0, 15.0)
        else:  # 5% جاكبوت
            result = random.uniform(15.0, 50.0)
        
        return round(min(result, 10.0), 2)

game_round = GameRound()
active_bets = {}  # user_id: {"amount": int, "cashed_out": bool, "cashout_multiplier": float}

# ==================== إدارة الجولات ====================
async def start_new_round():
    """بدء جولة جديدة"""
    global game_round
    try:
        game_round.round_id = await create_round()
        game_round.start_time = datetime.now()
        game_round.betting_end = game_round.start_time + timedelta(seconds=BETTING_DURATION)
        game_round.round_end = game_round.start_time + timedelta(seconds=ROUND_DURATION)
        game_round.result = None
        game_round.status = "betting"
        game_round.current_multiplier = 1.0
        game_round.active_bets = {}
        
        logger.info(f"🔄 بدأت الجولة #{game_round.round_id}")
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في بدء الجولة: {e}")
        return False

async def process_round():
    """معالجة الجولة الحالية"""
    logger.info("🎮 بدء نظام الجولات...")
    
    # بدء الجولة الأولى
    await start_new_round()
    
    while True:
        try:
            now = datetime.now()
            game_round.update_timer()
            
            # التحقق من انتهاء وقت الرهان
            if game_round.status == "betting" and game_round.betting_end and now >= game_round.betting_end:
                game_round.status = "counting"
                game_round.result = game_round.generate_result()
                
                await update_round_result(game_round.round_id, game_round.result)
                logger.info(f"🎯 نتيجة الجولة #{game_round.round_id}: {game_round.result}x")
                
                # انتظار نهاية الجولة
                counting_duration = ROUND_DURATION - BETTING_DURATION
                await asyncio.sleep(counting_duration)
                
                # معالجة الرهانات المتبقية
                await process_remaining_bets()
                
                # إنهاء الجولة
                await finish_round(game_round.round_id)
                
                # انتظار قصير قبل الجولة التالية
                await asyncio.sleep(3)
                
                # بدء جولة جديدة
                await start_new_round()
            
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"❌ خطأ في معالجة الجولة: {e}")
            await asyncio.sleep(5)

async def process_remaining_bets():
    """معالجة الرهانات المتبقية"""
    try:
        for user_id, bet_info in list(active_bets.items()):
            if not bet_info["cashed_out"] and bet_info.get("round_id") == game_round.round_id:
                # معالجة الرهان النهائي
                win_amount = int(bet_info["amount"] * game_round.result)
                
                # تحديث رصيد المستخدم (الأدمن لا يتغير رصيده)
                if user_id != ADMIN_ID:
                    await update_balance(user_id, win_amount)
                
                # إضافة معاملة
                await add_transaction(
                    user_id,
                    win_amount,
                    "final_win",
                    f"فوز نهائي بمضاعف {game_round.result}x في الجولة #{game_round.round_id}"
                )
                
                # حذف الرهان النشط
                del active_bets[user_id]
                
                # محاولة إرسال رسالة للمستخدم
                try:
                    await bot.send_message(
                        user_id,
                        f"🎉 <b>انتهت الجولة #{game_round.round_id}</b>\n\n"
                        f"🎯 النتيجة النهائية: {game_round.result}x\n"
                        f"💰 رهانك: {bet_info['amount']}\n"
                        f"🏆 ربحك: {win_amount}"
                    )
                except:
                    pass
                    
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة الرهانات النهائية: {e}")

async def process_bet_cashout(user_id: int):
    """معالجة صرف الرهان"""
    if user_id not in active_bets:
        return None
    
    bet_info = active_bets[user_id]
    if bet_info["cashed_out"]:
        return None
    
    # حساب المبلغ الفائز
    win_amount = int(bet_info["amount"] * bet_info["cashout_multiplier"])
    
    # تحديث رصيد المستخدم (الأدمن لا يتغير رصيده)
    if user_id != ADMIN_ID:
        await update_balance(user_id, win_amount)
    
    # تحديث حالة الرهان
    bet_info["cashed_out"] = True
    
    # إضافة معاملة
    await add_transaction(user_id, win_amount, "win", f"فوز بمضاعف {bet_info['cashout_multiplier']}x")
    
    return win_amount

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
        """
        
        if user_id == ADMIN_ID:
            stats_text += "\n👑 <b>أنت الأدمن - إحصائيات غير محدودة</b>"
        
        await message.answer(stats_text)
        
    except Exception as e:
        logger.error(f"❌ خطأ في أمر stats: {e}")
        await message.answer("❌ حدث خطأ في جلب الإحصائيات")

@dp.message_handler(commands=["round", "جولة"])
async def cmd_round(message: types.Message):
    """معلومات الجولة الحالية"""
    try:
        round_text = f"""
🔄 <b>الجولة #{game_round.round_id if game_round.round_id else '0'}</b>

⏰ <b>الحالة:</b> {"🕒 وقت الرهان" if game_round.status == 'betting' else "✈️ الجولة جارية" if game_round.status == 'counting' else "⏳ انتظار"}
⏳ <b>الوقت المتبقي:</b> {game_round.remaining_time} ثانية
🎮 <b>اللاعبين النشطين:</b> {len(active_bets)}
        """
        
        if game_round.status == 'counting':
            round_text += f"""
🎯 <b>المضاعف الحالي:</b> {game_round.current_multiplier}x
🏆 <b>النتيجة النهائية:</b> {game_round.result if game_round.result else 'قيد التحديد'}x
"""
        
        await message.answer(round_text)
        
    except Exception as e:
        logger.error(f"❌ خطأ في أمر round: {e}")

# ==================== معالجة Callback ====================
@dp.callback_query_handler(lambda c: c.data in [
    "check_balance", "send_balance_menu", "stats"
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
        asyncio.create_task(process_round())
        
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

app = FastAPI(
    title="Aviator Game Pro",
    description="لعبة رهان Aviator الاحترافية مع نظام جولات متكامل",
    version="5.0.0",
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
    return {
        "app": "Aviator Game Pro v5.0",
        "status": "running",
        "round_id": game_round.round_id,
        "round_status": game_round.status,
        "result": game_round.result,
        "current_multiplier": game_round.current_multiplier,
        "active_players": len(active_bets),
        "admin_id": ADMIN_ID,
        "base_url": BASE_URL
    }

@app.get("/game")
async def game_page(request: Request):
    """صفحة اللعبة"""
    user_id = request.query_params.get("user_id", "0")
    
    # استبدال المتغيرات في HTML
    html_content = HTML_TEMPLATE
    replacements = {
        "BASE_URL_PLACEHOLDER": BASE_URL,
        "BET_OPTIONS_PLACEHOLDER": str(BET_OPTIONS),
        "ROUND_DURATION_PLACEHOLDER": str(ROUND_DURATION),
        "BETTING_DURATION_PLACEHOLDER": str(BETTING_DURATION)
    }
    
    for key, value in replacements.items():
        html_content = html_content.replace(key, value)
    
    # إضافة user_id إلى JavaScript
    html_content = html_content.replace("const USER_ID = new URLSearchParams(window.location.search).get('user_id') || '0';", 
                                       f"const USER_ID = '{user_id}';")
    
    return HTMLResponse(content=html_content)

@app.get("/api/round")
async def api_round():
    """معلومات الجولة الحالية"""
    game_round.update_timer()
    
    response = {
        "round_id": game_round.round_id,
        "status": game_round.status,
        "result": game_round.result,
        "current_multiplier": game_round.current_multiplier,
        "remaining_time": game_round.remaining_time,
        "can_bet": game_round.status == "betting",
        "active_players": len(active_bets)
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
        
        if game_round.status != "betting":
            return JSONResponse({"error": "ليس وقت الرهان الآن"}, status_code=400)
        
        # الأدمن يمكنه الرهان دائماً
        if user_id != ADMIN_ID:
            balance = await get_balance(user_id)
            if balance < amount:
                return JSONResponse(
                    {"error": "رصيد غير كافي", "balance": balance}, 
                    status_code=400
                )
        
        # وضع الرهان
        active_bets[user_id] = {
            "amount": amount,
            "round_id": game_round.round_id,
            "cashed_out": False,
            "cashout_multiplier": 1.0
        }
        
        game_round.active_bets[user_id] = amount
        
        # إضافة الرهان إلى قاعدة البيانات
        await add_bet(user_id, game_round.round_id, amount)
        
        # خصم المبلغ (الأدمن لا يخصم منه)
        if user_id != ADMIN_ID:
            await update_balance(user_id, -amount)
        
        # إضافة معاملة
        await add_transaction(
            user_id, 
            -amount, 
            "bet", 
            f"رهان على الجولة #{game_round.round_id}"
        )
        
        return {
            "success": True,
            "message": f"تم وضع رهان {amount}",
            "round_id": game_round.round_id,
            "remaining_time": game_round.remaining_time
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
        
        if user_id not in active_bets:
            return JSONResponse({"error": "ليس لديك رهان نشط"}, status_code=400)
        
        bet_info = active_bets[user_id]
        
        if bet_info["cashed_out"]:
            return JSONResponse({"error": "تم صرف هذا الرهان مسبقاً"}, status_code=400)
        
        if bet_info.get("round_id") != game_round.round_id:
            return JSONResponse({"error": "هذا الرهان ليس للجولة الحالية"}, status_code=400)
        
        # تحديث المضاعف الحالي
        bet_info["cashout_multiplier"] = game_round.current_multiplier
        
        # صرف الرهان
        win_amount = await process_bet_cashout(user_id)
        
        if win_amount:
            return {
                "success": True,
                "win_amount": win_amount,
                "multiplier": game_round.current_multiplier,
                "message": f"تم الصرف بمضاعف {game_round.current_multiplier}x"
            }
        else:
            return JSONResponse({"error": "خطأ في الصرف"}, status_code=500)
        
    except Exception as e:
        logger.error(f"❌ خطأ في الصرف: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/multiplier")
async def api_multiplier():
    """جلب المضاعف الحالي للجولة"""
    game_round.update_timer()
    
    return {
        "multiplier": game_round.current_multiplier,
        "status": game_round.status,
        "result": game_round.result,
        "round_id": game_round.round_id
    }

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

# ==================== نقطة الدخول ====================
if __name__ == "__main__":
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=PORT,
        log_level="info"
    )