import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    CallbackQueryHandler, ContextTypes
)

# Логгинг
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = "https://test-1-1-zard.onrender.com"  # Твой Render-домен

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Кнопка 1", callback_data="btn1")],
        [InlineKeyboardButton("Кнопка 2", callback_data="btn2")],
        [InlineKeyboardButton("➡️ Готово", callback_data="done")]
    ]
    await update.message.reply_text(
        "Выберите кнопку:", reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Callback'и
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text=f"Вы нажали: {query.data}")

# Ошибки
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Ошибка!", exc_info=context.error)

# Запуск
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_error_handler(error_handler)

    # Render требует url_path отличным от "/"
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        url_path="/webhook",
        webhook_url=f"{WEBHOOK_URL}/webhook"
    )
