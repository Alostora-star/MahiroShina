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
from telegram import Update
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
        # استخدام نموذج Flash لضمان السرعة مع الحفاظ على الذكاء
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
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY') # <-- مفتاح API جديد للطقس

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

مهمتك الآن هي الرد على الرسالة الأخيرة من {user_name} في سجل المحادثة.
"""

# --- إدارة بيانات المستخدم ---
USER_DATA_FILE = "user_data.json"

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

def get_user_data(user_id):
    return user_data.get(str(user_id), {})

def initialize_user_data(user_id, name):
    user_id_str = str(user_id)
    user_data[user_id_str] = {
        'name': name,
        'timezone': 'Asia/Riyadh',
        'location': {'city': 'Riyadh'}, # <-- موقع افتراضي
        'conversation_history': [], 'memory_summary': ""
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
        # بدء الروتين اليومي عند بدء التشغيل
        await setup_daily_routines(context, user.id)

async def help_command(update: Update, context: CallbackContext):
    help_text = """
    أهلاً بك! أنا ماهيرو، رفيقتك الرقمية. يمكنك التحدث معي بشكل طبيعي.

    فقط اطلب ما تريد! إليك بعض الأمثلة:
    - "ابحثي عن أفضل وصفات الأرز"
    - "ذكريني بالاتصال بوالدتي غداً الساعة 5 مساءً"
    - "ما هي الجواهر الخفية في طوكيو؟" (أو أرسل موقعك)
    - أرسل صورة لملابسك واسألني "ما رأيك؟"

    **الأوامر المتاحة:**
    /settings - لضبط منطقتك الزمنية وموقعك.

    أنا هنا لأساعدك وأكون صديقتك. 🌸
    """
    await update.message.reply_text(help_text)

async def settings_command(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    args = context.args
    if not args:
        user_settings = get_user_data(user_id)
        user_tz = user_settings.get('timezone', 'Asia/Riyadh')
        user_city = user_settings.get('location', {}).get('city', 'Riyadh')
        await update.message.reply_text(
            f"إعداداتك الحالية:\n"
            f"- المنطقة الزمنية: {user_tz}\n"
            f"- المدينة للطقس: {user_city}\n\n"
            "لتغييرها، استخدم الأمر هكذا:\n"
            "/settings timezone Europe/Berlin\n"
            "/settings city Tokyo"
        )
        return
    
    setting_type = args[0].lower()
    if setting_type == 'timezone' and len(args) > 1:
        try:
            new_tz = pytz.timezone(args[1])
            user_data[user_id]['timezone'] = str(new_tz)
            save_data(user_data, USER_DATA_FILE)
            await update.message.reply_text(f"حسناً... لقد قمت بتحديث منطقتك الزمنية إلى {new_tz}. 💕")
        except pytz.UnknownTimeZoneError:
            await update.message.reply_text("...آسفة، لم أتعرف على هذه المنطقة الزمنية.")
    elif setting_type == 'city' and len(args) > 1:
        new_city = " ".join(args[1:])
        user_data[user_id]['location'] = {'city': new_city}
        save_data(user_data, USER_DATA_FILE)
        await update.message.reply_text(f"حسناً، لقد قمت بتحديث مدينتك إلى {new_city}. سأستخدمها للطقس والاستكشاف. 🥰")
    else:
        await update.message.reply_text("...لم أفهم. استخدم /settings timezone [المنطقة] أو /settings city [المدينة].")


async def handle_message(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    text = update.message.text if update.message.text else ""
    user_data_local = get_user_data(user_id)

    if user_data_local.get('awaiting_name'):
        name = text.strip()
        initialize_user_data(user_id, name)
        await update.message.reply_text(f"حسناً، {name}-كن. ...سأناديك هكذا من الآن.")
        return

    # التعامل مع الموقع المرسل
    if update.message.location:
        await handle_location_message(update, context)
        return

    # --- العقل الموجه (Intent Router) ---
    intent_prompt = f"""
    حلل الرسالة التالية من المستخدم: '{text}'.
    حدد "قصد" المستخدم من بين الخيارات التالية:
    [conversation, search, reminder, explore_location]
    
    أرجع الرد فقط على شكل JSON: {{\"intent\": \"اسم_القصد\", \"data\": \"البيانات_المستخرجة\"}}.
    أمثلة:
    "ما هي الجواهر الخفية في باريس؟" -> {{\"intent\": \"explore_location\", \"data\": \"باريس\"}}
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
        "explore_location": handle_exploration_request,
    }

    if intent in action_map:
        await action_map[intent](update, context, data)
    else:
        await respond_to_conversation(update, context, text_input=data)


async def respond_to_conversation(update: Update, context: CallbackContext, text_input=None, audio_input=None, image_input=None):
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
        
        if len(history_list) > 20:
            summary_prompt = f"لخص المحادثة التالية في نقاط أساسية للحفاظ عليها في الذاكرة طويلة الأمد:\n\n{json.dumps(history_list[:10])}"
            summary_response = await model.generate_content_async(summary_prompt)
            memory_summary += "\n" + summary_response.text
            history_list = history_list[10:]
            user_data[str(user_id)]['memory_summary'] = memory_summary
        
        memory = get_user_data(user_id).get('memory', {})
        memory_context = f"ملخص محادثاتنا السابقة:\n{memory_summary}\n\nأشياء أعرفها عنك:\n" + "\n".join(f"- {k}: {v}" for k, v in memory.items())
        
        system_instruction = SYSTEM_INSTRUCTION_TEMPLATE.format(user_name=user_name, memory_context=memory_context)
        
        chat_history_for_api = [
            {'role': 'user', 'parts': [system_instruction]},
            {'role': 'model', 'parts': ["...حسناً، فهمت. سأتحدث مع {user_name}-كن الآن.".format(user_name=user_name)]}
        ]
        chat_history_for_api.extend(history_list)
        
        new_message_parts = []
        if text_input: new_message_parts.append(text_input)
        if image_input: new_message_parts.append(image_input)
        if audio_input:
            new_message_parts.append(audio_input)
            if not text_input: new_message_parts.insert(0, "صديقي أرسل لي هذا المقطع الصوتي، استمعي إليه وردي عليه.")
        
        chat_history_for_api.append({'role': 'user', 'parts': new_message_parts})

        response = await model.generate_content_async(chat_history_for_api)
        response_text = response.text
        
        # تحديث السجل المحلي بالبيانات القابلة للحفظ فقط
        history_list.append({'role': 'user', 'parts': [text_input if text_input else "ملف وسائط (صورة/صوت)"]})
        history_list.append({'role': 'model', 'parts': [response_text]})
        user_data[str(user_id)]['conversation_history'] = history_list[-20:]
        
        await update.message.reply_text(response_text)
    
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        await update.message.reply_text(f"...آسفة {user_name}-كن، عقلي مشوش قليلاً الآن.")
    finally:
        save_data(user_data, USER_DATA_FILE)

# --- دوال الميزات الجديدة ---

async def handle_voice_message(update: Update, context: CallbackContext):
    try:
        voice_file_obj = await context.bot.get_file(update.message.voice.file_id)
        voice_data = io.BytesIO()
        await voice_file_obj.download_to_memory(voice_data)
        voice_data.seek(0)
        audio_file = genai.upload_file(voice_data, mime_type="audio/ogg")
        await respond_to_conversation(update, context, audio_input=audio_file)
    except Exception as e:
        logger.error(f"Voice processing error: {e}")
        await update.message.reply_text("😥 آسفة، لم أستطع معالجة رسالتك الصوتية الآن.")

async def handle_photo_message(update: Update, context: CallbackContext):
    try:
        photo_file = await context.bot.get_file(update.message.photo[-1].file_id)
        photo_data = io.BytesIO()
        await photo_file.download_to_memory(photo_data)
        photo_data.seek(0)
        
        # استخدام مكتبة Pillow لتحويل الصورة إلى PNG إذا لزم الأمر
        from PIL import Image
        img = Image.open(photo_data)
        png_data = io.BytesIO()
        img.save(png_data, format='PNG')
        png_data.seek(0)

        image_file = genai.upload_file(png_data, mime_type="image/png")
        prompt = update.message.caption or "صديقي أرسل لي هذه الصورة. ألقي نظرة عليها وقدمي رأيك أو نصيحتك بأسلوبك اللطيف."
        await respond_to_conversation(update, context, text_input=prompt, image_input=image_file)
    except Exception as e:
        logger.error(f"Photo processing error: {e}")
        await update.message.reply_text("...آسفة، حدث خطأ ما أثناء رؤيتي للصورة.")

async def handle_location_message(update: Update, context: CallbackContext):
    location = update.message.location
    lat = location.latitude
    lon = location.longitude
    await handle_exploration_request(update, context, f"خط العرض {lat} وخط الطول {lon}")

async def handle_exploration_request(update: Update, context: CallbackContext, data: str):
    await update.message.reply_text(f"حسناً، سأبحث عن جواهر خفية حول '{data}'...")
    await respond_to_conversation(update, context, text_input=f"بصفتك 'رفيقة الاستكشاف'، ابحثي عن أماكن فريدة ومحلية (مقاهٍ، حدائق، متاجر) قريبة من الموقع التالي: '{data}'. قدمي 3 اقتراحات مع وصف بسيط وجذاب لكل منها.")

# --- نظام التذكيرات ---
async def reminder_callback(context: CallbackContext):
    job = context.job
    await context.bot.send_message(chat_id=job.chat_id, text=f"⏰ ...تذكير، {job.data['user_name']}-كن. لقد طلبت مني أن أذكرك بـ: '{job.data['task']}'")

async def handle_smart_reminder(update: Update, context: CallbackContext, text: str):
    # ... (نفس الكود السابق)
    pass

# --- الروتين اليومي والوعي الاستباقي ---
async def proactive_weather_check(context: CallbackContext):
    job = context.job
    user_id = job.chat_id
    user_name = get_user_data(user_id).get('name', 'أماني-كن')
    city = get_user_data(user_id).get('location', {}).get('city', 'Riyadh')

    if not WEATHER_API_KEY:
        logger.warning("مفتاح Weather API غير موجود، لا يمكن التحقق من الطقس.")
        return

    try:
        # استخدام واجهة برمجة تطبيقات الطقس للتحقق من توقعات المطر
        url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={WEATHER_API_KEY}&units=metric"
        response = requests.get(url).json()
        
        # البحث عن أي توقعات للمطر في الـ 12 ساعة القادمة
        will_rain = False
        if response.get("list"):
            for forecast in response["list"][:4]: # التحقق من الـ 4 فترات القادمة (12 ساعة)
                if "rain" in forecast.get("weather", [{}])[0].get("main", "").lower():
                    will_rain = True
                    break
        
        if will_rain:
            await context.bot.send_message(chat_id=user_id, text=f"صباح الخير، {user_name}-كن... لاحظت أن الطقس قد يتغير لاحقاً اليوم وهناك احتمال لسقوط المطر. لا تنسَ أن تأخذ معك مظلة إذا كنت ستخرج... لا أريدك أن تمرض. ☔️")

    except Exception as e:
        logger.error(f"Proactive weather check failed: {e}")

async def setup_daily_routines(context: CallbackContext, user_id: int):
    # إزالة المهام القديمة لضمان عدم تكرارها
    for job in context.job_queue.get_jobs_by_name(f'weather_{user_id}'):
        job.schedule_removal()
        
    user_tz_str = get_user_data(user_id).get('timezone', 'Asia/Riyadh')
    user_tz = pytz.timezone(user_tz_str)
    
    # جدولة التحقق من الطقس كل صباح الساعة 7 بتوقيت المستخدم
    context.job_queue.run_daily(proactive_weather_check, time=time(hour=7, minute=0, tzinfo=user_tz), chat_id=user_id, name=f'weather_{user_id}')

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
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))
    application.add_handler(MessageHandler(filters.LOCATION, handle_location_message))
    
    application.add_error_handler(error_handler)
    
    logger.info("🌸 Mahiro (Proactive Awareness Edition) is running!")
    application.run_polling()

if __name__ == '__main__':
    main()
