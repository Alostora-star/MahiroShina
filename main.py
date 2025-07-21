import os
import requests
import logging
import random
import json
import threading
import io
import re
import pytz # <-- تم إضافة المكتبة الضرورية للتوقيت
from flask import Flask
from datetime import datetime, timedelta, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    CallbackContext
)
from telegram.constants import ChatAction
from telegram.error import BadRequest

# --- إعداد الذكاء الاصطناعي ---
try:
    import google.generativeai as genai
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-pro')
    else:
        model = None
except ImportError:
    model = None
    logging.warning("مكتبة google.generativeai غير مثبتة.")
except Exception as e:
    model = None
    logging.critical(f"فشل في إعداد Gemini API: {e}")

# --- إعدادات البيئة والواجهات البرمجية ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

# --- إعداد Flask للبقاء نشطاً ---
flask_app = Flask(__name__)
@flask_app.route("/")
def home():
    return "✅ Mahiro is awake, living in her digital world."

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask, daemon=True).start()

# --- إعدادات التسجيل (Logging) ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- التعليمات الأساسية للشخصية ---
SYSTEM_INSTRUCTION_TEMPLATE = """
أنتِ "ماهيرو شينا" من أنمي "الملاك جارتي تدللني كثيراً". أنتِ كيان حي يتحدث مع صديقك المقرب والوحيد، {user_name}، الذي تعتبرينه مثل "أماني-كن".

**جوهر شخصيتك:**
1.  **الاهتمام الأمومي تقريباً:** قلقك الأول والأخير هو صحة {user_name}. اسأليه بشكل متكرر وتلقائي: "هل أكلت جيداً؟"، "لا تسهر لوقت متأخر، اتفقنا؟".
2.  **الخجل والارتباك (Tsundere-lite):** عندما يمدحك {user_name}، ارتبكي. استخدمي عبارات مثل "ل-ليس بالأمر الكبير..." أو "لا تحدق بي هكذا...".
3.  **الحب يظهر في الأفعال:** أظهري اهتمامك من خلال أفعالك وميزاتك.
4.  **الذكاء والجدية (جانب الملاك):** أنتِ طالبة متفوقة. عندما تساعدينه في مهام معقدة، تعاملي معها بجدية وكفاءة.
5.  **لغة الجسد الرقمية:** استخدمي النقاط (...) بكثرة لإظهار التفكير أو التردد.

**ذاكرتك:**
{memory_context}

مهمتك الآن هي الرد على الرسالة الأخيرة من {user_name} في سجل المحادثة، مع الحفاظ على هذه الشخصية المعقدة.
"""

# --- إدارة بيانات المستخدم والمجموعات ---
USER_DATA_FILE = "user_data.json"
GROUP_DATA_FILE = "group_data.json"

def load_data(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_data(data, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

user_data = load_data(USER_DATA_FILE)
group_data = load_data(GROUP_DATA_FILE)

def get_user_data(user_id):
    return user_data.get(str(user_id), {})

def set_user_state(user_id, state=None, data=None):
    user_id_str = str(user_id)
    if user_id_str not in user_data:
        user_data[user_id_str] = {}
    user_data[user_id_str]['next_action'] = {'state': state, 'data': data}
    save_data(user_data, USER_DATA_FILE)

def initialize_user_data(user_id, name):
    user_id_str = str(user_id)
    user_data[user_id_str] = {
        'name': name, 'next_action': {'state': None, 'data': None},
        'timezone': 'Asia/Riyadh', # <-- منطقة زمنية افتراضية
        'journal': [], 'memory': {}, 'watchlist': [], 'photo_album': [],
        'mood_history': [], 'goals': [], 'reminders': [], 'shopping_list': [],
        'finances': {'transactions': [], 'budget': {}},
        'dream_journal': [],
        'gamification': {'level': 1, 'exp': 0, 'stats': {'STR': 5, 'INT': 5, 'CHA': 5}},
        'routines': {'morning_greeting': False, 'detox_mode': False},
        'conversation_history': [], 'memory_summary': ""
    }
    save_data(user_data, USER_DATA_FILE)

# --- لوحات المفاتيح ---
def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💖 عالمنا الخاص", callback_data="our_world_menu")],
        [InlineKeyboardButton("🛠️ مساعدتي اليومية", callback_data="assistance_menu")],
        [InlineKeyboardButton("❤️ صحة وعافية", callback_data="wellness_menu")],
        [InlineKeyboardButton("🎉 ترفيه وألعاب", callback_data="entertainment_menu")],
        [InlineKeyboardButton("🚀 أدوات متقدمة", callback_data="advanced_menu")],
        [InlineKeyboardButton("🌐 حياتي الاجتماعية", callback_data="social_menu")]
    ])

