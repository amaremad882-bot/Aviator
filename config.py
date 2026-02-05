import os
import sys
from dotenv import load_dotenv

# تحميل متغيرات البيئة
load_dotenv()

# ==================== إعدادات البوت ====================
BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
ADMIN_ID_STR = os.getenv('ADMIN_ID', '').strip()

# ==================== إعدادات Railway ====================
RAILWAY_PUBLIC_DOMAIN = os.getenv('RAILWAY_PUBLIC_DOMAIN', '').strip()
RAILWAY_STATIC_URL = os.getenv('RAILWAY_STATIC_URL', '').strip()

# تحديد الرابط الأساسي - تأكد من HTTPS
if RAILWAY_STATIC_URL:
    BASE_URL = RAILWAY_STATIC_URL if RAILWAY_STATIC_URL.startswith('https://') else f"https://{RAILWAY_STATIC_URL}"
elif RAILWAY_PUBLIC_DOMAIN:
    BASE_URL = f"https://{RAILWAY_PUBLIC_DOMAIN}"
else:
    BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000').strip()

# تأكد من أن BASE_URL يبدأ بـ https:// في الإنتاج
if 'railway.app' in BASE_URL and not BASE_URL.startswith('https://'):
    BASE_URL = f"https://{BASE_URL.replace('http://', '')}"

# ==================== إعدادات الجولات الجديدة ====================
ROUND_DURATION = 60  # مدة الجولة الكاملة
BETTING_DURATION = 30  # وقت الرهان فقط
FLYING_DURATION = ROUND_DURATION - BETTING_DURATION  # وقت الطيران

# أضف هذا ⬇⬇⬇
BET_OPTIONS = [10, 50, 100, 500, 1000, 5000]  # خيارات الرهان

# نظام 50 جولة مختلفة مع مضاعفات عشوائية
ROUND_MULTIPLIERS = [
    1.2, 1.5, 2.0, 0.5, 3.0, 1.8, 2.5, 0.8, 4.0, 1.3,
    2.2, 0.3, 5.0, 1.6, 2.8, 0.7, 6.0, 1.9, 3.2, 0.6,
    7.0, 2.1, 3.5, 0.4, 8.0, 2.3, 3.8, 0.2, 9.0, 2.4,
    4.0, 0.1, 10.0, 2.6, 4.2, 0, 12.0, 2.7, 4.5, 0.9,
    15.0, 2.9, 4.8, 0, 18.0, 3.1, 5.0, 0, 20.0, 3.3,
    5.5, 0, 25.0, 3.6, 6.0, 0, 30.0, 3.9, 7.0, 0,
    35.0, 4.3, 8.0, 0, 40.0, 4.7, 9.0, 0, 50.0, 5.0,
    10.0, 0, 60.0, 6.0, 12.0, 0, 70.0, 7.0, 15.0, 0,
    8.0, 8.0, 18.0, 0, 9.0, 9.0, 6.0, 0, 3.0, 10.0
]

# احتمالية كل نوع من الجولات
ROUND_PROBABILITIES = {
    "low": 0.6,      # مضاعفات منخفضة (1.0 - 3.0x)
    "medium": 0.3,   # مضاعفات متوسطة (3.0 - 8.0x)
    "high": 0.2,     # مضاعفات عالية (8.0 - 20.0x)
    "jackpot": 0.08, # مضاعفات عالية جداً (20.0 - 50.0x)
    "crash": 0.02    # جولات تغلق فوراً (0x - 0.5x)
}

# ==================== تحويل ADMIN_ID لرقم ====================
try:
    ADMIN_ID = int(ADMIN_ID_STR) if ADMIN_ID_STR else 0
except ValueError:
    ADMIN_ID = 0

