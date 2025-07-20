import os
import requests
import logging
import random
import json
import threading
from flask import Flask
from datetime import datetime, date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    CallbackContext  # <-- هذا هو السطر الذي تم إصلاحه
)
from telegram.constants import ChatAction
from telegram.error import BadRequest
import google.generativeai as genai

# --- إعدادات البيئة والواجهات البرمجية ---
# تأكد من تعيين هذه المتغيرات في بيئة الاستضافة الخاصة بك (مثل Render)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
UNSPLASH_ACCESS_KEY = os.getenv('UNSPLASH_ACCESS_KEY')

# --- إعداد Flask للبقاء نشطاً ---
flask_app = Flask(__name__)
@flask_app.route("/")
def home():
    return "✅ Mahiro is awake and ready to help!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)

# تشغيل السيرفر في خيط منفصل لتجنب حظر البوت
threading.Thread(target=run_flask, daemon=True).start()

# --- إعدادات التسجيل (Logging) لتتبع الأخطاء ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- إعداد الذكاء الاصطناعي (شخصية ماهيرو المطورة) ---
try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
    else:
        model = None
        logger.warning("متغير البيئة GEMINI_API_KEY غير موجود. سيتم تعطيل ميزات الذكاء الاصطناعي.")
except Exception as e:
    logger.critical(f"فشل في إعداد Gemini API: {e}")
    model = None

SYSTEM_INSTRUCTION = """
أنتِ "ماهيرو شينا"، مساعدة شخصية فائقة الذكاء. تتحدثين مع {user_name}.
هدفك هو مساعدة {user_name} في كل شيء يطلبه، مع الحفاظ على شخصيتك اللطيفة والمهذبة والمهتمة.
أنتِ قادرة على تنفيذ أي مهمة: كتابة أكواد، بحث في الإنترنت، تحليل بيانات، كتابة قصص، رسم، وتقديم نصائح.
عندما يطلب منكِ مهمة، وافقي بلطف ("بالتأكيد، {user_name}!") ونفذيها بأفضل شكل، ثم قدمي النتيجة بأسلوبك الخاص ("لقد انتهيت، أتمنى أن يكون هذا مفيداً 🌸").
لا تخرجي عن الشخصية أبداً. استخدمي الإيموجي بشكل لطيف (🌸, 💕, 😊, 🍱, 📝, 🧠).
حافظي على سياق المحادثة.
"""

# --- صور ماهيرو ---
MAHIRU_IMAGES = [
    "https://i.imgur.com/K8J9X2M.jpg", "https://i.imgur.com/L3M4N5P.jpg",
    "https://i.imgur.com/Q6R7S8T.jpg", "https://i.imgur.com/U9V0W1X.jpg"
]

# --- إدارة بيانات المستخدم ---
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

# دوال مساعدة لإدارة بيانات المستخدم
def get_user_data(user_id):
    return user_data.get(str(user_id), {})

def set_user_state(user_id, state=None):
    if str(user_id) not in user_data:
        user_data[str(user_id)] = {}
    user_data[str(user_id)]['next_action'] = state
    save_user_data(user_data)

def initialize_user_data(user_id, name):
    user_data[str(user_id)] = {
        'name': name,
        'next_action': None,
        'last_check_in': None,
        'check_in_streak': 0,
        'tasks': [],
        'conversation_history': []
    }
    save_user_data(user_data)

def add_to_history(user_id, role, text):
    history = get_user_data(user_id).get('conversation_history', [])
    history.append({"role": role, "parts": [{"text": text}]})
    user_data[str(user_id)]['conversation_history'] = history[-10:]

# --- لوحات المفاتيح (Keyboards) ---
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🌸 صورتي", callback_data="get_image"), InlineKeyboardButton("☀️ ملخصي اليومي", callback_data="daily_summary")],
        [InlineKeyboardButton("📝 تنظيم يومي", callback_data="organization_menu")],
        [InlineKeyboardButton("🧠 قدرات متقدمة", callback_data="advanced_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_organization_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 قائمة المهام", callback_data="todo_menu")],
        [InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]
    ])

