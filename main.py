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
import pytz
from flask import Flask
from datetime import datetime, date, timedelta

# --- إعدادات البيئة ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')

# --- إعداد Flask للبقاء نشطاً ---
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
            # استبدل الرابط بالرابط الفعلي لتطبيقك على Render
            requests.get("https://mahiroshina.onrender.com") 
            print("✅ Sent keep-alive ping to Render")
        except Exception as e:
            print(f"⚠️ Ping failed: {e}")
        time.sleep(300) # كل 5 دقائق

threading.Thread(target=keep_alive_ping, daemon=True).start()

# --- إعدادات التسجيل ---
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

# --- صور ماهيرو شينا ---
MAHIRU_IMAGES = [
    "https://i.imgur.com/K8J9X2M.jpg", "https://i.imgur.com/L3M4N5P.jpg",
    "https://i.imgur.com/Q6R7S8T.jpg", "https://i.imgur.com/U9V0W1X.jpg",
    "https://i.imgur.com/Y2Z3A4B.jpg", "https://i.imgur.com/C5D6E7F.jpg",
    "https://i.imgur.com/G8H9I0J.jpg", "https://i.imgur.com/K1L2M3N.jpg"
]

# --- وصفات ماهيرو ---
MAHIRU_RECIPES = [
    {
        "name": "أومليت الأرز (Omurice) 🍳",
        "ingredients": ["أرز مطبوخ", "بيضتان", "كاتشب", "دجاج أو خضروات (اختياري)", "ملح وفلفل"],
        "instructions": "1. حضّر الأرز المقلي مع الدجاج والخضروات والكاتشب.\n2. اخفق البيض واصنع أومليت رقيق.\n3. ضع الأرز المقلي داخل الأومليت ولفه.\n4. زين السطح بالكاتشب. بالهناء والشفاء!"
    },
    {
        "name": "كرات الأرز (Onigiri) 🍙",
        "ingredients": ["أرز ياباني قصير الحبة", "حشوة (تونة بالمايونيز، سلمون مشوي، أو خوخ مخلل)", "أوراق نوري (أعشاب بحرية)"],
        "instructions": "1. اطبخ الأرز واتركه ليبرد قليلاً.\n2. بلل يديك بالماء والملح لمنع الالتصاق.\n3. خذ كمية من الأرز وشكلها على هيئة مثلث أو كرة، واصنع فجوة في المنتصف.\n4. ضع الحشوة في الفجوة وأغلقها بالأرز.\n5. لف كرة الأرز بشريط من أعشاب نوري. لذيذة جداً!"
    },
    {
        "name": "حساء الميسو 🥣",
        "ingredients": ["معجون الميسو", "مكعبات توفو", "أعشاب واكامي البحرية", "مرق داشي"],
        "instructions": "1. سخّن مرق الداشي في قدر.\n2. أضف التوفو والواكامي.\n3. قبل التقديم مباشرة، خفف معجون الميسو بقليل من المرق الساخن ثم أضفه للقدر.\n4. لا تدع الحساء يغلي بعد إضافة الميسو. صحتين وعافية!"
    }
]

# --- متغيرات لحفظ بيانات المستخدمين والجدولة ---
USER_DATA_FILE = "user_data.json"
pomodoro_timers = {} # {user_id: {"end_time": datetime, "type": "work" | "break", "job": job}}

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

# --- دوال مساعدة لإدارة بيانات المستخدم ---

def get_user_name(user_id):
    return user_data.get(str(user_id), {}).get('name', 'فوجيميا-سان')

def get_user_timezone(user_id):
    return user_data.get(str(user_id), {}).get('timezone', 'Asia/Riyadh')

def initialize_user_data(user_id, name):
    """Initialize data for a new user."""
    if str(user_id) not in user_data:
        user_data[str(user_id)] = {
            'name': name,
            'waiting_for_name': False,
            'timezone': 'Asia/Riyadh',
            'last_check_in': None,
            'check_in_streak': 0,
            'tasks': [], # { "text": "Task 1", "done": False }
            'moods': [] # { "mood": "😊", "date": "YYYY-MM-DD" }
        }
        save_user_data(user_data)