# ... باقي الملف (HTML_TEMPLATE طويلة) ...
# ==================== HTML واجهة اللعبة ====================
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>✈️ لعبة Aviator Pro</title>
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
            font-family: 'Segoe UI', 'Arial', sans-serif;
        }
        
        body {
            background: linear-gradient(135deg, var(--dark) 0%, var(--darker) 100%);
            min-height: 100vh;
            color: white;
            padding: 10px;
            overflow-x: hidden;
        }
        
        .container {
            max-width: 500px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            border: 1px solid rgba(255,255,255,0.1);
            animation: fadeIn 0.5s ease;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid rgba(255,255,255,0.1);
        }
        
        .logo {
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 20px;
            font-weight: bold;
        }
        
        .logo span {
            font-size: 28px;
            animation: float 3s ease-in-out infinite;
        }
        
        @keyframes float {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-5px); }
        }
        
        .user-info {
            text-align: left;
            font-size: 12px;
            opacity: 0.8;
        }
        
        .balance-card {
            background: linear-gradient(45deg, var(--primary), var(--secondary));
            padding: 12px 20px;
            border-radius: 15px;
            font-weight: bold;
            font-size: 16px;
            text-align: center;
            box-shadow: 0 4px 15px rgba(0, 180, 216, 0.3);
            margin-bottom: 15px;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.02); }
        }
        
        .round-info {
            background: rgba(0,0,0,0.3);
            padding: 15px;
            border-radius: 15px;
            margin: 10px 0;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.1);
        }
        
        .round-id {
            font-size: 14px;
            opacity: 0.8;
            margin-bottom: 5px;
        }
        
        .timer {
            font-size: 32px;
            font-weight: bold;
            margin: 10px 0;
            color: var(--success);
            text-shadow: 0 0 15px var(--success);
            font-family: 'Courier New', monospace;
        }
        
        .round-status {
            font-size: 16px;
            margin: 5px 0;
            color: var(--warning);
        }
        
        .multiplier-info {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 10px;
            padding: 8px 15px;
            background: rgba(0,0,0,0.2);
            border-radius: 10px;
        }
        
        .game-area {
            position: relative;
            height: 300px;
            background: rgba(0, 0, 0, 0.4);
            border-radius: 15px;
            margin: 15px 0;
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
        
        .clouds {
            position: absolute;
            top: 20px;
            width: 100%;
            height: 50px;
            background: rgba(255,255,255,0.05);
            animation: cloudsMove 20s linear infinite;
        }
        
        @keyframes cloudsMove {
            from { transform: translateX(100%); }
            to { transform: translateX(-100%); }
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
            font-size: 40px;
            z-index: 10;
            filter: drop-shadow(0 0 5px rgba(255, 255, 255, 0.7));
            transition: all 0.1s ease-out;
        }
        
        .multiplier-display {
            position: absolute;
            top: 15px;
            left: 50%;
            transform: translateX(-50%);
            font-size: 24px;
            font-weight: bold;
            color: var(--success);
            z-index: 20;
            text-shadow: 0 0 10px var(--success);
            background: rgba(0,0,0,0.5);
            padding: 5px 15px;
            border-radius: 20px;
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
        
        .message {
            text-align: center;
            margin: 10px 0;
            padding: 12px;
            border-radius: 10px;
            font-size: 14px;
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
            margin: 15px 0;
        }
        
        .section-title {
            font-size: 16px;
            margin-bottom: 10px;
            color: var(--primary);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .bet-amounts {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
            margin: 10px 0;
        }
        
        .bet-btn {
            padding: 15px 10px;
            border: none;
            border-radius: 10px;
            background: rgba(255,255,255,0.1);
            color: white;
            font-size: 16px;
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
            transform: translateY(-2px);
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
            font-size: 18px;
        }
        
        .bet-label {
            font-size: 11px;
            opacity: 0.8;
        }
        
        .controls {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin: 15px 0;
        }
        
        .action-btn {
            padding: 18px;
            border: none;
            border-radius: 15px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }
        
        .bet-action {
            background: linear-gradient(45deg, var(--danger), #ff4b2b);
        }
        
        .bet-action:hover:not(:disabled) {
            background: linear-gradient(45deg, #ff4b2b, var(--danger));
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(255, 65, 108, 0.4);
        }
        
        .cashout-action {
            background: linear-gradient(45deg, var(--success), #00b09b);
        }
        
        .cashout-action:hover:not(:disabled) {
            background: linear-gradient(45deg, #00b09b, var(--success));
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(0, 255, 136, 0.4);
        }
        
        .action-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none !important;
        }
        
        .stats-section {
            background: rgba(0,0,0,0.3);
            padding: 15px;
            border-radius: 10px;
            margin-top: 15px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            margin-top: 10px;
        }
        
        .stat-item {
            background: rgba(255,255,255,0.05);
            padding: 10px;
            border-radius: 8px;
            text-align: center;
        }
        
        .stat-value {
            font-size: 18px;
            font-weight: bold;
            color: var(--primary);
            margin-top: 5px;
        }
        
        .instructions {
            background: rgba(0,0,0,0.2);
            padding: 15px;
            border-radius: 10px;
            margin-top: 15px;
            font-size: 12px;
            line-height: 1.6;
            border: 1px solid rgba(255,255,255,0.1);
        }
        
        .instructions ul {
            padding-right: 20px;
            margin: 10px 0;
        }
        
        .instructions li {
            margin-bottom: 5px;
        }
        
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top-color: var(--primary);
            animation: spin 1s ease-in-out infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .glow {
            animation: glow 1s ease-in-out infinite alternate;
        }
        
        @keyframes glow {
            from { box-shadow: 0 0 5px var(--success); }
            to { box-shadow: 0 0 20px var(--success); }
        }
        
        .shake {
            animation: shake 0.5s ease-in-out;
        }
        
        @keyframes shake {
            0%, 100% { transform: translateX(-50%); }
            25% { transform: translateX(-52%); }
            75% { transform: translateX(-48%); }
        }
        
        @media (max-width: 600px) {
            .container {
                padding: 10px;
                margin: 5px;
                border-radius: 15px;
            }
            
            .game-area {
                height: 250px;
            }
            
            .timer {
                font-size: 28px;
            }
            
            .bet-amounts {
                grid-template-columns: repeat(3, 1fr);
            }
            
            .bet-btn {
                padding: 12px 8px;
                font-size: 14px;
            }
            
            .action-btn {
                padding: 15px;
                font-size: 14px;
            }
        }
        
        @media (max-width: 400px) {
            .bet-amounts {
                grid-template-columns: repeat(2, 1fr);
            }
            
            .stats-grid {
                grid-template-columns: 1fr;
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
                <div id="current-multiplier" class="glow">1.00x</div>
            </div>
        </div>
        
        <!-- منطقة اللعبة -->
        <div class="game-area">
            <div class="sky"></div>
            <div class="clouds"></div>
            <div class="flight-path"></div>
            <div class="runway">
                <div class="runway-lines"></div>
            </div>
            <div id="plane">✈️</div>
            <div class="multiplier-display" id="multiplier-display">1.00x</div>
        </div>
        
        <!-- الرسائل -->
        <div class="message" id="message">
            🚀 اختر مبلغ الرهان وابدأ اللعب!
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
                    <div>اللاعبين النشطين</div>
                    <div class="stat-value" id="active-players">0</div>
                </div>
                <div class="stat-item">
                    <div>الوقت المتبقي</div>
                    <div class="stat-value" id="time-left">0s</div>
                </div>
                <div class="stat-item">
                    <div>حالة الجولة</div>
                    <div class="stat-value" id="game-status">انتظار</div>
                </div>
                <div class="stat-item">
                    <div>أعلى مضاعف</div>
                    <div class="stat-value" id="max-multiplier">1.00x</div>
                </div>
            </div>
        </div>
        
        <!-- التعليمات -->
        <div class="instructions">
            <div class="section-title">
                <span>📖</span> كيف تلعب
            </div>
            <ul>
                <li>اختر مبلغ الرهان من الأعلى</li>
                <li>اضغط "وضع الرهان" خلال وقت الرهان (<span id="betting-time">30</span> ثانية)</li>
                <li>شاهد الطائرة تصعد والمضاعف يزداد</li>
                <li>اضغط "صرف الآن" للحصول على المضاعف الحالي</li>
                <li>إذا لم تصرف، تحصل على المضاعف النهائي عند انتهاء الجولة</li>
            </ul>
            <div style="text-align: center; margin-top: 10px; font-size: 11px; opacity: 0.7;">
                ⚠️ الرهان مسؤوليتك. العب بمسؤولية.
            </div>
        </div>
    </div>

    <script>
    
    
    <!-- قسم نوع الجولة -->
    <div class="round-type" id="round-type">
        <span class="type-badge" id="type-badge">عادي</span>
        <span class="round-info" id="round-info">جولة مضاعف متوسطة</span>
    </div>
    <style>
    .round-type {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 10px;
        margin: 10px 0;
        padding: 10px;
        background: rgba(0,0,0,0.3);
        border-radius: 10px;
    }

    .type-badge {
        padding: 5px 15px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 14px;
    }
    .type-crash { background: #ff4444; color: white; }
    .type-low { background: #ffd700; color: black; }
    .type-medium { background: #00b4d8; color: white; }
    .type-high { background: #9d4edd; color: white; }
    .type-jackpot { background: #ff6d00; color: white; }
    </style>

    <script>
    // تحديث نوع الجولة
    function updateRoundType(roundType) {
        const badge = document.getElementById('type-badge');
        const info = document.getElementById('round-info');
    
        const types = {
            'crash': {text: 'تحطم', class: 'type-crash', info: '⚠️ جولة خطيرة - قد تتحطم!'},
            'low': {text: 'منخفض', class: 'type-low', info: '📊 جولة مضاعف منخفض'},
            'medium': {text: 'متوسط', class: 'type-medium', info: '🎯 جولة مضاعف متوسط'},
            'high': {text: 'عالي', class: 'type-high', info: '🚀 جولة مضاعف عالي'},
            'jackpot': {text: 'جاكبوت', class: 'type-jackpot', info: '💰 جولة جاكبوت!'}
        };
    
        const type = types[roundType] || types['medium'];
        badge.textContent = type.text;
        badge.className = 'type-badge ' + type.class;
        info.textContent = type.info;
    }

    // في دالة refreshRoundInfo أضف:
    if (data.round_type) {
        updateRoundType(data.round_type);
    }
    </script>
         
        
    
    
    
        // ==================== الإعدادات الأساسية ====================
        const USER_ID = new URLSearchParams(window.location.search).get('user_id') || '0';
        const BASE_URL = '''' + BASE_URL + '''';
        const BET_OPTIONS = JSON.parse('BET_OPTIONS_PLACEHOLDER'.replace(/'/g, '"'));
        const ROUND_DURATION = parseInt('ROUND_DURATION_PLACEHOLDER');
        const BETTING_DURATION = parseInt('BETTING_DURATION_PLACEHOLDER');
        
        // ==================== المتغيرات العامة ====================
        let selectedAmount = 0;
        let currentBet = null;
        let currentMultiplier = 1.0;
        let maxMultiplier = 1.0;
        let isPlaying = false;
        let roundStatus = "waiting";
        let remainingTime = 0;
        let updateInterval = null;
        let multiplierInterval = null;
        let activePlayers = 0;
        
        // ==================== تهيئة الصفحة ====================
        function initPage() {
            document.getElementById('user-id').textContent = USER_ID;
            document.getElementById('betting-time').textContent = BETTING_DURATION;
            createBetButtons();
            refreshAllData();
            startAutoUpdate();
            setupEventListeners();
        }
        
        // ==================== إنشاء أزرار الرهان ====================
        function createBetButtons() {
            const container = document.getElementById('bet-amounts');
            container.innerHTML = '';
            
            BET_OPTIONS.forEach(amount => {
                const button = document.createElement('button');
                button.className = 'bet-btn';
                button.innerHTML = `
                    <div class="bet-amount">${amount}</div>
                    <div class="bet-label">نقطة</div>
                `;
                button.onclick = () => selectAmount(amount);
                container.appendChild(button);
            });
            
            if (BET_OPTIONS.length > 0) {
                selectAmount(BET_OPTIONS[0]);
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
            
            showMessage(`✅ تم اختيار الرهان: ${amount} نقطة`, 'success');
            updateBetButton();
        }
        
        // ==================== تحديث البيانات ====================
        async function refreshAllData() {
            await Promise.all([
                refreshBalance(),
                refreshRoundInfo(),
                refreshMultiplier()
            ]);
        }
        
        // ==================== جلب الرصيد ====================
        async function refreshBalance() {
            try {
                const response = await fetch(`${BASE_URL}/api/balance/${USER_ID}`);
                const data = await response.json();
                
                if (data.error) {
                    console.error('خطأ في الرصيد:', data.error);
                    return;
                }
                
                const balanceText = data.is_admin ? '∞ (غير محدود)' : data.balance.toLocaleString();
                document.getElementById('balance').innerHTML = `${balanceText} <span>💰</span>`;
                
            } catch (error) {
                console.error('خطأ في جلب الرصيد:', error);
            }
        }
        
        // ==================== جلب معلومات الجولة ====================
        async function refreshRoundInfo() {
            try {
                const response = await fetch(`${BASE_URL}/api/round`);
                const data = await response.json();
                
                if (!data.round_id) {
                    document.getElementById('round-id').textContent = '#0';
                    document.getElementById('timer').textContent = '00:00';
                    document.getElementById('round-status').textContent = '⏳ انتظار الجولة القادمة';
                    document.getElementById('game-status').textContent = 'انتظار';
                    return;
                }
                
                // تحديث معلومات الجولة
                document.getElementById('round-id').textContent = `#${data.round_id}`;
                
                const statusText = data.status === 'betting' ? '🕒 وقت الرهان' :
                                  data.status === 'counting' ? '✈️ الجولة جارية' :
                                  '⏳ انتظار الجولة القادمة';
                
                document.getElementById('round-status').textContent = statusText;
                document.getElementById('game-status').textContent = 
                    data.status === 'betting' ? 'مراهنة' :
                    data.status === 'counting' ? 'جارية' : 'انتظار';
                
                // تحديث العداد
                remainingTime = data.remaining_time || 0;
                updateTimer(remainingTime);
                document.getElementById('time-left').textContent = `${remainingTime}s`;
                
                // تحديث اللاعبين النشطين
                activePlayers = data.active_players || 0;
                document.getElementById('active-players').textContent = activePlayers;
                
                roundStatus = data.status;
                
                // تحديث حالة أزرار التحكم
                updateBetButton();
                updateCashoutButton();
                
            } catch (error) {
                console.error('خطأ في جلب معلومات الجولة:', error);
            }
        }
        
        // ==================== جلب المضاعف ====================
        async function refreshMultiplier() {
            try {
                const response = await fetch(`${BASE_URL}/api/multiplier`);
                const data = await response.json();
                
                if (data.multiplier) {
                    currentMultiplier = data.multiplier;
                    maxMultiplier = Math.max(maxMultiplier, currentMultiplier);
                    
                    // تحديث العرض
                    document.getElementById('current-multiplier').textContent = currentMultiplier.toFixed(2) + 'x';
                    document.getElementById('multiplier-display').textContent = currentMultiplier.toFixed(2) + 'x';
                    document.getElementById('max-multiplier').textContent = maxMultiplier.toFixed(2) + 'x';
                    
                    // تحديث الطائرة
                    updatePlanePosition();
                    
                    // إضافة تأثيرات للمضاعفات العالية
                    if (currentMultiplier >= 5) {
                        document.getElementById('multiplier-display').classList.add('glow');
                        document.getElementById('plane').classList.add('shake');
                    } else {
                        document.getElementById('multiplier-display').classList.remove('glow');
                        document.getElementById('plane').classList.remove('shake');
                    }
                }
                
            } catch (error) {
                console.error('خطأ في جلب المضاعف:', error);
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
            if (currentMultiplier >= 8) {
                plane.style.filter = 'drop-shadow(0 0 20px #ff0000)';
                plane.style.transform = 'translateX(-50%) scale(1.5)';
                plane.style.color = '#ff0000';
            } else if (currentMultiplier >= 5) {
                plane.style.filter = 'drop-shadow(0 0 15px #00ff88)';
                plane.style.transform = 'translateX(-50%) scale(1.3)';
                plane.style.color = '#00ff88';
            } else if (currentMultiplier >= 3) {
                plane.style.filter = 'drop-shadow(0 0 10px #ffd700)';
                plane.style.transform = 'translateX(-50%) scale(1.2)';
                plane.style.color = '#ffd700';
            } else if (currentMultiplier >= 2) {
                plane.style.filter = 'drop-shadow(0 0 8px #00b4d8)';
                plane.style.transform = 'translateX(-50%) scale(1.1)';
                plane.style.color = '#00b4d8';
            } else {
                plane.style.filter = 'drop-shadow(0 0 5px #ffffff)';
                plane.style.transform = 'translateX(-50%) scale(1)';
                plane.style.color = '#ffffff';
            }
        }
        
        // ==================== تحديث العداد ====================
        function updateTimer(seconds) {
            const minutes = Math.floor(seconds / 60);
            const secs = seconds % 60;
            const timerText = `${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
            
            document.getElementById('timer').textContent = timerText;
            
            // تغيير اللون حسب الوقت
            const timerElement = document.getElementById('timer');
            if (seconds <= 10) {
                timerElement.style.color = '#ff416c';
                timerElement.style.textShadow = '0 0 15px #ff416c';
            } else if (seconds <= 30) {
                timerElement.style.color = '#ffd700';
                timerElement.style.textShadow = '0 0 10px #ffd700';
            } else {
                timerElement.style.color = '#00ff88';
                timerElement.style.textShadow = '0 0 10px #00ff88';
            }
        }
        
        // ==================== تحديث أزرار التحكم ====================
        function updateBetButton() {
            const canBet = roundStatus === 'betting' && selectedAmount > 0 && !isPlaying;
            const btnBet = document.getElementById('btn-bet');
            btnBet.disabled = !canBet;
            
            if (canBet) {
                btnBet.innerHTML = `<span>🎯</span> وضع رهان (${selectedAmount})`;
            } else {
                btnBet.innerHTML = `<span>🎯</span> وضع الرهان`;
            }
        }
        
        function updateCashoutButton() {
            const canCashout = isPlaying && roundStatus === 'counting' && currentMultiplier >= 1.1;
            const btnCashout = document.getElementById('btn-cashout');
            btnCashout.disabled = !canCashout;
            
            if (canCashout && currentBet) {
                const potentialWin = Math.floor(currentBet * currentMultiplier);
                btnCashout.innerHTML = `<span>💰</span> صرف (${potentialWin})`;
            } else {
                btnCashout.innerHTML = `<span>💰</span> صرف الآن`;
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
            
            if (roundStatus !== 'betting') {
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
                
                // إعادة تعيين أعلى مضاعف
                maxMultiplier = 1.0;
                
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
            
            const winAmount = Math.floor(currentBet * currentMultiplier);
            
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
                
                showMessage(`🎉 تم الصرف! ربحت ${winAmount} نقطة (${currentMultiplier.toFixed(2)}x)`, 'success');
                
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
        
        // ==================== عرض الرسائل ====================
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
                refreshRoundInfo();
                if (roundStatus === 'counting') {
                    refreshMultiplier();
                }
            }, 1000);
            
            // تحديث الرصيد كل 10 ثواني
            setInterval(() => {
                refreshBalance();
            }, 10000);
            
            // تحديث المضاعف أثناء الجولة كل 500 مللي ثانية
            if (multiplierInterval) clearInterval(multiplierInterval);
            multiplierInterval = setInterval(() => {
                if (roundStatus === 'counting') {
                    refreshMultiplier();
                }
            }, 500);
        }
        
        // ==================== إعداد مستمعي الأحداث ====================
        function setupEventListeners() {
            // تحديث الصفحة عند العودة
            window.addEventListener('focus', refreshAllData);
            
            // تحذير عند مغادرة الصفحة أثناء اللعب
            window.addEventListener('beforeunload', (e) => {
                if (isPlaying) {
                    e.preventDefault();
                    e.returnValue = 'لديك رهان نشط! إذا غادرت قد تخسره.';
                }
            });
            
            // تأثيرات Hover
            document.querySelectorAll('.bet-btn, .action-btn').forEach(btn => {
                btn.addEventListener('mouseenter', function() {
                    if (!this.disabled) {
                        this.style.transform = 'translateY(-3px)';
                    }
                });
                
                btn.addEventListener('mouseleave', function() {
                    this.style.transform = 'translateY(0)';
                });
            });
        }
        
        // ==================== بدء التشغيل ====================
        window.onload = function() {
            initPage();
            showMessage('🚀 أهلاً بك في Aviator Pro! اختر مبلغ الرهان للبدء.', 'info');
        };
    </script>
</body>
</html>
'''

# ==================== التحقق من الإعدادات ====================
def validate_config():
    """التحقق من صحة الإعدادات"""
    print("🎮 التحقق من إعدادات لعبة Aviator")
    print("=" * 50)
    
    errors = []
    warnings = []
    
    # التحقق من BOT_TOKEN
    if not BOT_TOKEN:
        errors.append("❌ BOT_TOKEN غير معين")
        print("❌ خطأ: BOT_TOKEN غير موجود")
    elif len(BOT_TOKEN) < 30:
        warnings.append("⚠️ BOT_TOKEN قد يكون غير صالح")
        print(f"⚠️ تحذير: BOT_TOKEN قصير")
    else:
        print(f"✅ BOT_TOKEN: {BOT_TOKEN[:15]}...")
    
    # التحقق من ADMIN_ID
    if not ADMIN_ID_STR:
        errors.append("❌ ADMIN_ID غير معين")
        print("❌ خطأ: ADMIN_ID غير موجود")
    elif not ADMIN_ID_STR.isdigit():
        errors.append("❌ ADMIN_ID يجب أن يكون رقم")
        print("❌ خطأ: ADMIN_ID يجب أن يكون رقم")
    else:
        admin_id_int = int(ADMIN_ID_STR)
        if admin_id_int == 123456789:
            warnings.append("⚠️ ADMIN_ID لا يزال بالقيمة الافتراضية")
            print(f"⚠️ تحذير: ADMIN_ID: {admin_id_int} (افتراضي)")
        else:
            print(f"✅ ADMIN_ID: {admin_id_int}")
    
    # التحقق من BASE_URL
    if not BASE_URL:
        errors.append("❌ BASE_URL غير معين")
        print("❌ خطأ: BASE_URL غير موجود")
    else:
        print(f"✅ BASE_URL: {BASE_URL}")
    
    # إعدادات اللعبة
    print(f"🎮 ROUND_DURATION: {ROUND_DURATION} ثانية")
    print(f"🎮 BETTING_DURATION: {BETTING_DURATION} ثانية")
    print(f"🎮 BET_OPTIONS: {BET_OPTIONS}")
    print(f"🎮 مضاعفات: من {MIN_MULTIPLIER}x إلى {MAX_MULTIPLIER}x")
    print(f"🌐 PORT: {PORT}")
    
    # عرض التحذيرات
    if warnings:
        print("\n⚠️ التحذيرات:")
        for warning in warnings:
            print(f"   {warning}")
    
    # عرض الأخطاء
    if errors:
        print("\n❌ الأخطاء:")
        for error in errors:
            print(f"   {error}")
        print("\n🔧 يجب إصلاح هذه الأخطاء قبل التشغيل!")
        print("=" * 50)
        return False
    
    print("\n✅ جميع الإعدادات صالحة")
    print("=" * 50)
    return True

if __name__ == "__main__":
    validate_config()