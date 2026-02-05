import random
import math
from datetime import datetime
from config import ROUND_PROBABILITIES, FLYING_DURATION

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
        self.flying_progress = 0
        self.crash_point = None
        
    def generate_round_result(self):
        rand = random.random()
        
        if rand < ROUND_PROBABILITIES["low"]:
            if random.random() < 0.7:
                self.result = round(random.uniform(1.1, 3.0), 2)
                self.crash_point = None
            else:
                self.result = 0
                self.crash_point = round(random.uniform(0.5, 2.5), 2)
                
        elif rand < ROUND_PROBABILITIES["low"] + ROUND_PROBABILITIES["medium"]:
            if random.random() < 0.6:
                self.result = round(random.uniform(3.0, 8.0), 2)
                self.crash_point = None
            else:
                self.result = 0
                self.crash_point = round(random.uniform(2.5, 5.0), 2)
                
        elif rand < ROUND_PROBABILITIES["low"] + ROUND_PROBABILITIES["medium"] + ROUND_PROBABILITIES["high"]:
            if random.random() < 0.4:
                self.result = round(random.uniform(8.0, 20.0), 2)
                self.crash_point = None
            else:
                self.result = 0
                self.crash_point = round(random.uniform(5.0, 15.0), 2)
                
        elif rand < ROUND_PROBABILITIES["low"] + ROUND_PROBABILITIES["medium"] + ROUND_PROBABILITIES["high"] + ROUND_PROBABILITIES["jackpot"]:
            self.result = round(random.uniform(20.0, 50.0), 2)
            self.crash_point = None
            
        else:
            self.result = 0
            self.crash_point = round(random.uniform(0.1, 1.0), 2)
        
        return self.result
    
    def calculate_current_multiplier(self):
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
            if progress < 0.3:
                multiplier = 1.0 + (self.result - 1.0) * (progress / 0.3) * 0.3
            elif progress < 0.7:
                multiplier = 1.0 + (self.result - 1.0) * (0.3 + (progress - 0.3) / 0.4 * 0.5)
            else:
                multiplier = 1.0 + (self.result - 1.0) * (0.8 + (progress - 0.7) / 0.3 * 0.2)
            
            return round(min(multiplier, self.result), 2)
        
        else:
            if self.crash_point:
                if self.current_multiplier >= self.crash_point:
                    return 0
                else:
                    volatility = random.random()
                    if volatility > 0.95:
                        return 0
                    elif volatility > 0.7:
                        drop = random.uniform(0.1, 0.5)
                        new_multiplier = max(0.1, self.current_multiplier - drop)
                        return round(new_multiplier, 2)
                    else:
                        increase = random.uniform(0.1, 0.3)
                        return round(self.current_multiplier + increase, 2)
            
            return self.current_multiplier
    
    def update_timer(self):
        now = datetime.now()
        
        if self.status == "betting" and self.betting_end:
            self.remaining_time = max(0, int((self.betting_end - now).total_seconds()))
            self.current_multiplier = 1.0
            
        elif self.status == "flying":
            if self.flying_end:
                self.remaining_time = max(0, int((self.flying_end - now).total_seconds()))
            else:
                self.remaining_time = 0
            
            self.current_multiplier = self.calculate_current_multiplier()
            
            if self.result == 0 and self.current_multiplier == 0:
                self.status = "crashed"
        
        return self.current_multiplier

game_round = GameRoundAdvanced()