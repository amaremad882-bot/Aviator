import os
import sys
from dotenv import load_dotenv

# تحميل متغيرات البيئة
load_dotenv()

# ==================== إعدادات البوت ====================
BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
ADMIN_ID_STR = os.getenv('ADMIN_ID', '').strip()

BASE_URL = "https://aviator-production-e666.up.railway.app"
# ==================== إعدادات Railway ====================
RAILWAY_PUBLIC_DOMAIN = os.getenv('RAILWAY_PUBLIC_DOMAIN', '').strip()
RAILWAY_STATIC_URL = os.getenv('RAILWAY_STATIC_URL', '').strip()

# تحديد الرابط الأساسي
if RAILWAY_STATIC_URL:
    BASE_URL = RAILWAY_STATIC_URL
elif RAILWAY_PUBLIC_DOMAIN:
    BASE_URL = f"https://{RAILWAY_PUBLIC_DOMAIN}"
else:
    BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000').strip()

# ==================== إعدادات اللعبة ====================
PORT = int(os.getenv('PORT', '8000'))
ROUND_DURATION = 60
BETTING_DURATION = 30
BET_OPTIONS = [10, 50, 100, 500, 1000, 5000]
MIN_MULTIPLIER = 1.0
MAX_MULTIPLIER = 10.0

# تحويل ADMIN_ID لرقم
try:
    ADMIN_ID = int(ADMIN_ID_STR) if ADMIN_ID_STR else 0
except ValueError:
    ADMIN_ID = 0

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