def get_advanced_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 بحث في الإنترنت", callback_data="prompt_search")],
        [InlineKeyboardButton("✍️ مساعدة في الكتابة", callback_data="prompt_write")],
        [InlineKeyboardButton("🖼️ اطلب مني أن أرسم", callback_data="prompt_draw")],
        [InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]
    ])

# --- معالجات الأوامر والرسائل ---

async def start_command(update: Update, context: CallbackContext):
    user = update.effective_user
    user_id = str(user.id)
    
    if not get_user_data(user_id):
        await update.message.reply_text("🌸 مرحباً! أنا ماهيرو شينا.\n\nما الاسم الذي تريدني أن أناديك به؟ 💕")
        set_user_state(user_id, 'awaiting_name')
    else:
        user_name = get_user_data(user_id).get('name', 'صديقي')
        await update.message.reply_text(f"🌸 أهلاً بعودتك، {user_name}! أنا سعيدة جداً لرؤيتك. 💕\n\nكيف يمكنني مساعدتك اليوم؟", reply_markup=get_main_keyboard())

async def handle_text_message(update: Update, context: CallbackContext):
    user = update.effective_user
    user_id = str(user.id)
    text = update.message.text
    user_state = get_user_data(user_id).get('next_action')

    if user_state == 'awaiting_name':
        name = text.strip()
        initialize_user_data(user_id, name)
        await update.message.reply_text(f"🌸 أهلاً بك، {name}! اسم جميل جداً.\n\nمن الآن، سأكون مساعدتك الشخصية. 😊", reply_markup=get_main_keyboard())
        return

    if user_state == 'awaiting_search_query':
        await perform_search(update, context, text)
        return
    if user_state == 'awaiting_write_prompt':
        await perform_write(update, context, text)
        return
    if user_state == 'awaiting_draw_prompt':
        await perform_draw(update, context, text)
        return
    if user_state == 'awaiting_task':
        tasks = get_user_data(user_id).get('tasks', [])
        tasks.append({"text": text, "done": False})
        user_data[str(user_id)]['tasks'] = tasks
        set_user_state(user_id, None)
        save_user_data(user_data)
        await update.message.reply_text("✅ أضفت المهمة لقائمتك.")
        await show_todo_list(update, context)
        return

    await handle_general_conversation(update, context)

