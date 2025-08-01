import asyncio
import logging
import os
import sys
import json
import time
from typing import Dict, List, Optional

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
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
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')

# Вебхук теперь жёстко прописан в коде.
WEBHOOK_URL = "https://test-1-1-zard.onrender.com"

if not BOT_TOKEN or not ADMIN_PASSWORD:
    logging.error("BOT_TOKEN или ADMIN_PASSWORD не заданы в переменных окружения.")
    sys.exit(1)

# --- Файлы для локального хранения данных ---
DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

PROFILES_FILE = os.path.join(DATA_DIR, "profiles.json")
ADMIN_FILE = os.path.join(DATA_DIR, "admins.json")
BANS_FILE = os.path.join(DATA_DIR, "bans.json")
AGREEMENTS_FILE = os.path.join(DATA_DIR, "agreements.json")
CHATS_FILE = os.path.join(DATA_DIR, "chats.json")
REPORTED_FILE = os.path.join(DATA_DIR, "reported.json")
REFERRALS_FILE = os.path.join(DATA_DIR, "referrals.json")
LIKES_FILE = os.path.join(DATA_DIR, "likes.json")
MUTES_FILE = os.path.join(DATA_DIR, "mutes.json")


# --- Функции для сохранения/загрузки данных ---
def save_data(data: dict, filename: str):
    """Сохраняет словарь в JSON-файл."""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_data(filename: str, default: dict) -> dict:
    """Загружает данные из JSON-файла или возвращает значение по умолчанию."""
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default

# --- Переменные состояния ---
ADMIN_IDS = set(load_data(ADMIN_FILE, {"admins": []})["admins"])
banned_users = set(load_data(BANS_FILE, {"banned": []})["banned"])
muted_users = set(load_data(MUTES_FILE, {"muted": []})["muted"])
user_agreements = load_data(AGREEMENTS_FILE, {})
user_profiles = load_data(PROFILES_FILE, {})
user_interests = {}
waiting_users = []
active_chats = load_data(CHATS_FILE, {})
reported_users = load_data(REPORTED_FILE, {"reports": {}})
referrals = load_data(REFERRALS_FILE, {"referrals": {}})["referrals"]
invited_by = {}
user_likes: Dict[str, int] = load_data(LIKES_FILE, {"likes": {}})["likes"]

user_states = {}

AVAILABLE_INTERESTS = ["Музыка", "Игры", "Кино", "Путешествия", "Спорт", "Книги"]
GENDERS = ["Мужчина", "Женщина", "Другое"]

# --- Обработчики ошибок ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка ошибок, которые возникают при обработке обновлений."""
    logging.error(f"Исключение при обработке обновления: {context.error}")
    if update and update.effective_chat:
        logging.error(f"Обновление {update} вызвало ошибку в чате {update.effective_chat.id}")

# --- Команды и основная логика ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /start."""
    user_id = str(update.effective_user.id)
    username = update.effective_user.username
    
    if user_id in banned_users:
        await update.message.reply_text("❌ Вы заблокированы и не можете использовать бота.")
        return

    if context.args:
        try:
            referrer_id = str(context.args[0])
            if referrer_id != user_id and user_id not in invited_by:
                referrals.setdefault(referrer_id, 0)
                referrals[referrer_id] += 1
                invited_by[user_id] = referrer_id
                save_data({"referrals": referrals}, REFERRALS_FILE)
                await context.bot.send_message(
                    referrer_id, f"🎉 По вашей ссылке зарегистрировался новый пользователь!"
                )
                logging.info(f"User {user_id} (@{username}) was invited by {referrer_id}")
        except (ValueError, IndexError):
            logging.error("Неверный формат реферальной ссылки.")

    if user_agreements.get(user_id):
        await show_main_menu(user_id, context)
        return

    agreement_text = (
        "👋 Добро пожаловать в анонимный чат!\n\n"
        "⚠️ Перед использованием подтвердите согласие с правилами:\n"
        "• Запрещено нарушать законы.\n"
        "• Соблюдайте уважение.\n"
        "• Администрация не несет ответственности за контент.\n\n"
        "Нажмите 'Согласен', чтобы начать."
    )
    keyboard = [[KeyboardButton("✅ Согласен")]]
    await update.message.reply_text(agreement_text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True))


