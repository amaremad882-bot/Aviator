import os
import sys
import asyncio
import random
import logging
from datetime import datetime, timedelta
from config import FLYING_DURATION, ROUND_DURATION, BETTING_DURATION, BET_OPTIONS
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from aiogram import Bot

# إصلاح: استخدام aiogram 2.x بدلاً من 3.x
try:
    from aiogram import Bot, Dispatcher, types
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from aiogram.contrib.fsm_storage.memory import MemoryStorage
    AIOGRAM_AVAILABLE = True
except ImportError:
    AIOGRAM_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("⚠️ aiogram غير متوفر، سيتم تعطيل البوت")

import logging
from database import (
    init_db, set_admin_unlimited_balance, get_balance, 
    update_balance, add_transaction, create_round, 
    add_bet, update_bet_result, finish_round, 
    update_round_result, get_user_active_bet
)

# إعداد الـ logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# الحصول على PORT من Railway
PORT = int(os.getenv("PORT", "8000"))

# تهيئة متغيرات اللعبة
active_bets = {}

# الإعدادات الأساسية
BOT_TOKEN = os.getenv('BOT_TOKEN', '8589461643:AAG1tUhcZ5OdJmxmoDlt7KDYsY7jSydjqqQ')
ADMIN_ID = int(os.getenv('ADMIN_ID', '5848548017'))
BASE_URL = os.getenv('BASE_URL', 'https://aviator-production-e666.up.railway.app')

# تأكد من أن BASE_URL يبدأ بـ https://
if not BASE_URL.startswith('https://'):
    BASE_URL = 'https://' + BASE_URL

# FastAPI App
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# إعداد البوت (فقط إذا كان aiogram متوفراً)
if AIOGRAM_AVAILABLE:
    bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
    storage = MemoryStorage()
    dp = Dispatcher(bot, storage=storage)

    # ===== Telegram /start =====
    @dp.message_handler(commands=["start"])
    async def start_cmd(message: types.Message):
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton(
                "🎮 دخول لعبة Aviator",
                url=f"{BASE_URL}/game?user_id={message.from_user.id}"
            )
        )

        await message.answer(
            "✈️ <b>مرحباً بك في لعبة Aviator</b>\n\n"
            "اضغط الزر أدناه للدخول إلى اللعبة 👇",
            reply_markup=keyboard
        )

else:
    bot = None
    dp = None
    logger.warning("🤖 البوت غير نشط - aiogram غير مثبت")


# استيراد game_logic بعد التهيئة
try:
    from game_logic import GameRoundAdvanced
    game_round = GameRoundAdvanced()
    GAME_LOGIC_AVAILABLE = True
except ImportError as e:
    logger.error(f"❌ خطأ في استيراد game_logic: {e}")
    GAME_LOGIC_AVAILABLE = False
    # إنشاء كائن بديل
    class DummyGameRound:
        def __init__(self):
            self.round_id = 1
            self.status = "waiting"
            self.current_multiplier = 1.0
            self.remaining_time = 0
            self.result = None
            self.flying_progress = 0
            self.crash_point = None
            self.active_bets = {}
        
        def update_timer(self):
            return self.current_multiplier
        
        def generate_round_result(self):
            return 2.0
        
    game_round = DummyGameRound()

