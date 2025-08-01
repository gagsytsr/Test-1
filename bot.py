from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.ext.filters import BaseFilter
import logging
import os
import sys

# ========== НАСТРОЙКИ ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ========== ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ==========
BOT_TOKEN      = os.environ.get('BOT_TOKEN')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
WEBHOOK_URL    = "https://test-1-1-zard.onrender.com"

if not BOT_TOKEN or not ADMIN_PASSWORD:
    logging.error("Не заданы BOT_TOKEN или ADMIN_PASSWORD")
    sys.exit(1)

# ========== ГЛОБАЛЬНЫЕ СТРУКТУРЫ ==========
ADMIN_IDS         = set()
waiting_users     = []
active_chats      = {}
show_name_requests= {}
user_agreements   = {}
banned_users      = set()
reported_users    = {}
search_timeouts   = {}
user_interests    = {}
available_interests = ["Музыка", "Игры", "Кино", "Путешествия", "Спорт", "Книги"]
referrals         = {}
invited_by        = {}

# ========== КАСТОМНЫЙ ФИЛЬТР ==========
class NotAdminFilter(BaseFilter):
    def filter(self, message):
        return message.from_user.id not in ADMIN_IDS

not_admin_filter = NotAdminFilter()

# ========== ОБРАБОТЧИК ОШИБОК ==========
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error("Исключение: %s", context.error)

# ========== /start ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in banned_users:
        await update.message.reply_text("❌ Вы заблокированы.")
        return

    # рефералка
    if context.args:
        try:
            ref = int(context.args[0])
            if ref != user_id and user_id not in invited_by:
                referrals.setdefault(ref, 0)
                referrals[ref] += 1
                invited_by[user_id] = ref
                await context.bot.send_message(ref, "🎉 Новый реферал!")
        except:
            logging.warning("Некорректный реферальный параметр")

    user_agreements[user_id] = False
    text = (
        "👋 Добро пожаловать в анонимный чат!\n\n"
        "⚠️ Прочитайте правила и нажмите «Согласен»:\n"
        "• Нет спама\n"
        "• Уважайте собеседника\n\n"
    )
    kb = [[InlineKeyboardButton("✅ Согласен", callback_data="agree")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

# ========== agree ==========
async def agree_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if uid in banned_users:
        await q.edit_message_text("❌ Вы заблокированы.")
        return

    user_agreements[uid] = True
    await q.edit_message_text("✅ Вы согласились. Выберите действие в меню.")
    await show_main_menu(update, uid)

# ========== Главное меню ==========
async def show_main_menu(update, user_id):
    kb = [["🔍 Поиск собеседника"], ["⚠️ Сообщить о проблеме"], ["🔗 Мои рефералы"]]
    markup = ReplyKeyboardMarkup(kb, resize_keyboard=True)
    if update:
        await update.effective_chat.send_message("Выберите действие:", reply_markup=markup)
    else:
        await app.bot.send_message(user_id, "Выберите действие:", reply_markup=markup)

# ========== Меню интересов ==========
async def show_interests_menu(update, user_id):
    kb = [[InlineKeyboardButton(i, callback_data=f"interest_{i}")] for i in available_interests]
    kb.append([InlineKeyboardButton("➡️ Готово", callback_data="interests_done")])
    await update.message.reply_text("Выберите интересы:", reply_markup=InlineKeyboardMarkup(kb))
    user_interests[user_id] = []

# ========== Обработка interest_* ==========
async def interests_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    data = q.data

    logging.info(f"[CALLBACK] {uid=} {data=}")
    await q.answer()

    # выбор/снятие метки
    if data.startswith("interest_"):
        interest = data.split("interest_",1)[1]
        lst = user_interests.setdefault(uid, [])
        if interest in lst:
            lst.remove(interest)
        else:
            lst.append(interest)

        # обновляем клавиатуру
        kb = []
        for i in available_interests:
            mark = "✅ " if i in lst else ""
            kb.append([InlineKeyboardButton(mark + i, callback_data=f"interest_{i}")])
        kb.append([InlineKeyboardButton("➡️ Готово", callback_data="interests_done")])
        await q.edit_message_reply_markup(InlineKeyboardMarkup(kb))

# ========== Обработка interests_done ==========
async def interests_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()
    chosen = user_interests.get(uid, [])
    await q.edit_message_text(f"✅ Ваши интересы: {', '.join(chosen) or 'Не выбраны'}.\nИдёт поиск...")
    waiting_users.append(uid)

    # таймаут поиска
    job = context.application.job_queue.run_once(
        search_timeout_callback, 120, chat_id=uid, name=str(uid)
    )
    search_timeouts[uid] = job

    await find_partner(context)

# ========== Здесь идут все остальные ваши функции без изменений: 
# referrals_command, message_handler, media_handler, find_partner, 
# search_timeout_callback, handle_show_name_request, end_chat, admin_command, 
# password_handler, show_admin_menu, admin_menu_handler
# ================================================

# ========== Запуск ==========
if __name__ == '__main__':
    PORT = int(os.environ.get('PORT', 5000))
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_error_handler(error_handler)

    # 🛎 CallbackQueryHandlers
    app.add_handler(CallbackQueryHandler(agree_callback,              pattern='^agree$'))
    app.add_handler(CallbackQueryHandler(interests_callback,         pattern='^interest_'))
    app.add_handler(CallbackQueryHandler(interests_done_callback,    pattern='^interests_done$'))

    # 📌 Команды
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('admin', admin_command))

    # 🔑 Админ-пароль
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(ADMIN_PASSWORD) & not_admin_filter, password_handler))

    # 💬 Текстовые сообщения
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))

    # 📷 Медиа
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.VOICE | filters.Sticker.ALL, media_handler))

    # 🚀 Запускаем webhook
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
    )
