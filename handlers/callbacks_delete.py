"""
Callback handlers untuk flow hapus transaksi dengan undo countdown.
Handles: hapus_*, konfirmhapus_*, undel_*
"""

import asyncio
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from services.database import (
    delete_transaction,
    hard_delete_transaction,
    restore_transaction,
    get_transaction_by_id,
)
from services.parser import format_rupiah
from handlers.keyboards import after_tx_keyboard
from utils.formatter import tx_confirmation_message

logger = logging.getLogger(__name__)


async def handle_delete_callbacks(query, data: str, user_id: int, context) -> bool:
    """
    Handle semua callback terkait hapus/undo.
    Return True jika callback ditangani, False jika bukan domain ini.
    """
    if data.startswith("hapus_"):
        await _handle_hapus(query, data, user_id)
        return True
    if data.startswith("konfirmhapus_"):
        await _handle_konfirmhapus(query, data, user_id, context)
        return True
    if data.startswith("undel_"):
        await _handle_undel(query, data, user_id, context)
        return True
    return False


async def _handle_hapus(query, data: str, user_id: int):
    """Tampilkan konfirmasi sebelum hapus"""
    tx_id = int(data.split("_")[1])
    tx = get_transaction_by_id(tx_id, user_id)
    if tx:
        emoji = "💰" if tx["type"] == "masuk" else "💸"
        tipe = "Pemasukan" if tx["type"] == "masuk" else "Pengeluaran"
        await query.message.edit_text(
            f"🗑️ <b>Hapus Transaksi?</b>\n\n"
            f"┌ 📌 {tx['description']}\n"
            f"├ 💵 {format_rupiah(tx['amount'])}\n"
            f"├ 🗂️ {tx.get('category', 'Lainnya')}\n"
            f"└ {emoji} {tipe}\n\n"
            f"⚠️ Aksi ini tidak bisa dibatalkan.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Ya, Hapus", callback_data=f"konfirmhapus_{tx_id}"),
                    InlineKeyboardButton("❌ Batal", callback_data=f"back_{tx_id}"),
                ],
            ]),
        )
    else:
        await query.message.edit_text(
            f"❌ Transaksi <code>#{tx_id}</code> tidak ditemukan.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )


async def _handle_konfirmhapus(query, data: str, user_id: int, context):
    """Lakukan soft-delete dan mulai countdown undo"""
    tx_id = int(data.split("_")[1])
    tx = get_transaction_by_id(tx_id, user_id)
    if not tx:
        await query.message.edit_text(
            f"❌ Transaksi <code>#{tx_id}</code> tidak ditemukan.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )
        return

    success = delete_transaction(tx_id, user_id)
    if not success:
        await query.message.edit_text(
            "❌ Gagal menghapus transaksi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )
        return

    COUNTDOWN = 10
    stop_key = f"undo_stop_{tx_id}"
    context.bot_data.pop(stop_key, None)
    context.bot_data[f"active_undo_{user_id}"] = tx_id

    def _undo_kb(secs: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"↩️ Undo ({secs}s)", callback_data=f"undel_{tx_id}")],
            [
                InlineKeyboardButton("📊 Hari Ini", callback_data="cmd_hariini"),
                InlineKeyboardButton("🏠 Menu", callback_data="cmd_start"),
            ],
        ])

    msg = await query.message.edit_text(
        f"🗑️ Transaksi dihapus.\n\n"
        f"💸 {tx['description']} — {format_rupiah(tx['amount'])}",
        parse_mode="HTML",
        reply_markup=_undo_kb(COUNTDOWN),
    )

    async def countdown_then_hard_delete():
        for secs in range(COUNTDOWN - 1, 0, -1):
            await asyncio.sleep(1)
            stop = context.bot_data.get(stop_key)
            if stop == "undo":
                return
            if stop == "nav":
                remaining = secs
                await asyncio.sleep(remaining)
                if context.bot_data.get(stop_key) == "undo":
                    return
                hard_delete_transaction(tx_id, user_id)
                context.bot_data.pop(stop_key, None)
                return
            try:
                await msg.edit_reply_markup(reply_markup=_undo_kb(secs))
            except Exception:
                pass
        await asyncio.sleep(1)
        if context.bot_data.get(stop_key) == "undo":
            return
        hard_delete_transaction(tx_id, user_id)
        context.bot_data.pop(stop_key, None)
        context.bot_data.pop(f"active_undo_{user_id}", None)
        try:
            await msg.edit_text(
                f"🗑️ Transaksi dihapus permanen.\n\n"
                f"💸 {tx['description']} — {format_rupiah(tx['amount'])}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📊 Hari Ini", callback_data="cmd_hariini"),
                    InlineKeyboardButton("🏠 Menu", callback_data="cmd_start"),
                ]]),
            )
        except Exception:
            pass

    asyncio.create_task(countdown_then_hard_delete())


async def _handle_undel(query, data: str, user_id: int, context):
    """Pulihkan transaksi yang baru dihapus (undo)"""
    tx_id = int(data.split("_")[1])
    context.bot_data[f"undo_stop_{tx_id}"] = "undo"
    context.bot_data.pop(f"active_undo_{user_id}", None)
    success = restore_transaction(tx_id, user_id)
    if success:
        tx = get_transaction_by_id(tx_id, user_id)
        await query.message.edit_text(
            "↩️ Transaksi dipulihkan.\n\n" + tx_confirmation_message(tx),
            parse_mode="HTML",
            reply_markup=after_tx_keyboard(tx_id),
        )
    else:
        await query.message.edit_text(
            "❌ Gagal memulihkan transaksi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )
