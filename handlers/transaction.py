"""
Handler untuk input transaksi (teks dan foto struk)
Dengan konfirmasi yang lebih rapi & inline keyboard.
"""

import re
import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
from services.parser import parse_transaction, parse_amount, format_rupiah
from services.database import insert_transaction, update_transaction, get_transaction_by_id
from services.groq_ai import analyze_receipt
from utils.auth import require_auth
from utils.formatter import tx_confirmation_message
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from handlers.general import after_tx_keyboard

logger = logging.getLogger(__name__)



def _render_receipt_preview(items: list[dict], title: str = "📸 <b>Preview Hasil Scan Struk</b>") -> tuple[str, InlineKeyboardMarkup]:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from services.parser import format_rupiah

    lines = [title + "\n"]
    buttons = []
    
    total = 0
    for i, item in enumerate(items):
        emoji = "💸" if item["type"] == "keluar" else "💰"
        amount = item["amount"]
        total += int(amount)
        desc = item["description"]
        cat = item["category"]
        
        date_str = ""
        if item.get("date"):
            from utils.formatter import format_tanggal, parse_iso_date
            dt = parse_iso_date(item["date"]) if isinstance(item["date"], str) else item["date"]
            if dt:
                date_str = f" • {format_tanggal(dt, short=True)}"
        lines.append(f"{i+1}. {emoji} {desc}")
        lines.append(f"   {format_rupiah(amount)} ({cat}){date_str}")
        
        buttons.append([
            InlineKeyboardButton(f"✏️ Edit Item {i+1}", callback_data=f"rcpt_edit_{i}"),
            InlineKeyboardButton(f"❌ Hapus Item {i+1}", callback_data=f"rcpt_del_{i}")
        ])

    lines.append(f"\n{'─' * 28}")
    lines.append(f"📌 <b>{len(items)} transaksi</b> • Total: <b>{format_rupiah(total)}</b>")
    lines.append("\n<i>Silakan periksa atau edit sebelum menyimpan.</i>")
    
    buttons.append([
        InlineKeyboardButton("✅ Simpan Semua", callback_data="rcpt_ok"),
        InlineKeyboardButton("🚫 Batalkan", callback_data="rcpt_no")
    ])
    
    return "\n".join(lines), InlineKeyboardMarkup(buttons)

async def _handle_receipt_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, edit_idx: int, text: str):
    items = context.user_data.get("pending_receipt", [])
    field = context.user_data.pop("receipt_edit_field", None)
    context.user_data.pop("receipt_edit_index", None)

    if edit_idx >= len(items):
        return

    from services.parser import parse_amount

    def _save_and_reply(msg_prefix="✅ Item diperbarui!"):
        context.user_data["pending_receipt"] = items
        msg, kb = _render_receipt_preview(items)
        return update.message.reply_text(msg_prefix + "\n\n" + msg, parse_mode="HTML", reply_markup=kb)

    if field == "amount":
        val = parse_amount(text)
        if not val:
            await update.message.reply_text(
                "❌ Nominal tidak valid. Contoh: <code>30k</code>, <code>1.5jt</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data=f"rcpt_edit_{edit_idx}")]]),
            )
            return
        items[edit_idx]["amount"] = val
        await _save_and_reply()
        return

    if field == "description":
        items[edit_idx]["description"] = text.strip()
        await _save_and_reply()
        return

    # fallback (no field set — legacy): try full parse
    from services.parser import parse_transaction
    result = parse_transaction(text)
    if result:
        items[edit_idx].update({
            "amount": result["amount"],
            "description": result["description"],
            "category": result["category"],
            "type": result["type"],
        })
        await _save_and_reply()
        return

    val = parse_amount(text)
    if val:
        items[edit_idx]["amount"] = val
        await _save_and_reply()
        return

    await update.message.reply_text(
        "❌ Format tidak valid.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Kembali", callback_data=f"rcpt_edit_{edit_idx}")]
        ])
    )

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


