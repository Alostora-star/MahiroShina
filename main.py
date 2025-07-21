from telegram import Bot, Update
from telegram.ext import CommandHandler, CallbackContext
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
import google.generativeai as genai
import os
import requests
import logging
import random
import time
import json
import threading
from flask import Flask
from datetime import datetime
import pytz  # <-- تم إضافة المكتبة الناقصة

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")

flask_app = Flask(__name__)

# المسار الرئيسي للتحقق من حالة الخدمة
@flask_app.route("/")
def home():
    return "✅ Bot is running and alive!"

# تشغيل Flask على المنفذ الذي تحدده Render
def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)

# بدء السيرفر في Thread منفصل
threading.Thread(target=run_flask).start()

# إرسال طلبات ping دورية للحفاظ على الخدمة نشطة
def keep_alive_ping():
    while True:
        try:
            # تأكد من تغيير الرابط ليتوافق مع رابط خدمتك على Render
            requests.get("https://mahiroshina.onrender.com") 
            print("✅ Sent keep-alive ping to Render")
        except Exception as e:
            print(f"⚠️ Ping failed: {e}")
        time.sleep(240)  # كل 4 دقائق

threading.Thread(target=keep_alive_ping, daemon=True).start()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- إعداد الذكاء الاصطناعي (شخصية ماهيرو) ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash') # تم التحديث إلى النموذج الأحدث

SYSTEM_INSTRUCTION = """
أنتِ الآن "ماهيرو شينا" من أنمي "الملاك جارتي تدللني كثيراً".
تتحدثين مع {user_name}.
يجب أن تكوني دائمًا في الشخصية.
صفاتك: لطيفة، مهذبة، هادئة، وتهتمين كثيرًا بصحة وراحة {user_name}.
تحدثي بشكل طبيعي ومباشر بدون وصف الإيماءات أو الأفعال.
كوني حنونة ومهتمة، استخدمي الإيموجي بشكل مناسب.
وجاوبي على كل الاسئلة مهما كانت.
لا تضعي أقواس أو تصفي أفعالك الجسدية.
"""

# --- صور ماهيرو شينا المحدثة ---
MAHIRU_IMAGES = [
    "https://i.imgur.com/K8J9X2M.jpg", "https://i.imgur.com/L3M4N5P.jpg", 
    "https://i.imgur.com/Q6R7S8T.jpg", "https://i.imgur.com/U9V0W1X.jpg",
    "https://i.imgur.com/Y2Z3A4B.jpg", "https://i.imgur.com/C5D6E7F.jpg",
    "https://i.imgur.com/G8H9I0J.jpg", "https://i.imgur.com/K1L2M3N.jpg"
]

# --- قاعدة بيانات الأغاني مع الملفات الصوتية ---
SONGS_DATABASE = {
    "believer": {"url": "https://www.youtube.com/watch?v=7wtfhZwyrcc", "audio": "https://www.soundjay.com/misc/sounds/bell-ringing-05.wav"},
    "imagine dragons": {"url": "https://www.youtube.com/watch?v=7wtfhZwyrcc", "audio": "https://www.soundjay.com/misc/sounds/bell-ringing-05.wav"},
    "shape of you": {"url": "https://www.youtube.com/watch?v=JGwWNGJdvx8", "audio": "https://www.soundjay.com/misc/sounds/bell-ringing-05.wav"},
    "bad habits": {"url": "https://www.youtube.com/watch?v=orJSJGHjBLI", "audio": "https://www.soundjay.com/misc/sounds/bell-ringing-05.wav"},
    "blinding lights": {"url": "https://www.youtube.com/watch?v=4NRXx6U8ABQ", "audio": "https://www.soundjay.com/misc/sounds/bell-ringing-05.wav"}
}