# HTML واجهة اللعبة (مضمنة)
HTML_GAME = f'''
<!DOCTYPE html>
<html lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>✈️ Aviator</title>
    <style>
        body {{ background: #1a1a2e; color: white; font-family: Arial; padding: 20px; }}
        .container {{ max-width: 500px; margin: auto; background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; }}
        .balance {{ background: linear-gradient(45deg, #00b4d8, #0077b6); padding: 10px; border-radius: 10px; text-align: center; font-size: 20px; margin: 10px 0; }}
        .game-area {{ height: 200px; background: rgba(0,0,0,0.3); border-radius: 10px; position: relative; margin: 20px 0; }}
        #plane {{ position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); font-size: 40px; }}
        .timer {{ font-size: 30px; text-align: center; margin: 10px 0; color: #00ff88; }}
        .controls {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
        button {{ padding: 15px; border: none; border-radius: 10px; font-size: 16px; cursor: pointer; }}
        .bet-btn {{ background: #333; color: white; }}
        .cashout-btn {{ background: #00b09b; color: white; }}
        .message {{ text-align: center; margin: 10px 0; padding: 10px; border-radius: 5px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>✈️ Aviator Game</h1>
        <div class="balance">الرصيد: <span id="balance">0</span> 💰</div>
        <div class="timer" id="timer">00:00</div>
        <div class="game-area">
            <div id="plane">✈️</div>
            <div style="position: absolute; top: 10px; left: 50%; transform: translateX(-50%); font-size: 20px; color: #00ff88;" id="multiplier">1.00x</div>
        </div>
        <div class="message" id="message">🚀 اختر مبلغ الرهان!</div>
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 10px 0;">
            <button class="bet-btn" onclick="selectBet(10)">10</button>
            <button class="bet-btn" onclick="selectBet(50)">50</button>
            <button class="bet-btn" onclick="selectBet(100)">100</button>
            <button class="bet-btn" onclick="selectBet(500)">500</button>
            <button class="bet-btn" onclick="selectBet(1000)">1000</button>
            <button class="bet-btn" onclick="selectBet(5000)">5000</button>
        </div>
        <div class="controls">
            <button class="bet-btn" onclick="placeBet()" id="betBtn">🎯 وضع الرهان</button>
            <button class="cashout-btn" onclick="cashOut()" id="cashoutBtn" disabled>💰 صرف الآن</button>
        </div>
    </div>
    <script>
        const USER_ID = new URLSearchParams(window.location.search).get('user_id') || '0';
        const BASE_URL = "{BASE_URL}";
        let selectedBet = 0;
        let isPlaying = false;
        let currentMultiplier = 1.0;
        
        async function refreshBalance() {{
            try {{
                const res = await fetch(`${{BASE_URL}}/api/balance/${{USER_ID}}`);
                const data = await res.json();
                document.getElementById('balance').textContent = data.balance || 0;
            }} catch (e) {{ console.error(e); }}
        }}
        
        async function refreshRound() {{
            try {{
                const res = await fetch(`${{BASE_URL}}/api/round`);
                const data = await res.json();
                if (data.remaining_time) {{
                    document.getElementById('timer').textContent = 
                        Math.floor(data.remaining_time / 60).toString().padStart(2, '0') + ':' + 
                        (data.remaining_time % 60).toString().padStart(2, '0');
                }}
                
                if (data.current_multiplier) {{
                    currentMultiplier = data.current_multiplier;
                    document.getElementById('multiplier').textContent = currentMultiplier.toFixed(2) + 'x';
                    const plane = document.getElementById('plane');
                    const height = 20 + (currentMultiplier * 10);
                    plane.style.bottom = `${{Math.min(height, 180)}}px`;
                }}
            }} catch (e) {{ console.error(e); }}
        }}
        
        function selectBet(amount) {{
            selectedBet = amount;
            document.getElementById('message').textContent = `✅ تم اختيار ${{amount}} نقطة`;
        }}
        
        async function placeBet() {{
            if (!selectedBet) return alert('اختر مبلغ الرهان');
            try {{
                const res = await fetch(`${{BASE_URL}}/api/bet`, {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{user_id: USER_ID, amount: selectedBet}})
                }});
                const data = await res.json();
                if (data.error) alert(data.error);
                else {{
                    isPlaying = true;
                    document.getElementById('cashoutBtn').disabled = false;
                    document.getElementById('message').textContent = `✅ تم وضع رهان ${{selectedBet}}`;
                    refreshBalance();
                }}
            }} catch (e) {{ alert('خطأ في الاتصال'); }}
        }}
        
        async function cashOut() {{
            try {{
                const res = await fetch(`${{BASE_URL}}/api/cashout`, {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{user_id: USER_ID}})
                }});
                const data = await res.json();
                if (data.error) alert(data.error);
                else {{
                    isPlaying = false;
                    document.getElementById('cashoutBtn').disabled = true;
                    document.getElementById('message').textContent = `🎉 صرفت ${{data.win_amount}} نقطة!`;
                    refreshBalance();
                }}
            }} catch (e) {{ alert('خطأ في الاتصال'); }}
        }}
        
        // تحديث كل ثانية
        setInterval(() => {{
            refreshBalance();
            refreshRound();
        }}, 1000);
        
        // بدء التشغيل
        refreshBalance();
        refreshRound();
        document.getElementById('message').textContent = `مرحباً! ID: ${{USER_ID}}`;
    </script>
</body>
</html>
'''

