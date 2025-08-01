import asyncio
import logging
import os
import sys

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Настройка логирования для вывода информации о работе бота.
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

# --- Настройки ---
# BOT_TOKEN и ADMIN_PASSWORD должны быть установлены как переменные окружения.
# Если они не заданы, бот не запустится.
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')

# URL для вебхуков, нужен для развёртывания на сервере.
WEBHOOK_URL = "https://test-1-1-zard.onrender.com"

if not BOT_TOKEN or not ADMIN_PASSWORD:
    logging.error("BOT_TOKEN или ADMIN_PASSWORD не заданы в переменных окружения.")
    sys.exit(1)

# --- Переменные состояния ---
# Эти словари и списки будут хранить информацию о пользователях и чатах
# пока бот работает. После перезапуска все данные будут потеряны.
ADMIN_IDS = set()
banned_users = set()
user_agreements = {}
user_interests = {}
waiting_users = []
active_chats = {}
reported_users = {}
search_timeouts = {}
show_name_requests = {}
referrals = {}
invited_by = {}

# Доступные для выбора интересы
AVAILABLE_INTERESTS = ["Музыка", "Игры", "Кино", "Путешествия", "Спорт", "Книги"]

# --- Обработчики ошибок ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка ошибок, которые возникают при обработке обновлений."""
    logging.error(f"Исключение при обработке обновления: {context.error}")
    if update and update.effective_chat:
        logging.error(f"Обновление {update} вызвало ошибку в чате {update.effective_chat.id}")


