"""
Handler untuk input transaksi (teks dan foto struk)
Dengan konfirmasi yang lebih rapi & inline keyboard.
"""

import re
import logging
from telegram import Update
from telegram.ext import ContextTypes
from services.parser import parse_transaction, parse_amount, format_rupiah
from services.database import insert_transaction, update_transaction, get_transaction_by_id
from services.gemini import analyze_receipt
from utils.auth import require_auth
from utils.formatter import tx_confirmation_message
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from handlers.general import after_tx_keyboard

logger = logging.getLogger(__name__)


async def _handle_edit_input(update: Update, context: ContextTypes.DEFAULT_TYPE, edit_state: dict, text: str):
    """Proses input teks saat user sedang dalam mode edit"""
    user_id = update.effective_user.id
    tx_id = edit_state["tx_id"]
    field = edit_state["field"]

    # Clear state langsung (one-shot)
    context.user_data.pop("edit_state", None)

    tx = get_transaction_by_id(tx_id, user_id)
    if not tx:
        await update.message.reply_text(
            f"❌ Transaksi <code>#{tx_id}</code> tidak ditemukan.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )
        return

    field_labels = {"amount": "Nominal", "description": "Deskripsi"}

    if field == "amount":
        value = parse_amount(text)
        if not value:
            await update.message.reply_text(
                "⚠️ <b>Format nominal tidak valid</b>\n\n"
                "Contoh: <code>30k</code>, <code>50rb</code>, <code>1.5jt</code>\n\n"
                "<i>Silakan coba lagi dari tombol ✏️ Edit.</i>",
                parse_mode="HTML",
                reply_markup=after_tx_keyboard(tx_id),
            )
            return
        old_display = format_rupiah(tx["amount"])
        new_display = format_rupiah(value)
    elif field == "description":
        value = text
        old_display = tx.get("description", "")
        new_display = text
    else:
        return

    success = update_transaction(tx_id, user_id, **{field: value})
    if success:
        await update.message.reply_text(
            f"✅ <b>Transaksi Diperbarui</b>\n\n"
            f"🔖 ID: <code>#{tx_id}</code>\n"
            f"📝 {field_labels.get(field, field)}: {old_display} → <b>{new_display}</b>",
            parse_mode="HTML",
            reply_markup=after_tx_keyboard(tx_id),
        )
    else:
        await update.message.reply_text(
            "❌ Gagal memperbarui transaksi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )


@require_auth
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pesan teks natural dari user"""
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # Cek apakah user sedang dalam mode edit
    edit_state = context.user_data.get("edit_state")
    if edit_state:
        await _handle_edit_input(update, context, edit_state, text)
        return

    result = parse_transaction(text)

    if not result:
        # Deteksi masalah spesifik untuk feedback yang lebih baik
        lower = text.lower()
        has_type = lower.startswith(("keluar", "masuk", "out", "in", "bayar", "beli", "terima", "dapat", "income", "+", "-"))
        has_number = bool(re.search(r"\d", text))

        if not has_type and has_number:
            hint = (
                "⚠️ <b>Mulai dengan tipe transaksi</b>\n\n"
                f"Pesan kamu: <code>{text}</code>\n\n"
                "Tambahkan <b>keluar</b> atau <b>masuk</b> di depan:\n"
                f"┌ <code>keluar {text}</code>\n"
                f"└ <code>masuk {text}</code>"
            )
        elif has_type and not has_number:
            hint = (
                "⚠️ <b>Nominal tidak ditemukan</b>\n\n"
                f"Pesan kamu: <code>{text}</code>\n\n"
                "Tambahkan nominal, contoh:\n"
                f"<code>{text} 25k</code>"
            )
        else:
            hint = (
                "❓ <b>Format tidak dikenali</b>\n\n"
                "Contoh yang bisa kamu kirim:\n"
                "┌ <code>keluar makan siang 25k</code>\n"
                "├ <code>masuk gaji 3jt</code>\n"
                "├ <code>keluar grab 15000</code>\n"
                "└ <code>masuk freelance desain 500rb</code>\n\n"
                "📸 Atau kirim <b>foto struk</b> untuk dicatat otomatis."
            )

        await update.message.reply_text(
            hint,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❓ Bantuan", callback_data="cmd_help")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )
        return

    tx = insert_transaction(
        user_id=user_id,
        tx_type=result["type"],
        amount=result["amount"],
        category=result["category"],
        description=result["description"],
        source="text",
        created_at=result.get("date"),
    )

    # Tambahkan info tanggal jika backdate
    msg = tx_confirmation_message(tx)
    if result.get("date"):
        from utils.formatter import format_tanggal
        msg += f"\n\n📅 <i>Dicatat untuk tanggal {format_tanggal(result['date'])}</i>"

    await update.message.reply_text(
        msg,
        parse_mode="HTML",
        reply_markup=after_tx_keyboard(tx["id"]),
    )


@require_auth
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle foto struk yang dikirim user"""
    user_id = update.effective_user.id

    await update.message.reply_text("🔍 Menganalisis struk... mohon tunggu sebentar.")

    # Ambil foto resolusi terbesar
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()

    transactions = await analyze_receipt(bytes(image_bytes))

    if not transactions:
        await update.message.reply_text(
            "❌ <b>Gagal Membaca Struk</b>\n\n"
            "Pastikan:\n"
            "┌ 📷 Foto cukup terang dan jelas\n"
            "├ 📄 Struk terlihat seluruhnya\n"
            "└ 🔍 Bukan foto blur\n\n"
            "💡 Coba kirim ulang foto atau catat manual:\n"
            "<code>keluar nama_toko jumlah</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❓ Bantuan", callback_data="cmd_help")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )
        return

    saved = []
    for tx_data in transactions:
        tx = insert_transaction(
            user_id=user_id,
            tx_type=tx_data["type"],
            amount=tx_data["amount"],
            category=tx_data["category"],
            description=tx_data["description"],
            source="photo",
        )
        saved.append(tx)

    if len(saved) == 1:
        await update.message.reply_text(
            "📸 <b>Struk Berhasil Dicatat!</b>\n\n"
            + tx_confirmation_message(saved[0]),
            parse_mode="HTML",
            reply_markup=after_tx_keyboard(saved[0]["id"]),
        )
    else:
        total = sum(tx["amount"] for tx in saved)
        lines = [
            "📸 <b>Struk Berhasil Dicatat!</b>\n",
        ]
        for tx in saved:
            emoji = "💸" if tx["type"] == "keluar" else "💰"
            lines.append(f"{emoji} {tx['description']} — <b>{format_rupiah(tx['amount'])}</b>")

        lines.append(f"\n{'─' * 28}")
        lines.append(f"📌 <b>{len(saved)} transaksi</b> • Total: <b>{format_rupiah(total)}</b>")

        from handlers.general import main_menu_keyboard
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
