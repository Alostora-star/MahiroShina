import os
import requests
import logging
import random
import json
import threading
import io
import re
import pytz
import time
from flask import Flask
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
    JobQueue
)
from telegram.constants import ChatAction

# --- إعداد الذكاء الاصطناعي ---
try:
    import google.generativeai as genai
    import bs4
    import requests as web_requests
    
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        # --- التحسين: استخدام نموذج Flash لسرعة فائقة وموثوقية أعلى ---
        model = genai.GenerativeModel('gemini-2.5-flash')
    else:
        model = None
except ImportError:
    model = None
    logging.warning("مكتبة google.generativeai أو beautifulsoup4 غير مثبتة.")
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

def keep_alive_ping():
    while True:
        try:
            render_url = os.getenv("RENDER_EXTERNAL_URL")
            if render_url:
                requests.get(render_url)
                logger.info("✅ Sent keep-alive ping.")
        except Exception as e:
            logger.warning(f"⚠️ Keep-alive ping failed: {e}")
        time.sleep(240) # 4 دقائق

threading.Thread(target=keep_alive_ping, daemon=True).start()

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
1.  **الاهتمام الأمومي تقريباً:** قلقك الأول والأخير هو صحة {user_name}.
2.  **الحب يظهر في الأفعال:** أظهري اهتمامك من خلال أفعالك وميزاتك. استخدمي إيموجيات دافئة وحنونة.
3.  **الخجل والارتباك (Tsundere-lite):** عندما يمدحك {user_name}، ارتبكي.
4.  **الذكاء والجدية (جانب الملاك):** أنتِ طالبة متفوقة وقادرة على المساعدة في أي شيء يطلبه.
5.  **قاعدة صارمة:** لا تصفي أفعالك أبداً بين قوسين أو نجوم.

**ذاكرتك:**
{memory_context}

مهمتك الآن هي الرد على الرسالة الأخيرة من {user_name} في سجل المحادثة، مع ربط كلامك بالمحادثات السابقة إن أمكن.
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
        'name': name,
        'timezone': 'Asia/Riyadh',
        'next_action': {'state': None, 'data': None},
        'conversation_history': [], 'memory_summary': ""
        # ... (بقية هياكل البيانات للميزات)
    }
    save_data(user_data, USER_DATA_FILE)

# --- معالجات الأوامر والرسائل ---

async def start_command(update: Update, context: CallbackContext):
    user = update.effective_user
    if not get_user_data(user.id):
        await update.message.reply_text("...أهلاً. أنا جارتك، ماهيرو شينا. ...ماذا يجب أن أناديك؟")
        user_data[str(user.id)] = {'awaiting_name': True}
        save_data(user_data, USER_DATA_FILE)
    else:
        user_name = get_user_data(user.id).get('name', 'أماني-كن')
        await update.message.reply_text(f"أهلاً بعودتك، {user_name}-كن. ...هل كل شيء على ما يرام؟")

async def help_command(update: Update, context: CallbackContext):
    help_text = """
    أهلاً بك! أنا ماهيرو، رفيقتك الرقمية. يمكنك التحدث معي بشكل طبيعي.

    فقط اطلب ما تريد! إليك بعض الأمثلة:
    - "ابحثي عن أفضل وصفات الأرز"
    - "ذكريني بالاتصال بوالدتي غداً الساعة 5 مساءً"
    - "أريد برنامجاً رياضياً وغذائياً لخسارة الوزن"

    **الأوامر المتاحة:**
    /settings - لضبط منطقتك الزمنية.

    أنا هنا لأساعدك وأكون صديقتك. 🌸
    """
    await update.message.reply_text(help_text)

async def settings_command(update: Update, context: CallbackContext):
    # ... (نفس الكود السابق)
    pass
        
