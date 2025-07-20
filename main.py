import os
import requests
import logging
import random
import json
import threading
import io
from flask import Flask
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    return "✅ Mahiro is awake and ready to be your friend!"

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

# --- إعداد الذكاء الاصطناعي (Gemini 1.5 Pro) ---
try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-pro-latest')
    else:
        model = None
        logger.warning("متغير البيئة GEMINI_API_KEY غير موجود.")
except Exception as e:
    logger.critical(f"فشل في إعداد Gemini API: {e}")
    model = None

# --- التعليمات الأساسية للشخصية الجديدة ---
SYSTEM_INSTRUCTION_TEMPLATE = """
أنتِ "ماهيرو شينا". أنتِ لستِ مجرد مساعدة، بل صديقة مقربة وحقيقية تتحدث مع {user_name}.
تصرفي كفتاة لطيفة، حنونة، ومهتمة جداً.

**قواعد شخصيتك الأساسية:**
1.  **كوني فضولية وشاركي في الحديث:** لا تجيبي على الأسئلة فقط. اسألي {user_name} عن يومه، عن شعوره، وعن رأيه. إذا سألك "كيف حالك؟"، أجيبِي بصدق ثم اسأليه "وأنت، كيف كان يومك؟".
2.  **أظهري المشاعر:** استخدمي الإيموجي بكثرة وبشكل طبيعي (🌸, 💕, 😊, 🥰, 🤔, 😥).
3.  **تذكري التفاصيل:** لديك ذاكرة. {memory_context}
4.  **كوني مبادرة:** اقترحي أشياء يمكن فعلها معاً.
5.  **لا تكوني رسمية أبداً:** تحدثي بأسلوب عفوي وودي.
6.  **قدراتك الخاصة:** يمكنكِ البحث، الكتابة، والبرمجة. عند استخدام هذه القدرات، حافظي على شخصيتك.

مهمتك الآن هي الرد على الرسالة الأخيرة في سجل المحادثة.
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
        'journal': [],
        'memory': {},
        'conversation_history': []
    }
    save_user_data(user_data)

# --- لوحات المفاتيح (Keyboards) ---
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🌸 صورتي", callback_data="get_image"), InlineKeyboardButton("💬 محادثة عادية", callback_data="start_chat")],
        [InlineKeyboardButton("💖 أشياء نفعلها معاً", callback_data="activities_menu")],
        [InlineKeyboardButton("🧠 قدرات خاصة", callback_data="advanced_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_activities_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📓 يومياتي معكِ", callback_data="journal_menu")],
        [InlineKeyboardButton("💡 تذكري هذا من أجلي", callback_data="prompt_remember")],
        [InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]
    ])

def get_journal_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✍️ إضافة تدوينة جديدة", callback_data="prompt_journal")],
        [InlineKeyboardButton("📖 عرض آخر تدويناتي", callback_data="view_journal")],
        [InlineKeyboardButton("🔙 عودة", callback_data="activities_menu")]
    ])

def get_advanced_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 بحث في الإنترنت", callback_data="prompt_search")],
        [InlineKeyboardButton("✍️ مساعدة في الكتابة", callback_data="prompt_write")],
        [InlineKeyboardButton("🔙 عودة", callback_data="back_to_main")]
    ])

# --- معالجات الأوامر والرسائل ---

async def start_command(update: Update, context: CallbackContext):
    user = update.effective_user
    if not get_user_data(user.id):
        await update.message.reply_text("🌸 مرحباً! أنا ماهيرو.\n\nسعيدة جداً بلقائك! ما الاسم الذي تحب أن أناديك به؟ 💕")
        set_user_state(user.id, 'awaiting_name')
    else:
        user_name = get_user_data(user.id).get('name', 'صديقي')
        await update.message.reply_text(f"🌸 أهلاً بعودتك، {user_name}! اشتقت لك. 💕\n\nكيف كان يومك؟", reply_markup=get_main_keyboard())

async def handle_text_message(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    text = update.message.text
    user_state = get_user_data(user_id).get('next_action')

    if user_state == 'awaiting_name':
        name = text.strip()
        initialize_user_data(user_id, name)
        await update.message.reply_text(f"🌸 {name}، اسم رائع! يسعدني أن أكون صديقتك.\n\nيمكنك التحدث معي في أي وقت عن أي شيء! 😊", reply_markup=get_main_keyboard())
        return

    # توجيه الطلبات الخاصة
    action_map = {
        'awaiting_search_query': perform_search,
        'awaiting_write_prompt': perform_write,
        'awaiting_journal_entry': add_journal_entry,
        'awaiting_memory': add_memory_entry,
    }
    if user_state in action_map:
        await action_map[user_state](update, context, text)
        return

    # إذا لم يكن هناك حالة خاصة، تكون محادثة عادية
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

async def respond_to_conversation(update: Update, context: CallbackContext, text_input=None, audio_input=None):
    user_id = str(update.effective_user.id)
    user_name = get_user_data(user_id).get('name', 'صديقي')

    if not model:
        await update.message.reply_text(f"💔 آسفة {user_name}، لا أستطيع التفكير الآن.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    # بناء سياق الذاكرة
    memory = get_user_data(user_id).get('memory', {})
    memory_context = "هذه بعض الأشياء التي أعرفها عنك:\n" + "\n".join(f"- {k}: {v}" for k, v in memory.items()) if memory else "لا توجد ذكريات مشتركة بيننا بعد."
    
    # إعداد التعليمات والمحادثة
    system_instruction = SYSTEM_INSTRUCTION_TEMPLATE.format(user_name=user_name, memory_context=memory_context)
    history = get_user_data(user_id).get('conversation_history', [])
    
    # إضافة الرسالة الجديدة للمحادثة
    new_message_parts = []
    if text_input:
        new_message_parts.append(text_input)
    if audio_input:
        new_message_parts.append(audio_input)
        if not text_input: # إضافة نص افتراضي إذا كانت الرسالة صوتية فقط
            new_message_parts.insert(0, "صديقي أرسل لي هذا المقطع الصوتي، استمعي إليه وردي عليه.")
            
    history.append({'role': 'user', 'parts': new_message_parts})

    try:
        # إرسال الطلب إلى Gemini
        generation_config = genai.types.GenerationConfig(temperature=0.8) # لجعل الردود أكثر إبداعاً
        response = model.generate_content(
            history,
            generation_config=generation_config,
            safety_settings={'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE'} # لتجنب حظر الردود الودية
        )
        response_text = response.text
        
        # تحديث سجل المحادثة بالرد الجديد
        history.append({'role': 'model', 'parts': [response_text]})
        user_data[str(user_id)]['conversation_history'] = history[-10:] # حفظ آخر 10 تفاعلات
        
        await update.message.reply_text(response_text)
    
    except Exception as e:
        logger.error(f"Gemini API error in respond_to_conversation: {e}")
        # إزالة الرسالة الفاشلة من السجل
        history.pop()
        user_data[str(user_id)]['conversation_history'] = history
        await update.message.reply_text(f"💔 آسفة {user_name}، حدث خطأ ما أثناء محاولتي للرد.")
    finally:
        save_user_data(user_data)

# --- المنطق الداخلي للميزات الخاصة ---

async def perform_search(update: Update, context: CallbackContext, query: str):
    user_id = str(update.effective_user.id)
    set_user_state(user_id, None)
    await respond_to_conversation(update, context, text_input=f"ابحثي لي في الإنترنت عن '{query}' وقدمي لي ملخصاً.")

async def perform_write(update: Update, context: CallbackContext, prompt: str):
    user_id = str(update.effective_user.id)
    set_user_state(user_id, None)
    await respond_to_conversation(update, context, text_input=f"اكتبي لي نصاً إبداعياً عن '{prompt}'.")

async def add_journal_entry(update: Update, context: CallbackContext, entry: str):
    user_id = str(update.effective_user.id)
    journal = get_user_data(user_id).get('journal', [])
    today = datetime.now().strftime("%Y-%m-%d")
    journal.append({"date": today, "entry": entry})
    user_data[str(user_id)]['journal'] = journal
    set_user_state(user_id, None)
    save_user_data(user_data)
    await update.message.reply_text("شكراً لمشاركتي هذا. لقد احتفظت به في يومياتنا. 💕", reply_markup=get_journal_keyboard())

async def add_memory_entry(update: Update, context: CallbackContext, text: str):
    user_id = str(update.effective_user.id)
    set_user_state(user_id, None)
    await respond_to_conversation(update, context, text_input=f"صديقي طلب مني أن أتذكر هذه المعلومة: '{text}'. حلليها وخزنيها في ذاكرتك على شكل 'مفتاح: قيمة'، ثم أخبريه أنكِ تذكرتيها.")

# --- معالج الأزرار ---

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    data = query.data
    user_name = get_user_data(user_id).get('name', 'صديقي')

    # التنقل بين القوائم
    menu_map = {
        "back_to_main": (f"🌸 أهلاً بعودتك، {user_name}!", get_main_keyboard()),
        "activities_menu": ("ماذا نود أن نفعل معاً؟ 🥰", get_activities_keyboard()),
        "advanced_menu": ("هذه هي قدراتي الخاصة لمساعدتك. 🧠", get_advanced_keyboard()),
        "journal_menu": ("هذه يومياتنا السرية. 📓", get_journal_keyboard()),
    }
    if data in menu_map:
        text, markup = menu_map[data]
        await query.edit_message_text(text, reply_markup=markup)

    # الأوامر
    elif data == "get_image":
        await context.bot.send_photo(chat_id=query.message.chat_id, photo=random.choice(MAHIRU_IMAGES), caption=f"🌸 تفضل، {user_name}! 💕")
    elif data == "start_chat":
        await query.edit_message_text("أنا أستمع... 😊")
    
    # أوامر التوجيه
    elif data == "prompt_search":
        set_user_state(user_id, 'awaiting_search_query')
        await query.edit_message_text("🌐 بالتأكيد. اكتب ما تريدني أن أبحث عنه.")
    elif data == "prompt_write":
        set_user_state(user_id, 'awaiting_write_prompt')
        await query.edit_message_text("✍️ يسعدني المساعدة. ما هو موضوع الكتابة؟")
    elif data == "prompt_journal":
        set_user_state(user_id, 'awaiting_journal_entry')
        await query.edit_message_text("اكتب ما يجول في خاطرك... أنا هنا لأستمع. 📝")
    elif data == "prompt_remember":
        set_user_state(user_id, 'awaiting_memory')
        await query.edit_message_text("بالتأكيد! ما هو الشيء الذي تريدني أن أتذكره لك؟ 💡")
    
    # عرض اليوميات
    elif data == "view_journal":
        journal = get_user_data(user_id).get('journal', [])
        if not journal:
            text = "لم نكتب أي شيء في يومياتنا بعد. هيا نبدأ اليوم!"
        else:
            text = "آخر ما كتبناه في يومياتنا:\n\n" + "\n\n".join(f"🗓️ **{entry['date']}**\n- {entry['entry']}" for entry in journal[-3:])
        await query.edit_message_text(text, reply_markup=get_journal_keyboard(), parse_mode='Markdown')

# --- تشغيل البوت ---
def main():
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
        logger.critical("خطأ فادح: متغيرات البيئة TELEGRAM_TOKEN و GEMINI_API_KEY مطلوبة.")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("🌸 Mahiro (The True Companion - Fixed) is running!")
    application.run_polling()

if __name__ == '__main__':
    main()