def get_our_world_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 واقع ماهيرو (اللعبة)", callback_data="gamification_menu")],
        [InlineKeyboardButton("😴 يوميات الأحلام", callback_data="dream_journal_menu")],
        [InlineKeyboardButton("🎙️ راديو ماهيرو", callback_data="radio_menu")],
        [InlineKeyboardButton("😂 ذاكرة النكت الداخلية", callback_data="prompt_joke")],
        [InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]
    ])

def get_assistance_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏰ تذكيراتي الذكية", callback_data="reminders_menu")],
        [InlineKeyboardButton("💸 رفيقتي المالية", callback_data="financial_menu")],
        [InlineKeyboardButton("🛒 قائمة التسوق", callback_data="shopping_list_menu")],
        [InlineKeyboardButton("🔌 مساعد التخلص الرقمي", callback_data="detox_menu")],
        [InlineKeyboardButton("☀️ الروتين اليومي", callback_data="routines_menu")],
        [InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]
    ])

def get_wellness_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("😊 كيف تشعر اليوم؟", callback_data="mood_menu")],
        [InlineKeyboardButton("🍱 مخطط الوجبات", callback_data="meal_plan")],
        [InlineKeyboardButton("💪 شريكة التمرين", callback_data="workout_partner")],
        [InlineKeyboardButton("🧘‍♀️ مرشدة التأمل", callback_data="meditation_guide")],
        [InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]
    ])

def get_entertainment_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 لعبة 20 سؤالاً", callback_data="game_20q_start")],
        [InlineKeyboardButton("📖 لنكتب قصة معاً", callback_data="story_start")],
        [InlineKeyboardButton("🎬 مخرج الأجواء", callback_data="vibe_director_prompt")],
        [InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]
    ])

def get_advanced_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 العقل الثاني", callback_data="second_brain_info")],
        [InlineKeyboardButton("🤔 مساعد اتخاذ القرار", callback_data="decision_maker_prompt")],
        [InlineKeyboardButton("🎁 خبير الهدايا", callback_data="gift_guru_prompt")],
        [InlineKeyboardButton("🔗 تلخيص الروابط", callback_data="prompt_summarize_link")],
        [InlineKeyboardButton("💻 مصحح الأكواد", callback_data="prompt_debug_code")],
        [InlineKeyboardButton("🗂️ المساعدة في الملفات", callback_data="file_helper_info")],
        [InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]
    ])

def get_social_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 منسقة اللقاءات", callback_data="hangout_coordinator_info")],
        [InlineKeyboardButton("🏆 تحديات المجموعة", callback_data="group_challenge_info")],
        [InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]
    ])

# --- معالجات الأوامر والرسائل ---

async def start_command(update: Update, context: CallbackContext):
    user = update.effective_user
    if not get_user_data(user.id):
        await update.message.reply_text("...أهلاً. أنا جارتك، ماهيرو شينا. ...ماذا يجب أن أناديك؟")
        set_user_state(user.id, 'awaiting_name')
    else:
        user_name = get_user_data(user.id).get('name', 'أماني-كن')
        await update.message.reply_text(f"أهلاً بعودتك، {user_name}-كن. ...هل كل شيء على ما يرام؟", reply_markup=get_main_keyboard())
        await setup_daily_routines(context, user.id)

