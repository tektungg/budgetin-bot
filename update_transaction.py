import re

with open("handlers/transaction.py", "r") as f:
    text = f.read()

old_photo = """    saved = []
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
            "📸 <b>Struk Berhasil Dicatat!</b>\\n\\n"
            + tx_confirmation_message(saved[0]),
            parse_mode="HTML",
            reply_markup=after_tx_keyboard(saved[0]["id"]),
        )
    else:
        total = sum(tx["amount"] for tx in saved)
        lines = [
            "📸 <b>Struk Berhasil Dicatat!</b>\\n",
        ]
        for tx in saved:
            emoji = "💸" if tx["type"] == "keluar" else "💰"
            lines.append(f"{emoji} {tx['description']} — <b>{format_rupiah(tx['amount'])}</b>")

        lines.append(f"\\n{'─' * 28}")
        lines.append(f"📌 <b>{len(saved)} transaksi</b> • Total: <b>{format_rupiah(total)}</b>")

        from handlers.general import main_menu_keyboard
        await update.message.reply_text(
            "\\n".join(lines),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )"""

new_photo = """    context.user_data["pending_receipt"] = transactions
    text, kb = _render_receipt_preview(transactions)
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)"""

if old_photo in text:
    text = text.replace(old_photo, new_photo)

preview_helper = """
def _render_receipt_preview(items: list[dict]) -> tuple[str, InlineKeyboardMarkup]:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from services.parser import format_rupiah
    
    lines = ["📸 <b>Preview Hasil Scan Struk</b>\\n"]
    buttons = []
    
    total = 0
    for i, item in enumerate(items):
        emoji = "💸" if item["type"] == "keluar" else "💰"
        amount = item["amount"]
        total += int(amount)
        desc = item["description"]
        cat = item["category"]
        
        lines.append(f"{i+1}. {emoji} {desc}")
        lines.append(f"   {format_rupiah(amount)} ({cat})")
        
        buttons.append([
            InlineKeyboardButton(f"✏️ Edit Item {i+1}", callback_data=f"rcpt_edit_{i}"),
            InlineKeyboardButton(f"❌ Hapus Item {i+1}", callback_data=f"rcpt_del_{i}")
        ])

    lines.append(f"\\n{'─' * 28}")
    lines.append(f"📌 <b>{len(items)} transaksi</b> • Total: <b>{format_rupiah(total)}</b>")
    lines.append("\\n<i>Silakan periksa atau edit sebelum menyimpan.</i>")
    
    buttons.append([
        InlineKeyboardButton("✅ Simpan Semua", callback_data="rcpt_ok"),
        InlineKeyboardButton("🚫 Batalkan", callback_data="rcpt_no")
    ])
    
    return "\\n".join(lines), InlineKeyboardMarkup(buttons)

async def _handle_receipt_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, edit_idx: int, text: str):
    items = context.user_data.get("pending_receipt", [])
    context.user_data.pop("receipt_edit_index", None)
    
    if edit_idx < len(items):
        from services.parser import parse_transaction, parse_amount
        result = parse_transaction(text)
        if result:
            items[edit_idx]["amount"] = result["amount"]
            items[edit_idx]["description"] = result["description"]
            items[edit_idx]["category"] = result["category"]
            items[edit_idx]["type"] = result["type"]
            context.user_data["pending_receipt"] = items
            msg, kb = _render_receipt_preview(items)
            await update.message.reply_text(
                "✅ Item diperbarui!\\n\\n" + msg,
                parse_mode="HTML",
                reply_markup=kb
            )
            return

        # fallback parsing failed
        val = parse_amount(text)
        if val:
            items[edit_idx]["amount"] = val
            desc = text.replace(str(val), "").replace(f"{val//1000}k", "").strip()
            if not desc:
                desc = items[edit_idx]["description"]
            items[edit_idx]["description"] = desc
            
            context.user_data["pending_receipt"] = items
            msg, kb = _render_receipt_preview(items)
            await update.message.reply_text(
                "✅ Item diperbarui!\\n\\n" + msg,
                parse_mode="HTML",
                reply_markup=kb
            )
            return
            
        await update.message.reply_text(
            "❌ Format tidak valid. Batal mengedit item.\\n"
            "Ganti nominal / format salah.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")]
            ])
        )
"""

if "def _render_receipt_preview" not in text:
    text = text.replace("async def _handle_edit_input", preview_helper + "\nasync def _handle_edit_input")

text_modify = """    edit_idx = context.user_data.get("receipt_edit_index")
    if edit_idx is not None:
        await _handle_receipt_edit(update, context, int(edit_idx), text)
        return

    # Cek apakah user sedang dalam mode edit"""

if "receipt_edit_index" not in text:
    text = text.replace("    # Cek apakah user sedang dalam mode edit", text_modify)

with open("handlers/transaction.py", "w") as f:
    f.write(text)
