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
import pytz

# --- إعداد المتغيرات البيئية ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')

# --- إعداد Flask لإبقاء البوت نشطاً ---
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "✅ Bot is running and alive!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask).start()

def keep_alive_ping():
    while True:
        try:
            # تأكد من تغيير الرابط ليتوافق مع رابط خدمتك على Render
            # مثال: https://your-app-name.onrender.com
            requests.get("https://mahiroshina.onrender.com") 
            print("✅ Sent keep-alive ping to Render")
        except Exception as e:
            print(f"⚠️ Ping failed: {e}")
        time.sleep(240)  # كل 4 دقائق

threading.Thread(target=keep_alive_ping, daemon=True).start()

# --- إعداد التسجيل (Logging) ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- إعداد الذكاء الاصطناعي (شخصية ماهيرو) ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

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

# --- البيانات الثابتة (صور، أغاني، رسائل) ---
MAHIRU_IMAGES = [
    "https://i.imgur.com/K8J9X2M.jpg", "https://i.imgur.com/L3M4N5P.jpg", 
    "https://i.imgur.com/Q6R7S8T.jpg", "https://i.imgur.com/U9V0W1X.jpg",
    "https://i.imgur.com/Y2Z3A4B.jpg", "https://i.imgur.com/C5D6E7F.jpg",
    "https://i.imgur.com/G8H9I0J.jpg", "https://i.imgur.com/K1L2M3N.jpg"
]
SONGS_DATABASE = {
    "believer": {"url": "https://www.youtube.com/watch?v=7wtfhZwyrcc", "audio": "https://www.soundjay.com/misc/sounds/bell-ringing-05.wav"},
    "imagine dragons": {"url": "https://www.youtube.com/watch?v=7wtfhZwyrcc", "audio": "https://www.soundjay.com/misc/sounds/bell-ringing-05.wav"},
    "shape of you": {"url": "https://www.youtube.com/watch?v=JGwWNGJdvx8", "audio": "https://www.soundjay.com/misc/sounds/bell-ringing-05.wav"},
}
RANDOM_MESSAGES = [
    "{user_name}، هل تذكرت أن تشرب الماء اليوم؟ 💧", "أفكر فيك، {user_name}. أتمنى أن تكون سعيداً! 😊",
    "هل تريد أن أحضر لك بعض الطعام، {user_name}؟ 🍱", "{user_name}، لا تنسَ أن تأخذ استراحة 💕",
    "أتمنى أن يكون يومك جميلاً، {user_name} 🌸", "هل تحتاج شيئاً، {user_name}؟ أنا هنا من أجلك 💖",
]

# --- إدارة بيانات المستخدمين والإحصائيات ---
USER_DATA_FILE = "user_data.json"
BOT_STATS_FILE = "bot_stats.json"

def load_json_file(filename, default_data):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default_data

