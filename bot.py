from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.ext.filters import BaseFilter
import asyncio
import logging
import os

# Настройка логирования для отладки
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ========== ПЕРЕМЕННЫЕ ==========
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
ADMIN_IDS = set()

if not BOT_TOKEN or not ADMIN_PASSWORD:
    logging.error("BOT_TOKEN или ADMIN_PASSWORD не установлены в переменных окружения. Бот не может быть запущен.")
    import sys
    sys.exit(1)

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

# ========== ФИЛЬТРЫ ==========
class NotAdminFilter(BaseFilter):
    def filter(self, message):
        return message.from_user.id not in ADMIN_IDS

not_admin_filter = NotAdminFilter()

# ========== СТАРТ И СОГЛАСИЕ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in banned_users:
        await update.message.reply_text("❌ Вы заблокированы и не можете использовать бота.")
        return

    if context.args:
        try:
            referrer_id = int(context.args[0])
            if referrer_id != user_id and user_id not in invited_by:
                if referrer_id not in referrals:
                    referrals[referrer_id] = 0
                referrals[referrer_id] += 1
                invited_by[user_id] = referrer_id
                await context.bot.send_message(referrer_id, f"🎉 По вашей ссылке зарегистрировался новый пользователь!")
                logging.info(f"User {user_id} was invited by {referrer_id}")
        except (ValueError, IndexError):
            logging.error("Неверный формат реферальной ссылки.")

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
    if user_id in banned_users:
        await query.edit_message_text("❌ Вы заблокированы и не можете использовать бота.")
        return
        
    user_agreements[user_id] = True
    await query.edit_message_text("✅ Вы согласились с условиями. Теперь можете искать собеседника.")
    await show_main_menu(update, user_id)

async def show_main_menu(update, user_id):
    keyboard = [["🔍 Поиск собеседника"], ["⚠️ Сообщить о проблеме"], ["🔗 Мои рефералы"]]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    if update:
        await update.effective_chat.send_message("Выберите действие:", reply_markup=markup)
    else:
        await app.bot.send_message(user_id, "Выберите действие:", reply_markup=markup)

async def referrals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    referral_count = referrals.get(user_id, 0)
    referral_link = f"https://t.me/{context.bot.username}?start={user_id}"
    await update.message.reply_text(
        f"🔗 Ваша реферальная ссылка: `{referral_link}`\n"
        f"👥 Приглашено друзей: `{referral_count}`",
        parse_mode='Markdown'
    )

# ========== ОБРАБОТЧИК СООБЩЕНИЙ ==========
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id in banned_users:
        return

    if not user_agreements.get(user_id, False):
        await update.message.reply_text("❗️Сначала примите условия, используя /start.")
        return

    if user_id in active_chats:
        partner_id = active_chats[user_id]
        await context.bot.send_message(partner_id, text)
        return

    if text == "🔍 Поиск собеседника" or text == "🔍 Начать новый чат":
        if user_id in waiting_users:
            await update.message.reply_text("⏳ Поиск уже идёт...")
            return
        
        await show_interests_menu(update, user_id)
        
    elif text == "⚠️ Сообщить о проблеме":
        if user_id in active_chats:
            partner_id = active_chats[user_id]
            reported_users[user_id] = partner_id
            
            await update.message.reply_text("⚠️ Спасибо за сообщение! Администрация проверит ситуацию.")
            
            for admin_id in ADMIN_IDS:
                await context.bot.send_message(
                    admin_id,
                    f"❗ **Новая жалоба!**\n"
                    f"Пожаловался: `{user_id}` (ник: @{update.effective_user.username})\n"
                    f"На пользователя: `{partner_id}`",
                    parse_mode='Markdown'
                )
        else:
            await update.message.reply_text("❗️ Вы не находитесь в чате, чтобы подать жалобу.")
            
    elif text == "🚫 Завершить чат":
        await end_chat(user_id, context)
    elif text == "👤 Показать мой ник":
        await handle_show_name_request(user_id, context, agree=True)
    elif text == "🙈 Не показывать ник":
        await handle_show_name_request(user_id, context, agree=False)
    elif text == "🔗 Мои рефералы":
        await referrals_command(update, context)
    else:
        await update.message.reply_text("❓ Неизвестная команда.")

async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        
        if update.message.photo:
            await context.bot.send_photo(partner_id, photo=update.message.photo[-1].file_id, caption=update.message.caption)
        elif update.message.video:
            await context.bot.send_video(partner_id, video=update.message.video.file_id, caption=update.message.caption)
        elif update.message.voice:
            await context.bot.send_voice(partner_id, voice=update.message.voice.file_id, caption=update.message.caption)
        elif update.message.sticker:
            await context.bot.send_sticker(partner_id, sticker=update.message.sticker.file_id)