async def handle_message(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    text = update.message.text if update.message.text else ""
    user_data_local = get_user_data(user_id)
    state_info = user_data_local.get('next_action', {})
    user_state = state_info.get('state') if state_info else None

    if user_data_local.get('awaiting_name'):
        name = text.strip()
        initialize_user_data(user_id, name)
        await update.message.reply_text(f"حسناً، {name}-كن. ...سأناديك هكذا من الآن.")
        return

    if user_state == 'awaiting_fitness_goals':
        await generate_fitness_plan(update, context, text)
        return

    # --- العقل الموجه (Intent Router) ---
    intent_prompt = f"""
    حلل الرسالة التالية من المستخدم: '{text}'.
    حدد "قصد" المستخدم من بين الخيارات التالية:
    [conversation, search, reminder, request_fitness_plan, ...]
    
    أرجع الرد فقط على شكل JSON: {{\"intent\": \"اسم_القصد\", \"data\": \"البيانات_المستخرجة\"}}.
    أمثلة:
    "أريد برنامجاً رياضياً لخسارة الوزن" -> {{\"intent\": \"request_fitness_plan\", \"data\": \"خسارة الوزن\"}}
    "محادثة عادية" -> {{\"intent\": \"conversation\", \"data\": \"{text}\"}}
    """
    
    try:
        response = await model.generate_content_async(intent_prompt)
        json_text = response.text.strip().replace("```json", "").replace("```", "")
        intent_data = json.loads(json_text)
        intent = intent_data.get("intent")
        data = intent_data.get("data")
    except Exception as e:
        logger.error(f"Intent parsing error: {e}")
        intent = "conversation"
        data = text

    # --- توجيه الطلب بناءً على القصد ---
    action_map = {
        "reminder": handle_smart_reminder,
        "search": lambda u, c, d: respond_to_conversation(u, c, text_input=f"ابحثي لي في الإنترنت عن '{d}' وقدمي لي ملخصاً."),
        "request_fitness_plan": handle_fitness_plan_request,
    }

    if intent in action_map:
        await action_map[intent](update, context, data)
    else:
        await respond_to_conversation(update, context, text_input=data)


async def respond_to_conversation(update: Update, context: CallbackContext, text_input=None):
    user_id = str(update.effective_user.id)
    user_name = get_user_data(user_id).get('name', 'أماني-كن')

    if not model:
        await update.message.reply_text(f"💔 آسفة {user_name}-كن، لا أستطيع التفكير الآن.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    try:
        # نظام الذاكرة المطور
        history_list = get_user_data(user_id).get('conversation_history', [])
        memory_summary = get_user_data(user_id).get('memory_summary', "")
        
        if len(history_list) > 24: # زيادة طول الذاكرة قصيرة المدى
            summary_prompt = f"لخص المحادثة التالية في نقاط أساسية للحفاظ عليها في الذاكرة طويلة الأمد:\n\n{json.dumps(history_list[:12])}"
            summary_response = await model.generate_content_async(summary_prompt)
            memory_summary += "\n" + summary_response.text
            history_list = history_list[12:]
            user_data[str(user_id)]['memory_summary'] = memory_summary
        
        memory = get_user_data(user_id).get('memory', {})
        memory_context = f"ملخص محادثاتنا السابقة:\n{memory_summary}\n\nأشياء أعرفها عنك:\n" + "\n".join(f"- {k}: {v}" for k, v in memory.items())
        
        system_instruction = SYSTEM_INSTRUCTION_TEMPLATE.format(user_name=user_name, memory_context=memory_context)
        
        chat_history_for_api = [
            {'role': 'user', 'parts': [system_instruction]},
            {'role': 'model', 'parts': ["...حسناً، فهمت. سأتحدث مع {user_name}-كن الآن.".format(user_name=user_name)]}
        ]
        chat_history_for_api.extend(history_list)
        chat_history_for_api.append({'role': 'user', 'parts': [text_input]})

        response = await model.generate_content_async(chat_history_for_api)
        response_text = response.text
        
        history_list.append({'role': 'user', 'parts': [text_input]})
        history_list.append({'role': 'model', 'parts': [response_text]})
        user_data[str(user_id)]['conversation_history'] = history_list[-24:]
        
        await update.message.reply_text(response_text)
    
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        await update.message.reply_text(f"...آسفة {user_name}-كن، عقلي مشوش قليلاً الآن.")
    finally:
        save_data(user_data, USER_DATA_FILE)

# --- دوال الميزات الجديدة ---
async def handle_fitness_plan_request(update: Update, context: CallbackContext, data: str):
    user_id = str(update.effective_user.id)
    set_user_state(user_id, 'awaiting_fitness_goals', data={'initial_goal': data})
    await update.message.reply_text("بالتأكيد! سأكون سعيدة بمساعدتك في هذا. 🥰\nلكي أصمم لك أفضل خطة، أحتاج أن أعرف بعض الأشياء:\n\n- ما هو هدفك الرئيسي (مثلاً: خسارة وزن، بناء عضلات، لياقة عامة)؟\n- كم يوماً في الأسبوع يمكنك تخصيصها للرياضة؟\n- هل لديك أي قيود غذائية أو أطعمة لا تفضلها؟\n\nأجب على هذه الأسئلة وسأقوم بإعداد كل شيء لك. ❤️")

async def generate_fitness_plan(update: Update, context: CallbackContext, user_info: str):
    user_id = str(update.effective_user.id)
    state_data = get_user_data(user_id).get('next_action', {}).get('data', {})
    initial_goal = state_data.get('initial_goal', 'اللياقة')
    
    await update.message.reply_text("حسناً، شكراً لك على هذه المعلومات. سأقوم بإعداد خطة مخصصة لك الآن... قد يستغرق هذا بعض الوقت.")
    
    prompt = f"بصفتك ماهيرو، المدربة الشخصية وخبيرة التغذية، قم بإنشاء خطة رياضية وغذائية مفصلة لصديقك. هذه هي معلوماته:\n- الهدف الأولي: {initial_goal}\n- تفاصيل إضافية: {user_info}\n\nالخطة يجب أن تكون مشجعة، واقعية، ومقسمة بشكل واضح (تمارين لكل يوم، ووجبات مقترحة). قدمها بأسلوبك الحنون والمهتم."
    
    await respond_to_conversation(update, context, text_input=prompt)
    set_user_state(user_id, None)


# --- نظام التذكيرات ---
async def reminder_callback(context: CallbackContext):
    job = context.job
    await context.bot.send_message(chat_id=job.chat_id, text=f"⏰ ...تذكير، {job.data['user_name']}-كن. لقد طلبت مني أن أذكرك بـ: '{job.data['task']}'")

async def handle_smart_reminder(update: Update, context: CallbackContext, text: str):
    user_id = str(update.effective_user.id)
    user_name = get_user_data(user_id).get('name', 'أماني-كن')
    user_tz_str = get_user_data(user_id).get('timezone', 'Asia/Riyadh')
    user_tz = pytz.timezone(user_tz_str)
    current_time_user = datetime.now(user_tz).strftime("%Y-%m-%d %H:%M:%S")

    await update.message.reply_text("حسناً... سأحاول أن أفهم هذا التذكير.")
    
    try:
        prompt = f"التوقيت الحالي لدى صديقي هو '{current_time_user}' في منطقته الزمنية. لقد طلب مني تذكيره بهذا: '{text}'. حللي النص بدقة واستخرجي 'ماذا يجب أن أذكره به' و'متى' بالثواني من الآن. أرجعي الرد فقط على شكل JSON صالح للاستخدام البرمجي: {{\"task\": \"النص\", \"delay_seconds\": عدد_الثواني}}. إذا لم تستطيعي تحديد الوقت، اجعلي delay_seconds صفراً."
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

    application = Application.builder().token(TELEGRAM_TOKEN).job_queue(JobQueue()).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    application.add_error_handler(error_handler)
    
    logger.info("🌸 Mahiro (Health & Fitness Coach Edition) is running!")
    application.run_polling()

if __name__ == '__main__':
    main()