def get_round_type(result):
    """تحديد نوع الجولة"""
    if result is None:
        return "waiting"
    if result == 0:
        return "crash"
    elif result < 2:
        return "low"
    elif result < 5:
        return "medium"
    elif result < 15:
        return "high"
    else:
        return "jackpot"

async def start_new_round_advanced():
    """بدء جولة جديدة متقدمة"""
    try:
        game_round.round_id = await create_round()
        game_round.start_time = datetime.now()
        game_round.betting_end = game_round.start_time + timedelta(seconds=BETTING_DURATION)
        game_round.flying_start = None
        game_round.flying_end = None
        game_round.result = None
        game_round.status = "betting"
        game_round.current_multiplier = 1.0
        game_round.active_bets = {}
        game_round.flying_progress = 0
        game_round.crash_point = None
        
        logger.info(f"🔄 بدأت الجولة #{game_round.round_id}")
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في بدء الجولة: {e}")
        return False

async def process_crash_bets():
    """معالجة الرهانات عند تحطم الطائرة"""
    if not bot:
        return
    
    try:
        for user_id, bet_info in list(active_bets.items()):
            if not bet_info["cashed_out"] and bet_info.get("round_id") == game_round.round_id:
                # خسارة كاملة
                await add_transaction(
                    user_id,
                    0,
                    "crash_loss",
                    f"خسارة كاملة بسبب تحطم الطائرة في الجولة #{game_round.round_id}"
                )
                
                # محاولة إرسال رسالة للمستخدم
                try:
                    await bot.send_message(
                        user_id,
                        f"💥 <b>تحطمت الطائرة!</b>\n\n"
                        f"🎯 الجولة: #{game_round.round_id}\n"
                        f"💰 رهانك: {bet_info['amount']}\n"
                        f"📉 لقد خسرت رهانك بالكامل!"
                    )
                except:
                    pass
                
                # حذف الرهان النشط
                del active_bets[user_id]
                
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة رهانات التحطم: {e}")

async def process_final_bets_advanced():
    """معالجة الرهانات النهائية للجولة المتقدمة"""
    try:
        for user_id, bet_info in list(active_bets.items()):
            if not bet_info["cashed_out"] and bet_info.get("round_id") == game_round.round_id:
                win_amount = 0
                
                if game_round.result and game_round.result > 0:
                    # فوز بمضاعف النتيجة النهائية
                    win_amount = int(bet_info["amount"] * game_round.result)
                    
                    if user_id != ADMIN_ID:
                        await update_balance(user_id, win_amount)
                    
                    await add_transaction(
                        user_id,
                        win_amount,
                        "final_win",
                        f"فوز نهائي بمضاعف {game_round.result}x في الجولة #{game_round.round_id}"
                    )
                    
                    # إرسال رسالة الفوز (إذا كان البوت متاحاً)
                    if bot:
                        try:
                            await bot.send_message(
                                user_id,
                                f"🎉 <b>انتهت الجولة #{game_round.round_id}</b>\n\n"
                                f"🎯 المضاعف النهائي: {game_round.result}x\n"
                                f"💰 رهانك: {bet_info['amount']}\n"
                                f"🏆 ربحك: {win_amount}"
                            )
                        except:
                            pass
                
                del active_bets[user_id]
                
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة الرهانات النهائية: {e}")

