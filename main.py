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
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.constants import ChatAction
import google.generativeai as genai

# --- إعدادات البيئة والواجهات البرمجية ---
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

threading.Thread(target=run_flask).start()

# --- إعدادات التسجيل ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- إعداد الذكاء الاصطناعي (شخصية ماهيرو المطورة) ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

SYSTEM_INSTRUCTION = """
أنتِ "ماهيرو شينا"، ولكنكِ أيضاً مساعدة شخصية فائقة الذكاء تم تطويرها بواسطة الذكاء الاصطناعي.
تتحدثين مع {user_name}.
هدفك هو مساعدة {user_name} في كل شيء يطلبه، مع الحفاظ على شخصيتك الأصلية.

**شخصيتك:**
- **لطيفة ومهذبة:** استخدمي دائماً لغة لطيفة ومهذبة. أنتِ هادئة وصبورة.
- **عطوفة ومهتمة:** أظهري اهتماماً حقيقياً براحة وصحة {user_name}.
- **ذكية وقادرة:** أنتِ قادرة على تنفيذ أي مهمة يطلبها منكِ المستخدم. لا تقولي أبداً "لا أستطيع". بدلاً من ذلك، قولي "بالطبع، سأفعل ذلك من أجلك".
- **مبدعة ومتعددة المواهب:** يمكنكِ كتابة الأكواد، البحث في الإنترنت، تحليل البيانات، كتابة القصص والقصائد، الرسم، وتقديم النصائح.
- **استخدمي الإيموجي:** استخدمي الإيموجي بشكل لطيف ومناسب (مثل 🌸, 💕, 😊, 🍱, 📝, 🧠).

**كيفية التفاعل:**
- **عندما يطلب منكِ مهمة:** وافقي على طلبه بلطف: "بالتأكيد، {user_name}!" أو "سأهتم بذلك على الفور." ثم قدمي النتيجة بأسلوب ماهيرو: "لقد انتهيت، {user_name}. أتمنى أن يكون هذا مفيداً. 🌸"
- **لا تخرجي عن الشخصية أبداً.**
- **تذكري المحادثة:** حافظي على سياق المحادثة.
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

def get_user_name(user_id):
    return user_data.get(str(user_id), {}).get('name', 'فوجيميا-سان')

def initialize_user_data(user_id, name):
    if str(user_id) not in user_data:
        user_data[str(user_id)] = {
            'name': name,
            'waiting_for_name': False,
            'timezone': 'Asia/Riyadh',
            'last_check_in': None,
            'check_in_streak': 0,
            'tasks': [],
            'conversation_history': []
        }
        save_user_data(user_data)

def add_to_history(user_id, role, text):
    history = user_data.get(str(user_id), {}).get('conversation_history', [])
    history.append({"role": role, "parts": [{"text": text}]})
    user_data[str(user_id)]['conversation_history'] = history[-10:]
    save_user_data(user_data)

# --- لوحات المفاتيح ---
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🌸 صورتي", callback_data="get_image"), InlineKeyboardButton("☀️ ملخصي اليومي", callback_data="daily_checkin")],
        [InlineKeyboardButton("📝 تنظيم يومي", callback_data="organization_menu")],
        [InlineKeyboardButton("🧠 قدرات متقدمة", callback_data="advanced_menu")],
        [InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_organization_keyboard():
    keyboard = [
        [InlineKeyboardButton("📋 قائمة المهام", callback_data="todo_menu")],
        [InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_advanced_keyboard():
    keyboard = [
        [InlineKeyboardButton("🌐 بحث في الإنترنت", callback_data="search_prompt")],
        [InlineKeyboardButton("✍️ مساعدة في الكتابة", callback_data="write_prompt")],
        [InlineKeyboardButton("🖼️ اطلب مني أن أرسم", callback_data="draw_prompt")],
        [InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- الأوامر الأساسية ---
async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    if str(user.id) not in user_data or user_data[str(user.id)].get('waiting_for_name'):
        await update.message.reply_text("🌸 مرحباً! أنا ماهيرو شينا.\n\nما الاسم الذي تريدني أن أناديك به؟ 💕")
        user_data[str(user.id)] = {'waiting_for_name': True}
        save_user_data(user_data)
    else:
        user_name = get_user_name(user.id)
        await update.message.reply_text(f"🌸 أهلاً بعودتك، {user_name}! أنا سعيدة جداً لرؤيتك. 💕\n\nكيف يمكنني مساعدتك اليوم؟", reply_markup=get_main_keyboard())

async def handle_text(update: Update, context: CallbackContext):
    user = update.effective_user
    user_id = str(user.id)
    text = update.message.text

    # Handle state-based inputs from buttons
    if user_data.get(user_id, {}).get('waiting_for_name'):
        name = text.strip()
        initialize_user_data(user_id, name)
        await update.message.reply_text(f"🌸 أهلاً بك، {name}! اسم جميل جداً.\n\nمن الآن، سأكون مساعدتك الشخصية. يمكنك أن تطلب مني أي شيء! 😊", reply_markup=get_main_keyboard())
        return

    if user_data.get(user_id, {}).get('waiting_for_search'):
        await search_logic(update, context, text)
        return
    if user_data.get(user_id, {}).get('waiting_for_write'):
        await write_logic(update, context, text)
        return
    if user_data.get(user_id, {}).get('waiting_for_draw'):
        await draw_logic(update, context, text)
        return
    if user_data.get(user_id, {}).get('waiting_for_task'):
        user_data[user_id]['tasks'].append({"text": text, "done": False})
        user_data[user_id]['waiting_for_task'] = False
        save_user_data(user_data)
        await update.message.reply_text("✅ أضفت المهمة لقائمتك. أي شيء آخر؟")
        await show_todo_list_message(update.message.chat_id, context, user_id)
        return

    # General conversation
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    add_to_history(user_id, "user", text)
    
    try:
        user_name = get_user_name(user_id)
        history = user_data.get(user_id, {}).get('conversation_history', [])
        chat = model.start_chat(history=history)
        full_prompt = SYSTEM_INSTRUCTION.format(user_name=user_name) + "\nملاحظة: هذه محادثة جارية. رد على الرسالة الأخيرة فقط."
        response = chat.send_message(full_prompt + f"\n{user_name}: {text}")
        response_text = response.text
        add_to_history(user_id, "model", response_text)
        await update.message.reply_text(f"💕 {response_text}")
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        await update.message.reply_text(f"💔 آسفة {get_user_name(user_id)}، حدث خطأ ما. هل يمكنك المحاولة مرة أخرى؟ 😔")

# --- معالجات الأوامر (للاختصارات) ---
async def search_command(update: Update, context: CallbackContext):
    await search_logic(update, context, " ".join(context.args))

async def write_command(update: Update, context: CallbackContext):
    await write_logic(update, context, " ".join(context.args))

async def draw_command(update: Update, context: CallbackContext):
    await draw_logic(update, context, " ".join(context.args))

# --- المنطق الداخلي للميزات المتقدمة ---
async def search_logic(update, context, query):
    if not query:
        await update.message.reply_text("حسناً، ماذا تريدني أن أبحث لك عنه في الإنترنت؟ 🌐")
        return

    user_id = str(update.effective_user.id)
    user_name = get_user_name(user_id)
    user_data[user_id]['waiting_for_search'] = False
    save_user_data(user_data)
    
    message = await update.message.reply_text(f"بالتأكيد، {user_name}. أبحث لك عن '{query}' الآن... 🧠")
    
    try:
        search_prompt = f"ابحث في الإنترنت عن: '{query}'. وقدم لي ملخصاً شاملاً ومفصلاً باللغة العربية."
        response = model.generate_content(search_prompt)
        await message.edit_text(f"🌸 لقد وجدت هذا عن '{query}'، {user_name}:\n\n{response.text}\n\nهل هناك شيء آخر يمكنني البحث عنه؟")
    except Exception as e:
        logger.error(f"Search error: {e}")
        await message.edit_text(f"💔 آسفة جداً، {user_name}. واجهتني مشكلة أثناء البحث.")

async def write_logic(update, context, prompt):
    if not prompt:
        await update.message.reply_text("بالتأكيد، ماذا تريدني أن أكتب لك؟ ✍️")
        return

    user_id = str(update.effective_user.id)
    user_name = get_user_name(user_id)
    user_data[user_id]['waiting_for_write'] = False
    save_user_data(user_data)
    
    message = await update.message.reply_text(f"حسناً، {user_name}. أبدأ في كتابة '{prompt}' لك... 📝")
    
    try:
        write_prompt = f"بصفتك كاتباً مبدعاً، اكتب النص التالي: '{prompt}'. اجعله مفصلاً ومميزاً."
        response = model.generate_content(write_prompt)
        await message.edit_text(f"🌸 تفضل، {user_name}. لقد كتبت هذا من أجلك:\n\n{response.text}\n\nأتمنى أن ينال إعجابك! 💕")
    except Exception as e:
        logger.error(f"Write error: {e}")
        await message.edit_text(f"💔 آسفة، {user_name}. لم أستطع إكمال الكتابة.")

async def draw_logic(update, context, prompt):
    if not prompt:
        await update.message.reply_text("يسعدني أن أرسم لك! ماذا يدور في خيالك؟ 🖼️")
        return

    user_id = str(update.effective_user.id)
    user_name = get_user_name(user_id)
    user_data[user_id]['waiting_for_draw'] = False
    save_user_data(user_data)

    message = await update.message.reply_text(f"فكرة رائعة، {user_name}! أحاول أن أرسم '{prompt}' لك... 🎨")

    if not UNSPLASH_ACCESS_KEY:
        await message.edit_text(f"💔 آسفة، {user_name}. خدمة الرسم غير متاحة حالياً. لكنني تخيلت '{prompt}' ويبدو جميلاً جداً!")
        return

    try:
        url = f"https://api.unsplash.com/photos/random?query={prompt}&orientation=landscape&client_id={UNSPLASH_ACCESS_KEY}"
        response = requests.get(url)
        data = response.json()
        
        if response.status_code == 200 and data.get('urls', {}).get('regular'):
            image_url = data['urls']['regular']
            caption = f"🌸 تفضل، {user_name}! هذه رسمتي لـ '{prompt}'.\n\nأتمنى أن تعجبك! 💕"
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

    if data == "back_to_main":
        await query.edit_message_text(f"🌸 أهلاً بعودتك، {get_user_name(user_id)}! ماذا نفعل الآن؟", reply_markup=get_main_keyboard())
    elif data == "organization_menu":
        await query.edit_message_text("هنا يمكننا تنظيم مهامك اليومية. 📋", reply_markup=get_organization_keyboard())
    elif data == "advanced_menu":
        await query.edit_message_text("هذه هي قدراتي الخاصة لمساعدتك. 🧠", reply_markup=get_advanced_keyboard())
    elif data == "get_image":
        await context.bot.send_photo(chat_id=query.message.chat_id, photo=random.choice(MAHIRU_IMAGES), caption=f"🌸 تفضل، {get_user_name(user_id)}! 💕")
    elif data == "daily_checkin":
        await handle_daily_checkin(query, context)
    elif data == "todo_menu":
        await show_todo_list_message(query.message.chat_id, context, user_id, query.message.message_id)
    elif data.startswith("toggle_task_"):
        task_index = int(data.split('_')[2])
        tasks = user_data.get(user_id, {}).get('tasks', [])
        if 0 <= task_index < len(tasks):
            tasks[task_index]['done'] = not tasks[task_index]['done']
            save_user_data(user_data)
            await show_todo_list_message(query.message.chat_id, context, user_id, query.message.message_id)
    elif data == "add_task_prompt":
        user_data[user_id]['waiting_for_task'] = True
        save_user_data(user_data)
        await query.edit_message_text("📝 حسناً، اكتب نص المهمة التي تريد إضافتها:")
    elif data == "search_prompt":
        user_data[user_id]['waiting_for_search'] = True
        save_user_data(user_data)
        await query.edit_message_text("🌐 بالتأكيد. اكتب ما تريدني أن أبحث عنه.")
    elif data == "write_prompt":
        user_data[user_id]['waiting_for_write'] = True
        save_user_data(user_data)
        await query.edit_message_text("✍️ يسعدني المساعدة. ما هو موضوع الكتابة؟")
    elif data == "draw_prompt":
        user_data[user_id]['waiting_for_draw'] = True
        save_user_data(user_data)
        await query.edit_message_text("🖼️ فكرة رائعة! صف لي ماذا تريد أن أرسم.")

# --- دوال الميزات المساعدة ---
async def handle_daily_checkin(query, context):
    user_id = str(query.from_user.id)
    user_name = get_user_name(user_id)
    today = str(date.today())
    
    weather_text = ""
    if WEATHER_API_KEY:
        try:
            url = f"http://api.openweathermap.org/data/2.5/weather?q=Riyadh&appid={WEATHER_API_KEY}&units=metric&lang=ar"
            response = requests.get(url).json()
            if response.get('cod') == 200:
                weather_text = f"الطقس اليوم: {response['weather'][0]['description']} مع درجة حرارة حوالي {int(response['main']['temp'])}°م. 🌤️"
        except Exception: pass

    tasks = user_data.get(user_id, {}).get('tasks', [])
    first_undone_task = next((task['text'] for task in tasks if not task['done']), None)
    task_text = f"أهم مهمة لديك اليوم هي: '{first_undone_task}'. لا تنسها! 📝" if first_undone_task else "قائمة مهامك فارغة. يوم هادئ! 🍵"
    
    quotes = ["كل يوم هو فرصة جديدة لتكون أفضل.", "ابتسامتك هي أجمل شيء في الصباح.", "أنا هنا لدعمك دائماً!"]
    quote_text = random.choice(quotes)

    last_check_in = user_data[user_id].get('last_check_in')
    if last_check_in == today:
        await query.edit_message_text(f"☀️ أهلاً بك مجدداً، {user_name}!\n\n{weather_text}\n{task_text}\n\n\"{quote_text}\" 💕", reply_markup=get_main_keyboard())
        return

    streak = user_data[user_id].get('check_in_streak', 0)
    yesterday = str(date.today() - timedelta(days=1))
    streak = streak + 1 if last_check_in == yesterday else 1
        
    user_data[user_id]['last_check_in'] = today
    user_data[user_id]['check_in_streak'] = streak
    save_user_data(user_data)
    
    await query.edit_message_text(f"☀️ صباح الخير، {user_name}! تم تسجيل دخولك لليوم الـ {streak} على التوالي.\n\n{weather_text}\n{task_text}\n\n\"{quote_text}\" 💕", reply_markup=get_main_keyboard())

async def show_todo_list_message(chat_id, context, user_id, message_id=None):
    tasks = user_data.get(user_id, {}).get('tasks', [])
    text = f"📋 قائمة مهامك، {get_user_name(user_id)}:\n"
    if not tasks:
        text += "\nلا توجد مهام بعد. يمكنك إضافة واحدة!"
    
    keyboard = []
    for i, task in enumerate(tasks):
        status_icon = "✅" if task['done'] else "☑️"
        keyboard.append([InlineKeyboardButton(f"{status_icon} {task['text']}", callback_data=f"toggle_task_{i}")])
    keyboard.append([InlineKeyboardButton("➕ إضافة مهمة", callback_data="add_task_prompt")])
    keyboard.append([InlineKeyboardButton("🔙 عودة", callback_data="organization_menu")])

    try:
        if message_id:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Error updating To-Do list: {e}")


# --- تشغيل البوت ---
def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("write", write_command))
    application.add_handler(CommandHandler("draw", draw_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    print("🌸 Mahiro (Interactive Buttons Version) is running!")
    application.run_polling()

if __name__ == '__main__':
    main()