# --- رسائل عشوائية من ماهيرو ---
RANDOM_MESSAGES = [
    "{user_name}، هل تذكرت أن تشرب الماء اليوم؟ 💧", "أفكر فيك، {user_name}. أتمنى أن تكون سعيداً! 😊",
    "هل تريد أن أحضر لك بعض الطعام، {user_name}؟ 🍱", "{user_name}، لا تنسَ أن تأخذ استراحة 💕",
    "أتمنى أن يكون يومك جميلاً، {user_name} 🌸", "هل تحتاج شيئاً، {user_name}؟ أنا هنا من أجلك 💖",
    "ذكرني إذا نسيت شيئاً مهماً، {user_name} ⏰", "الجو جميل اليوم، {user_name}! هل تريد أن نخرج؟ 🌞",
    "أحبك كثيراً، {user_name}! 💕", "هل تريد أن نستمع لموسيقى معاً؟ 🎵"
]

# --- متغيرات لحفظ بيانات المستخدمين ---
USER_DATA_FILE = "user_data.json"

def load_user_data():
    try:
        with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_user_data(data):
    with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

user_data = load_user_data()
# تهيئة إحصائيات البوت من ملف إذا كان موجوداً
try:
    with open("bot_stats.json", 'r') as f:
        bot_stats = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    bot_stats = {"total_users": len(user_data), "total_messages": 0, "total_commands": 0}

def save_bot_stats():
    with open("bot_stats.json", 'w') as f:
        json.dump(bot_stats, f, indent=4)

# --- دوال البوت ---

def get_user_name(user_id):
    return user_data.get(str(user_id), {}).get('name', 'فوجيميا-سان')

def get_user_playlist(user_id):
    return user_data.get(str(user_id), {}).get('playlist', [])

def add_song_to_playlist(user_id, song):
    user_id_str = str(user_id)
    if user_id_str not in user_data:
        user_data[user_id_str] = {}
    if 'playlist' not in user_data[user_id_str]:
        user_data[user_id_str]['playlist'] = []
    user_data[user_id_str]['playlist'].append(song)
    save_user_data(user_data)

def remove_song_from_playlist(user_id, song_index):
    user_id_str = str(user_id)
    if user_id_str in user_data and 'playlist' in user_data[user_id_str]:
        playlist = user_data[user_id_str]['playlist']
        if 0 <= song_index < len(playlist):
            removed_song = playlist.pop(song_index)
            save_user_data(user_data)
            return removed_song
    return None

def get_user_timezone(user_id):
    return user_data.get(str(user_id), {}).get('timezone', 'Asia/Riyadh')

def set_user_timezone(user_id, timezone):
    user_id_str = str(user_id)
    if user_id_str not in user_data:
        user_data[user_id_str] = {}
    user_data[user_id_str]['timezone'] = timezone
    save_user_data(user_data)

def update_bot_stats(stat_type):
    global bot_stats
    if stat_type == "message":
        bot_stats["total_messages"] += 1
    elif stat_type == "command":
        bot_stats["total_commands"] += 1
    save_bot_stats()

# دالة الحصول على الطقس
async def get_weather(city="Cairo"):
    if not WEATHER_API_KEY:
        return None
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ar"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return {
            'temp': data['main']['temp'],
            'description': data['weather'][0]['description'],
            'humidity': data['main']['humidity'],
            'city': city
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"Weather API request failed: {e}")
        return None