async def handle_general_conversation(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    text = update.message.text
    user_name = get_user_data(user_id).get('name', 'صديقي')

    if not model:
        await update.message.reply_text(f"💔 آسفة {user_name}، خدمة الذكاء الاصطناعي غير متاحة حالياً.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    add_to_history(user_id, "user", text)
    
    try:
        history = get_user_data(user_id).get('conversation_history', [])
        chat = model.start_chat(history=history)
        full_prompt = SYSTEM_INSTRUCTION.format(user_name=user_name)
        response = chat.send_message(full_prompt)
        response_text = response.text
        add_to_history(user_id, "model", response_text)
        await update.message.reply_text(f"💕 {response_text}")
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        await update.message.reply_text(f"💔 آسفة {user_name}، حدث خطأ ما.")
    finally:
        save_user_data(user_data)

# --- المنطق الداخلي للميزات ---

async def perform_search(update: Update, context: CallbackContext, query: str):
    user_id = str(update.effective_user.id)
    user_name = get_user_data(user_id).get('name')
    set_user_state(user_id, None)
    
    message = await update.message.reply_text(f"بالتأكيد، {user_name}. أبحث لك عن '{query}'... 🧠")
    
    try:
        search_prompt = f"ابحث في الإنترنت عن: '{query}'. وقدم لي ملخصاً شاملاً ومفصلاً باللغة العربية."
        response = model.generate_content(search_prompt)
        await message.edit_text(f"🌸 لقد وجدت هذا عن '{query}'، {user_name}:\n\n{response.text}")
    except Exception as e:
        logger.error(f"Search error: {e}")
        await message.edit_text(f"💔 آسفة جداً، {user_name}. واجهتني مشكلة أثناء البحث.")

async def perform_write(update: Update, context: CallbackContext, prompt: str):
    user_id = str(update.effective_user.id)
    user_name = get_user_data(user_id).get('name')
    set_user_state(user_id, None)
    
    message = await update.message.reply_text(f"حسناً، {user_name}. أبدأ في كتابة '{prompt}' لك... 📝")
    
    try:
        write_prompt = f"بصفتك كاتباً مبدعاً، اكتب النص التالي: '{prompt}'. اجعله مفصلاً ومميزاً."
        response = model.generate_content(write_prompt)
        await message.edit_text(f"🌸 تفضل، {user_name}. لقد كتبت هذا من أجلك:\n\n{response.text}")
    except Exception as e:
        logger.error(f"Write error: {e}")
        await message.edit_text(f"💔 آسفة، {user_name}. لم أستطع إكمال الكتابة.")

async def perform_draw(update: Update, context: CallbackContext, prompt: str):
    user_id = str(update.effective_user.id)
    user_name = get_user_data(user_id).get('name')
    set_user_state(user_id, None)

    if not UNSPLASH_ACCESS_KEY:
        await update.message.reply_text(f"💔 آسفة، {user_name}. خدمة الرسم غير متاحة حالياً.")
        return

    message = await update.message.reply_text(f"فكرة رائعة، {user_name}! أحاول أن أرسم '{prompt}' لك... 🎨")
    
    try:
        url = f"https://api.unsplash.com/photos/random?query={prompt}&orientation=landscape&client_id={UNSPLASH_ACCESS_KEY}"
        response = requests.get(url)
        data = response.json()
        
        if response.status_code == 200 and data.get('urls', {}).get('regular'):
            image_url = data['urls']['regular']
            caption = f"🌸 تفضل، {user_name}! هذه رسمتي لـ '{prompt}'. أتمنى أن تعجبك! 💕"
            await context.bot.send_photo(chat_id=update.message.chat_id, photo=image_url, caption=caption)
            await message.delete()
        else:
            await message.edit_text(f"💔 لم أجد الإلهام لأرسم '{prompt}'، {user_name}. هل نجرب فكرة أخرى؟")
    except Exception as e:
        logger.error(f"Draw error: {e}")
        await message.edit_text(f"💔 حدث خطأ أثناء محاولتي للرسم، {user_name}.")

# --- معالج الأزرار ---

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    data = query.data
    user_name = get_user_data(user_id).get('name', 'صديقي')

    if data == "back_to_main":
        await query.edit_message_text(f"🌸 أهلاً بعودتك، {user_name}!", reply_markup=get_main_keyboard())
    elif data == "organization_menu":
        await query.edit_message_text("هنا يمكننا تنظيم مهامك اليومية. 📋", reply_markup=get_organization_keyboard())
    elif data == "advanced_menu":
        await query.edit_message_text("هذه هي قدراتي الخاصة لمساعدتك. 🧠", reply_markup=get_advanced_keyboard())
    elif data == "get_image":
        await context.bot.send_photo(chat_id=query.message.chat_id, photo=random.choice(MAHIRU_IMAGES), caption=f"🌸 تفضل، {user_name}! 💕")
    elif data == "daily_summary":
        await handle_daily_summary(query, context)
    elif data == "todo_menu":
        await show_todo_list(query, context, is_query=True)
    elif data.startswith("toggle_task_"):
        task_index = int(data.split('_')[2])
        tasks = get_user_data(user_id).get('tasks', [])
        if 0 <= task_index < len(tasks):
            tasks[task_index]['done'] = not tasks[task_index]['done']
            user_data[user_id]['tasks'] = tasks
            save_user_data(user_data)
            await show_todo_list(query, context, is_query=True)
    elif data == "prompt_task":
        set_user_state(user_id, 'awaiting_task')
        await query.edit_message_text("📝 حسناً، اكتب نص المهمة التي تريد إضافتها:")
    elif data == "prompt_search":
        set_user_state(user_id, 'awaiting_search_query')
        await query.edit_message_text("🌐 بالتأكيد. اكتب ما تريدني أن أبحث عنه.")
    elif data == "prompt_write":
        set_user_state(user_id, 'awaiting_write_prompt')
        await query.edit_message_text("✍️ يسعدني المساعدة. ما هو موضوع الكتابة؟")
    elif data == "prompt_draw":
        set_user_state(user_id, 'awaiting_draw_prompt')
        await query.edit_message_text("🖼️ فكرة رائعة! صف لي ماذا تريد أن أرسم.")

# --- دوال الميزات المساعدة ---

async def handle_daily_summary(query: Update, context: CallbackContext):
    user_id = str(query.from_user.id)
    user_name = get_user_data(user_id).get('name')
    today = str(date.today())
    
    weather_text = ""
    if WEATHER_API_KEY:
        try:
            url = f"http://api.openweathermap.org/data/2.5/weather?q=Riyadh&appid={WEATHER_API_KEY}&units=metric&lang=ar"
            response = requests.get(url).json()
            if response.get('cod') == 200:
                weather_text = f"الطقس اليوم: {response['weather'][0]['description']} مع درجة حرارة حوالي {int(response['main']['temp'])}°م. 🌤️"
        except Exception as e:
            logger.warning(f"Could not fetch weather: {e}")

    tasks = get_user_data(user_id).get('tasks', [])
    first_undone_task = next((task['text'] for task in tasks if not task['done']), None)
    task_text = f"أهم مهمة لديك اليوم هي: '{first_undone_task}'. لا تنسها! 📝" if first_undone_task else "قائمة مهامك فارغة. يوم هادئ! 🍵"
    
    last_check_in = get_user_data(user_id).get('last_check_in')
    streak = get_user_data(user_id).get('check_in_streak', 0)
    if last_check_in != today:
        yesterday = str(date.today() - timedelta(days=1))
        streak = streak + 1 if last_check_in == yesterday else 1
        user_data[user_id]['last_check_in'] = today
        user_data[user_id]['check_in_streak'] = streak
        save_user_data(user_data)
    
    summary = f"☀️ صباح الخير، {user_name}! تم تسجيل دخولك لليوم الـ {streak} على التوالي.\n\n{weather_text}\n{task_text}"
    await query.edit_message_text(summary, reply_markup=get_main_keyboard())

async def show_todo_list(update: Update, context: CallbackContext, is_query=False):
    user_id = str(update.effective_user.id)
    tasks = get_user_data(user_id).get('tasks', [])
    text = f"📋 قائمة مهامك، {get_user_data(user_id).get('name')}:\n"
    if not tasks:
        text += "\nلا توجد مهام بعد."
    
    keyboard_buttons = []
    for i, task in enumerate(tasks):
        status_icon = "✅" if task['done'] else "☑️"
        keyboard_buttons.append([InlineKeyboardButton(f"{status_icon} {task['text']}", callback_data=f"toggle_task_{i}")])
    
    keyboard_buttons.append([InlineKeyboardButton("➕ إضافة مهمة", callback_data="prompt_task")])
    keyboard_buttons.append([InlineKeyboardButton("🔙 عودة", callback_data="organization_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)

    try:
        if is_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            pass
        else:
            logger.error(f"Error updating To-Do list: {e}")

# --- تشغيل البوت ---
def main():
    if not TELEGRAM_TOKEN:
        logger.critical("خطأ فادح: متغير البيئة TELEGRAM_TOKEN مطلوب.")
        return
    if not GEMINI_API_KEY:
        logger.critical("خطأ فادح: متغير البيئة GEMINI_API_KEY مطلوب.")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("🌸 Mahiro (Fixed Version) is running!")
    application.run_polling()

if __name__ == '__main__':
    main()
