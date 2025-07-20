from telegram import Bot, Update
from telegram.ext import CommandHandler, CallbackContext
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
import google.generativeai as genai
import os
import requests
import random
import time
import json
from flask import Flask
from datetime import datetime # <- This line has been corrected
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
    port = int(os.environ.get("PORT", 5000))  # ضروري استخدام المتغير البيئي PORT
    flask_app.run(host="0.0.0.0", port=port)

# بدء السيرفر في Thread منفصل
threading.Thread(target=run_flask).start()

# إرسال طلبات ping دورية للحفاظ على الخدمة نشطة
def keep_alive_ping():
    while True:
        try:
            requests.get("https://mahiroshina.onrender.com")  # غيّر الرابط حسب نطاق موقعك
            print("✅ Sent keep-alive ping to Render")
        except Exception as e:
            print(f"⚠️ Ping failed: {e}")
        time.sleep(300)  # كل 5 دقائق

threading.Thread(target=keep_alive_ping, daemon=True).start()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- إعداد الذكاء الاصطناعي (شخصية ماهيرو) ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

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
    "https://i.imgur.com/K8J9X2M.jpg",
    "https://i.imgur.com/L3M4N5P.jpg", 
    "https://i.imgur.com/Q6R7S8T.jpg",
    "https://i.imgur.com/U9V0W1X.jpg",
    "https://i.imgur.com/Y2Z3A4B.jpg",
    "https://i.imgur.com/C5D6E7F.jpg",
    "https://i.imgur.com/G8H9I0J.jpg",
    "https://i.imgur.com/K1L2M3N.jpg"
]

# --- قاعدة بيانات الأغاني مع الملفات الصوتية ---
SONGS_DATABASE = {
    "believer": {
        "url": "https://www.youtube.com/watch?v=7wtfhZwyrcc",
        "audio": "https://www.soundjay.com/misc/sounds/bell-ringing-05.wav"
    },
    "imagine dragons": {
        "url": "https://www.youtube.com/watch?v=7wtfhZwyrcc", 
        "audio": "https://www.soundjay.com/misc/sounds/bell-ringing-05.wav"
    },
    "shape of you": {
        "url": "https://www.youtube.com/watch?v=JGwWNGJdvx8",
        "audio": "https://www.soundjay.com/misc/sounds/bell-ringing-05.wav"
    },
    "bad habits": {
        "url": "https://www.youtube.com/watch?v=orJSJGHjBLI",
        "audio": "https://www.soundjay.com/misc/sounds/bell-ringing-05.wav"
    },
    "blinding lights": {
        "url": "https://www.youtube.com/watch?v=4NRXx6U8ABQ",
        "audio": "https://www.soundjay.com/misc/sounds/bell-ringing-05.wav"
    }
}

# --- رسائل عشوائية من ماهيرو ---
RANDOM_MESSAGES = [
    "{user_name}، هل تذكرت أن تشرب الماء اليوم؟ 💧",
    "أفكر فيك، {user_name}. أتمنى أن تكون سعيداً! 😊",
    "هل تريد أن أحضر لك بعض الطعام، {user_name}؟ 🍱",
    "{user_name}، لا تنسَ أن تأخذ استراحة 💕",
    "أتمنى أن يكون يومك جميلاً، {user_name} 🌸",
    "هل تحتاج شيئاً، {user_name}؟ أنا هنا من أجلك 💖",
    "ذكرني إذا نسيت شيئاً مهماً، {user_name} ⏰",
    "الجو جميل اليوم، {user_name}! هل تريد أن نخرج؟ 🌞",
    "أحبك كثيراً، {user_name}! 💕",
    "هل تريد أن نستمع لموسيقى معاً؟ 🎵"
]

# --- متغيرات لحفظ بيانات المستخدمين ---
USER_DATA_FILE = "user_data.json"

def load_user_data():
    try:
        with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_user_data(data):
    with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

user_data = load_user_data()
bot_stats = {"total_users": 0, "total_messages": 0, "total_commands": 0}

# --- دوال البوت ---

def get_user_name(user_id):
    return user_data.get(str(user_id), {}).get('name', 'فوجيميا-سان')

def get_user_playlist(user_id):
    return user_data.get(str(user_id), {}).get('playlist', [])

def add_song_to_playlist(user_id, song):
    if str(user_id) not in user_data:
        user_data[str(user_id)] = {}
    if 'playlist' not in user_data[str(user_id)]:
        user_data[str(user_id)]['playlist'] = []
    user_data[str(user_id)]['playlist'].append(song)
    save_user_data(user_data)

def remove_song_from_playlist(user_id, song_index):
    if str(user_id) in user_data and 'playlist' in user_data[str(user_id)]:
        playlist = user_data[str(user_id)]['playlist']
        if 0 <= song_index < len(playlist):
            removed_song = playlist.pop(song_index)
            save_user_data(user_data)
            return removed_song
    return None

def get_user_timezone(user_id):
    return user_data.get(str(user_id), {}).get('timezone', 'Asia/Riyadh')

def set_user_timezone(user_id, timezone):
    if str(user_id) not in user_data:
        user_data[str(user_id)] = {}
    user_data[str(user_id)]['timezone'] = timezone
    save_user_data(user_data)

def update_bot_stats(stat_type):
    global bot_stats
    if stat_type == "message":
        bot_stats["total_messages"] += 1
    elif stat_type == "command":
        bot_stats["total_commands"] += 1