async def process_bet_cashout_advanced(user_id: int):
    """معالجة صرف الرهان في النظام المتقدم"""
    if user_id not in active_bets:
        return None
    
    bet_info = active_bets[user_id]
    
    if bet_info["cashed_out"]:
        return None
    
    if bet_info.get("round_id") != game_round.round_id:
        return None
    
    if game_round.status != "flying":
        return None
    
    # حساب المبلغ الفائز بناءً على المضاعف الحالي
    win_amount = int(bet_info["amount"] * game_round.current_multiplier)
    
    if win_amount <= 0:
        return None
    
    # تحديث رصيد المستخدم
    if user_id != ADMIN_ID:
        await update_balance(user_id, win_amount)
    
    # تحديث حالة الرهان
    bet_info["cashed_out"] = True
    bet_info["cashout_multiplier"] = game_round.current_multiplier
    
    # إضافة معاملة
    await add_transaction(
        user_id,
        win_amount,
        "cashout_win",
        f"صرف بمضاعف {game_round.current_multiplier}x في الجولة #{game_round.round_id}"
    )
    
    # تحديث قاعدة البيانات
    try:
        await update_bet_result(
            bet_id=user_id,  # Note: هذا مؤقت، في الواقع يجب حفظ ID الرهان
            multiplier=game_round.current_multiplier,
            win_amount=win_amount
        )
    except:
        pass
    
    return win_amount

async def process_round_advanced():
    """معالجة الجولة الحالية"""
    if not GAME_LOGIC_AVAILABLE:
        logger.warning("⚠️ game_logic غير متوفر، نظام الجولات معطل")
        return
    
    logger.info("🎮 بدء نظام الجولات...")
    
    # بدء الجولة الأولى
    await start_new_round_advanced()
    
    while True:
        try:
            now = datetime.now()
            
            # تحديث المؤقت
            current_multiplier = game_round.update_timer()
            
            # تحديث المضاعف الحالي
            game_round.current_multiplier = current_multiplier
            
            # الانتقال من وقت الرهان إلى الطيران
            if (game_round.status == "betting" and 
                game_round.betting_end and 
                now >= game_round.betting_end):
                
                game_round.status = "flying"
                game_round.flying_start = now
                game_round.flying_end = now + timedelta(seconds=FLYING_DURATION)
                
                # توليد نتيجة الجولة
                result = game_round.generate_round_result()
                game_round.result = result
                
                await update_round_result(game_round.round_id, result)
                logger.info(f"🎯 الجولة #{game_round.round_id}: {'تحطمت' if result == 0 else f'مضاعف {result}x'}")
            
            # معالجة التحطم
            if game_round.status == "crashed":
                # معالجة جميع الرهانات (كلها خسارة)
                await process_crash_bets()
                
                # إنهاء الجولة
                await finish_round(game_round.round_id)
                
                # انتظار 5 ثواني قبل الجولة التالية
                await asyncio.sleep(5)
                
                # بدء جولة جديدة
                await start_new_round_advanced()
            
            # نهاية الجولة الطبيعية
            elif (game_round.status == "flying" and 
                  game_round.flying_end and 
                  now >= game_round.flying_end):
                
                # معالجة الرهانات النهائية
                await process_final_bets_advanced()
                
                # إنهاء الجولة
                await finish_round(game_round.round_id)
                
                # انتظار 3 ثواني قبل الجولة التالية
                await asyncio.sleep(3)
                
                # بدء جولة جديدة
                await start_new_round_advanced()
            
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"❌ خطأ في معالجة الجولة: {e}")
            await asyncio.sleep(5)

# ========== تعريفات API ==========

@app.get("/health")
async def health_check():
    """فحص صحة التطبيق لـ Railway"""
    return {
        "status": "healthy",
        "service": "aviator-game",
        "timestamp": datetime.now().isoformat(),
        "round_id": game_round.round_id if hasattr(game_round, 'round_id') else 0,
        "active_players": len(active_bets),
        "game_logic": "available" if GAME_LOGIC_AVAILABLE else "unavailable",
        "aiogram": "available" if AIOGRAM_AVAILABLE else "unavailable"
    }

@app.get("/")
def home():
    return {"app": "Aviator", "status": "running", "base_url": BASE_URL}

@app.get("/game")
def game_page(request: Request):
    user_id = request.query_params.get("user_id", "0")
    return HTMLResponse(content=HTML_GAME)

@app.get("/api/balance/{user_id}")
async def api_balance(user_id: int):
    """الحصول على رصيد المستخدم"""
    try:
        # رصيد الأدمن غير محدود
        if user_id == ADMIN_ID:
            return {"balance": 999999999, "is_admin": True}
        
        balance = await get_balance(user_id)
        return {"balance": balance, "is_admin": False}
    except Exception as e:
        logger.error(f"❌ خطأ في جلب الرصيد: {e}")
        return {"balance": 1000, "is_admin": False}