def save_json_file(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

user_data = load_json_file(USER_DATA_FILE, {})
bot_stats = load_json_file(BOT_STATS_FILE, {"total_users": len(user_data), "total_messages": 0, "total_commands": 0})

def update_bot_stats(stat_type):
    global bot_stats
    if stat_type == "message":
        bot_stats["total_messages"] += 1
    elif stat_type == "command":
        bot_stats["total_commands"] += 1
    save_json_file(BOT_STATS_FILE, bot_stats)

# --- دوال مساعدة خاصة ببيانات المستخدم ---
def get_user_name(user_id):
    return user_data.get(str(user_id), {}).get('name', 'فوجيميا-سان')

def get_user_playlist(user_id):
    return user_data.get(str(user_id), {}).get('playlist', [])

def add_song_to_playlist(user_id, song):
    user_id_str = str(user_id)
    user_data.setdefault(user_id_str, {}).setdefault('playlist', []).append(song)
    save_json_file(USER_DATA_FILE, user_data)

def get_user_timezone(user_id):
    return user_data.get(str(user_id), {}).get('timezone', 'Asia/Riyadh')

def set_user_timezone(user_id, timezone):
    user_id_str = str(user_id)
    user_data.setdefault(user_id_str, {})['timezone'] = timezone
    save_json_file(USER_DATA_FILE, user_data)

# --- دوال إنشاء لوحات المفاتيح (Keyboards) ---
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
        [InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_music_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎵 عرض قائمتي", callback_data="show_playlist")],
        [InlineKeyboardButton("🎧 أغنية عشوائية", callback_data="random_song")],
        [InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_reminders_keyboard():
    keyboard = [
        [InlineKeyboardButton("🍱 تذكير طعام", callback_data="food_reminder"), InlineKeyboardButton("😴 تذكير نوم", callback_data="sleep_reminder")],
        [InlineKeyboardButton("💧 تذكير ماء", callback_data="water_reminder"), InlineKeyboardButton("🏃‍♂️ تذكير رياضة", callback_data="exercise_reminder")],
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

# --- معالجات الأوامر والرسائل الأساسية ---
async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    user_id = str(user.id)
    update_bot_stats("command")

    if user_id not in user_data:
        bot_stats["total_users"] += 1
        user_data[user_id] = {'waiting_for_name': True}
        save_json_file(USER_DATA_FILE, user_data)
        save_json_file(BOT_STATS_FILE, bot_stats)
        
        welcome_text = "🌸 مرحباً! أنا ماهيرو شينا!\n\nهذه هي المرة الأولى التي نتقابل فيها...\nما الاسم الذي تريدني أن أناديك به؟\n\nاكتب اسمك في الرسالة التالية من فضلك! 💕"
        await update.message.reply_text(welcome_text)
        return

    user_name = get_user_name(user_id)
    welcome_text = f"🌸 مرحباً بعودتك، {user_name}!\n\nأنا سعيدة جداً برؤيتك! 💕\nكيف حالك اليوم؟ هل تناولت طعامك؟ 🍱"
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())

async def handle_message(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    user_message = update.message.text
    update_bot_stats("message")

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
            save_json_file(USER_DATA_FILE, user_data)

            response = f"🌸 أهلاً وسهلاً، {name}!\n\nاسم جميل جداً! 💕\nمن الآن سأناديك {name}.\nأتمنى أن نصبح أصدقاء مقربين!\nهيا لنبدأ! يمكنك استخدام الأزرار أدناه 👇"
            await update.message.reply_text(response, reply_markup=get_main_keyboard())
            return
        except Exception as e:
            logger.error(f"Error while saving new user name for {user_id}: {e}")
            await update.message.reply_text("💔 عذراً، حدث خطأ ما أثناء حفظ اسمك. هل يمكنك المحاولة مرة أخرى؟")
            return

    user_name = get_user_name(user_id)
    
    # التعامل مع الرسائل العادية باستخدام الذكاء الاصطناعي
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        prompt = SYSTEM_INSTRUCTION.format(user_name=user_name) + f"\n\n{user_name} يقول: {user_message}"
        response = model.generate_content(prompt)
        await update.message.reply_text(f"💕 {response.text}")
    except Exception as e:
        logger.error(f"Error in Gemini API call: {e}")
        await update.message.reply_text(f"💔 آسفة {user_name}، حدث خطأ. هل يمكنك المحاولة مرة أخرى؟ 😔")

# --- معالج الأزرار (CallbackQueryHandler) ---
async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    user_name = get_user_name(user_id)
    data = query.data

    # القائمة الرئيسية
    if data == "back_to_main":
        await query.edit_message_text(f"🌸 أهلاً بعودتك {user_name}! ماذا تريد أن نفعل الآن؟", reply_markup=get_main_keyboard())
    elif data == "get_image":
        await send_mahiru_image(query, context)
    elif data == "random_message":
        message = random.choice(RANDOM_MESSAGES).format(user_name=user_name)
        await query.edit_message_text(f"💭 رسالة خاصة لك!\n\n{message}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]]))
    
    # القوائم الفرعية
    elif data == "games_menu":
        await query.edit_message_text(f"🎮 اختر لعبتك المفضلة، {user_name}!", reply_markup=get_games_keyboard())
    elif data == "music_menu":
        await query.edit_message_text(f"🎶 أهلاً بك في عالم الموسيقى، {user_name}!", reply_markup=get_music_keyboard())
    elif data == "reminders_menu":
        await query.edit_message_text(f"⏰ {user_name}، أريد أن أعتني بك! اختر تذكيراً.", reply_markup=get_reminders_keyboard())
    elif data == "settings_menu":
        await query.edit_message_text(f"⚙️ إعدادات البوت. المنطقة الزمنية الحالية: {get_user_timezone(user_id)}", reply_markup=get_settings_keyboard())

    # الإحصائيات والطقس
    elif data == "bot_stats":
        stats_text = f"""📊 إحصائيات البوت 📊
        👥 إجمالي المستخدمين: {bot_stats["total_users"]}
        💬 إجمالي الرسائل: {bot_stats["total_messages"]}
        🎯 إجمالي الأوامر: {bot_stats["total_commands"]}"""
        await query.edit_message_text(stats_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]]))
    elif data == "weather_info":
        await show_weather_info(query, context)

    # دوال الموسيقى
    elif data == "show_playlist":
        playlist = get_user_playlist(user_id)
        if not playlist:
            message = f"🎵 قائمة التشغيل فارغة يا {user_name}."
        else:
            message = f"🎶 قائمة {user_name} الموسيقية:\n" + "\n".join([f"{i+1}. {song}" for i, song in enumerate(playlist)])
        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 عودة", callback_data="music_menu")]]))
    elif data == "random_song":
        song_key = random.choice(list(SONGS_DATABASE.keys()))
        song_data = SONGS_DATABASE[song_key]
        add_song_to_playlist(user_id, song_key)
        await query.edit_message_text(f"🎧 اخترت لك: {song_key}\n🔗 {song_data['url']}", reply_markup=get_music_keyboard())

    # دوال الألعاب
    elif data == "game_dice":
        result = random.randint(1, 6)
        await query.edit_message_text(f"🎲 لقد رميت النرد والنتيجة هي: {result}", reply_markup=get_games_keyboard())

# --- دوال مساعدة لمعالج الأزرار ---
async def send_mahiru_image(query, context):
    user_name = get_user_name(query.from_user.id)
    try:
        image_url = random.choice(MAHIRU_IMAGES)
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=image_url,
            caption=f"🌸 هذه صورتي، {user_name}!\nأتمنى أن تعجبك! 💕"
        )
    except Exception as e:
        logger.error(f"Failed to send photo: {e}")
        await query.message.reply_text(f"💔 آسفة {user_name}، لا أستطيع إرسال الصورة الآن.")

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

        weather_text = f"مرحباً {user_name}! 💕\n\n📅 {current_date}\n🕐 {current_time} ({day_arabic})\n🌍 المنطقة الزمنية: {user_timezone_str}"
        
    except pytz.UnknownTimeZoneError:
        weather_text = f"💔 آسفة {user_name}، المنطقة الزمنية '{user_timezone_str}' غير معروفة."
    except Exception as e:
        logger.error(f"Error in show_weather_info: {e}")
        weather_text = "💔 حدث خطأ ما، أرجو المحاولة لاحقاً."

    await query.edit_message_text(weather_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]]))

# --- تشغيل البوت ---
def main():
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN is not set!")
        return
        
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # إضافة المعالجات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🌸 بوت ماهيرو يعمل الآن!")
    app.run_polling()

if __name__ == '__main__':
    main()
