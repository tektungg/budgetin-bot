"""
Budgetin Bot - Telegram bot untuk pencatatan keuangan otomatis
"""

import logging
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from config.settings import settings
from handlers.transaction import handle_text, handle_photo
from handlers.report import (
    cmd_hari_ini,
    cmd_bulan_ini,
    cmd_kategori,
    cmd_export,
)
from handlers.general import cmd_start, cmd_help, cmd_hapus, cmd_edit, handle_callback
from services.database import check_connection

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log"),
    ],
)
logger = logging.getLogger(__name__)


def main():
    settings.validate()
    check_connection()
    logger.info("Supabase connected")

    app = Application.builder().token(settings.TELEGRAM_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("hariini", cmd_hari_ini))
    app.add_handler(CommandHandler("bulanini", cmd_bulan_ini))
    app.add_handler(CommandHandler("kategori", cmd_kategori))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("hapus", cmd_hapus))
    app.add_handler(CommandHandler("edit", cmd_edit))

    # Callback handler (inline keyboard)
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Message handlers
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot started, polling...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
