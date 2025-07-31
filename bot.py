from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import asyncio
import os
import logging

# Настройка логирования для отладки
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ========== ПЕРЕМЕННЫЕ ==========
# Загружаем токен бота и пароль администратора из переменных окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
ADMIN_IDS = set()

if not BOT_TOKEN or not ADMIN_PASSWORD:
    logging.error("BOT_TOKEN или ADMIN_PASSWORD не установлены в переменных окружения. Бот не может быть запущен.")
    import sys
    sys.exit(1)

# Временное хранилище
waiting_users = []
active_chats = {}
show_name_requests = {}
user_agreements = {}
reported_users = set()

# ========== СТАРТ И СОГЛАСИЕ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_agreements[user_id] = False
    agreement_text = (
        "👋 Добро пожаловать в анонимный чат!\n\n"
        "⚠️ Перед использованием подтвердите согласие с правилами:\n"
        "• Запрещено нарушать законы.\n"
        "• Соблюдайте уважение.\n"
        "• Администрация не несет ответственности за контент пользователей.\n\n"
        "Нажмите 'Согласен' чтобы начать."
    )
    keyboard = [[InlineKeyboardButton("✅ Согласен", callback_data="agree")]]
    await update.message.reply_text(agreement_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def agree_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_agreements[user_id] = True
    await query.edit_message_text("✅ Вы согласились с условиями. Теперь можете искать собеседника.")
    await show_main_menu(update, user_id)

async def show_main_menu(update, user_id):
    keyboard = [["🔍 Поиск собеседника"], ["⚠️ Сообщить о проблеме"]]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.effective_chat.send_message("Выберите действие:", reply_markup=markup)

# ========== ПОИСК И ЧАТ ==========
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if not user_agreements.get(user_id, False):
        await update.message.reply_text("❗️Сначала примите условия, используя /start.")
        return

    # Сообщение админ-панели
    if user_id in ADMIN_IDS:
        await admin_menu_handler(update, context)
        return

    # Пользователь в чате
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        await context.bot.send_message(partner_id, text)
        return

    # Команды
    if text == "🔍 Поиск собеседника":
        if user_id in waiting_users:
            await update.message.reply_text("⏳ Поиск уже идёт...")
            return
        waiting_users.append(user_id)
        await update.message.reply_text("🔎 Ищем собеседника...")
        await find_partner(context)
    elif text == "⚠️ Сообщить о проблеме":
        reported_users.add(user_id)
        await update.message.reply_text("⚠️ Спасибо за сообщение! Администрация проверит ситуацию.")
    elif text == "🚫 Завершить чат":
        await end_chat(user_id, context)
    elif text == "👤 Показать мой ник":
        await handle_show_name_request(user_id, context, agree=True)
    elif text == "🙈 Не показывать ник":
        await handle_show_name_request(user_id, context, agree=False)
    else:
        await update.message.reply_text("❓ Неизвестная команда.")

async def find_partner(context):
    if len(waiting_users) >= 2:
        user1 = waiting_users.pop(0)
        user2 = waiting_users.pop(0)
        active_chats[user1] = user2
        active_chats[user2] = user1
        show_name_requests[(user1, user2)] = {user1: None, user2: None}

        markup = ReplyKeyboardMarkup(
            [["🚫 Завершить чат"], ["👤 Показать мой ник", "🙈 Не показывать ник"]],
            resize_keyboard=True
        )
        await context.bot.send_message(user1, "👤 Собеседник найден! Общайтесь.", reply_markup=markup)
        await context.bot.send_message(user2, "👤 Собеседник найден! Общайтесь.", reply_markup=markup)

async def handle_show_name_request(user_id, context, agree):
    if user_id not in active_chats:
        await context.bot.send_message(user_id, "❗️Вы сейчас не в чате.")
        return

    partner_id = active_chats[user_id]
    chat_key = tuple(sorted((user_id, partner_id)))

    if chat_key not in show_name_requests:
        await context.bot.send_message(user_id, "❗️Ошибка запроса.")
        return

    show_name_requests[chat_key][user_id] = agree
    other = show_name_requests[chat_key][partner_id]

    if other is None:
        await context.bot.send_message(user_id, "⏳ Ожидаем решение собеседника.")
    elif agree and other:
        name1 = f"@{(await context.bot.get_chat(user_id)).username or 'Без ника'}"
        name2 = f"@{(await context.bot.get_chat(partner_id)).username or 'Без ника'}"
        await context.bot.send_message(user_id, f"🔓 Ник собеседника: {name2}")
        await context.bot.send_message(partner_id, f"🔓 Ник собеседника: {name1}")
    else:
        await context.bot.send_message(user_id, "❌ Кто-то из вас отказался показывать ник.")
        await context.bot.send_message(partner_id, "❌ Кто-то из вас отказался показывать ник.")

async def end_chat(user_id, context):
    if user_id in active_chats:
        partner_id = active_chats.pop(user_id)
        active_chats.pop(partner_id, None)
        await context.bot.send_message(user_id, "❌ Чат завершён.", reply_markup=ReplyKeyboardRemove())
        await context.bot.send_message(partner_id, "❌ Собеседник завершил чат.", reply_markup=ReplyKeyboardRemove())
        await show_main_menu(None, user_id)
        await show_main_menu(None, partner_id)
    else:
        await context.bot.send_message(user_id, "❗️Вы не находитесь в чате.")

# ========== АДМИНКА ==========
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:
        await show_admin_menu(update)
    else:
        await update.message.reply_text("🔐 Введите пароль для доступа к админ-панели:")
        context.user_data['awaiting_admin_password'] = True

async def password_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_admin_password'):
        if update.message.text.strip() == ADMIN_PASSWORD:
            ADMIN_IDS.add(update.effective_user.id)
            await update.message.reply_text("✅ Пароль верный. Добро пожаловать в админ-панель.")
            await show_admin_menu(update)
        else:
            await update.message.reply_text("❌ Неверный пароль.")
        context.user_data['awaiting_admin_password'] = False

async def show_admin_menu(update: Update):
    keyboard = [
        ["📊 Статистика", "♻️ Завершить все чаты"],
        ["🔐 Выйти из админ-панели"]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("👑 Админ-панель активна.", reply_markup=markup)

async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    text = update.message.text

    if text == "📊 Статистика":
        await update.message.reply_text(
            f"👥 Пользователей согласилось: {len([u for u in user_agreements.values() if u])}\n"
            f"💬 Активных чатов: {len(active_chats)//2}\n"
            f"⚠️ Жалоб: {len(reported_users)}"
        )
    elif text == "♻️ Завершить все чаты":
        for uid in list(active_chats.keys()):
            await end_chat(uid, context)
        await update.message.reply_text("🔄 Все активные чаты завершены.")
    elif text == "🔐 Выйти из админ-панели":
        ADMIN_IDS.discard(user_id)
        await update.message.reply_text("🚪 Вы вышли из админ-панели.", reply_markup=ReplyKeyboardRemove())

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    if not BOT_TOKEN or not ADMIN_PASSWORD:
        logging.error("Бот не может быть запущен без токена и пароля администратора. Проверьте переменные окружения.")
        import sys
        sys.exit(1)
    else:
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        
        # Обработчики в твоем рабочем порядке
        app.add_handler(CommandHandler('start', start))
        app.add_handler(CommandHandler('admin', admin_command))
        
        app.add_handler(CallbackQueryHandler(agree_callback))
        
        # Эти обработчики перехватывают все текстовые сообщения, что может вызывать конфликт
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), password_handler))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))

        app.run_polling()
