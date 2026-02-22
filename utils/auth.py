"""
Utility untuk autentikasi user Telegram.
Jika ALLOWED_USER_IDS diisi, hanya user yang terdaftar yang bisa pakai bot.
"""

import logging
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from config.settings import settings

logger = logging.getLogger(__name__)


def require_auth(func):
    """Decorator: cek apakah user diizinkan menggunakan bot"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user:
            return

        if settings.ALLOWED_USER_IDS and user.id not in settings.ALLOWED_USER_IDS:
            logger.warning(f"Unauthorized access attempt by user {user.id} (@{user.username})")
            await update.message.reply_text(
                "⛔ Kamu tidak memiliki akses ke bot ini."
            )
            return

        return await func(update, context, *args, **kwargs)

    return wrapper