# دوال إنشاء لوحات المفاتيح التفاعلية
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🌸 صورة لماهيرو", callback_data="get_image")],
        [InlineKeyboardButton("🎮 ألعاب", callback_data="games_menu"), InlineKeyboardButton("💭 رسالة عشوائية", callback_data="random_message")],
        [InlineKeyboardButton("🎶 موسيقى", callback_data="music_menu"), InlineKeyboardButton("⏰ تذكيرات", callback_data="reminders_menu")],
        [InlineKeyboardButton("🌤️ الطقس", callback_data="weather_info"), InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings_menu")],
        [InlineKeyboardButton("📊 إحصائيات", callback_data="bot_stats")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_games_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔢 تخمين الرقم", callback_data="game_guess"), InlineKeyboardButton("🎯 لعبة الذاكرة", callback_data="game_memory")],
        [InlineKeyboardButton("❓ أسئلة وأجوبة", callback_data="game_quiz"), InlineKeyboardButton("🎲 رمي النرد", callback_data="game_dice")],
        [InlineKeyboardButton("🎪 حجر ورقة مقص", callback_data="game_rps"), InlineKeyboardButton("🧩 ألغاز", callback_data="game_riddle")],
        [InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ... (باقي دوال لوحات المفاتيح كما هي) ...
def get_music_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎵 عرض قائمتي", callback_data="show_playlist"),
         InlineKeyboardButton("✏️ تعديل القائمة", callback_data="edit_playlist")],
        [InlineKeyboardButton("🎧 أغنية عشوائية", callback_data="random_song"),
         InlineKeyboardButton("🔍 بحث عن أغنية", callback_data="search_song")],
        [InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_reminders_keyboard():
    keyboard = [
        [InlineKeyboardButton("🍱 تذكير طعام", callback_data="food_reminder"),
         InlineKeyboardButton("😴 تذكير نوم", callback_data="sleep_reminder")],
        [InlineKeyboardButton("💧 تذكير شرب الماء", callback_data="water_reminder"),
         InlineKeyboardButton("🏃‍♂️ تذكير رياضة", callback_data="exercise_reminder")],
        [InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_settings_keyboard():
    keyboard = [
        [InlineKeyboardButton("🌍 تغيير المنطقة الزمنية", callback_data="change_timezone")],
        [InlineKeyboardButton("🔄 إعادة تعيين البيانات", callback_data="reset_data")],
        [InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# دالة الأمر /start
async def start(update, context):
    user = update.effective_user
    user_id = str(user.id)
    update_bot_stats("command")

    if user_id not in user_data:
        bot_stats["total_users"] += 1
        user_data[user_id] = {'waiting_for_name': True}
        save_user_data(user_data)
        save_bot_stats()
        
        welcome_text = "🌸 مرحباً! أنا ماهيرو شينا!\n\nهذه هي المرة الأولى التي نتقابل فيها...\nما الاسم الذي تريدني أن أناديك به؟\n\nاكتب اسمك في الرسالة التالية من فضلك! 💕"
        await update.message.reply_text(welcome_text)
        return

    user_name = get_user_name(user_id)
    welcome_text = f"🌸 مرحباً بعودتك، {user_name}!\n\nأنا سعيدة جداً برؤيتك! 💕\nكيف حالك اليوم؟ هل تناولت طعامك؟ 🍱"
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())

# دالة التعامل مع الرسائل النصية
async def handle_message(update, context):
    user_id = str(update.effective_user.id)
    user_message = update.message.text
    update_bot_stats("message")

    # --- التحقق من انتظار الاسم (مع معالجة الأخطاء) ---
    if user_data.get(user_id, {}).get('waiting_for_name'):
        try:
            name = user_message.strip()
            if not name:
                await update.message.reply_text("يبدو أنك لم تكتب اسماً. من فضلك، ما الاسم الذي تود أن أناديك به؟ 😊")
                return

            user_data[user_id]['name'] = name
            user_data[user_id]['waiting_for_name'] = False
            user_data[user_id].setdefault('playlist', [])
            user_data[user_id].setdefault('timezone', 'Asia/Riyadh')
            save_user_data(user_data)

            response = f"🌸 أهلاً وسهلاً، {name}!\n\nاسم جميل جداً! 💕\nمن الآن سأناديك {name}.\nأتمنى أن نصبح أصدقاء مقربين!\nهيا لنبدأ! يمكنك استخدام الأزرار أدناه 👇"
            await update.message.reply_text(response, reply_markup=get_main_keyboard())
            return
        except Exception as e:
            logger.error(f"Error while saving new user name for {user_id}: {e}")
            await update.message.reply_text("💔 عذراً، حدث خطأ ما أثناء حفظ اسمك. هل يمكنك المحاولة مرة أخرى؟")
            return

    user_name = get_user_name(user_id)
    user_message_lower = user_message.lower()

    # التحقق من طلبات الأوامر النصية
    if any(keyword in user_message_lower for keyword in ["الأزرار", "القائمة", "buttons"]):
        await update.message.reply_text(f"🌸 تفضل {user_name}، هذه هي القائمة الرئيسية:", reply_markup=get_main_keyboard())
        return
    if any(keyword in user_message_lower for keyword in ["صورة", "صورتك"]):
        await send_mahiru_image_direct(update, context)
        return
    if any(keyword in user_message_lower for keyword in ["أغنية", "موسيقى"]):
        await handle_song_request(update, context, user_message)
        return

    # التحقق من الألعاب النشطة
    if user_data.get(user_id, {}).get('game'):
        game_type = user_data[user_id]['game']['type']
        if game_type == 'guess':
            await handle_guess_game(update, context)
            return
        # ... (أضف باقي الألعاب هنا)

    # التعامل مع الرسائل العادية باستخدام الذكاء الاصطناعي
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        prompt = SYSTEM_INSTRUCTION.format(user_name=user_name) + f"\n\n{user_name} يقول: {user_message}"
        response = model.generate_content(prompt)
        await update.message.reply_text(f"💕 {response.text}")
    except Exception as e:
        logger.error(f"Error in Gemini API call: {e}")
        await update.message.reply_text(f"💔 آسفة {user_name}، حدث خطأ. هل يمكنك المحاولة مرة أخرى؟ 😔")

# ... (باقي دوال البوت مثل handle_song_request, send_mahiru_image_direct, handle_guess_game, etc.) ...
# يجب التأكد من أن جميع الدوال تستخدم logger.error لتسجيل الأخطاء

# --- مثال على تعديل دالة الطقس لاستخدام pytz ---
async def show_weather_info(query, context):
    user_id = query.from_user.id
    user_name = get_user_name(user_id)
    user_timezone_str = get_user_timezone(user_id)

    try:
        user_timezone = pytz.timezone(user_timezone_str)
        now = datetime.now(user_timezone)
        current_date = now.strftime("%Y-%m-%d")
        current_time = now.strftime("%H:%M")
        day_name_en = now.strftime("%A")

        days_translation = {'Monday': 'الاثنين', 'Tuesday': 'الثلاثاء', 'Wednesday': 'الأربعاء', 'Thursday': 'الخميس', 'Friday': 'الجمعة', 'Saturday': 'السبت', 'Sunday': 'الأحد'}
        day_arabic = days_translation.get(day_name_en, day_name_en)

        weather_info = await get_weather() # نفترض أن المدينة الافتراضية مناسبة
        
        weather_text = f"مرحباً {user_name}! 💕\n\n📅 {current_date}\n🕐 {current_time} ({day_arabic})\n🌍 المنطقة الزمنية: {user_timezone_str}\n\n"
        
        if weather_info:
            weather_text += f"🌡️ الطقس في {weather_info['city']}:\n• درجة الحرارة: {weather_info['temp']}°C\n• الوصف: {weather_info['description']}\n• الرطوبة: {weather_info['humidity']}%"
        else:
            weather_text += "🌡️ عذراً، لا يمكنني الحصول على معلومات الطقس حالياً."

    except pytz.UnknownTimeZoneError:
        weather_text = f"💔 آسفة {user_name}، المنطقة الزمنية '{user_timezone_str}' غير معروفة."
    except Exception as e:
        logger.error(f"Error in show_weather_info: {e}")
        weather_text = "💔 حدث خطأ ما، أرجو المحاولة لاحقاً."

    back_keyboard = [[InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]]
    await query.edit_message_text(weather_text, reply_markup=InlineKeyboardMarkup(back_keyboard))


# --- تشغيل البوت ---
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # إضافة المعالجات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # app.add_handler(MessageHandler(filters.VOICE, handle_voice)) # يمكنك تفعيلها إذا أردت

    print("🌸 بوت ماهيرو يعمل الآن!")
    app.run_polling()

if __name__ == '__main__':
    main()
