from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.ext.filters import BaseFilter
import asyncio
import logging
import os
import sys

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# === Переменные окружения ===
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
WEBHOOK_URL = "https://test-1-1-zard.onrender.com"  # <-- ВАШ вебхук

if not BOT_TOKEN or not ADMIN_PASSWORD:
    logging.error("BOT_TOKEN или ADMIN_PASSWORD не установлены.")
    sys.exit(1)

ADMIN_IDS = set()
waiting_users = []
active_chats = {}
show_name_requests = {}
user_agreements = {}
banned_users = set()
reported_users = {}
search_timeouts = {}
user_interests = {}
available_interests = ["Музыка", "Игры", "Кино", "Путешествия", "Спорт", "Книги"]
referrals = {}
invited_by = {}

# === Фильтр ===
class NotAdminFilter(BaseFilter):
    def filter(self, message):
        return message.from_user.id not in ADMIN_IDS

not_admin_filter = NotAdminFilter()

# === Обработчик ошибок ===
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error("Ошибка: %s", context.error)

# === Start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in banned_users:
        await update.message.reply_text("❌ Вы заблокированы.")
        return

    if context.args:
        try:
            referrer_id = int(context.args[0])
            if referrer_id != user_id and user_id not in invited_by:
                referrals.setdefault(referrer_id, 0)
                referrals[referrer_id] += 1
                invited_by[user_id] = referrer_id
                await context.bot.send_message(referrer_id, "🎉 По вашей ссылке зарегистрировался пользователь!")
        except:
            logging.warning("Неверная реферальная ссылка.")

    user_agreements[user_id] = False
    agreement_text = (
        "👋 Добро пожаловать в анонимный чат!\n\n"
        "⚠️ Подтвердите согласие с правилами:\n"
        "• Соблюдайте уважение.\n"
        "• Администрация не несёт ответственности за контент пользователей.\n\n"
        "Нажмите 'Согласен' чтобы начать."
    )
    keyboard = [[InlineKeyboardButton("✅ Согласен", callback_data="agree")]]
    await update.message.reply_text(agreement_text, reply_markup=InlineKeyboardMarkup(keyboard))

# === Agree ===
async def agree_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id in banned_users:
        await query.edit_message_text("❌ Вы заблокированы.")
        return

    user_agreements[user_id] = True
    await query.edit_message_text("✅ Вы согласились. Теперь вы можете искать собеседника.")
    await show_main_menu(update, user_id)

# === Главное меню ===
async def show_main_menu(update, user_id):
    keyboard = [["🔍 Поиск собеседника"], ["⚠️ Сообщить о проблеме"], ["🔗 Мои рефералы"]]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    if update:
        await update.effective_chat.send_message("Выберите действие:", reply_markup=markup)
    else:
        await app.bot.send_message(user_id, "Выберите действие:", reply_markup=markup)

# === Выбор интересов ===
async def show_interests_menu(update, user_id):
    keyboard = [[InlineKeyboardButton(interest, callback_data=f"interest_{interest}")] for interest in available_interests]
    keyboard.append([InlineKeyboardButton("➡️ Готово", callback_data="interests_done")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите интересы:", reply_markup=reply_markup)
    user_interests[user_id] = []

# === Обработка интересов ===
async def interests_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    logging.info(f"[DEBUG] Callback received: {query.data} from user {user_id}")  # <-- DEBUG
    await query.answer()

    if query.data.startswith("interest_"):
        interest = query.data.replace("interest_", "")
        if interest in user_interests.get(user_id, []):
            user_interests[user_id].remove(interest)
        else:
            user_interests.setdefault(user_id, []).append(interest)

        keyboard = []
        for interest in available_interests:
            text = f"✅ {interest}" if interest in user_interests.get(user_id, []) else interest
            keyboard.append([InlineKeyboardButton(text, callback_data=f"interest_{interest}")])
        keyboard.append([InlineKeyboardButton("➡️ Готово", callback_data="interests_done")])
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "interests_done":
        await query.edit_message_text(f"✅ Ваши интересы: {', '.join(user_interests.get(user_id, [])) or 'Не выбраны'}.\nИщем собеседника...")
        waiting_users.append(user_id)

        job = context.application.job_queue.run_once(
            search_timeout_callback,
            120,
            chat_id=user_id,
            name=str(user_id)
        )
        search_timeouts[user_id] = job

        await find_partner(context)

# === Остальные функции ===
# (неизменны — всё как у вас: referrals_command, message_handler, media_handler, find_partner, search_timeout_callback, handle_show_name_request, end_chat, admin_command, password_handler, show_admin_menu, admin_menu_handler)

# === Запуск приложения ===
if __name__ == '__main__':
    PORT = int(os.environ.get('PORT', 5000))
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_error_handler(error_handler)

    # === Обработчики CallbackQuery ===
    app.add_handler(CallbackQueryHandler(agree_callback, pattern='^agree$'))
    app.add_handler(CallbackQueryHandler(interests_callback, pattern='^(interest_.*|interests_done)$'))  # <-- FIXED

    # === Команды ===
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('admin', admin_command))

    # === Админ-пароль ===
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(ADMIN_PASSWORD) & not_admin_filter, password_handler))

    # === Основной обработчик текста ===
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))

    # === Медиа ===
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.VOICE | filters.Sticker.ALL, media_handler))

    # === Webhook-запуск для Render ===
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
    )
