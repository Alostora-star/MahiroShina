import os
import requests
import logging
import random
import json
import threading
import io
from flask import Flask
from datetime import datetime
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
import google.generativeai as genai

# --- إعدادات البيئة والواجهات البرمجية ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# --- إعداد Flask للبقاء نشطاً ---
flask_app = Flask(__name__)
@flask_app.route("/")
def home():
    return "✅ Mahiro is awake, tending to her digital home."

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

# --- إعداد الذكاء الاصطناعي (Gemini 2.5 Pro) ---
try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-pro')
    else:
        model = None
        logger.warning("متغير البيئة GEMINI_API_KEY غير موجود.")
except Exception as e:
    logger.critical(f"فشل في إعداد Gemini API: {e}")
    model = None

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

def get_user_data(user_id):
    return user_data.get(str(user_id), {})

def set_user_state(user_id, state=None, data=None):
    if str(user_id) not in user_data:
        user_data[str(user_id)] = {}
    user_data[str(user_id)]['next_action'] = {'state': state, 'data': data}
    save_user_data(user_data)

def initialize_user_data(user_id, name):
    user_data[str(user_id)] = {
        'name': name, 'next_action': {'state': None, 'data': None},
        'journal': [], 'memory': {}, 'watchlist': [], 'photo_album': [],
        'mood_history': [], 'conversation_history': []
    }
    save_user_data(user_data)

# --- لوحات المفاتيح ---
def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💖 عالمنا المشترك", callback_data="our_world_menu")],
        [InlineKeyboardButton("🧠 قدرات الملاك", callback_data="advanced_menu")],
        [InlineKeyboardButton("😊 كيف تشعر اليوم؟", callback_data="mood_menu")]
    ])

def get_our_world_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🍱 مخطط الوجبات", callback_data="meal_plan")],
        [InlineKeyboardButton("📚 جلسة مذاكرة", callback_data="study_session")],
        [InlineKeyboardButton("🖼️ ألبوم صورنا", callback_data="photo_album")],
        [InlineKeyboardButton("🔙 عودة للقائمة الرئيسية", callback_data="back_to_main")]
    ])

def get_advanced_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 بحث في الإنترنت", callback_data="prompt_search")],
        [InlineKeyboardButton("✍️ مساعدة في الكتابة", callback_data="prompt_write")],
        [InlineKeyboardButton("🗂️ المساعدة في الملفات", callback_data="file_helper_info")],
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
        await update.message.reply_text(f"أهلاً بعودتك، {user_name}-كن. ...هل أكلت جيداً؟", reply_markup=get_main_keyboard())

