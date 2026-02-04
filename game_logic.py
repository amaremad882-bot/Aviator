import asyncio
import random
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from config import ROUND_DURATION, BETTING_DURATION, MIN_MULTIPLIER, MAX_MULTIPLIER

class GameRound:
    """فئة تمثل جولة في اللعبة"""
    def __init__(self):
        self.round_id = None
        self.start_time = None
        self.betting_end = None
        self.round_end = None
        self.result = None
        self.status = "waiting"
        self.remaining_time = 0
        self.current_multiplier = 1.0
        self.betting_phase = True
        self.active_bets = {}  # user_id: amount
        
    def update_timer(self):
        """تحديث المؤقت"""
        if not self.start_time:
            return
        
        now = datetime.now()
        
        if self.status == "betting":
            self.remaining_time = max(0, int((self.betting_end - now).total_seconds()))
        elif self.status == "counting":
            self.remaining_time = max(0, int((self.round_end - now).total_seconds()))
            
            # حساب المضاعف الحالي أثناء مرحلة العد
            if self.result and self.betting_end:
                elapsed = (now - self.betting_end).total_seconds()
                total_counting = ROUND_DURATION - BETTING_DURATION
                
                if elapsed <= total_counting:
                    progress = min(1.0, elapsed / total_counting)
                    # منحنى مضاعف أكثر واقعية
                    self.current_multiplier = self.calculate_multiplier(progress)
    
    def calculate_multiplier(self, progress: float) -> float:
        """حساب المضاعف بناءً على التقدم"""
        if not self.result:
            return 1.0
        
        # منحنى مضاعف واقعي
        if progress < 0.3:
            # بداية بطيئة
            multiplier = 1.0 + (self.result - 1.0) * (progress / 0.3) * 0.5
        elif progress < 0.7:
            # وسط سريع
            multiplier = 1.0 + (self.result - 1.0) * (0.5 + (progress - 0.3) / 0.4 * 0.4)
        else:
            # نهاية خطيرة
            multiplier = 1.0 + (self.result - 1.0) * (0.9 + (progress - 0.7) / 0.3 * 0.1)
        
        return round(min(multiplier, self.result), 2)
    
    def generate_result(self) -> float:
        """توليد نتيجة عشوائية للجولة"""
        # احتمالات واقعية
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
        
        return round(min(result, MAX_MULTIPLIER), 2)

class ActiveBet:
    """فئة تمثل رهان نشط"""
    def __init__(self, user_id: int, amount: int, round_id: int):
        self.user_id = user_id
        self.amount = amount
        self.round_id = round_id
        self.cashed_out = False
        self.cashout_multiplier = 1.0
        self.max_multiplier = 1.0

class GameManager:
    """مدير اللعبة"""
    def __init__(self):
        self.current_round = GameRound()
        self.active_bets: Dict[int, ActiveBet] = {}
        self.game_task = None
        self.is_running = False
    
    async def start_new_round(self):
        """بدء جولة جديدة"""
        from database import create_round
        
        round_id = await create_round()
        self.current_round.round_id = round_id
        self.current_round.start_time = datetime.now()
        self.current_round.betting_end = self.current_round.start_time + timedelta(seconds=BETTING_DURATION)
        self.current_round.round_end = self.current_round.start_time + timedelta(seconds=ROUND_DURATION)
        self.current_round.result = None
        self.current_round.status = "betting"
        self.current_round.current_multiplier = 1.0
        self.current_round.active_bets = {}
        
        print(f"🔄 بدأت الجولة #{round_id}")
        return True
    
    async def process_round(self):
        """معالجة الجولة الحالية"""
        self.is_running = True
        
        while self.is_running:
            try:
                now = datetime.now()
                self.current_round.update_timer()
                
                # الانتقال من وقت الرهان إلى العد
                if (self.current_round.status == "betting" and 
                    self.current_round.betting_end and 
                    now >= self.current_round.betting_end):
                    
                    self.current_round.status = "counting"
                    self.current_round.result = self.current_round.generate_result()
                    
                    from database import update_round_result
                    await update_round_result(self.current_round.round_id, self.current_round.result)
                    
                    print(f"🎯 نتيجة الجولة #{self.current_round.round_id}: {self.current_round.result}x")
                
                # نهاية الجولة
                if (self.current_round.status == "counting" and 
                    self.current_round.round_end and 
                    now >= self.current_round.round_end):
                    
                    # معالجة الرهانات المتبقية
                    await self.process_remaining_bets()
                    
                    # إنهاء الجولة
                    from database import finish_round
                    await finish_round(self.current_round.round_id)
                    
                    # انتظار قصير قبل الجولة التالية
                    await asyncio.sleep(3)
                    
                    # بدء جولة جديدة
                    await self.start_new_round()
                
                await asyncio.sleep(1)
                
            except Exception as e:
                print(f"❌ خطأ في معالجة الجولة: {e}")
                await asyncio.sleep(5)
    
    async def place_bet(self, user_id: int, amount: int) -> bool:
        """وضع رهان"""
        if self.current_round.status != "betting":
            return False
        
        if user_id in self.current_round.active_bets:
            return False
        
        self.current_round.active_bets[user_id] = amount
        self.active_bets[user_id] = ActiveBet(user_id, amount, self.current_round.round_id)
        
        from database import add_bet
        await add_bet(user_id, self.current_round.round_id, amount)
        
        return True
    
    async def cashout_bet(self, user_id: int) -> Optional[float]:
        """صرف الرهان"""
        if user_id not in self.active_bets:
            return None
        
        bet = self.active_bets[user_id]
        
        if bet.cashed_out or bet.round_id != self.current_round.round_id:
            return None
        
        bet.cashed_out = True
        bet.cashout_multiplier = self.current_round.current_multiplier
        
        win_amount = int(bet.amount * bet.cashout_multiplier)
        
        # تحديث قاعدة البيانات
        from database import update_bet_result
        await update_bet_result(
            bet_id=user_id,  # هذا مؤقت، في الواقع يجب حفظ ID الرهان
            multiplier=bet.cashout_multiplier,
            win_amount=win_amount
        )
        
        return win_amount
    
    async def process_remaining_bets(self):
        """معالجة الرهانات المتبقية"""
        for user_id, bet in list(self.active_bets.items()):
            if not bet.cashed_out and bet.round_id == self.current_round.round_id:
                # معالجة الرهان النهائي
                win_amount = int(bet.amount * self.current_round.result)
                
                from database import update_bet_result
                await update_bet_result(
                    bet_id=user_id,
                    multiplier=self.current_round.result,
                    win_amount=win_amount
                )
                
                # تحديث الرصيد
                from database import update_balance
                await update_balance(user_id, win_amount)
                
                # إضافة معاملة
                from database import add_transaction
                await add_transaction(
                    user_id,
                    win_amount,
                    "final_win",
                    f"فوز نهائي بمضاعف {self.current_round.result}x في الجولة #{self.current_round.round_id}"
                )
                
                del self.active_bets[user_id]
    
    def get_game_state(self) -> dict:
        """الحصول على حالة اللعبة الحالية"""
        return {
            "round_id": self.current_round.round_id,
            "status": self.current_round.status,
            "result": self.current_round.result,
            "current_multiplier": self.current_round.current_multiplier,
            "remaining_time": self.current_round.remaining_time,
            "betting_phase": self.current_round.status == "betting",
            "active_players": len(self.current_round.active_bets)
        }

# إنشاء مدير اللعبة العام
game_manager = GameManager()