async def _handle_multiline_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Handle pesan teks multi-baris: parse setiap baris dengan parser lokal."""
    from services.parser import parse_transaction

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    transactions = []
    failed_lines = []

    for line in lines:
        result = parse_transaction(line)
        if result:
            # Konversi date (datetime) ke string ISO jika ada
            if "date" in result and hasattr(result["date"], "isoformat"):
                result["date"] = result["date"].isoformat()
            transactions.append(result)
        else:
            failed_lines.append(line)

    if not transactions:
        failed_preview = "\n".join(f"• <code>{l}</code>" for l in failed_lines[:5])
        await update.message.reply_text(
            "❌ <b>Gagal mengurai transaksi.</b>\n\n"
            "Pastikan setiap baris mengandung:\n"
            "• Tipe: <code>keluar</code> / <code>masuk</code>\n"
            "• Nominal: <code>25k</code>, <code>1jt</code>, <code>50000</code>\n\n"
            f"Baris tidak dikenali:\n{failed_preview}\n\n"
            "Atau kirim satu per satu.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")]
            ])
        )
        return

    context.user_data["pending_receipt"] = transactions
    title = f"📋 <b>Preview {len(transactions)} Transaksi</b>"
    if failed_lines:
        title += f"\n⚠️ {len(failed_lines)} baris tidak dikenali dan dilewati."
    context.user_data["pending_receipt_title"] = title
    preview_text, kb = _render_receipt_preview(transactions, title=title)
    await update.message.reply_text(preview_text, parse_mode="HTML", reply_markup=kb)


@require_auth
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pesan teks natural dari user"""
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # Cek apakah user sedang dalam mode pencarian
    search_state = context.user_data.pop("search_state", None)
    if search_state:
        from handlers.report import _send_search, _send_search_month
        if search_state["scope"] == "global":
            await _send_search(update.message, user_id, text)
        else:
            await _send_search_month(
                update.message, user_id, text,
                search_state["year"], search_state["month"],
            )
        return

    # Cek apakah user sedang dalam mode edit
    edit_state = context.user_data.get("edit_state")
    if edit_state:
        await _handle_edit_input(update, context, edit_state, text)
        return

    # Cek apakah user sedang dalam mode edit item struk
    receipt_edit_index = context.user_data.get("receipt_edit_index")
    if receipt_edit_index is not None:
        await _handle_receipt_edit(update, context, receipt_edit_index, text)
        return

    # Deteksi multi-baris → route ke Gemini multi-transaction flow
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) >= 2:
        await _handle_multiline_text(update, context, text)
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
    """Handle foto struk yang dikirim user (termasuk multiple foto/album)"""
    user_id = update.effective_user.id
    message = update.message
    media_group_id = message.media_group_id

    if media_group_id:
        # Kumpulkan foto dari album yang sama
        group_key = f"mg_{media_group_id}"
        if group_key not in context.bot_data:
            context.bot_data[group_key] = {
                "photos": [],
                "chat_id": message.chat_id,
                "message_id": message.message_id,
                "user_id": user_id,
                "processing": False,
            }
            # Jadwalkan pemrosesan setelah 1.5 detik (tunggu semua foto tiba)
            asyncio.get_event_loop().call_later(
                1.5,
                lambda: asyncio.ensure_future(
                    _process_media_group(context, group_key, message)
                ),
            )

        if not context.bot_data[group_key]["processing"]:
            context.bot_data[group_key]["photos"].append(message.photo[-1])
        return

    # Foto tunggal — proses langsung
    await message.reply_text("🔍 Menganalisis struk... mohon tunggu sebentar.")
    photo = message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()

    transactions = await analyze_receipt(bytes(image_bytes))

    if not transactions:
        await message.reply_text(
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

    context.user_data["pending_receipt"] = transactions
    text, kb = _render_receipt_preview(transactions)
    await message.reply_text(text, parse_mode="HTML", reply_markup=kb)


async def _process_media_group(context: ContextTypes.DEFAULT_TYPE, group_key: str, first_message):
    """Proses semua foto dari satu album setelah selesai terkumpul"""
    group = context.bot_data.get(group_key)
    if not group or group["processing"]:
        return
    group["processing"] = True

    photos = group["photos"]
    user_id = group["user_id"]
    chat_id = group["chat_id"]

    status_msg = await context.bot.send_message(
        chat_id,
        f"🔍 Menganalisis {len(photos)} struk... mohon tunggu sebentar.",
    )

    all_transactions = []
    failed = 0
    for photo in photos:
        try:
            file = await context.bot.get_file(photo.file_id)
            image_bytes = await file.download_as_bytearray()
            txs = await analyze_receipt(bytes(image_bytes))
            if txs:
                all_transactions.extend(txs)
            else:
                failed += 1
        except Exception as e:
            logger.error(f"Error analyzing photo in media group: {e}")
            failed += 1

    # Bersihkan data group
    context.bot_data.pop(group_key, None)

    if not all_transactions:
        await status_msg.edit_text(
            "❌ <b>Gagal Membaca Semua Struk</b>\n\n"
            "Pastikan foto cukup terang, jelas, dan struk terlihat seluruhnya.",
            parse_mode="HTML",
        )
        return

    # Mutate inner dict langsung — MappingProxyType tidak bisa di-assign tapi value-nya bisa di-update
    context.application.user_data[user_id]["pending_receipt"] = all_transactions

    note = f"\n⚠️ {failed} foto gagal dibaca." if failed else ""
    text, kb = _render_receipt_preview(all_transactions)
    await status_msg.edit_text(
        text + note,
        parse_mode="HTML",
        reply_markup=kb,
    )
