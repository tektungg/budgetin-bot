"""
Callback handlers untuk flow preview dan edit struk (receipt).
Handles: rcpt_ok, rcpt_no, rcpt_del_*, rcpt_edit_*, rcpt_editfield_*,
         rcpt_editset_*, rcpt_tglbulan_*, rcpt_tglset_*, rcpt_back_preview
"""

import calendar
import logging
from datetime import datetime, date as _date, timezone, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from services.database import insert_transaction_from_dict
from services.parser import format_rupiah, CATEGORY_KEYWORDS
from handlers.keyboards import main_menu_keyboard, after_tx_keyboard
from utils.formatter import (
    tx_confirmation_message,
    format_tanggal,
    parse_iso_date,
    BULAN,
)

logger = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))


async def handle_receipt_callbacks(query, data: str, user_id: int, context) -> bool:
    """
    Handle semua callback terkait preview dan edit struk.
    Return True jika callback ditangani, False jika bukan domain ini.
    """
    if data == "rcpt_ok":
        await _handle_rcpt_ok(query, user_id, context)
        return True
    if data == "rcpt_no":
        await _handle_rcpt_no(query, context)
        return True
    if data.startswith("rcpt_del_"):
        await _handle_rcpt_del(query, data, context)
        return True
    if data.startswith("rcpt_edit_") and not data.startswith("rcpt_editfield_") and not data.startswith("rcpt_editset_"):
        await _handle_rcpt_edit(query, data, context)
        return True
    if data.startswith("rcpt_editfield_"):
        await _handle_rcpt_editfield(query, data, context)
        return True
    if data.startswith("rcpt_editset_"):
        await _handle_rcpt_editset(query, data, context)
        return True
    if data.startswith("rcpt_tglbulan_"):
        await _handle_rcpt_tglbulan(query, data, context)
        return True
    if data.startswith("rcpt_tglset_"):
        await _handle_rcpt_tglset(query, data, context)
        return True
    if data == "rcpt_back_preview":
        await _handle_rcpt_back_preview(query, context)
        return True
    return False


def _render_preview(context) -> tuple[str, InlineKeyboardMarkup]:
    """Helper: ambil pending_receipt dari context dan render preview."""
    from handlers.transaction import _render_receipt_preview
    items = context.user_data.get("pending_receipt", [])
    title = context.user_data.get("pending_receipt_title")
    if title:
        return _render_receipt_preview(items, title=title)
    return _render_receipt_preview(items)


async def _handle_rcpt_ok(query, user_id: int, context):
    """Simpan semua item struk ke database"""
    context.user_data.pop("pending_receipt_title", None)
    items = context.user_data.pop("pending_receipt", [])
    if not items:
        await query.message.edit_text("❌ Gagal: Tidak ada data struk tersimpan.")
        return

    saved = [insert_transaction_from_dict(user_id, tx_data, source="photo") for tx_data in items]

    if len(saved) == 1:
        await query.message.edit_text(
            "📸 <b>Struk Berhasil Dicatat!</b>\n\n" + tx_confirmation_message(saved[0]),
            parse_mode="HTML",
            reply_markup=after_tx_keyboard(saved[0]["user_tx_no"]),
        )
    else:
        total = sum(tx["amount"] for tx in saved)
        lines = ["📸 <b>Struk Berhasil Dicatat!</b>\n"]
        for tx in saved:
            emoji = "💸" if tx["type"] == "keluar" else "💰"
            lines.append(f"{emoji} {tx['description']} — <b>{format_rupiah(tx['amount'])}</b>")
        lines.append(f"\n{'─' * 28}")
        lines.append(f"📌 <b>{len(saved)} transaksi</b> • Total: <b>{format_rupiah(total)}</b>")
        await query.message.edit_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )


async def _handle_rcpt_no(query, context):
    """Batalkan penyimpanan struk"""
    context.user_data.pop("pending_receipt", None)
    context.user_data.pop("pending_receipt_title", None)
    await query.message.edit_text(
        "🚫 <b>Penyimpanan Struk Dibatalkan</b>",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


async def _handle_rcpt_del(query, data: str, context):
    """Hapus satu item dari preview struk"""
    idx = int(data.split("_")[-1])
    items = context.user_data.get("pending_receipt", [])
    if idx < len(items):
        items.pop(idx)
        if not items:
            context.user_data.pop("pending_receipt", None)
            await query.message.edit_text(
                "🚫 <b>Penyimpanan Struk Dibatalkan</b> (semua item dihapus)",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
            return
        context.user_data["pending_receipt"] = items
        msg, kb = _render_preview(context)
        await query.message.edit_text(msg, parse_mode="HTML", reply_markup=kb)


async def _handle_rcpt_edit(query, data: str, context):
    """Tampilkan menu edit untuk item tertentu"""
    idx = int(data.split("_")[-1])
    items = context.user_data.get("pending_receipt", [])
    if idx < len(items):
        item = items[idx]
        dt = parse_iso_date(item["date"]) if item.get("date") and isinstance(item["date"], str) else item.get("date")
        date_display = format_tanggal(dt, short=True) if dt else "Hari ini"
        emoji = "💸" if item["type"] == "keluar" else "💰"
        await query.message.edit_text(
            f"✏️ <b>Edit Item {idx+1}</b>\n\n"
            f"{emoji} {item['description']}\n"
            f"{format_rupiah(item['amount'])} • {item['category']} • {date_display}\n\n"
            "Pilih field yang ingin diubah 👇",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("💵 Nominal", callback_data=f"rcpt_editfield_{idx}_amount"),
                    InlineKeyboardButton("🔄 Tipe", callback_data=f"rcpt_editfield_{idx}_type"),
                ],
                [
                    InlineKeyboardButton("🗂️ Kategori", callback_data=f"rcpt_editfield_{idx}_category"),
                    InlineKeyboardButton("📝 Deskripsi", callback_data=f"rcpt_editfield_{idx}_description"),
                ],
                [
                    InlineKeyboardButton("📅 Tanggal", callback_data=f"rcpt_editfield_{idx}_date"),
                ],
                [
                    InlineKeyboardButton("⬅️ Kembali", callback_data="rcpt_back_preview"),
                ],
            ]),
        )


