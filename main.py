import os
import requests
import logging
import random
import json
import threading
import io
import re
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
        model = genai.GenerativeModel('gemini-1.5-pro-latest')
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
        'journal': [], 'memory': {}, 'watchlist': [], 'photo_album': [],
        'mood_history': [], 'goals': [], 'reminders': [], 'shopping_list': [],
        'finances': {'transactions': [], 'budget': {}},
        'dream_journal': [],
        'gamification': {'level': 1, 'exp': 0, 'stats': {'STR': 5, 'INT': 5, 'CHA': 5}},
        'routines': {'morning_greeting': False, 'detox_mode': False},
        'conversation_history': [], 'memory_summary': ""
    }
    save_data(user_data, USER_DATA_FILE)

# --- لوحات المفاتيح (تمت إعادة الهيكلة بالكامل) ---
def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💖 عالمنا الخاص", callback_data="our_world_menu")],
        [InlineKeyboardButton("🛠️ مساعدتي اليومية", callback_data="assistance_menu")],
        [InlineKeyboardButton("❤️ صحة وعافية", callback_data="wellness_menu")],
        [InlineKeyboardButton("🎉 ترفيه وألعاب", callback_data="entertainment_menu")],
        [InlineKeyboardButton("🚀 أدوات متقدمة", callback_data="advanced_menu")],
        [InlineKeyboardButton("🌐 حياتي الاجتماعية", callback_data="social_menu")]
    ])
# ... (بقية دوال لوحات المفاتيح)
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
    # ... (منطق معالجة الرسائل النصية، بما في ذلك الحالات والمحادثة العامة)
    pass

async def handle_forwarded_message(update: Update, context: CallbackContext):
    # ... (منطق "العقل الثاني")
    pass
    
# ... (بقية معالجات الرسائل: صوت، صورة، ملف)

async def respond_to_conversation(update: Update, context: CallbackContext, text_input=None, audio_input=None):
    user_id = str(update.effective_user.id)
    user_name = get_user_data(user_id).get('name', 'أماني-كن')

    if not model:
        await update.message.reply_text(f"💔 آسفة {user_name}-كن، لا أستطيع التفكير الآن.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    try:
        # نظام الذاكرة المطور
        history = get_user_data(user_id).get('conversation_history', [])
        memory_summary = get_user_data(user_id).get('memory_summary', "")
        
        # تلخيص المحادثة إذا طالت
        if len(history) > 20:
            summary_prompt = f"لخص المحادثة التالية في نقاط أساسية للحفاظ عليها في الذاكرة طويلة الأمد:\n\n{json.dumps(history[:10])}"
            summary_response = await model.generate_content_async(summary_prompt)
            memory_summary += "\n" + summary_response.text
            history = history[10:]
            user_data[str(user_id)]['memory_summary'] = memory_summary
        
        memory = get_user_data(user_id).get('memory', {})
        memory_context = f"ملخص محادثاتنا السابقة:\n{memory_summary}\n\nأشياء أعرفها عنك:\n" + "\n".join(f"- {k}: {v}" for k, v in memory.items())
        
        system_instruction = SYSTEM_INSTRUCTION_TEMPLATE.format(user_name=user_name, memory_context=memory_context)
        
        chat = model.start_chat(history=[
            {'role': 'user', 'parts': [system_instruction]},
            {'role': 'model', 'parts': ["...حسناً، فهمت. سأتحدث مع {user_name}-كن الآن.".format(user_name=user_name)]},
            *history
        ])
        
        new_message_parts = []
        if text_input: new_message_parts.append(text_input)
        if audio_input:
            new_message_parts.append(audio_input)
            if not text_input: new_message_parts.insert(0, "صديقي أرسل لي هذا المقطع الصوتي، استمعي إليه وردي عليه.")
        
        response = await chat.send_message_async(new_message_parts)
        response_text = response.text
        
        user_data[str(user_id)]['conversation_history'] = chat.history[2:]
        await update.message.reply_text(response_text)
    
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        await update.message.reply_text(f"...آسفة {user_name}-كن، عقلي مشوش قليلاً الآن.")
    finally:
        save_data(user_data, USER_DATA_FILE)

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
        
        # تنظيف وتحليل الـ JSON
        json_text = response.text.strip().replace("```json", "").replace("```", "")
        reminder_data = json.loads(json_text)
        
        task = reminder_data.get("task")
        delay = reminder_data.get("delay_seconds")

        if task and isinstance(delay, int) and delay > 0:
            context.job_queue.run_once(reminder_callback, delay, chat_id=user_id, name=f"reminder_{user_id}_{task}", data={'task': task, 'user_name': user_name})
            await update.message.reply_text(f"حسناً، سأذكرك بـ '{task}' بعد {timedelta(seconds=delay)}.")
        else:
            await update.message.reply_text("...آسفة، لم أفهم الوقت المحدد في طلبك. هل يمكنك أن تكون أكثر تحديداً؟")

    except Exception as e:
        logger.error(f"Smart reminder parsing error: {e}")
        await update.message.reply_text("...آسفة، واجهتني مشكلة في فهم هذا التذكير.")

# ... (بقية دوال الميزات)

# --- نظام الأمان: معالج الأخطاء ---
async def error_handler(update: object, context: CallbackContext) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)
    # ... (منطق إرسال رسالة الخطأ للمستخدم)

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
    # ... (بقية المعالجات)
    
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_error_handler(error_handler)
    
    logger.info("🌸 Mahiro (The Legendary Saga) is running!")
    application.run_polling()

if __name__ == '__main__':
    main()