async def show_main_menu(user_id: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает основное меню пользователю."""
    keyboard = [
        ["🔍 Поиск собеседника"], 
        ["👤 Мой профиль", "🔗 Мои рефералы"],
        ["⚠️ Сообщить о проблеме"]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await context.bot.send_message(user_id, "Выберите действие:", reply_markup=markup)


async def show_search_menu(user_id: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает меню поиска собеседника."""
    keyboard = [["🚫 Отменить поиск"]]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await context.bot.send_message(user_id, "⏳ Идёт поиск собеседника. Вы можете отменить его.", reply_markup=markup)


async def show_chat_menu(user_id: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает меню чата пользователю."""
    keyboard = [
        ["🚫 Завершить чат", "🔍 Начать новый чат"],
        ["👤 Показать мой ник", "❤️ Отправить лайк"],
        ["🙈 Не показывать ник"]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await context.bot.send_message(user_id, "Вы в чате. Общайтесь.", reply_markup=markup)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает все текстовые сообщения от пользователей."""
    user_id = str(update.effective_user.id)
    text = update.message.text
    
    if user_id in banned_users:
        return

    if user_id in muted_users and text not in ["🚫 Завершить чат", "🔍 Начать новый чат"]:
        await update.message.reply_text("🔇 Вы не можете отправлять сообщения, пока находитесь в муте.")
        return

    # Логика для согласия с правилами
    if text == "✅ Согласен" and not user_agreements.get(user_id):
        user_agreements[user_id] = True
        save_data(user_agreements, AGREEMENTS_FILE)
        await update.message.reply_text("✅ Вы согласились с условиями. Теперь можете настроить профиль.", reply_markup=ReplyKeyboardRemove())
        await start_profile_setup(update, context)
        return

    if not user_agreements.get(user_id):
        await update.message.reply_text("❗️Сначала примите условия, используя /start.")
        return

    # Логика пошагового заполнения профиля
    if user_states.get(user_id) == "awaiting_gender":
        if text in GENDERS:
            user_profiles.setdefault(user_id, {})
            user_profiles[user_id]["gender"] = text
            user_states[user_id] = "awaiting_age"
            await update.message.reply_text("Отлично! Теперь укажите ваш возраст:")
        else:
            await update.message.reply_text("Пожалуйста, выберите пол из предложенных вариантов.")
        return
    elif user_states.get(user_id) == "awaiting_age":
        if text.isdigit() and 12 <= int(text) <= 99:
            user_profiles[user_id]["age"] = int(text)
            user_states[user_id] = "awaiting_city"
            await update.message.reply_text("Спасибо! Теперь укажите ваш город:")
        else:
            await update.message.reply_text("Пожалуйста, введите корректный возраст (от 12 до 99).")
        return
    elif user_states.get(user_id) == "awaiting_city":
        user_profiles[user_id]["city"] = text.strip()
        del user_states[user_id]
        save_data(user_profiles, PROFILES_FILE)
        await update.message.reply_text("Профиль сохранён! Теперь вы можете начать общение.")
        await show_main_menu(user_id, context)
        return

    # Логика для выбора интересов
    if user_states.get(user_id) == "awaiting_interests":
        if text in AVAILABLE_INTERESTS:
            user_interests.setdefault(user_id, [])
            if text in user_interests[user_id]:
                user_interests[user_id].remove(text)
                await update.message.reply_text(f"Интерес '{text}' убран. Текущие: {', '.join(user_interests[user_id]) or 'Нет'}")
            else:
                user_interests[user_id].append(text)
                await update.message.reply_text(f"Интерес '{text}' добавлен. Текущие: {', '.join(user_interests[user_id])}")
            return
        elif text == "➡️ Готово":
            del user_states[user_id]
            await update.message.reply_text(
                f"✅ Ваши интересы: {', '.join(user_interests.get(user_id, [])) or 'Не выбраны'}.\nИщем собеседника...",
                reply_markup=ReplyKeyboardRemove()
            )
            await start_search(user_id, context)
            return

    # Если пользователь в чате, пересылаем сообщение собеседнику
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        await context.bot.send_message(partner_id, text)
        return

    # Обработка команд из главного меню
    if text == "🔍 Поиск собеседника":
        if user_id in waiting_users:
            await update.message.reply_text("⏳ Поиск уже идёт...")
        else:
            await show_interests_menu(user_id, context)
    
    elif text == "🚫 Отменить поиск":
        await cancel_search(user_id, context)

    elif text == "⚠️ Сообщить о проблеме":
        await report_issue(user_id, update.effective_user.username, context)

    elif text == "🚫 Завершить чат" or text == "🔍 Начать новый чат":
        await end_chat(user_id, context)
        
    elif text == "👤 Показать мой ник":
        await handle_show_name_request(user_id, context, agree=True)
    
    elif text == "🙈 Не показывать ник":
        await handle_show_name_request(user_id, context, agree=False)
        
    elif text == "🔗 Мои рефералы":
        await show_referrals(user_id, context)

    elif text == "👤 Мой профиль":
        await show_profile(user_id, context)

    elif text == "❤️ Отправить лайк":
        await send_like(user_id, context)
    
    else:
        await update.message.reply_text("❓ Неизвестная команда. Пожалуйста, выберите из меню.")

async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает медиафайлы (фото, видео, стикеры, голосовые)."""
    user_id = str(update.effective_user.id)
    if user_id in muted_users:
        await update.message.reply_text("🔇 Вы не можете отправлять медиа, пока находитесь в муте.")
        return
        
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        await context.bot.forward_message(
            chat_id=partner_id,
            from_chat_id=user_id,
            message_id=update.message.message_id
        )

# --- Функции для профиля ---
async def start_profile_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Начинает процесс создания/редактирования профиля."""
    user_id = str(update.effective_user.id)
    keyboard = [[KeyboardButton(gender) for gender in GENDERS]]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    user_states[user_id] = "awaiting_gender"
    await update.message.reply_text("Давайте создадим ваш профиль. Выберите ваш пол:", reply_markup=markup)

async def show_profile(user_id: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает профиль пользователя."""
    profile = user_profiles.get(user_id)
    if not profile:
        await context.bot.send_message(user_id, "❗️ Ваш профиль ещё не создан. Используйте /start, чтобы начать.")
        return

    profile_info = (
        f"**Ваш профиль:**\n"
        f"Пол: `{profile.get('gender', 'Не указан')}`\n"
        f"Возраст: `{profile.get('age', 'Не указан')}`\n"
        f"Город: `{profile.get('city', 'Не указан')}`\n"
        f"Лайков: `{user_likes.get(user_id, 0)}`"
    )
    await context.bot.send_message(user_id, profile_info, parse_mode='Markdown')

# --- Функции поиска и чата ---
async def show_interests_menu(user_id: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает меню выбора интересов."""
    keyboard = [[KeyboardButton(interest)] for interest in AVAILABLE_INTERESTS]
    keyboard.append([KeyboardButton("➡️ Готово")])
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    user_interests[user_id] = []
    user_states[user_id] = 'awaiting_interests'
    await context.bot.send_message(
        user_id,
        "Выберите ваши интересы, чтобы найти подходящего собеседника:",
        reply_markup=markup
    )

async def start_search(user_id: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запускает поиск собеседника."""
    # Убеждаемся, что пользователь ещё не в поиске
    if user_id in waiting_users:
        return
        
    waiting_users.append(user_id)
    await show_search_menu(user_id, context)
    
    job = context.application.job_queue.run_once(
        search_timeout_callback,
        120, # Тайм-аут 2 минуты
        chat_id=int(user_id),
        name=user_id
    )
    search_timeouts[user_id] = job
    
    # Сразу запускаем проверку, чтобы найти пару, если есть
    await find_partner(context)


async def find_partner(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ищет пару для общения среди ожидающих пользователей."""
    if len(waiting_users) >= 2:
        user1_id = waiting_users.pop(0)
        user2_id = waiting_users.pop(0)

        if user1_id in search_timeouts:
            search_timeouts.pop(user1_id).job.schedule_removal()
        if user2_id in search_timeouts:
            search_timeouts.pop(user2_id).job.schedule_removal()
            
        active_chats[user1_id] = user2_id
        active_chats[user2_id] = user1_id
        save_data(active_chats, CHATS_FILE)

        show_name_requests[tuple(sorted((user1_id, user2_id)))] = {user1_id: None, user2_id: None}
        
        await show_chat_menu(user1_id, context)
        await show_chat_menu(user2_id, context)
        
async def search_timeout_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает истечение времени поиска."""
    user_id = str(context.job.chat_id)
    if user_id in waiting_users:
        waiting_users.remove(user_id)
        search_timeouts.pop(user_id, None)
        await context.bot.send_message(
            user_id,
            "⏳ Время поиска истекло. Попробуйте ещё раз.",
            reply_markup=ReplyKeyboardRemove()
        )
        await show_main_menu(user_id, context)

async def cancel_search(user_id: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отменяет поиск собеседника."""
    if user_id in waiting_users:
        waiting_users.remove(user_id)
        if user_id in search_timeouts:
            search_timeouts.pop(user_id).job.schedule_removal()
        await context.bot.send_message(user_id, "❌ Поиск отменён.", reply_markup=ReplyKeyboardRemove())
        await show_main_menu(user_id, context)
    else:
        await context.bot.send_message(user_id, "❗️ Вы не находитесь в поиске.")

async def end_chat(user_id: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Завершает текущий чат."""
    if user_id in active_chats:
        partner_id = active_chats.pop(user_id)
        active_chats.pop(partner_id, None)
        save_data(active_chats, CHATS_FILE)
        
        chat_key = tuple(sorted((user_id, partner_id)))
        show_name_requests.pop(chat_key, None)
        
        await context.bot.send_message(user_id, "❌ Чат завершён.")
        await context.bot.send_message(partner_id, "❌ Собеседник завершил чат.")
        
        await show_main_menu(user_id, context)
        await show_main_menu(partner_id, context)
    else:
        await context.bot.send_message(user_id, "❗️Вы не находитесь в чате.")
        

async def report_issue(user_id: str, username: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет жалобу админам."""
    if user_id not in active_chats:
        await context.bot.send_message(user_id, "❗️ Вы не в чате, чтобы подать жалобу.")
        return

    partner_id = active_chats[user_id]
    reported_users["reports"].setdefault(partner_id, [])
    reported_users["reports"][partner_id].append({"reporter": user_id, "timestamp": time.time()})
    save_data(reported_users, REPORTED_FILE)
    
    await context.bot.send_message(user_id, "⚠️ Спасибо за сообщение! Администрация проверит ситуацию.")
    
    for admin_id in ADMIN_IDS:
        await context.bot.send_message(
            admin_id,
            f"❗ **Новая жалоба!**\n"
            f"Пожаловался: `{user_id}` (ник: @{username})\n"
            f"На пользователя: `{partner_id}`\n"
            f"Количество жалоб на этого пользователя: `{len(reported_users['reports'].get(partner_id, []))}`",
            parse_mode='Markdown'
        )

async def handle_show_name_request(user_id: str, context: ContextTypes.DEFAULT_TYPE, agree: bool) -> None:
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
        user = await context.bot.get_chat(user_id)
        name1 = f"@{user.username}" if user.username else 'Без ника'
        name2_user = await context.bot.get_chat(partner_id)
        name2 = f"@{name2_user.username}" if name2_user.username else 'Без ника'

        await context.bot.send_message(user_id, f"🔓 Ник собеседника: {name2}")
        await context.bot.send_message(partner_id, f"🔓 Ник собеседника: {name1}")
    else:
        await context.bot.send_message(user_id, "❌ Кто-то из вас отказался показывать ник.")
        await context.bot.send_message(partner_id, "❌ Кто-то из вас отказался показывать ник.")


async def show_referrals(user_id: str, context: ContextTypes.DEFAULT_TYPE) -> None:
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

async def send_like(user_id: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет лайк собеседнику."""
    if user_id not in active_chats:
        await context.bot.send_message(user_id, "❗️Вы сейчас не в чате.")
        return
    
    partner_id = active_chats[user_id]
    chat_key = tuple(sorted((user_id, partner_id)))

    if chat_key not in show_name_requests:
        show_name_requests[chat_key] = {user_id: None, partner_id: None}
    
    if show_name_requests[chat_key].get(user_id) == "liked":
        await context.bot.send_message(user_id, "❤️ Вы уже отправили лайк этому собеседнику.")
        return

    show_name_requests[chat_key][user_id] = "liked"
    partner_liked = show_name_requests[chat_key][partner_id]

    await context.bot.send_message(user_id, "❤️ Вы отправили лайк! Ожидаем ответа.")
    await context.bot.send_message(partner_id, "❤️ Ваш собеседник отправил вам лайк! Отправьте лайк в ответ, чтобы открыть имена.")
    
    if partner_liked == "liked":
        user_likes[user_id] = user_likes.get(user_id, 0) + 1
        user_likes[partner_id] = user_likes.get(partner_id, 0) + 1
        save_data({"likes": user_likes}, LIKES_FILE)
        
        await context.bot.send_message(user_id, "🎉 Это взаимный лайк! Вы можете показать свой ник.")
        await context.bot.send_message(partner_id, "🎉 Это взаимный лайк! Вы можете показать свой ник.")

# --- Админ-панель ---
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /admin для входа в админ-панель."""
    user_id = str(update.effective_user.id)
    if user_id in ADMIN_IDS:
        await show_admin_menu(user_id, context)
    else:
        await update.message.reply_text("🔐 Введите пароль для доступа к админ-панели:", reply_markup=ReplyKeyboardRemove())
        context.user_data['awaiting_admin_password'] = True

async def password_check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверяет пароль, если пользователь его ожидает."""
    user_id = str(update.effective_user.id)
    
    if user_id in ADMIN_IDS:
        await admin_menu_handler(update, context)
        return
        
    if context.user_data.get('awaiting_admin_password'):
        if update.message.text.strip() == ADMIN_PASSWORD:
            ADMIN_IDS.add(user_id)
            save_data({"admins": list(ADMIN_IDS)}, ADMIN_FILE)
            await update.message.reply_text("✅ Пароль верный. Добро пожаловать в админ-панель.")
            await show_admin_menu(user_id, context)
        else:
            await update.message.reply_text("❌ Неверный пароль.")
        del context.user_data['awaiting_admin_password']
        return

    await message_handler(update, context)

async def show_admin_menu(user_id: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает админ-меню."""
    keyboard = [
        ["📊 Статистика", "♻️ Завершить все чаты"],
        ["👮‍♂️ Забанить", "🔓 Разбанить", "🔇 Мут", "🔊 Размут"],
        ["🔎 Профиль", "🔒 Выйти из админ-панели"]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await context.bot.send_message(user_id, "👑 Админ-панель активна.", reply_markup=markup)


async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команды из админ-меню."""
    user_id = str(update.effective_user.id)
    text = update.message.text
    
    if user_id not in ADMIN_IDS:
        return
    
    if user_states.get(user_id) == "awaiting_ban_id":
        try:
            target_id = str(text)
            banned_users.add(target_id)
            save_data({"banned": list(banned_users)}, BANS_FILE)
            await context.bot.send_message(target_id, "🚫 Вы были заблокированы администратором.")
            await update.message.reply_text(f"✅ Пользователь `{target_id}` забанен.", parse_mode='Markdown')
        except (ValueError, Exception):
            await update.message.reply_text("❌ Неверный ID. Попробуйте снова.")
        finally:
            del user_states[user_id]
        return
    
    if user_states.get(user_id) == "awaiting_unban_id":
        try:
            target_id = str(text)
            if target_id in banned_users:
                banned_users.remove(target_id)
                save_data({"banned": list(banned_users)}, BANS_FILE)
                await update.message.reply_text(f"✅ Пользователь `{target_id}` разбанен.", parse_mode='Markdown')
            else:
                await update.message.reply_text(f"❌ Пользователь `{target_id}` не был забанен.", parse_mode='Markdown')
        except (ValueError, Exception):
            await update.message.reply_text("❌ Неверный ID. Попробуйте снова.")
        finally:
            del user_states[user_id]
        return

    if user_states.get(user_id) == "awaiting_mute_id":
        try:
            target_id = str(text)
            muted_users.add(target_id)
            save_data({"muted": list(muted_users)}, MUTES_FILE)
            await context.bot.send_message(target_id, "🔇 Вы были заглушены администратором. Вы можете завершить чат, но не можете отправлять сообщения.")
            await update.message.reply_text(f"✅ Пользователь `{target_id}` заглушен.", parse_mode='Markdown')
        except (ValueError, Exception):
            await update.message.reply_text("❌ Неверный ID. Попробуйте снова.")
        finally:
            del user_states[user_id]
        return
        
    if user_states.get(user_id) == "awaiting_unmute_id":
        try:
            target_id = str(text)
            if target_id in muted_users:
                muted_users.remove(target_id)
                save_data({"muted": list(muted_users)}, MUTES_FILE)
                await update.message.reply_text(f"✅ Пользователь `{target_id}` разглушен.", parse_mode='Markdown')
            else:
                await update.message.reply_text(f"❌ Пользователь `{target_id}` не был заглушен.", parse_mode='Markdown')
        except (ValueError, Exception):
            await update.message.reply_text("❌ Неверный ID. Попробуйте снова.")
        finally:
            del user_states[user_id]
        return

    if user_states.get(user_id) == "awaiting_profile_id":
        try:
            target_id = str(text)
            profile = user_profiles.get(target_id, {})
            if profile:
                profile_info = (
                    f"**Профиль пользователя `{target_id}`:**\n"
                    f"Пол: `{profile.get('gender', 'Не указан')}`\n"
                    f"Возраст: `{profile.get('age', 'Не указан')}`\n"
                    f"Город: `{profile.get('city', 'Не указан')}`\n"
                    f"Лайков: `{user_likes.get(target_id, 0)}`\n"
                    f"Жалоб: `{len(reported_users['reports'].get(target_id, []))}`"
                )
                await update.message.reply_text(profile_info, parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ Профиль не найден.")
        except (ValueError, Exception):
            await update.message.reply_text("❌ Неверный ID. Попробуйте снова.")
        finally:
            del user_states[user_id]
        return

    if text == "📊 Статистика":
        await update.message.reply_text(
            f"👥 Пользователей согласилось: {len(user_agreements)}\n"
            f"💬 Активных чатов: {len(active_chats)//2}\n"
            f"⚠️ Жалоб: {len(reported_users['reports'])}\n"
            f"⛔ Забанено: {len(banned_users)}\n"
            f"🔇 В муте: {len(muted_users)}\n"
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
        user_states[user_id] = "awaiting_ban_id"
    elif text == "🔓 Разбанить":
        await update.message.reply_text("Введите ID пользователя, которого нужно разбанить:")
        user_states[user_id] = "awaiting_unban_id"
    elif text == "🔇 Мут":
        await update.message.reply_text("Введите ID пользователя, которого нужно заглушить:")
        user_states[user_id] = "awaiting_mute_id"
    elif text == "🔊 Размут":
        await update.message.reply_text("Введите ID пользователя, которого нужно разглушить:")
        user_states[user_id] = "awaiting_unmute_id"
    elif text == "🔎 Профиль":
        await update.message.reply_text("Введите ID пользователя для просмотра профиля:")
        user_states[user_id] = "awaiting_profile_id"
    elif text == "🔒 Выйти из админ-панели":
        ADMIN_IDS.discard(user_id)
        save_data({"admins": list(ADMIN_IDS)}, ADMIN_FILE)
        await update.message.reply_text("🚪 Вы вышли из админ-панели.", reply_markup=ReplyKeyboardRemove())
        await show_main_menu(user_id, context)


# --- Основная точка входа ---
def main() -> None:
    """Запускает бота в режиме вебхуков."""
    PORT = int(os.environ.get('PORT', 5000))
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Обработчики
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('admin', admin_command))

    # Один общий обработчик для текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), password_check_handler))
    
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