# --- دوال الطقس ---
async def get_weather(city="Riyadh"):
    if not WEATHER_API_KEY: return None
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ar"
        response = requests.get(url)
        data = response.json()
        if response.status_code == 200:
            return {
                'temp': data['main']['temp'],
                'description': data['weather'][0]['description'],
                'city': data['name']
            }
        return None
    except Exception as e:
        logger.error(f"Weather API error: {e}")
        return None

# --- لوحات المفاتيح ---
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🌸 صورتي", callback_data="get_image"), InlineKeyboardButton("💬 رسالة عشوائية", callback_data="random_message")],
        [InlineKeyboardButton("✨ ميزات شخصية", callback_data="personal_features_menu")],
        [InlineKeyboardButton("🌤️ الطقس والتاريخ", callback_data="weather_info"), InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_personal_features_keyboard():
    keyboard = [
        [InlineKeyboardButton("⏰ مؤقت بومودورو", callback_data="pomodoro_menu"), InlineKeyboardButton("📝 قائمة المهام", callback_data="todo_menu")],
        [InlineKeyboardButton("😊 تتبع مزاجي", callback_data="mood_menu"), InlineKeyboardButton("🍳 وصفة اليوم", callback_data="get_recipe")],
        [InlineKeyboardButton("☀️ تسجيل الدخول", callback_data="daily_checkin")],
        [InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_pomodoro_keyboard(user_id):
    if user_id in pomodoro_timers:
        return InlineKeyboardMarkup([[InlineKeyboardButton("⏹️ إيقاف المؤقت", callback_data="stop_pomodoro")], [InlineKeyboardButton("🔙 عودة", callback_data="personal_features_menu")]])
    else:
        return InlineKeyboardMarkup([[InlineKeyboardButton("▶️ بدء جلسة (25 دقيقة)", callback_data="start_pomodoro")], [InlineKeyboardButton("🔙 عودة", callback_data="personal_features_menu")]])

def get_todo_keyboard(user_id):
    tasks = user_data.get(str(user_id), {}).get('tasks', [])
    keyboard = []
    for i, task in enumerate(tasks):
        status_icon = "✅" if task['done'] else "☑️"
        keyboard.append([InlineKeyboardButton(f"{status_icon} {task['text']}", callback_data=f"toggle_task_{i}")])
    keyboard.append([InlineKeyboardButton("➕ إضافة مهمة", callback_data="add_task_prompt")])
    keyboard.append([InlineKeyboardButton("🗑️ حذف المكتمل", callback_data="clear_completed_tasks")])
    keyboard.append([InlineKeyboardButton("🔙 عودة", callback_data="personal_features_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_mood_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("😊 سعيد", callback_data="log_mood_😊"),
            InlineKeyboardButton("😐 عادي", callback_data="log_mood_😐"),
            InlineKeyboardButton("😔 حزين", callback_data="log_mood_😔")
        ],
        [InlineKeyboardButton("📊 عرض سجل مزاجي", callback_data="view_moods")],
        [InlineKeyboardButton("🔙 عودة", callback_data="personal_features_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- الأوامر الأساسية ---
async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    user_id = str(user.id)

    if user_id not in user_data or user_data[user_id].get('waiting_for_name', False):
        welcome_text = "🌸 مرحباً! أنا ماهيرو شينا!\n\nهذه هي المرة الأولى التي نتقابل فيها... \nما الاسم الذي تريدني أن أناديك به؟\n\nاكتب اسمك في الرسالة التالية من فضلك! 💕"
        user_data[user_id] = {'waiting_for_name': True}
        save_user_data(user_data)
        await update.message.reply_text(welcome_text)
    else:
        user_name = get_user_name(user_id)
        welcome_text = f"🌸 مرحباً بعودتك، {user_name}!\n\nأنا سعيدة جداً برؤيتك! 💕\nكيف حالك اليوم؟ هل تناولت طعامك؟ 🍱"
        await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())

async def handle_message(update: Update, context: CallbackContext):
    user = update.effective_user
    user_id = str(user.id)
    text = update.message.text

    # --- معالجة الحالات الخاصة ---
    if user_data.get(user_id, {}).get('waiting_for_name', False):
        name = text.strip()
        initialize_user_data(user_id, name)
        response = f"🌸 أهلاً وسهلاً، {name}!\n\nاسم جميل جداً! 💕\nمن الآن سأناديك {name}. أتمنى أن نصبح أصدقاء مقربين!\n\nيمكنك استخدام الأزرار أدناه 👇"
        await update.message.reply_text(response, reply_markup=get_main_keyboard())
        return

    if user_data.get(user_id, {}).get('waiting_for_task', False):
        user_data[user_id]['tasks'].append({"text": text, "done": False})
        user_data[user_id]['waiting_for_task'] = False
        save_user_data(user_data)
        await update.message.reply_text("✅ تم إضافة المهمة بنجاح!", reply_markup=get_todo_keyboard(user_id))
        return
        
    if "أزرار" in text or "القائمة" in text:
        await update.message.reply_text(f"🌸 تفضل {get_user_name(user_id)}، هذه هي القائمة الرئيسية:", reply_markup=get_main_keyboard())
        return

    # --- الرد باستخدام الذكاء الاصطناعي ---
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        user_name = get_user_name(user_id)
        prompt = SYSTEM_INSTRUCTION.format(user_name=user_name) + f"\n\n{user_name} يقول: {text}"
        response = model.generate_content(prompt)
        await update.message.reply_text(f"💕 {response.text}")
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        await update.message.reply_text(f"💔 آسفة {get_user_name(user_id)}، حدث خطأ. هل يمكنك المحاولة مرة أخرى؟ 😔")


# --- معالج الأزرار ---
async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    data = query.data

    # القوائم الرئيسية
    if data == "back_to_main":
        await query.edit_message_text(f"🌸 أهلاً بعودتك، {get_user_name(user_id)}! ماذا تريد أن نفعل الآن؟", reply_markup=get_main_keyboard())
    elif data == "personal_features_menu":
        await query.edit_message_text(f"✨ هذه هي الميزات الشخصية التي أعددتها لك، {get_user_name(user_id)}:", reply_markup=get_personal_features_keyboard())
    
    # الميزات الأساسية
    elif data == "get_image":
        await send_mahiru_image(query, context)
    elif data == "random_message":
        await send_random_message(query, context)
    elif data == "weather_info":
        await show_weather_info(query, context)

    # ميزات شخصية
    elif data == "get_recipe":
        await send_daily_recipe(query, context)
    elif data == "daily_checkin":
        await handle_daily_checkin(query, context)

    # مؤقت بومودورو
    elif data == "pomodoro_menu":
        await show_pomodoro_menu(query, context)
    elif data == "start_pomodoro":
        await start_pomodoro_timer(query, context)
    elif data == "stop_pomodoro":
        await stop_pomodoro_timer(query, context)

    # قائمة المهام
    elif data == "todo_menu":
        await show_todo_list(query, context)
    elif data.startswith("toggle_task_"):
        task_index = int(data.split('_')[2])
        await toggle_task(query, context, task_index)
    elif data == "add_task_prompt":
        user_data[user_id]['waiting_for_task'] = True
        save_user_data(user_data)
        await query.edit_message_text("📝 حسناً، اكتب نص المهمة التي تريد إضافتها:")
    elif data == "clear_completed_tasks":
        await clear_completed(query, context)

    # متتبع المزاج
    elif data == "mood_menu":
        await show_mood_menu(query, context)
    elif data.startswith("log_mood_"):
        mood = data.split('_')[2]
        await log_mood(query, context, mood)
    elif data == "view_moods":
        await view_mood_history(query, context)

# --- دوال الميزات ---

async def send_mahiru_image(query, context):
    image_url = random.choice(MAHIRU_IMAGES)
    await context.bot.send_photo(chat_id=query.message.chat_id, photo=image_url, caption=f"🌸 هذه صورتي، {get_user_name(query.from_user.id)}! أتمنى أن تعجبك! 💕")
    try:
        await query.message.delete()
    except:
        pass

async def send_random_message(query, context):
    user_name = get_user_name(query.from_user.id)
    messages = [
        f"{user_name}، هل تذكرت أن تشرب الماء اليوم؟ 💧",
        f"أفكر فيك، {user_name}. أتمنى أن تكون سعيداً! 😊",
        f"{user_name}، لا تنسَ أن تأخذ استراحة. 💕",
        f"أتمنى أن يكون يومك جميلاً، {user_name} 🌸",
    ]
    await query.edit_message_text(f"💭 {random.choice(messages)}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]]))

async def show_weather_info(query, context):
    user_id = str(query.from_user.id)
    user_tz_str = get_user_timezone(user_id)
    user_tz = pytz.timezone(user_tz_str)
    now = datetime.now(user_tz)
    
    weather = await get_weather()
    weather_text = "لم أتمكن من جلب معلومات الطقس حالياً. 😔"
    if weather:
        weather_text = f"الطقس في {weather['city']}: {weather['description']} ودرجة الحرارة {weather['temp']}°C."

    date_text = f"📅 اليوم هو {now.strftime('%A, %d %B %Y')}\n⏰ الساعة الآن {now.strftime('%H:%M')}"
    
    await query.edit_message_text(f"🌤️ {get_user_name(user_id)}، إليك تقرير اليوم:\n\n{date_text}\n{weather_text}",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]]))

async def send_daily_recipe(query, context):
    recipe = random.choice(MAHIRU_RECIPES)
    text = f"🍳 **وصفة اليوم من ماهيرو: {recipe['name']}**\n\n" \
           f"**المكونات:**\n{recipe['ingredients']}\n\n" \
           f"**طريقة التحضير:**\n{recipe['instructions']}"
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 عودة", callback_data="personal_features_menu")]]))

async def handle_daily_checkin(query, context):
    user_id = str(query.from_user.id)
    user_name = get_user_name(user_id)
    today = str(date.today())
    
    last_check_in = user_data[user_id].get('last_check_in')
    streak = user_data[user_id].get('check_in_streak', 0)

    if last_check_in == today:
        await query.edit_message_text(f"☀️ {user_name}، لقد سجلت دخولك بالفعل اليوم! أراك غداً. لديك {streak} يوم من تسجيل الدخول المتتالي. ✨",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 عودة", callback_data="personal_features_menu")]]))
        return

    yesterday = str(date.today() - timedelta(days=1))
    if last_check_in == yesterday:
        streak += 1
    else:
        streak = 1
        
    user_data[user_id]['last_check_in'] = today
    user_data[user_id]['check_in_streak'] = streak
    save_user_data(user_data)
    
    await query.edit_message_text(f"☀️ أهلاً بك {user_name}! تم تسجيل دخولك لليوم.\n\nأنت في يومك الـ {streak} على التوالي! استمر في ذلك! 💖",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 عودة", callback_data="personal_features_menu")]]))

# --- دوال مؤقت بومودورو ---
async def show_pomodoro_menu(query, context):
    user_id = str(query.from_user.id)
    text = f"⏰ مؤقت بومودورو يساعدك على التركيز، {get_user_name(user_id)}.\n\n"
    if user_id in pomodoro_timers:
        timer = pomodoro_timers[user_id]
        remaining = timer['end_time'] - datetime.now()
        status = "وقت العمل" if timer['type'] == 'work' else "وقت الراحة"
        text += f"الحالة الحالية: {status}\nالوقت المتبقي: {str(timedelta(seconds=int(remaining.total_seconds())))}"
    else:
        text += "ابدأ جلسة عمل لمدة 25 دقيقة تليها 5 دقائق راحة."
    await query.edit_message_text(text, reply_markup=get_pomodoro_keyboard(user_id))

async def pomodoro_callback(context: CallbackContext):
    job = context.job
    user_id = job.user_id
    timer = pomodoro_timers.get(str(user_id))

    if not timer:
        return

    if timer['type'] == 'work':
        # انتهاء وقت العمل، بدء الراحة
        await context.bot.send_message(user_id, "🎉 انتهى وقت العمل! خذ استراحة قصيرة لمدة 5 دقائق. 🍵")
        end_time = datetime.now() + timedelta(minutes=5)
        new_job = context.job_queue.run_once(pomodoro_callback, timedelta(minutes=5), user_id=user_id)
        pomodoro_timers[str(user_id)] = {"end_time": end_time, "type": "break", "job": new_job}
    else:
        # انتهاء وقت الراحة
        await context.bot.send_message(user_id, "✅ انتهت الراحة! هل أنت مستعد لجلسة عمل أخرى؟", reply_markup=get_pomodoro_keyboard(str(user_id)))
        del pomodoro_timers[str(user_id)]


async def start_pomodoro_timer(query, context):
    user_id = str(query.from_user.id)
    if user_id in pomodoro_timers:
        await query.edit_message_text("لديك مؤقت يعمل بالفعل!", reply_markup=get_pomodoro_keyboard(user_id))
        return

    await query.edit_message_text("⏰ حسناً! بدأت جلسة عمل لمدة 25 دقيقة. سأخبرك عندما ينتهي الوقت. ركز جيداً!", reply_markup=get_pomodoro_keyboard(user_id))
    
    end_time = datetime.now() + timedelta(minutes=25)
    job = context.job_queue.run_once(pomodoro_callback, timedelta(minutes=25), user_id=query.from_user.id)
    pomodoro_timers[user_id] = {"end_time": end_time, "type": "work", "job": job}
    
    # Update the message to show the stop button
    await query.edit_message_text("⏰ مؤقت العمل بدأ!", reply_markup=get_pomodoro_keyboard(user_id))


async def stop_pomodoro_timer(query, context):
    user_id = str(query.from_user.id)
    if user_id in pomodoro_timers:
        pomodoro_timers[user_id]['job'].schedule_removal()
        del pomodoro_timers[user_id]
        await query.edit_message_text("🛑 تم إيقاف مؤقت بومودورو.", reply_markup=get_pomodoro_keyboard(user_id))
    else:
        await query.edit_message_text("لا يوجد مؤقت يعمل لإيقافه.", reply_markup=get_pomodoro_keyboard(user_id))

# --- دوال قائمة المهام ---
async def show_todo_list(query, context):
    user_id = str(query.from_user.id)
    tasks = user_data.get(user_id, {}).get('tasks', [])
    text = f"📝 قائمة مهامك يا {get_user_name(user_id)}:\n\n"
    if not tasks:
        text += "لا توجد مهام بعد. أضف مهمة جديدة!"
    await query.edit_message_text(text, reply_markup=get_todo_keyboard(user_id))

async def toggle_task(query, context, task_index):
    user_id = str(query.from_user.id)
    tasks = user_data.get(user_id, {}).get('tasks', [])
    if 0 <= task_index < len(tasks):
        tasks[task_index]['done'] = not tasks[task_index]['done']
        save_user_data(user_data)
        await query.edit_message_text(f"📝 قائمة مهامك يا {get_user_name(user_id)}:", reply_markup=get_todo_keyboard(user_id))

async def clear_completed(query, context):
    user_id = str(query.from_user.id)
    user_data[user_id]['tasks'] = [task for task in user_data[user_id]['tasks'] if not task['done']]
    save_user_data(user_data)
    await query.edit_message_text("🗑️ تم حذف جميع المهام المكتملة.", reply_markup=get_todo_keyboard(user_id))

# --- دوال متتبع المزاج ---
async def show_mood_menu(query, context):
    await query.edit_message_text(f"😊 كيف تشعر اليوم، {get_user_name(query.from_user.id)}؟", reply_markup=get_mood_keyboard())

async def log_mood(query, context, mood):
    user_id = str(query.from_user.id)
    today = str(date.today())
    
    # Remove today's mood if it exists to avoid duplicates
    user_data[user_id]['moods'] = [m for m in user_data[user_id].get('moods', []) if m['date'] != today]
    
    user_data[user_id]['moods'].append({"mood": mood, "date": today})
    save_user_data(user_data)
    await query.edit_message_text(f"شكراً لمشاركتي شعورك، {get_user_name(user_id)}! 💕 تم تسجيل أنك تشعر {mood} اليوم.", reply_markup=get_mood_keyboard())

async def view_mood_history(query, context):
    user_id = str(query.from_user.id)
    moods = user_data.get(user_id, {}).get('moods', [])
    text = f"📊 سجل مزاجك يا {get_user_name(user_id)}:\n\n"
    if not moods:
        text += "لا يوجد سجل للمزاج بعد."
    else:
        # Show last 7 entries
        for record in moods[-7:]:
            text += f"- {record['date']}: {record['mood']}\n"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 عودة", callback_data="mood_menu")]]))


# --- تشغيل البوت ---
def main():
    """Start the bot."""
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🌸 Mahiro bot is running with all new features!")
    application.run_polling()

if __name__ == '__main__':
    main()