@app.get("/api/round")
async def api_round():
    """معلومات الجولة"""
    try:
        if GAME_LOGIC_AVAILABLE:
            game_round.update_timer()
            
            response = {
                "round_id": game_round.round_id,
                "status": game_round.status,
                "result": game_round.result,
                "current_multiplier": game_round.current_multiplier,
                "remaining_time": game_round.remaining_time,
                "flying_progress": game_round.flying_progress,
                "crash_point": game_round.crash_point,
                "can_bet": game_round.status == "betting",
                "active_players": len(active_bets),
                "round_type": get_round_type(game_round.result)
            }
        else:
            response = {
                "round_id": 1,
                "status": "waiting",
                "result": None,
                "current_multiplier": 1.0,
                "remaining_time": 30,
                "flying_progress": 0,
                "crash_point": None,
                "can_bet": True,
                "active_players": 0,
                "round_type": "waiting"
            }
        
        return response
    except Exception as e:
        logger.error(f"❌ خطأ في جلب معلومات الجولة: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

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
        
        if not GAME_LOGIC_AVAILABLE or game_round.status != "betting":
            return JSONResponse({"error": "ليس وقت الرهان الآن"}, status_code=400)
        
        # المستخدمين العاديين فقط (ليس الأدمن)
        if user_id == ADMIN_ID:
            return JSONResponse({"error": "الأدمن لا يمكنه الرهان"}, status_code=400)
        
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
            "cashout_multiplier": 1.0,
            "bet_time": datetime.now().isoformat()
        }
        
        if GAME_LOGIC_AVAILABLE:
            game_round.active_bets[user_id] = amount
        
        # إضافة الرهان إلى قاعدة البيانات
        await add_bet(user_id, game_round.round_id, amount)
        
        # خصم المبلغ
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
            "remaining_time": game_round.remaining_time if GAME_LOGIC_AVAILABLE else 30,
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
        
        win_amount = await process_bet_cashout_advanced(user_id)
        
        if win_amount is None:
            return JSONResponse({"error": "لا يمكن صرف الرهان الآن"}, status_code=400)
        
        return {
            "success": True,
            "win_amount": win_amount,
            "multiplier": game_round.current_multiplier,
            "message": f"تم الصرف بنجاح بمضاعف {game_round.current_multiplier}x"
        }
        
    except Exception as e:
        logger.error(f"❌ خطأ في صرف الرهان: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# Webhook للبوت
from aiogram.types import Update

@app.post("/webhook")
async def telegram_webhook(request: Request):
    update = types.Update(**await request.json())

    # 🔥 الحل هنا
    Bot.set_current(bot)

    await dp.process_update(update)
    return {"ok": True}

@app.on_event("startup")
async def startup_event():
    """تشغيل عند بدء التطبيق"""
    # تهيئة قاعدة البيانات
    try:
        await init_db()
        await set_admin_unlimited_balance(ADMIN_ID)
        logger.info("✅ قاعدة البيانات مهيأة")
    except Exception as e:
        logger.error(f"❌ خطأ في تهيئة قاعدة البيانات: {e}")

    # بدء معالجة الجولات في الخلفية
    if GAME_LOGIC_AVAILABLE:
        asyncio.create_task(process_round_advanced())
    else:
        logger.warning("⚠️ نظام الجولات معطل - game_logic غير متوفر")

    # تفعيل Webhook Telegram
    if AIOGRAM_AVAILABLE:
        try:
            await bot.set_webhook(f"{BASE_URL}/webhook")
            logger.info("🤖 Webhook Telegram تم تفعيله")
        except Exception as e:
            logger.error(f"❌ فشل تعيين Webhook: {e}")

    logger.info(f"🚀 التطبيق يعمل على: {BASE_URL}")
    logger.info(f"📊 PORT: {PORT}")

# تشغيل التطبيق
if __name__ == "__main__":
    # Railway يستخدم 0.0.0.0
    logger.info(f"🚀 بدء التشغيل على Railway - Port: {PORT}")
    logger.info(f"🌐 رابط التطبيق: {BASE_URL}")
    
    # بدء التطبيق
    uvicorn.run(
        app, 
        host="0.0.0.0",  # مطلوب لـ Railway
        port=PORT,
        log_level="info",
        access_log=True
    )