# --- Команды и основная логика ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /start."""
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    if user_id in banned_users:
        await update.message.reply_text("❌ Вы заблокированы и не можете использовать бота.")
        return

    # Обработка реферальной ссылки, если она есть
    if context.args:
        try:
            referrer_id = int(context.args[0])
            if referrer_id != user_id and user_id not in invited_by:
                referrals.setdefault(referrer_id, 0)
                referrals[referrer_id] += 1
                invited_by[user_id] = referrer_id
                await context.bot.send_message(
                    referrer_id, f"🎉 По вашей ссылке зарегистрировался новый пользователь!"
                )
                logging.info(f"User {user_id} (@{username}) was invited by {referrer_id}")
        except (ValueError, IndexError):
            logging.error("Неверный формат реферальной ссылки.")

    # Проверка согласия с правилами
    if user_agreements.get(user_id):
        await show_main_menu(user_id, context)
        return

    # Запрашиваем согласие
    agreement_text = (
        "👋 Добро пожаловать в анонимный чат!\n\n"
        "⚠️ Перед использованием подтвердите согласие с правилами:\n"
        "• Запрещено нарушать законы.\n"
        "• Соблюдайте уважение.\n"
        "• Администрация не несет ответственности за контент.\n\n"
        "Нажмите 'Согласен', чтобы начать."
    )
    keyboard = [[InlineKeyboardButton("✅ Согласен", callback_data="agree")]]
    await update.message.reply_text(agreement_text, reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Единый обработчик всех callback-запросов."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id

    if user_id in banned_users:
        await query.edit_message_text("❌ Вы заблокированы и не можете использовать бота.")
        return

    if data == "agree":
        user_agreements[user_id] = True
        await query.edit_message_text("✅ Вы согласились с условиями. Теперь можете искать собеседника.")
        await show_main_menu(user_id, context)
    
    elif data.startswith("interest_"):
        interest = data.replace("interest_", "")
        user_interests.setdefault(user_id, [])
        if interest in user_interests[user_id]:
            user_interests[user_id].remove(interest)
        else:
            user_interests[user_id].append(interest)
        
        keyboard = []
        for i in AVAILABLE_INTERESTS:
            text = f"✅ {i}" if i in user_interests[user_id] else i
            keyboard.append([InlineKeyboardButton(text, callback_data=f"interest_{i}")])
        keyboard.append([InlineKeyboardButton("➡️ Готово", callback_data="interests_done")])
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "interests_done":
        await query.edit_message_text(
            f"✅ Ваши интересы: {', '.join(user_interests.get(user_id, [])) or 'Не выбраны'}.\nИщем собеседника..."
        )
        await start_search(user_id, context)


async def show_main_menu(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает основное меню пользователю."""
    keyboard = [["🔍 Поиск собеседника"], ["⚠️ Сообщить о проблеме"], ["🔗 Мои рефералы"]]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await context.bot.send_message(user_id, "Выберите действие:", reply_markup=markup)


async def show_chat_menu(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает меню чата пользователю."""
    keyboard = [
        ["🚫 Завершить чат", "🔍 Начать новый чат"],
        ["👤 Показать мой ник", "🙈 Не показывать ник"]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await context.bot.send_message(user_id, "Вы в чате. Общайтесь.", reply_markup=markup)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает все текстовые сообщения от пользователей."""
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id in banned_users:
        return
    
    if not user_agreements.get(user_id):
        await update.message.reply_text("❗️Сначала примите условия, используя /start.")
        return

    # Если пользователь в чате, пересылаем сообщение собеседнику
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        await context.bot.send_message(partner_id, text)
        return

    # Обработка команд из главного меню
    if text == "🔍 Поиск собеседника" or text == "🔍 Начать новый чат":
        if user_id in waiting_users:
            await update.message.reply_text("⏳ Поиск уже идёт...")
        else:
            await show_interests_menu(user_id, context)
    
    elif text == "⚠️ Сообщить о проблеме":
        await report_issue(user_id, update.effective_user.username, context)

    elif text == "🚫 Завершить чат":
        await end_chat(user_id, context)
        
    elif text == "👤 Показать мой ник":
        await handle_show_name_request(user_id, context, agree=True)
    
    elif text == "🙈 Не показывать ник":
        await handle_show_name_request(user_id, context, agree=False)
        
    elif text == "🔗 Мои рефералы":
        await show_referrals(user_id, context)
    
    else:
        await update.message.reply_text("❓ Неизвестная команда. Пожалуйста, выберите из меню.")


async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает медиафайлы (фото, видео, стикеры, голосовые)."""
    user_id = update.effective_user.id
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        await context.bot.forward_message(
            chat_id=partner_id,
            from_chat_id=user_id,
            message_id=update.message.message_id
        )


async def show_interests_menu(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает меню выбора интересов."""
    keyboard = [[InlineKeyboardButton(interest, callback_data=f"interest_{interest}")] for interest in AVAILABLE_INTERESTS]
    keyboard.append([InlineKeyboardButton("➡️ Готово", callback_data="interests_done")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    user_interests[user_id] = [] # Сбрасываем интересы перед выбором
    await context.bot.send_message(
        user_id,
        "Выберите ваши интересы (можно несколько), чтобы найти более подходящего собеседника:",
        reply_markup=reply_markup
    )


async def start_search(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запускает поиск собеседника."""
    waiting_users.append(user_id)
    
    # Установка таймаута на поиск
    job = context.application.job_queue.run_once(
        search_timeout_callback,
        120,
        chat_id=user_id,
        name=str(user_id)
    )
    search_timeouts[user_id] = job
    
    await find_partner(context)


async def find_partner(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ищет пару для общения среди ожидающих пользователей."""
    if len(waiting_users) >= 2:
        user1_id = waiting_users.pop(0)
        user2_id = waiting_users.pop(0)

        # Отменяем таймауты
        if user1_id in search_timeouts:
            search_timeouts.pop(user1_id).job.schedule_removal()
        if user2_id in search_timeouts:
            search_timeouts.pop(user2_id).job.schedule_removal()
            
        active_chats[user1_id] = user2_id
        active_chats[user2_id] = user1_id
        show_name_requests[tuple(sorted((user1_id, user2_id)))] = {user1_id: None, user2_id: None}
        
        # Уведомляем пользователей о начале чата и показываем меню чата
        await show_chat_menu(user1_id, context)
        await show_chat_menu(user2_id, context)
        
async def search_timeout_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает истечение времени поиска."""
    user_id = context.job.chat_id
    if user_id in waiting_users:
        waiting_users.remove(user_id)
        search_timeouts.pop(user_id, None)
        await context.bot.send_message(
            user_id,
            "⏳ Время поиска истекло. Попробуйте ещё раз.",
            reply_markup=ReplyKeyboardRemove()
        )
        await show_main_menu(user_id, context)


async def end_chat(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Завершает текущий чат."""
    if user_id in active_chats:
        partner_id = active_chats.pop(user_id)
        active_chats.pop(partner_id, None)
        
        chat_key = tuple(sorted((user_id, partner_id)))
        show_name_requests.pop(chat_key, None)
        
        await context.bot.send_message(user_id, "❌ Чат завершён.")
        await context.bot.send_message(partner_id, "❌ Собеседник завершил чат.")
        
        await show_main_menu(user_id, context)
        await show_main_menu(partner_id, context)
    else:
        await context.bot.send_message(user_id, "❗️Вы не находитесь в чате.")
        

async def report_issue(user_id: int, username: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет жалобу админам."""
    if user_id not in active_chats:
        await context.bot.send_message(user_id, "❗️ Вы не в чате, чтобы подать жалобу.")
        return

    partner_id = active_chats[user_id]
    reported_users[user_id] = partner_id
    
    await context.bot.send_message(user_id, "⚠️ Спасибо за сообщение! Администрация проверит ситуацию.")
    
    for admin_id in ADMIN_IDS:
        await context.bot.send_message(
            admin_id,
            f"❗ **Новая жалоба!**\n"
            f"Пожаловался: `{user_id}` (ник: @{username})\n"
            f"На пользователя: `{partner_id}`",
            parse_mode='Markdown'
        )

async def handle_show_name_request(user_id: int, context: ContextTypes.DEFAULT_TYPE, agree: bool) -> None:
    """Обрабатывает запросы на показ ника."""
    if user_id not in active_chats:
        await context.bot.send_message(user_id, "❗️Вы сейчас не в чате.")
        return

    partner_id = active_chats[user_id]
    chat_key = tuple(sorted((user_id, partner_id)))

    show_name_requests[chat_key][user_id] = agree
    partner_agree = show_name_requests[chat_key][partner_id]

    if partner_agree is None:
        await context.bot.send_message(user_id, "⏳ Ожидаем решение собеседника.")
    elif agree and partner_agree:
        name1 = f"@{update.effective_user.username}" if update.effective_user.username else 'Без ника'
        name2_user = await context.bot.get_chat(partner_id)
        name2 = f"@{name2_user.username}" if name2_user.username else 'Без ника'

        await context.bot.send_message(user_id, f"🔓 Ник собеседника: {name2}")
        await context.bot.send_message(partner_id, f"🔓 Ник собеседника: {name1}")
    else:
        await context.bot.send_message(user_id, "❌ Кто-то из вас отказался показывать ник.")
        await context.bot.send_message(partner_id, "❌ Кто-то из вас отказался показывать ник.")


async def show_referrals(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает реферальную статистику пользователя."""
    referral_count = referrals.get(user_id, 0)
    bot_info = await context.bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start={user_id}"
    await context.bot.send_message(
        user_id,
        f"🔗 Ваша реферальная ссылка: `{referral_link}`\n"
        f"👥 Приглашено друзей: `{referral_count}`",
        parse_mode='Markdown'
    )


# --- Админ-панель ---
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /admin для входа в админ-панель."""
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:
        await show_admin_menu(user_id, context)
    else:
        await update.message.reply_text("🔐 Введите пароль для доступа к админ-панели:")
        context.user_data['awaiting_admin_password'] = True


async def password_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает введённый админ-пароль."""
    user_id = update.effective_user.id
    if update.message.text.strip() == ADMIN_PASSWORD:
        ADMIN_IDS.add(user_id)
        await update.message.reply_text("✅ Пароль верный. Добро пожаловать в админ-панель.")
        await show_admin_menu(user_id, context)
    else:
        await update.message.reply_text("❌ Неверный пароль.")
    del context.user_data['awaiting_admin_password']


async def show_admin_menu(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает админ-меню."""
    keyboard = [
        ["📊 Статистика", "♻️ Завершить все чаты"],
        ["👮‍♂️ Забанить", "🔓 Разбанить"],
        ["🔐 Выйти из админ-панели"]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await context.bot.send_message(user_id, "👑 Админ-панель активна.", reply_markup=markup)


async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команды из админ-меню."""
    user_id = update.effective_user.id
    text = update.message.text
    
    # Логика ожидания ID для бана/разбана
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

    # Обработка команд админ-меню
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


# --- Основная точка входа ---
def main() -> None:
    """Запускает бота в режиме вебхуков."""
    PORT = int(os.environ.get('PORT', 5000))
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Обработчики
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('admin', admin_command))
    
    # Обработчик сообщений для админа (для пароля)
    app.add_handler(MessageHandler(filters.TEXT & filters.User(user_data={'awaiting_admin_password': True}), password_handler))
    
    # Обработчик админ-команд (для тех, кто уже в админке)
    app.add_handler(MessageHandler(filters.TEXT & filters.User(user_id=list(ADMIN_IDS)), admin_menu_handler))

    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND) & ~filters.User(user_data={'awaiting_admin_password': True}), message_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.VOICE | filters.Sticker.ALL, media_handler))
    
    app.add_error_handler(error_handler)
    
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
    )


if __name__ == '__main__':
    main()
