import random
import math
from datetime import datetime
from config import ROUND_PROBABILITIES, FLYING_DURATION  # ← أضف هذا السطر

class GameRoundAdvanced:
    def __init__(self):
        self.round_id = None
        self.start_time = None
        self.betting_end = None
        self.flying_start = None
        self.flying_end = None
        self.result = None
        self.status = "waiting"
        self.current_multiplier = 1.0
        self.remaining_time = 0
        self.active_bets = {}
        self.flying_progress = 0  # تقدم الطيران (0-100%)
        self.crash_point = None   # نقطة التحطم للجولات الخاسرة
        
    def generate_round_result(self):
        """توليد نتيجة عشوائية للجولة مع احتمالات مختلفة"""
        rand = random.random()
        
        if rand < ROUND_PROBABILITIES["low"]:
            # جولات مضاعف منخفض
            if random.random() < 0.7:
                # جولات مربحة منخفضة
                self.result = round(random.uniform(1.1, 3.0), 2)
                self.crash_point = None
            else:
                # جولات خاسرة منخفضة
                self.result = 0
                self.crash_point = round(random.uniform(0.5, 2.5), 2)
                
        elif rand < ROUND_PROBABILITIES["low"] + ROUND_PROBABILITIES["medium"]:
            # جولات مضاعف متوسط
            if random.random() < 0.6:
                # جولات مربحة متوسطة
                self.result = round(random.uniform(3.0, 8.0), 2)
                self.crash_point = None
            else:
                # جولات خاسرة متوسطة
                self.result = 0
                self.crash_point = round(random.uniform(2.5, 5.0), 2)
                
        elif rand < ROUND_PROBABILITIES["low"] + ROUND_PROBABILITIES["medium"] + ROUND_PROBABILITIES["high"]:
            # جولات مضاعف عالي
            if random.random() < 0.4:
                # جولات مربحة عالية
                self.result = round(random.uniform(8.0, 20.0), 2)
                self.crash_point = None
            else:
                # جولات خاسرة عالية
                self.result = 0
                self.crash_point = round(random.uniform(5.0, 15.0), 2)
                
        elif rand < ROUND_PROBABILITIES["low"] + ROUND_PROBABILITIES["medium"] + ROUND_PROBABILITIES["high"] + ROUND_PROBABILITIES["jackpot"]:
            # جولات جاكبوت
            self.result = round(random.uniform(20.0, 50.0), 2)
            self.crash_point = None
            
        else:
            # جولات تحطم فوري
            self.result = 0
            self.crash_point = round(random.uniform(0.1, 1.0), 2)
        
        return self.result
    
    def calculate_current_multiplier(self):
        """حساب المضاعف الحالي بناءً على التقدم"""
        if not self.flying_start or self.status != "flying":
            return 1.0
        
        now = datetime.now()
        elapsed = (now - self.flying_start).total_seconds()
        total_flying = FLYING_DURATION
        
        if elapsed >= total_flying:
            return self.result if self.result > 0 else 0
        
        progress = elapsed / total_flying
        self.flying_progress = progress * 100
        
        if self.result > 0:
            # جولة مربحة - المضاعف يزداد تدريجياً
            if progress < 0.3:
                # بداية بطيئة
                multiplier = 1.0 + (self.result - 1.0) * (progress / 0.3) * 0.3
            elif progress < 0.7:
                # وسط سريع
                multiplier = 1.0 + (self.result - 1.0) * (0.3 + (progress - 0.3) / 0.4 * 0.5)
            else:
                # نهاية خطيرة
                multiplier = 1.0 + (self.result - 1.0) * (0.8 + (progress - 0.7) / 0.3 * 0.2)
            
            return round(min(multiplier, self.result), 2)
        
        else:
            # جولة خاسرة - قد تتحطم في أي لحظة
            if self.crash_point:
                if self.current_multiplier >= self.crash_point:
                    # تحطمت الطائرة
                    return 0
                else:
                    # لا تزال تطير ولكن قد تتحطم قريباً
                    volatility = random.random()
                    if volatility > 0.95:  # 5% فرصة تحطم فوري
                        return 0
                    elif volatility > 0.7:  # 25% فرصة انخفاض
                        drop = random.uniform(0.1, 0.5)
                        new_multiplier = max(0.1, self.current_multiplier - drop)
                        return round(new_multiplier, 2)
                    else:
                        # استمرار في الارتفاع
                        increase = random.uniform(0.1, 0.3)
                        return round(self.current_multiplier + increase, 2)
            
            return self.current_multiplier
    
    def update_timer(self):
    """تحديث المؤقت"""
        now = datetime.now()
    
        if self.status == "betting" and self.betting_end:
            self.remaining_time = max(0, int((self.betting_end - now).total_seconds()))
            self.current_multiplier = 1.0
        
        elif self.status == "flying":
            if self.flying_end:
                self.remaining_time = max(0, int((self.flying_end - now).total_seconds()))
                
                else:
                
                self.remaining_time = 0
        
        # حساب المضاعف الحالي
            self.current_multiplier = self.calculate_current_multiplier()
        
        # التحقق من التحطم
            if self.result == 0 and self.current_multiplier == 0:
            # الطائرة تحطمت
                self.status = "crashed"
                return
                
# إرجاع المضاعف الحالي
                return self.current_multiplier

game_round = GameRoundAdvanced()