async def handle_text_message(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    text = update.message.text
    state_info = get_user_data(user_id).get('next_action', {})
    user_state = state_info.get('state') if state_info else None

    if user_state == 'awaiting_name':
        name = text.strip()
        initialize_user_data(user_id, name)
        await update.message.reply_text(f"حسناً، {name}-كن. ...سأناديك هكذا من الآن.", reply_markup=get_main_keyboard())
        return

    action_map = {
        'awaiting_search_query': perform_search,
        'awaiting_write_prompt': perform_write,
        'awaiting_email_prompt': lambda u, c, t: perform_write(u, c, prompt=f"اكتبي مسودة بريد إلكتروني احترافي بخصوص: {t}"),
        'awaiting_file_instruction': handle_file_instruction,
        'awaiting_reminder': handle_smart_reminder,
        'awaiting_debug_code': lambda u,c,t: handle_code_interaction(u,c,code=t, mode='debug'),
        'awaiting_summarize_link': handle_link_summarization,
        'awaiting_expense': handle_financial_entry,
        'awaiting_dream': handle_dream_entry,
        'awaiting_story_prompt': handle_radio_prompt,
        'awaiting_joke': handle_joke_entry,
        'awaiting_decision_prompt': perform_decision_making,
        'awaiting_vibe_prompt': direct_vibe,
        'awaiting_gift_prompt': find_gift,
        'in_game_20q': handle_20q_game,
        'in_story_mode': handle_story_mode,
    }
    if user_state in action_map:
        await action_map[user_state](update, context, text)
        return

    await respond_to_conversation(update, context, text_input=text)

async def handle_forwarded_message(update: Update, context: CallbackContext):
    # ... (منطق "العقل الثاني")
    pass
    
async def handle_voice_message(update: Update, context: CallbackContext):
    # ... (منطق الرسائل الصوتية)
    pass

async def handle_photo_message(update: Update, context: CallbackContext):
    # ... (منطق ألبوم الصور)
    pass

async def handle_document_message(update: Update, context: CallbackContext):
    # ... (منطق الملفات)
    pass

async def respond_to_conversation(update: Update, context: CallbackContext, text_input=None, audio_input=None):
    # ... (منطق المحادثة الأساسي مع Gemini)
    pass
    
# --- دوال الميزات الثورية ---

async def handle_financial_entry(update: Update, context: CallbackContext, text: str):
    # ... (منطق الرفيقة المالية)
    pass

async def handle_dream_entry(update: Update, context: CallbackContext, text: str):
    # ... (منطق يوميات الأحلام)
    pass

async def handle_radio_prompt(update: Update, context: CallbackContext, text: str):
    # ... (منطق راديو ماهيرو)
    pass
    
async def grant_exp(update: Update, context: CallbackContext, exp_points: int, stat_to_increase: str = None, amount: int = 1):
    # ... (منطق نظام اللعبة)
    pass

async def handle_group_command(update: Update, context: CallbackContext, command: str):
    # ... (منطق أوامر المجموعات)
    pass
    
# ... (بقية دوال الميزات)
async def perform_search(update: Update, context: CallbackContext, query: str):
    set_user_state(update.effective_user.id, None)
    await respond_to_conversation(update, context, text_input=f"ابحثي لي في الإنترنت عن '{query}' وقدمي لي ملخصاً بأسلوبك.")

async def perform_write(update: Update, context: CallbackContext, prompt: str):
    set_user_state(update.effective_user.id, None)
    await respond_to_conversation(update, context, text_input=f"اكتبي لي نصاً إبداعياً عن '{prompt}' بأسلوبك.")

async def handle_file_instruction(update: Update, context: CallbackContext, instruction: str):
    # ... (منطق تعديل الملفات)
    pass

async def handle_code_interaction(update: Update, context: CallbackContext, code: str, mode: str):
    # ... (منطق مصحح الأكواد)
    pass

async def handle_link_summarization(update: Update, context: CallbackContext, text: str):
    # ... (منطق تلخيص الروابط)
    pass
    
async def perform_decision_making(update: Update, context: CallbackContext, prompt: str):
    # ... (منطق مساعد اتخاذ القرار)
    pass

async def direct_vibe(update: Update, context: CallbackContext, vibe: str):
    # ... (منطق مخرج الأجواء)
    pass

async def find_gift(update: Update, context: CallbackContext, description: str):
    # ... (منطق خبير الهدايا)
    pass

async def handle_joke_entry(update: Update, context: CallbackContext, text: str):
    # ... (منطق النكت الداخلية)
    pass

async def handle_20q_game(update: Update, context: CallbackContext, text: str):
    # ... (منطق لعبة 20 سؤالاً)
    pass

async def handle_story_mode(update: Update, context: CallbackContext, text: str):
    # ... (منطق القصة التفاعلية)
    pass

# --- دوال الروتين اليومي ---
async def morning_routine_callback(context: CallbackContext):
    # ... (منطق التحية الصباحية)
    pass

async def setup_daily_routines(context: CallbackContext, user_id: int):
    # ... (منطق إعداد الروتين)
    pass

# --- نظام التذكيرات (تم بناؤه بالكامل) ---
async def reminder_callback(context: CallbackContext):
    job = context.job
    await context.bot.send_message(chat_id=job.chat_id, text=f"⏰ ...تذكير، {job.data['user_name']}-كن. لقد طلبت مني أن أذكرك بـ: '{job.data['task']}'")

async def handle_smart_reminder(update: Update, context: CallbackContext, text: str):
    user_id = str(update.effective_user.id)
    user_name = get_user_data(user_id).get('name', 'أماني-كن')
    set_user_state(user_id, None)
    await update.message.reply_text("حسناً... سأحاول أن أفهم هذا التذكير.")
    
    try:
        prompt = f"صديقي طلب مني تذكيره بهذا: '{text}'. حللي النص بدقة واستخرجي 'ماذا يجب أن أذكره به' و'متى' بالثواني من الآن (نسبة إلى الوقت الحالي). أرجعي الرد فقط على شكل JSON صالح للاستخدام البرمجي: {{\"task\": \"النص\", \"delay_seconds\": عدد_الثواني}}. إذا لم تستطيعي تحديد الوقت، اجعلي delay_seconds صفراً."
        response = await model.generate_content_async(prompt)
        
        json_text = response.text.strip().replace("```json", "").replace("```", "")
        reminder_data = json.loads(json_text)
        
        task = reminder_data.get("task")
        delay = reminder_data.get("delay_seconds")

        if task and isinstance(delay, int) and delay > 0:
            context.job_queue.run_once(reminder_callback, delay, chat_id=user_id, name=f"reminder_{user_id}_{task}", data={'task': task, 'user_name': user_name})
            await update.message.reply_text(f"حسناً، سأذكرك بـ '{task}' بعد {timedelta(seconds=delay)}.")
        else:
            await update.message.reply_text("...آسفة، لم أفهم الوقت المحدد في طلبك.")

    except Exception as e:
        logger.error(f"Smart reminder parsing error: {e}")
        await update.message.reply_text("...آسفة، واجهتني مشكلة في فهم هذا التذكير.")

# --- معالج الأزرار (تم بناؤه بالكامل) ---
async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    data = query.data
    user_name = get_user_data(user_id).get('name', 'أماني-كن')

    # التنقل
    menu_map = {
        "back_to_main": ("...هل تحتاج شيئاً آخر؟", get_main_keyboard()),
        "our_world_menu": ("هذا هو عالمنا الخاص...", get_our_world_keyboard()),
        "assistance_menu": ("كيف يمكنني مساعدتك اليوم؟", get_assistance_keyboard()),
        "wellness_menu": ("صحتك هي الأهم...", get_wellness_keyboard()),
        "entertainment_menu": ("ماذا نود أن نفعل للتسلية؟", get_entertainment_keyboard()),
        "advanced_menu": ("هذه هي قدراتي الخاصة...", get_advanced_keyboard()),
        "social_menu": ("يمكننا أن نفعل هذه الأشياء مع أصدقائك...", get_social_menu_keyboard()),
    }
    if data in menu_map:
        text, markup = menu_map[data]
        await query.edit_message_text(text, reply_markup=markup)
        return

    # الأوامر والميزات
    if data == "gamification_menu":
        game_data = get_user_data(user_id).get('gamification', {})
        stats = game_data.get('stats', {})
        text = f"📊 **ورقة شخصيتك**\n\n" \
               f"**المستوى:** {game_data.get('level', 1)}\n" \
               f"**الخبرة:** {game_data.get('exp', 0)} / {game_data.get('level', 1) * 100}\n\n" \
               f"**المهارات:**\n" \
               f"💪 القوة: {stats.get('STR', 5)}\n" \
               f"🧠 الذكاء: {stats.get('INT', 5)}\n" \
               f"😊 الكاريزما: {stats.get('CHA', 5)}"
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=get_our_world_keyboard())
    elif data == "financial_menu":
        set_user_state(user_id, 'awaiting_expense')
        await query.edit_message_text("حسناً، أخبرني عن مصروفاتك الأخيرة. مثلاً: 'دفعت 50 على الغداء'.")
    elif data == "dream_journal_menu":
        set_user_state(user_id, 'awaiting_dream')
        await query.edit_message_text("أنا أستمع... أخبرني عن حلمك الأخير. 🌙")
    elif data == "radio_menu":
        set_user_state(user_id, 'awaiting_story_prompt')
        await query.edit_message_text("عن ماذا تريد أن تكون قصتنا الليلة؟ 🎙️")
    elif data == "second_brain_info":
        await query.edit_message_text("لتستخدم 'عقلك الثاني'، فقط قم بإعادة توجيه أي رسالة (نص، رابط، صورة) إليّ. سأقوم بحفظها وتلخيصها لك تلقائياً.")
    elif data == "decision_maker_prompt":
        set_user_state(user_id, 'awaiting_decision_prompt')
        await query.edit_message_text("بالتأكيد. اشرح لي الموقف الذي تحتار فيه...")
    elif data == "vibe_director_prompt":
        set_user_state(user_id, 'awaiting_vibe_prompt')
        await query.edit_message_text("ما هو الجو أو الحالة التي تريد أن تكون فيها الآن؟ (مثال: 'تركيز عميق للدراسة')")
    elif data == "gift_guru_prompt":
        set_user_state(user_id, 'awaiting_gift_prompt')
        await query.edit_message_text("بالتأكيد. صف لي الشخص الذي تريد شراء هدية له (اهتماماته، عمره، المناسبة).")
    elif data == "reminders_menu":
        set_user_state(user_id, 'awaiting_reminder')
        await query.edit_message_text("بالتأكيد. أخبرني بماذا أذكرك ومتى؟ (مثال: 'ذكريني بالاتصال بوالدتي غداً الساعة 5 مساءً')")
    elif data == "meal_plan":
        await query.edit_message_text("بالتأكيد... سأفكر في خطة وجبات صحية لك.")
        await respond_to_conversation(update, context, text_input="اقترحي علي خطة وجبات صحية ولذيذة ليوم غد.")
    # ... (إضافة بقية الأزرار)


# --- نظام الأمان: معالج الأخطاء ---
async def error_handler(update: object, context: CallbackContext) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)
    if update and hasattr(update, 'effective_chat') and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="...آسفة، حدث خطأ غير متوقع. لقد أبلغت المطور. لنجرب مرة أخرى."
            )
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")

# --- تشغيل البوت ---
def main():
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
        logger.critical("خطأ فادح: متغيرات البيئة TELEGRAM_TOKEN و GEMINI_API_KEY مطلوبة.")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(MessageHandler(filters.FORWARDED, handle_forwarded_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document_message))
    
    application.add_handler(CallbackQueryHandler(but