async def _handle_rcpt_editfield(query, data: str, context):
    """Tampilkan input untuk field yang dipilih"""
    parts = data.split("_", 3)  # ["rcpt", "editfield", "{idx}", "{field}"]
    idx = int(parts[2])
    field = parts[3]
    items = context.user_data.get("pending_receipt", [])
    if idx >= len(items):
        return
    item = items[idx]

    if field == "type":
        await query.message.edit_text(
            f"🔄 <b>Ubah Tipe — Item {idx+1}</b>\n\n"
            f"Saat ini: <b>{'Keluar' if item['type'] == 'keluar' else 'Masuk'}</b>\n\n"
            "Pilih tipe baru 👇",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("💰 Masuk", callback_data=f"rcpt_editset_{idx}_type_masuk"),
                    InlineKeyboardButton("💸 Keluar", callback_data=f"rcpt_editset_{idx}_type_keluar"),
                ],
                [InlineKeyboardButton("⬅️ Kembali", callback_data=f"rcpt_edit_{idx}")],
            ]),
        )
    elif field == "category":
        categories = list(CATEGORY_KEYWORDS.keys()) + ["Lainnya"]
        buttons = []
        row = []
        for cat in categories:
            row.append(InlineKeyboardButton(cat, callback_data=f"rcpt_editset_{idx}_category_{cat}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data=f"rcpt_edit_{idx}")])
        await query.message.edit_text(
            f"🗂️ <b>Ubah Kategori — Item {idx+1}</b>\n\n"
            f"Saat ini: <b>{item['category']}</b>\n\nPilih kategori baru 👇",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    elif field == "date":
        now = datetime.now(WIB)
        buttons = []
        row = []
        for i in range(6):
            m = now.month - i
            y = now.year
            while m <= 0:
                m += 12
                y -= 1
            label = f"{BULAN.get(m, '')} {y}"
            row.append(InlineKeyboardButton(label, callback_data=f"rcpt_tglbulan_{idx}_{y}_{m}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data=f"rcpt_edit_{idx}")])
        await query.message.edit_text(
            f"📅 <b>Ubah Tanggal — Item {idx+1}</b>\n\nPilih bulan 👇",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    else:
        # amount / description → minta user ketik
        context.user_data["receipt_edit_index"] = idx
        context.user_data["receipt_edit_field"] = field
        prompts = {
            "amount": ("💵 Nominal", "Ketik nominal baru\n\n<i>Contoh: 30k, 50rb, 1.5jt</i>"),
            "description": ("📝 Deskripsi", "Ketik deskripsi baru"),
        }
        label, hint = prompts.get(field, (field, "Ketik nilai baru"))
        await query.message.edit_text(
            f"✏️ <b>Edit {label} — Item {idx+1}</b>\n\n{hint}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Batal", callback_data=f"rcpt_edit_{idx}")],
            ]),
        )


async def _handle_rcpt_tglbulan(query, data: str, context):
    """Tampilkan grid tanggal untuk bulan yang dipilih"""
    parts = data.split("_")
    idx = int(parts[2])
    year = int(parts[3])
    month = int(parts[4])
    _, days_in_month = calendar.monthrange(year, month)
    month_name = BULAN.get(month, str(month))
    buttons = []
    row = []
    for day in range(1, days_in_month + 1):
        row.append(InlineKeyboardButton(str(day), callback_data=f"rcpt_tglset_{idx}_{year}_{month}_{day}"))
        if len(row) == 7:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton("⬅️ Pilih Bulan", callback_data=f"rcpt_editfield_{idx}_date"),
        InlineKeyboardButton("❌ Batal", callback_data=f"rcpt_edit_{idx}"),
    ])
    await query.message.edit_text(
        f"📅 <b>Pilih Tanggal — {month_name} {year}</b>\n\nKetuk tanggal yang diinginkan 👇",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _handle_rcpt_tglset(query, data: str, context):
    """Simpan tanggal yang dipilih ke item struk"""
    parts = data.split("_")
    idx = int(parts[2])
    year = int(parts[3])
    month = int(parts[4])
    day = int(parts[5])
    items = context.user_data.get("pending_receipt", [])
    if idx < len(items):
        items[idx]["date"] = _date(year, month, day).strftime("%Y-%m-%d")
        context.user_data["pending_receipt"] = items
        msg, kb = _render_preview(context)
        await query.message.edit_text(msg, parse_mode="HTML", reply_markup=kb)


async def _handle_rcpt_editset(query, data: str, context):
    """Simpan nilai field yang diubah via tombol (type, category)"""
    parts = data.split("_", 4)  # ["rcpt", "editset", "{idx}", "{field}", "{value}"]
    idx = int(parts[2])
    field = parts[3]
    value = parts[4]
    items = context.user_data.get("pending_receipt", [])
    if idx < len(items):
        items[idx][field] = value
        context.user_data["pending_receipt"] = items
        msg, kb = _render_preview(context)
        await query.message.edit_text(msg, parse_mode="HTML", reply_markup=kb)


async def _handle_rcpt_back_preview(query, context):
    """Kembali ke preview struk"""
    items = context.user_data.get("pending_receipt", [])
    if items:
        msg, kb = _render_preview(context)
        await query.message.edit_text(msg, parse_mode="HTML", reply_markup=kb)