# دالة الحصول على الطقس
async def get_weather(city="Cairo"):
    try:
        if WEATHER_API_KEY:
            url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ar"
            response = requests.get(url)
            data = response.json()
            
            if response.status_code == 200:
                temp = data['main']['temp']
                description = data['weather'][0]['description']
                humidity = data['main']['humidity']
                
                return {
                    'temp': temp,
                    'description': description,
                    'humidity': humidity,
                    'city': city
                }
        return None
    except:
        return None

# دالة إنشاء لوحة المفاتيح التفاعلية
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🌸 صورة لماهيرو", callback_data="get_image")],
        [InlineKeyboardButton("🎮 ألعاب متنوعة", callback_data="games_menu"), 
         InlineKeyboardButton("💭 رسالة عشوائية", callback_data="random_message")],
        [InlineKeyboardButton("🎶 قائمة الموسيقى", callback_data="music_menu"),
         InlineKeyboardButton("⏰ التذكيرات", callback_data="reminders_menu")],
        [InlineKeyboardButton("🌤️ الطقس والتاريخ", callback_data="weather_info"),
         InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings_menu")],
        [InlineKeyboardButton("📊 إحصائيات البوت", callback_data="bot_stats")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_games_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔢 تخمين الرقم", callback_data="game_guess"),
         InlineKeyboardButton("🎯 لعبة الذاكرة", callback_data="game_memory")],
        [InlineKeyboardButton("❓ أسئلة وأجوبة", callback_data="game_quiz"),
         InlineKeyboardButton("🎲 رمي النرد", callback_data="game_dice")],
        [InlineKeyboardButton("🎪 حجر ورقة مقص", callback_data="game_rps"),
         InlineKeyboardButton("🧩 ألغاز", callback_data="game_riddle")],
        [InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

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
    user_id = str(update.effective_user.id)
    update_bot_stats("command")
    
    # إحصائيات المستخدمين الجدد
    if user_id not in user_data:
        bot_stats["total_users"] += 1
    
    # التحقق من وجود المستخدم
    if user_id not in user_data:
        welcome_text = """
🌸 مرحباً! أنا ماهيرو شينا!

هذه هي المرة الأولى التي نتقابل فيها... 
ما الاسم الذي تريدني أن أناديك به؟

اكتب اسمك في الرسالة التالية من فضلك! 💕
        """
        user_data[user_id] = {'waiting_for_name': True}
        save_user_data(user_data)
        
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        await update.message.reply_text(welcome_text)
        return
    
    user_name = get_user_name(update.effective_user.id)
    
    welcome_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
🌸 مرحباً بعودتك، {user_name}! 🌸
━━━━━━━━━━━━━━━━━━━━━━

أنا ماهيرو شينا، وأنا سعيدة جداً برؤيتك! 💕

🎯 الميزات المتاحة:
• 🎮 ألعاب متنوعة ومسلية
• 🎶 إدارة قائمة الموسيقى الخاصة بك
• 🌸 صوري الجميلة
• ⏰ تذكيرات مفيدة
• 🌤️ معلومات الطقس حسب منطقتك
• 📊 إحصائيات البوت

كيف حالك اليوم؟ هل تناولت طعامك؟ 🍱
    """
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())

# دالة التعامل مع الرسائل النصية
async def handle_message(update, context):
    user_id = str(update.effective_user.id)
    user_message = update.message.text.lower()
    update_bot_stats("message")
    
    # التحقق من انتظار الاسم
    if user_id in user_data and user_data[user_id].get('waiting_for_name'):
        name = update.message.text.strip()
        user_data[user_id]['name'] = name
        user_data[user_id]['waiting_for_name'] = False
        user_data[user_id]['playlist'] = []
        user_data[user_id]['timezone'] = 'Asia/Riyadh'
        save_user_data(user_data)
        
        response = f"""
━━━━━━━━━━━━━━━━━━━━━━
🌸 أهلاً وسهلاً، {name}! 🌸
━━━━━━━━━━━━━━━━━━━━━━

اسم جميل جداً! 💕
من الآن سأناديك {name}. 

أتمنى أن نصبح أصدقاء مقربين! 
هيا لنبدأ! يمكنك استخدام الأزرار أدناه 👇
        """
        
        await update.message.reply_text(response, reply_markup=get_main_keyboard())
        return
    
    user_name = get_user_name(update.effective_user.id)
    
    # التحقق من طلب إظهار الأزرار
    if any(keyword in user_message for keyword in ["الأزرار", "ازرار", "أريد الأزرار", "اريد الازرار", "القائمة", "buttons"]):
        await update.message.reply_text(
            f"🌸 تفضل {user_name}، هذه هي القائمة الرئيسية:",
            reply_markup=get_main_keyboard()
        )
        return
    
    # التحقق من طلب صورة
    if any(keyword in user_message for keyword in ["صورة", "صوره", "أريد صورة", "اريد صورة", "صورتك"]):
        await send_mahiru_image_direct(update, context)
        return
    
    # التحقق من طلب أغنية
    if any(keyword in user_message for keyword in ["أغنية", "اغنية", "موسيقى", "موسيقا", "أريد أغنية", "اريد اغنية"]):
        await handle_song_request(update, context, user_message)
        return
    
    # التحقق من لعبة التخمين النشطة
    if user_id in user_data and 'game' in user_data[user_id]:
        if user_data[user_id]['game']['type'] == 'guess':
            await handle_guess_game(update, context)
            return
        elif user_data[user_id]['game']['type'] == 'memory':
            await handle_memory_game(update, context)
            return
        elif user_data[user_id]['game']['type'] == 'quiz':
            await handle_quiz_game(update, context)
            return
    
    # التعامل مع الرسائل العادية باستخدام الذكاء الاصطناعي
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        
        prompt = SYSTEM_INSTRUCTION.format(user_name=user_name) + f"\n\n{user_name} يقول: {update.message.text}"
        response = model.generate_content(prompt)
        
        await update.message.reply_text(f"💕 {response.text}")
    except Exception as e:
        await update.message.reply_text(f"💔 آسفة {user_name}، حدث خطأ. هل يمكنك المحاولة مرة أخرى؟ 😔")

# دالة للتعامل مع طلبات الأغاني
async def handle_song_request(update, context, message):
    user_id = update.effective_user.id
    user_name = get_user_name(user_id)
    
    # محاولة استخراج اسم الأغنية من الرسالة
    song_name = message.replace("أغنية", "").replace("اغنية", "").replace("موسيقى", "").replace("موسيقا", "").replace("أريد", "").replace("اريد", "").strip()
    
    if not song_name:
        await update.message.reply_text(f"🎵 {user_name}، ما اسم الأغنية التي تريد أن تسمعها؟")
        return
    
    # البحث عن الأغنية في قاعدة البيانات
    song_data = None
    for key, data in SONGS_DATABASE.items():
        if key in song_name.lower():
            song_data = data
            break
    
    # إضافة الأغنية للقائمة
    add_song_to_playlist(user_id, song_name)
    
    if song_data:
        # إرسال رابط الأغنية والمقطع الصوتي
        response = f"""
━━━━━━━━━━━━━━━━━━━━━━
🎶 أغنية "{song_name}" 🎶
━━━━━━━━━━━━━━━━━━━━━━

🔗 الرابط: {song_data['url']}

✅ تم إضافتها لقائمة تشغيلك!
        """
        
        await update.message.reply_text(response)
        
        # إرسال المقطع الصوتي
        try:
            await context.bot.send_audio(
                chat_id=update.effective_chat.id,
                audio=song_data['audio'],
                caption=f"🎵 مقطع من أغنية {song_name} 💕"
            )
        except:
            await update.message.reply_text(f"🎵 {user_name}، لا يمكنني إرسال المقطع الصوتي حالياً، لكن الرابط متاح! 💕")
    else:
        # إذا لم توجد الأغنية في قاعدة البيانات
        response = f"""
━━━━━━━━━━━━━━━━━━━━━━
🎶 تم إضافة "{song_name}" 🎶
━━━━━━━━━━━━━━━━━━━━━━

✅ أضفتها إلى قائمة تشغيلك!
🔍 ابحث عنها في YouTube أو Spotify!
        """
        
        await update.message.reply_text(response)

# دالة إرسال صورة ماهيرو مباشرة
async def send_mahiru_image_direct(update, context):
    user_name = get_user_name(update.effective_user.id)
    
    try:
        # اختيار صورة عشوائية من القائمة
        image_url = random.choice(MAHIRU_IMAGES)
        caption = f"🌸 هذه صورتي، {user_name}!\nأتمنى أن تعجبك! 💕"
        
        # إرسال الصورة
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=image_url,
            caption=caption
        )
        
    except Exception as e:
        # في حالة فشل إرسال الصورة
        await update.message.reply_text(f"💔 آسفة {user_name}، لا أستطيع إرسال الصورة الآن... لكن أنا هنا معك! 💕")

# دالة التعامل مع لعبة التخمين
async def handle_guess_game(update, context):
    user_id = str(update.effective_user.id)
    user_name = get_user_name(update.effective_user.id)
    
    try:
        guess = int(update.message.text)
        game_data = user_data[user_id]['game']
        secret_number = game_data['number']
        attempts = game_data['attempts']
        
        if guess == secret_number:
            del user_data[user_id]['game']
            save_user_data(user_data)
            await update.message.reply_text(f"🎉 أحسنت {user_name}! الرقم كان {secret_number}!\nأنت بطل حقيقي! 💕")
        elif attempts <= 1:
            del user_data[user_id]['game']
            save_user_data(user_data)
            await update.message.reply_text(f"😔 انتهت المحاولات {user_name}.\nالرقم كان {secret_number}.\nلعبة أخرى؟ 🎮")
        else:
            hint = "أعلى" if guess < secret_number else "أقل"
            user_data[user_id]['game']['attempts'] -= 1
            save_user_data(user_data)
            remaining = user_data[user_id]['game']['attempts']
            await update.message.reply_text(f"🎯 الرقم {hint}، {user_name}!\nلديك {remaining} محاولات متبقية")
    except ValueError:
        await update.message.reply_text(f"🔢 {user_name}، من فضلك اكتب رقماً صحيحاً!")

# دالة التعامل مع لعبة الذاكرة
async def handle_memory_game(update, context):
    user_id = str(update.effective_user.id)
    user_name = get_user_name(update.effective_user.id)
    
    try:
        user_sequence = list(map(int, update.message.text.split()))
        game_data = user_data[user_id]['game']
        correct_sequence = game_data['sequence']
        
        if user_sequence == correct_sequence:
            del user_data[user_id]['game']
            save_user_data(user_data)
            await update.message.reply_text(f"🎉 رائع {user_name}! حفظت التسلسل بشكل مثالي! 💕")
        else:
            del user_data[user_id]['game']
            save_user_data(user_data)
            await update.message.reply_text(f"😅 التسلسل الصحيح كان: {' '.join(map(str, correct_sequence))}\nلعبة أخرى؟ 🧠")
    except:
        await update.message.reply_text(f"🔢 {user_name}، اكتب الأرقام مفصولة بمسافات مثل: 1 2 3")

# دالة التعامل مع لعبة الأسئلة
async def handle_quiz_game(update, context):
    user_id = str(update.effective_user.id)
    user_name = get_user_name(update.effective_user.id)
    
    user_answer = update.message.text.lower().strip()
    game_data = user_data[user_id]['game']
    correct_answer = game_data['answer'].lower()
    
    if user_answer == correct_answer:
        del user_data[user_id]['game']
        save_user_data(user_data)
        await update.message.reply_text(f"🎉 إجابة صحيحة {user_name}! أنت ذكي جداً! 💕")
    else:
        del user_data[user_id]['game']
        save_user_data(user_data)
        await update.message.reply_text(f"😅 الإجابة الصحيحة: {game_data['answer']}\nسؤال آخر؟ 🤔")

# دالة التعامل مع الرسائل الصوتية
async def handle_voice(update, context):
    user_name = get_user_name(update.effective_user.id)
    await update.message.reply_text(f"🎵 سمعت صوتك الجميل، {user_name}!\nلكنني لا أستطيع فهم الرسائل الصوتية بعد.\nهل يمكنك كتابة رسالتك؟ 😊💕")

# دالة التعامل مع الأزرار
async def button_handler(update, context):
    query = update.callback_query
    await query.answer()
    
    # الإجراءات الرئيسية
    if query.data == "get_image":
        await send_mahiru_image(query, context)
    elif query.data == "games_menu":
        await show_games_menu(query, context)
    elif query.data == "music_menu":
        await show_music_menu(query, context)
    elif query.data == "reminders_menu":
        await show_reminders_menu(query, context)
    elif query.data == "settings_menu":
        await show_settings_menu(query, context)
    elif query.data == "bot_stats":
        await show_bot_stats(query, context)
    elif query.data == "random_message":
        await send_random_message(query, context)
    elif query.data == "weather_info":
        await show_weather_info(query, context)
    elif query.data == "back_to_main":
        await back_to_main_menu(query, context)
    
    # ألعاب
    elif query.data == "game_guess":
        await start_guess_game(query, context)
    elif query.data == "game_memory":
        await start_memory_game(query, context)
    elif query.data == "game_quiz":
        await start_quiz_game(query, context)
    elif query.data == "game_dice":
        await play_dice_game(query, context)
    elif query.data == "game_rps":
        await play_rps_game(query, context)
    elif query.data == "game_riddle":
        await show_riddle_game(query, context)
    
    # موسيقى
    elif query.data == "show_playlist":
        await show_user_playlist(query, context)
    elif query.data == "edit_playlist":
        await edit_playlist_menu(query, context)
    elif query.data == "random_song":
        await play_random_song(query, context)
    elif query.data == "search_song":
        await search_song_prompt(query, context)
    
    # تذكيرات
    elif query.data == "food_reminder":
        await set_food_reminder(query, context)
    elif query.data == "sleep_reminder":
        await set_sleep_reminder(query, context)
    elif query.data == "water_reminder":
        await set_water_reminder(query, context)
    elif query.data == "exercise_reminder":
        await set_exercise_reminder(query, context)
    
    # إعدادات
    elif query.data == "change_timezone":
        await change_timezone_prompt(query, context)
    elif query.data == "reset_data":
        await reset_user_data(query, context)

# دالة إرسال صورة ماهيرو
async def send_mahiru_image(query, context):
    user_name = get_user_name(query.from_user.id)
    
    try:
        # اختيار صورة عشوائية من القائمة
        image_url = random.choice(MAHIRU_IMAGES)
        caption = f"🌸 هذه صورتي، {user_name}!\nأتمنى أن تعجبك! 💕"
        
        # إرسال الصورة كرسالة جديدة
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=image_url,
            caption=caption,
            reply_markup=get_main_keyboard()
        )
        
        # حذف الرسالة القديمة
        try:
            await query.message.delete()
        except:
            pass
        
    except Exception as e:
        # في حالة فشل إرسال الصورة، إرسال رسالة نصية
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"💔 آسفة {user_name}، لا أستطيع إرسال الصورة الآن... لكن أنا هنا معك! 💕",
            reply_markup=get_main_keyboard()
        )
        try:
            await query.message.delete()
        except:
            pass

# دالة عرض قائمة الألعاب
async def show_games_menu(query, context):
    user_name = get_user_name(query.from_user.id)
    
    games_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
🎮 مرحباً بك في عالم الألعاب! 🎮
━━━━━━━━━━━━━━━━━━━━━━

اختر لعبتك المفضلة، {user_name}! 💕

🔢 تخمين الرقم - خمن الرقم السري!
🎯 لعبة الذاكرة - احفظ التسلسل!
❓ أسئلة وأجوبة - اختبر معلوماتك!
🎲 رمي النرد - الحظ معك؟
🎪 حجر ورقة مقص - التحدي الكلاسيكي!
🧩 ألغاز - فكر واستمتع!
    """
    
    await query.edit_message_text(games_text, reply_markup=get_games_keyboard())

# دالة عرض قائمة الموسيقى
async def show_music_menu(query, context):
    user_name = get_user_name(query.from_user.id)
    playlist = get_user_playlist(query.from_user.id)
    
    music_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
🎶 عالم الموسيقى الخاص بك! 🎶
━━━━━━━━━━━━━━━━━━━━━━

أهلاً {user_name}! 💕
لديك {len(playlist)} أغنية في قائمتك

🎵 عرض قائمتي - شاهد أغانيك المفضلة
✏️ تعديل القائمة - أضف أو احذف أغاني
🎧 أغنية عشوائية - اختر لي أغنية!
🔍 بحث عن أغنية - ابحث عن أغنية معينة
    """
    
    await query.edit_message_text(music_text, reply_markup=get_music_keyboard())

# دالة عرض قائمة التذكيرات
async def show_reminders_menu(query, context):
    user_name = get_user_name(query.from_user.id)
    
    reminders_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
⏰ تذكيرات مهمة لصحتك! ⏰
━━━━━━━━━━━━━━━━━━━━━━

{user_name}، أريد أن أعتني بك! 💕

🍱 تذكير طعام - لا تنسَ وجباتك!
😴 تذكير نوم - راحة جيدة مهمة!
💧 تذكير شرب الماء - حافظ على صحتك!
🏃‍♂️ تذكير رياضة - حرك جسمك!
    """
    
    await query.edit_message_text(reminders_text, reply_markup=get_reminders_keyboard())

# دالة عرض قائمة الإعدادات
async def show_settings_menu(query, context):
    user_name = get_user_name(query.from_user.id)
    user_timezone = get_user_timezone(query.from_user.id)
    
    settings_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
⚙️ إعدادات البوت ⚙️
━━━━━━━━━━━━━━━━━━━━━━

مرحباً {user_name}! 💕

المنطقة الزمنية الحالية: {user_timezone}

🌍 تغيير المنطقة الزمنية
🔄 إعادة تعيين البيانات
    """
    
    await query.edit_message_text(settings_text, reply_markup=get_settings_keyboard())

# دالة عرض إحصائيات البوت
async def show_bot_stats(query, context):
    user_name = get_user_name(query.from_user.id)
    
    stats_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
📊 إحصائيات البوت 📊
━━━━━━━━━━━━━━━━━━━━━━

{user_name}، هذه إحصائيات استخدام البوت! 💕

👥 إجمالي المستخدمين: {bot_stats["total_users"]}
💬 إجمالي الرسائل: {bot_stats["total_messages"]}
🎯 إجمالي الأوامر: {bot_stats["total_commands"]}

شكراً لك على استخدام البوت! 🌸
    """
    
    back_keyboard = [[InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]]
    await query.edit_message_text(stats_text, reply_markup=InlineKeyboardMarkup(back_keyboard))

# دالة عرض معلومات الطقس والتاريخ
async def show_weather_info(query, context):
    user_name = get_user_name(query.from_user.id)
    user_timezone_str = get_user_timezone(query.from_user.id)
    
    # التاريخ الحالي حسب المنطقة الزمنية للمستخدم
    user_timezone = pytz.timezone(user_timezone_str)
    now = datetime.now(user_timezone)
    current_date = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M")
    day_name = now.strftime("%A")
    
    # ترجمة أسماء الأيام
    days_translation = {
        'Monday': 'الاثنين', 'Tuesday': 'الثلاثاء', 'Wednesday': 'الأربعاء',
        'Thursday': 'الخميس', 'Friday': 'الجمعة', 'Saturday': 'السبت', 'Sunday': 'الأحد'
    }
    
    day_arabic = days_translation.get(day_name, day_name)
    
    # الحصول على الطقس
    weather_info = await get_weather()
    
    if weather_info:
        weather_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
🌤️ الطقس والتاريخ 🌤️
━━━━━━━━━━━━━━━━━━━━━━

مرحباً {user_name}! 💕

📅 التاريخ: {current_date}
🕐 الوقت: {current_time}
📆 اليوم: {day_arabic}
🌍 المنطقة الزمنية: {user_timezone_str}

🌡️ الطقس في {weather_info['city']}:
• درجة الحرارة: {weather_info['temp']}°C
• الوصف: {weather_info['description']}
• الرطوبة: {weather_info['humidity']}%

اعتنِ بنفسك! 🌸
        """
    else:
        weather_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
🌤️ التاريخ والوقت 🌤️
━━━━━━━━━━━━━━━━━━━━━━

مرحباً {user_name}! 💕

📅 التاريخ: {current_date}
🕐 الوقت: {current_time}
📆 اليوم: {day_arabic}
🌍 المنطقة الزمنية: {user_timezone_str}

🌡️ عذراً، لا يمكنني الحصول على معلومات الطقس حالياً.
لكن أتمنى أن يكون الطقس جميلاً! 🌞

اعتنِ بنفسك! 🌸
        """
    
    back_keyboard = [[InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]]
    await query.edit_message_text(weather_text, reply_markup=InlineKeyboardMarkup(back_keyboard))

# دوال الألعاب
async def start_guess_game(query, context):
    user_name = get_user_name(query.from_user.id)
    secret_number = random.randint(1, 10)
    
    if str(query.from_user.id) not in user_data:
        user_data[str(query.from_user.id)] = {}
    user_data[str(query.from_user.id)]['game'] = {'type': 'guess', 'number': secret_number, 'attempts': 3}
    save_user_data(user_data)
    
    game_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
🔢 لعبة تخمين الرقم! 🔢
━━━━━━━━━━━━━━━━━━━━━━

{user_name}، فكرت في رقم بين 1 و 10! 

🎯 خمن الرقم!
⏱️ لديك 3 محاولات
✍️ اكتب رقمك في الدردشة
    """
    
    back_keyboard = [[InlineKeyboardButton("🔙 عودة للألعاب", callback_data="games_menu")]]
    await query.edit_message_text(game_text, reply_markup=InlineKeyboardMarkup(back_keyboard))

async def start_memory_game(query, context):
    user_name = get_user_name(query.from_user.id)
    sequence = [random.randint(1, 9) for _ in range(4)]
    
    if str(query.from_user.id) not in user_data:
        user_data[str(query.from_user.id)] = {}
    user_data[str(query.from_user.id)]['game'] = {'type': 'memory', 'sequence': sequence}
    save_user_data(user_data)
    
    game_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
🎯 لعبة الذاكرة! 🎯
━━━━━━━━━━━━━━━━━━━━━━

{user_name}، احفظ هذا التسلسل:

🔥 {' '.join(map(str, sequence))} 🔥

الآن اكتب التسلسل في الدردشة!
(مثال: 1 2 3 4)
    """
    
    back_keyboard = [[InlineKeyboardButton("🔙 عودة للألعاب", callback_data="games_menu")]]
    await query.edit_message_text(game_text, reply_markup=InlineKeyboardMarkup(back_keyboard))

async def start_quiz_game(query, context):
    user_name = get_user_name(query.from_user.id)
    
    questions = [
        {"question": "ما هي عاصمة فرنسا؟", "answer": "باريس"},
        {"question": "كم عدد قارات العالم؟", "answer": "7"},
        {"question": "ما هو أكبر محيط في العالم؟", "answer": "الهادئ"},
        {"question": "من اخترع المصباح الكهربائي؟", "answer": "إديسون"},
        {"question": "كم عدد أيام السنة؟", "answer": "365"}
    ]
    
    question_data = random.choice(questions)
    
    if str(query.from_user.id) not in user_data:
        user_data[str(query.from_user.id)] = {}
    user_data[str(query.from_user.id)]['game'] = {'type': 'quiz', 'answer': question_data['answer']}
    save_user_data(user_data)
    
    game_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
❓ لعبة الأسئلة والأجوبة! ❓
━━━━━━━━━━━━━━━━━━━━━━

{user_name}، إليك السؤال:

🤔 {question_data['question']}

اكتب إجابتك في الدردشة!
    """
    
    back_keyboard = [[InlineKeyboardButton("🔙 عودة للألعاب", callback_data="games_menu")]]
    await query.edit_message_text(game_text, reply_markup=InlineKeyboardMarkup(back_keyboard))

async def play_dice_game(query, context):
    user_name = get_user_name(query.from_user.id)
    dice_result = random.randint(1, 6)
    
    game_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
🎲 لعبة رمي النرد! 🎲
━━━━━━━━━━━━━━━━━━━━━━

{user_name}، لقد رميت النرد...

🎯 النتيجة: {dice_result}

{'🎉 رقم رائع!' if dice_result >= 4 else '😅 حظ أفضل في المرة القادمة!'}
    """
    
    game_keyboard = [
        [InlineKeyboardButton("🎲 رمي مرة أخرى", callback_data="game_dice")],
        [InlineKeyboardButton("🔙 عودة للألعاب", callback_data="games_menu")]
    ]
    await query.edit_message_text(game_text, reply_markup=InlineKeyboardMarkup(game_keyboard))

async def play_rps_game(query, context):
    user_name = get_user_name(query.from_user.id)
    choices = ["🪨 حجر", "📄 ورقة", "✂️ مقص"]
    bot_choice = random.choice(choices)
    
    game_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
🎪 حجر ورقة مقص! 🎪
━━━━━━━━━━━━━━━━━━━━━━

{user_name}، اخترت أنا: {bot_choice}

اختر أنت الآن! 💪
    """
    
    rps_keyboard = [
        [InlineKeyboardButton("🪨 حجر", callback_data="rps_rock"),
         InlineKeyboardButton("📄 ورقة", callback_data="rps_paper")],
        [InlineKeyboardButton("✂️ مقص", callback_data="rps_scissors")],
        [InlineKeyboardButton("🔙 عودة للألعاب", callback_data="games_menu")]
    ]
    await query.edit_message_text(game_text, reply_markup=InlineKeyboardMarkup(rps_keyboard))

async def show_riddle_game(query, context):
    user_name = get_user_name(query.from_user.id)
    
    riddles = [
        "شيء يكبر بالأكل؟ (النار)",
        "له عين ولا يرى؟ (الإبرة)",
        "يمشي بلا أرجل؟ (الوقت)",
        "له رأس ولا يفكر؟ (الدبوس)",
        "أبيض من الثلج وأسود من الليل؟ (اللبن والحبر)"
    ]
    
    riddle = random.choice(riddles)
    
    game_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
🧩 لغز اليوم! 🧩
━━━━━━━━━━━━━━━━━━━━━━

{user_name}، هل تستطيع حل هذا اللغز؟

🤔 {riddle}

فكر جيداً! 💭
    """
    
    riddle_keyboard = [
        [InlineKeyboardButton("🧩 لغز آخر", callback_data="game_riddle")],
        [InlineKeyboardButton("🔙 عودة للألعاب", callback_data="games_menu")]
    ]
    await query.edit_message_text(game_text, reply_markup=InlineKeyboardMarkup(riddle_keyboard))

# دوال الموسيقى
async def show_user_playlist(query, context):
    user_name = get_user_name(query.from_user.id)
    playlist = get_user_playlist(query.from_user.id)
    
    if not playlist:
        message = f"""
━━━━━━━━━━━━━━━━━━━━━━
🎵 قائمة التشغيل فارغة! 🎵
━━━━━━━━━━━━━━━━━━━━━━

{user_name}، لا توجد أغاني في قائمتك بعد.

أضف بعض الأغاني أولاً! 💕
        """
    else:
        message = f"""
━━━━━━━━━━━━━━━━━━━━━━
🎶 قائمة {user_name} الموسيقية 🎶
━━━━━━━━━━━━━━━━━━━━━━

"""
        for i, song in enumerate(playlist, 1):
            message += f"{i}. 🎵 {song}\n"
        message += f"\n💕 ذوق رائع، {user_name}!"
    
    playlist_keyboard = [[InlineKeyboardButton("🔙 عودة للموسيقى", callback_data="music_menu")]]
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(playlist_keyboard))

async def edit_playlist_menu(query, context):
    user_name = get_user_name(query.from_user.id)
    
    edit_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
✏️ تعديل قائمة التشغيل ✏️
━━━━━━━━━━━━━━━━━━━━━━

{user_name}، كيف تريد تعديل قائمتك؟

• لإضافة أغنية: اكتب "أريد أغنية [اسم الأغنية]"
• لحذف أغنية: اكتب "احذف أغنية رقم [الرقم]"
    """
    
    edit_keyboard = [[InlineKeyboardButton("🔙 عودة للموسيقى", callback_data="music_menu")]]
    await query.edit_message_text(edit_text, reply_markup=InlineKeyboardMarkup(edit_keyboard))

async def play_random_song(query, context):
    user_name = get_user_name(query.from_user.id)
    
    if SONGS_DATABASE:
        song_key = random.choice(list(SONGS_DATABASE.keys()))
        song_data = SONGS_DATABASE[song_key]
        
        message = f"""
━━━━━━━━━━━━━━━━━━━━━━
🎧 أغنية عشوائية! 🎧
━━━━━━━━━━━━━━━━━━━━━━

{user_name}، اخترت لك: {song_key}

🔗 {song_data['url']}

استمتع! 💕
        """
        
        # إضافة للقائمة
        add_song_to_playlist(query.from_user.id, song_key)
        
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=message,
            reply_markup=get_music_keyboard()
        )
        
        # إرسال المقطع الصوتي
        try:
            await context.bot.send_audio(
                chat_id=query.message.chat_id,
                audio=song_data['audio'],
                caption=f"🎵 مقطع من {song_key} 💕"
            )
        except:
            pass
            
        try:
            await query.message.delete()
        except:
            pass
    else:
        random_keyboard = [[InlineKeyboardButton("🔙 عودة للموسيقى", callback_data="music_menu")]]
        await query.edit_message_text(f"😅 {user_name}، لا توجد أغاني متاحة حالياً!", reply_markup=InlineKeyboardMarkup(random_keyboard))

async def search_song_prompt(query, context):
    user_name = get_user_name(query.from_user.id)
    
    search_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
🔍 البحث عن أغنية 🔍
━━━━━━━━━━━━━━━━━━━━━━

{user_name}، اكتب اسم الأغنية التي تبحث عنها!

مثال: "أريد أغنية believer"
    """
    
    search_keyboard = [[InlineKeyboardButton("🔙 عودة للموسيقى", callback_data="music_menu")]]
    await query.edit_message_text(search_text, reply_markup=InlineKeyboardMarkup(search_keyboard))

# دوال التذكيرات
async def set_food_reminder(query, context):
    user_name = get_user_name(query.from_user.id)
    
    reminder_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
🍱 تذكير مهم للطعام! 🍱
━━━━━━━━━━━━━━━━━━━━━━

{user_name}، لا تنسَ تناول وجباتك! 💕

⏰ مواعيد الوجبات المثالية:
• الإفطار: 7:00 - 9:00 صباحاً
• الغداء: 12:00 - 2:00 ظهراً  
• العشاء: 6:00 - 8:00 مساءً

صحتك أهم شيء عندي! 🌸
    """
    
    reminder_keyboard = [[InlineKeyboardButton("🔙 عودة للتذكيرات", callback_data="reminders_menu")]]
    await query.edit_message_text(reminder_text, reply_markup=InlineKeyboardMarkup(reminder_keyboard))

async def set_sleep_reminder(query, context):
    user_name = get_user_name(query.from_user.id)
    
    reminder_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
😴 وقت النوم مهم! 😴
━━━━━━━━━━━━━━━━━━━━━━

{user_name}، احصل على راحة جيدة! 💕

💤 نصائح للنوم الصحي:
• نم 7-8 ساعات يومياً
• اذهب للفراش قبل 11:00 مساءً
• تجنب الشاشات قبل النوم بساعة
• اجعل غرفتك مظلمة وهادئة

أحلام سعيدة! 🌙✨
    """
    
    reminder_keyboard = [[InlineKeyboardButton("🔙 عودة للتذكيرات", callback_data="reminders_menu")]]
    await query.edit_message_text(reminder_text, reply_markup=InlineKeyboardMarkup(reminder_keyboard))

async def set_water_reminder(query, context):
    user_name = get_user_name(query.from_user.id)
    
    reminder_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
💧 تذكير شرب الماء! 💧
━━━━━━━━━━━━━━━━━━━━━━

{user_name}، لا تنسَ شرب الماء! 💕

🚰 نصائح لشرب الماء:
• اشرب 8-10 أكواب يومياً
• ابدأ يومك بكوب ماء
• اشرب الماء قبل الوجبات
• احتفظ بزجاجة ماء معك دائماً

جسمك يحتاج للماء! 🌊
    """
    
    reminder_keyboard = [[InlineKeyboardButton("🔙 عودة للتذكيرات", callback_data="reminders_menu")]]
    await query.edit_message_text(reminder_text, reply_markup=InlineKeyboardMarkup(reminder_keyboard))

async def set_exercise_reminder(query, context):
    user_name = get_user_name(query.from_user.id)
    
    reminder_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
🏃‍♂️ تذكير الرياضة! 🏃‍♂️
━━━━━━━━━━━━━━━━━━━━━━

{user_name}، حرك جسمك! 💕

💪 نصائح للرياضة:
• مارس الرياضة 30 دقيقة يومياً
• ابدأ بالمشي السريع
• جرب تمارين التمدد
• اصعد الدرج بدلاً من المصعد

جسم صحي، عقل صحي! 🌟
    """
    
    reminder_keyboard = [[InlineKeyboardButton("🔙 عودة للتذكيرات", callback_data="reminders_menu")]]
    await query.edit_message_text(reminder_text, reply_markup=InlineKeyboardMarkup(reminder_keyboard))

# دوال الإعدادات
async def change_timezone_prompt(query, context):
    user_name = get_user_name(query.from_user.id)
    
    timezone_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
🌍 تغيير المنطقة الزمنية 🌍
━━━━━━━━━━━━━━━━━━━━━━

{user_name}، اختر منطقتك الزمنية! 💕

الخيارات المتاحة:
• Asia/Riyadh (السعودية)
• Asia/Dubai (الإمارات) 
• Africa/Cairo (مصر)
• Asia/Baghdad (العراق)
• Asia/Beirut (لبنان)
• Europe/London (لندن)
• America/New_York (نيويورك)

اكتب المنطقة في الدردشة مثل: Asia/Riyadh
    """
    
    timezone_keyboard = [[InlineKeyboardButton("🔙 عودة للإعدادات", callback_data="settings_menu")]]
    await query.edit_message_text(timezone_text, reply_markup=InlineKeyboardMarkup(timezone_keyboard))

async def reset_user_data(query, context):
    user_name = get_user_name(query.from_user.id)
    user_id = str(query.from_user.id)
    
    # إعادة تعيين بيانات المستخدم مع الاحتفاظ بالاسم
    user_data[user_id] = {
        'name': user_name,
        'playlist': [],
        'timezone': 'Asia/Riyadh'
    }
    save_user_data(user_data)
    
    reset_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
🔄 تم إعادة التعيين! 🔄
━━━━━━━━━━━━━━━━━━━━━━

{user_name}، تم إعادة تعيين بياناتك بنجاح! 💕

• تم مسح قائمة الموسيقى
• تم إعادة تعيين الإعدادات للافتراضية
• تم الاحتفاظ باسمك

يمكنك البدء من جديد! 🌟
    """
    
    reset_keyboard = [[InlineKeyboardButton("🔙 عودة للإعدادات", callback_data="settings_menu")]]
    await query.edit_message_text(reset_text, reply_markup=InlineKeyboardMarkup(reset_keyboard))

# دوال مساعدة
async def send_random_message(query, context):
    user_name = get_user_name(query.from_user.id)
    message = random.choice(RANDOM_MESSAGES).format(user_name=user_name)
    
    random_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
💭 رسالة خاصة لك! 💭
━━━━━━━━━━━━━━━━━━━━━━

{message}
    """
    
    random_keyboard = [[InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]]
    await query.edit_message_text(random_text, reply_markup=InlineKeyboardMarkup(random_keyboard))

async def back_to_main_menu(query, context):
    user_name = get_user_name(query.from_user.id)
    
    main_text = f"""
━━━━━━━━━━━━━━━━━━━━━━
🌸 عدت للقائمة الرئيسية! 🌸
━━━━━━━━━━━━━━━━━━━━━━

أهلاً وسهلاً، {user_name}! 💕

ماذا تريد أن نفعل الآن؟
    """
    
    await query.edit_message_text(main_text, reply_markup=get_main_keyboard())

# --- تشغيل البوت ---
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    
    print("🌸 بوت ماهيرو محدث مع جميع الميزات الجديدة ويعمل بشكل مثالي!")
    app.run_polling()

if __name__ == '__main__':
    main()