async def handle_text_message(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    text = update.message.text
    state_info = get_user_data(user_id).get('next_action', {})
    user_state = state_info.get('state')

    if user_state == 'awaiting_name':
        name = text.strip()
        initialize_user_data(user_id, name)
        await update.message.reply_text(f"حسناً، {name}-كن. ...سأناديك هكذا من الآن.", reply_markup=get_main_keyboard())
        return

    action_map = {
        'awaiting_search_query': perform_search,
        'awaiting_write_prompt': perform_write,
        'awaiting_file_instruction': handle_file_instruction,
    }
    if user_state in action_map:
        await action_map[user_state](update, context, text)
        return

    await respond_to_conversation(update, context, text_input=text)

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
    user_id = str(update.effective_user.id)
    user_name = get_user_data(user_id).get('name', 'أماني-كن')
    if not update.message.photo: return

    try:
        photo_file_id = update.message.photo[-1].file_id
        album = get_user_data(user_id).get('photo_album', [])
        album.append({"file_id": photo_file_id, "caption": update.message.caption or f"صورة من {user_name}", "date": datetime.now().isoformat()})
        user_data[str(user_id)]['photo_album'] = album
        save_user_data(user_data)
        await update.message.reply_text("ص-صورة جميلة... لقد احتفظت بها في ألبومنا. (⁄ ⁄•⁄ω⁄•⁄ ⁄)")
    except Exception as e:
        logger.error(f"Photo handling error: {e}")
        await update.message.reply_text("...آسفة، حدث خطأ ما أثناء حفظ الصورة.")

async def handle_document_message(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    doc = update.message.document
    if doc.file_size > 5 * 1024 * 1024:
        await update.message.reply_text("...هذا الملف كبير جداً.")
        return
    set_user_state(user_id, 'awaiting_file_instruction', data={'file_id': doc.file_id, 'file_name': doc.file_name})
    await update.message.reply_text(f"لقد استلمت الملف ({doc.file_name})... ماذا تريدني أن أفعل به؟")

async def respond_to_conversation(update: Update, context: CallbackContext, text_input=None, audio_input=None):
    user_id = str(update.effective_user.id)
    user_name = get_user_data(user_id).get('name', 'أماني-كن')

    if not model:
        await update.message.reply_text(f"💔 آسفة {user_name}-كن، لا أستطيع التفكير الآن.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    memory = get_user_data(user_id).get('memory', {})
    memory_context = "هذه بعض الأشياء التي أعرفها عنك:\n" + "\n".join(f"- {k}: {v}" for k, v in memory.items()) if memory else "لا توجد ذكريات مشتركة بيننا بعد."
    
    system_instruction = SYSTEM_INSTRUCTION_TEMPLATE.format(user_name=user_name, memory_context=memory_context)
    history = get_user_data(user_id).get('conversation_history', [])
    
    new_message_parts = []
    if text_input: new_message_parts.append(text_input)
    if audio_input:
        new_message_parts.append(audio_input)
        if not text_input: new_message_parts.insert(0, "صديقي أرسل لي هذا المقطع الصوتي، استمعي إليه وردي عليه.")
            
    history.append({'role': 'user', 'parts': new_message_parts})

    try:
        full_conversation = [{'role': 'user', 'parts': [system_instruction]}]
        full_conversation.append({'role': 'model', 'parts': ["...حسناً، فهمت. سأتحدث مع {user_name}-كن الآن.".format(user_name=user_name)]})
        full_conversation.extend(history)

        generation_config = genai.types.GenerationConfig(temperature=0.85)
        response = model.generate_content(full_conversation, generation_config=generation_config)
        response_text = response.text
        
        history.append({'role': 'model', 'parts': [response_text]})
        user_data[str(user_id)]['conversation_history'] = history[-12:]
        
        await update.message.reply_text(response_text)
    
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        history.pop()
        user_data[str(user_id)]['conversation_history'] = history
        await update.message.reply_text(f"...آسفة {user_name}-كن، عقلي مشوش قليلاً الآن.")
    finally:
        save_user_data(user_data)

# --- الدوال التي تم إصلاحها ---
async def perform_search(update: Update, context: CallbackContext, query: str):
    user_id = str(update.effective_user.id)
    set_user_state(user_id, None)
    await respond_to_conversation(update, context, text_input=f"ابحثي لي في الإنترنت عن '{query}' وقدمي لي ملخصاً بأسلوبك.")

async def perform_write(update: Update, context: CallbackContext, prompt: str):
    user_id = str(update.effective_user.id)
    set_user_state(user_id, None)
    await respond_to_conversation(update, context, text_input=f"اكتبي لي نصاً إبداعياً عن '{prompt}' بأسلوبك.")

async def handle_file_instruction(update: Update, context: CallbackContext, instruction: str):
    user_id = str(update.effective_user.id)
    state_info = get_user_data(user_id).get('next_action', {})
    file_data = state_info.get('data')

    if not file_data:
        await update.message.reply_text("...آسفة، لا أجد الملف الذي نتحدث عنه.")
        set_user_state(user_id, None)
        return

    file_id = file_data['file_id']
    file_name = file_data['file_name']
    
    message = await update.message.reply_text(f"حسناً... سأحاول أن أنفذ طلبك على ملف {file_name}.")
    
    try:
        file_obj = await context.bot.get_file(file_id)
        file_content_bytes = await file_obj.download_as_bytearray()
        file_content_text = file_content_bytes.decode('utf-8')

        prompt = f"أنت مساعد برمجي خبير. صديقي أرسل لي هذا الملف المسمى '{file_name}' وهذا هو محتواه:\n\n```\n{file_content_text}\n```\n\nوقد طلب مني تنفيذ الأمر التالي: '{instruction}'.\n\nقم بتطبيق التعديل المطلوب على الكود وأرجع لي محتوى الملف كاملاً بعد التعديل. لا تضف أي ملاحظات أو شروحات خارج الكود. فقط الكود المعدل."
        
        response = model.generate_content(prompt)
        modified_content = response.text.strip().replace("```", "")
        
        modified_file_bytes = io.BytesIO(modified_content.encode('utf-8'))
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=InputFile(modified_file_bytes, filename=f"modified_{file_name}"),
            caption=f"لقد قمت بترتيب الملف كما طلبت، {get_user_data(user_id).get('name')}-كن."
        )
        await message.delete()
    except Exception as e:
        logger.error(f"File modification error: {e}")
        await message.edit_text("...آسفة، حدث خطأ أثناء تعديل الملف.")
    finally:
        set_user_state(user_id, None)

# --- معالج الأزرار ---
async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    data = query.data
    
    if data == "back_to_main":
        await query.edit_message_text("...هل تحتاج شيئاً آخر؟", reply_markup=get_main_keyboard())
    elif data == "our_world_menu":
        await query.edit_message_text("هذه الأشياء التي يمكننا فعلها معاً...", reply_markup=get_our_world_keyboard())
    elif data == "advanced_menu":
        await query.edit_message_text("هذه هي قدراتي الخاصة لمساعدتك...", reply_markup=get_advanced_keyboard())
    elif data == "file_helper_info":
        await query.edit_message_text("للمساعدة في ملف، فقط أرسل الملف مباشرة إلى المحادثة. 🗂️")
    # ... (إضافة معالجات لبقية الأزرار)

# --- تشغيل البوت ---
def main():
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
        logger.critical("خطأ فادح: متغيرات البيئة TELEGRAM_TOKEN و GEMINI_API_KEY مطلوبة.")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("🌸 Mahiro (Definitive Edition) is running!")
    application.run_polling()

if __name__ == '__main__':
    main()