async def show_interests_menu(update, user_id):
    keyboard = [[InlineKeyboardButton(interest, callback_data=f"interest_{interest}")] for interest in available_interests]
    keyboard.append([InlineKeyboardButton("➡️ Готово", callback_data="interests_done")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Выберите ваши интересы (можно несколько), чтобы найти более подходящего собеседника:",
        reply_markup=reply_markup
    )
    user_interests[user_id] = []

async def interests_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
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

async def find_partner(context):
    if len(waiting_users) >= 2:
        user1 = waiting_users.pop(0)
        user2 = waiting_users.pop(0)

        if user1 in search_timeouts:
            search_timeouts.pop(user1).job.schedule_removal()
        if user2 in search_timeouts:
            search_timeouts.pop(user2).job.schedule_removal()
            
        active_chats[user1] = user2
        active_chats[user2] = user1
        show_name_requests[(user1, user2)] = {user1: None, user2: None}

        markup = ReplyKeyboardMarkup(
            [["🚫 Завершить чат", "🔍 Начать новый чат"], ["👤 Показать мой ник", "🙈 Не показывать ник"]],
            resize_keyboard=True
        )
        await context.bot.send_message(user1, "👤 Собеседник найден! Общайтесь.", reply_markup=markup)
        await context.bot.send_message(user2, "👤 Собеседник найден! Общайтесь.", reply_markup=markup)

async def search_timeout_callback(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.chat_id
    if user_id in waiting_users:
        waiting_users.remove(user_id)
        search_timeouts.pop(user_id, None)
        await context.bot.send_message(
            user_id,
            "⏳ Время поиска истекло. Попробуйте ещё раз.",
            reply_markup=ReplyKeyboardRemove()
        )
        await show_main_menu(None, user_id)

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
        
        chat_key = tuple(sorted((user_id, partner_id)))
        show_name_requests.pop(chat_key, None)
        
        keyboard = [["🔍 Начать новый чат"], ["⚠️ Сообщить о проблеме"], ["🔗 Мои рефералы"]]
        markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await context.bot.send_message(user_id, "❌ Чат завершён.", reply_markup=markup)
        await context.bot.send_message(partner_id, "❌ Собеседник завершил чат.", reply_markup=markup)
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
            await update.message.reply_text("✅ Пароль верный. Добро пожаловать в админ-панель.", reply_markup=ReplyKeyboardRemove())
            await show_admin_menu(update)
        else:
            await update.message.reply_text("❌ Неверный пароль.")
        context.user_data['awaiting_admin_password'] = False

async def show_admin_menu(update: Update):
    keyboard = [
        ["📊 Статистика", "♻️ Завершить все чаты"],
        ["👮‍♂️ Забанить", "🔓 Разбанить"],
        ["🔐 Выйти из админ-панели"]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("👑 Админ-панель активна.", reply_markup=markup)

async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    text = update.message.text
    
    if "awaiting_ban_id" in context.user_data:
        try:
            target_id = int(text)
            banned_users.add(target_id)
            await context.bot.send_message(target_id, "🚫 Вы были заблокированы администратором.")
            await update.message.reply_text(f"✅ Пользователь `{target_id}` забанен.")
        except (ValueError, Exception):
            await update.message.reply_text("❌ Неверный ID. Попробуйте снова.")
        finally:
            del context.user_data["awaiting_ban_id"]
        return
        
    if "awaiting_unban_id" in context.user_data:
        try:
            target_id = int(text)
            if target_id in banned_users:
                banned_users.remove(target_id)
                await update.message.reply_text(f"✅ Пользователь `{target_id}` разбанен.")
            else:
                await update.message.reply_text(f"❌ Пользователь `{target_id}` не был забанен.")
        except (ValueError, Exception):
            await update.message.reply_text("❌ Неверный ID. Попробуйте снова.")
        finally:
            del context.user_data["awaiting_unban_id"]
        return

    if text == "📊 Статистика":
        await update.message.reply_text(
            f"👥 Пользователей согласилось: {len([u for u in user_agreements.values() if u])}\n"
            f"💬 Активных чатов: {len(active_chats)//2}\n"
            f"⚠️ Жалоб: {len(reported_users)}\n"
            f"⛔ Забанено: {len(banned_users)}\n"
            f"🔗 Всего рефералов: {sum(referrals.values())}"
        )
    elif text == "♻️ Завершить все чаты":
        active_chat_users = list(active_chats.keys())
        for uid in active_chat_users:
            if uid in active_chats:
                await end_chat(uid, context)
        await update.message.reply_text("🔄 Все активные чаты завершены.")
    elif text == "👮‍♂️ Забанить":
        await update.message.reply_text("Введите ID пользователя, которого нужно забанить:")
        context.user_data["awaiting_ban_id"] = True
    elif text == "🔓 Разбанить":
        await update.message.reply_text("Введите ID пользователя, которого нужно разбанить:")
        context.user_data["awaiting_unban_id"] = True
    elif text == "🔐 Выйти из админ-панели":
        ADMIN_IDS.discard(user_id)
        await update.message.reply_text("🚪 Вы вышли из админ-панели.", reply_markup=ReplyKeyboardRemove())

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    PORT = int(os.environ.get('PORT', 5000))
    WEBHOOK_URL = "https://test-1-1-zard.onrender.com"

    if not BOT_TOKEN or not ADMIN_PASSWORD:
        logging.error("Бот не может быть запущен без токена и пароля администратора. Проверьте переменные окружения.")
        import sys
        sys.exit(1)
    else:
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        
        # Добавляем обработчик для пароля администратора
        # Он должен идти перед основным message_handler, чтобы не конфликтовать
        app.add_handler(MessageHandler(filters.TEXT & filters.Regex(ADMIN_PASSWORD) & not_admin_filter, password_handler))
        
        # Основные обработчики
        app.add_handler(CommandHandler('start', start))
        app.add_handler(CommandHandler('admin', admin_command))
        app.add_handler(CallbackQueryHandler(agree_callback, pattern='^agree$'))
        app.add_handler(CallbackQueryHandler(interests_callback, pattern='^interest_'))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))
        app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.VOICE | filters.Sticker.ALL, media_handler))

        app.run_webhook(listen="0.0.0.0", port=PORT, url_path=BOT_TOKEN, webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
