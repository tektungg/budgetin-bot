"""
Callback handlers untuk flow edit transaksi yang sudah tersimpan.
Handles: edittx_*, edit_*, editfield_*, editset_*, canceledit_*, back_*,
         tgl_*, tglbulan_*, tglset_*
"""

import calendar
import logging
from datetime import datetime, timezone, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from services.database import (
    get_transaction_by_id,
    get_month_transactions,
    update_transaction,
    update_transaction_date,
)
from services.parser import format_rupiah, CATEGORY_KEYWORDS
from handlers.keyboards import after_tx_keyboard, edit_field_keyboard, _safe_edit_or_reply
from utils.formatter import (
    tx_confirmation_message,
    format_tanggal,
    parse_iso_date,
    BULAN,
)

_MONTH_NAMES = BULAN  # alias untuk kejelasan di konteks laporan bulan

logger = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))


async def handle_edit_callbacks(query, data: str, user_id: int, context) -> bool:
    """
    Handle semua callback terkait edit transaksi.
    Return True jika callback ditangani, False jika bukan domain ini.
    """
    if data.startswith("edittx_"):
        await _handle_edittx(query, data, user_id, context)
        return True
    if data.startswith("edit_"):
        await _handle_edit(query, data, user_id)
        return True
    if data.startswith("editfield_"):
        await _handle_editfield(query, data, user_id, context)
        return True
    if data.startswith("editset_"):
        await _handle_editset(query, data, user_id)
        return True
    if data.startswith("canceledit_"):
        await _handle_canceledit(query, data, user_id, context)
        return True
    if data.startswith("back_"):
        await _handle_back(query, data, user_id, context)
        return True
    if data.startswith("tgl_") and not data.startswith("tglbulan_") and not data.startswith("tglset_"):
        await _handle_tgl(query, data, user_id)
        return True
    if data.startswith("tglbulan_"):
        await _handle_tglbulan(query, data)
        return True
    if data.startswith("tglset_"):
        await _handle_tglset(query, data, user_id)
        return True
    return False


async def _handle_edittx(query, data: str, user_id: int, context):
    """Tampilkan daftar transaksi bulan untuk dipilih dan diedit"""
    parts = data.split("_")
    year = int(parts[1])
    month = int(parts[2])
    page = int(parts[3])

    per_page = 5
    txs = get_month_transactions(user_id, year, month)
    month_name = _MONTH_NAMES.get(month, str(month))

    if not txs:
        await _safe_edit_or_reply(
            query.message,
            f"✏️ <b>Edit Transaksi — {month_name} {year}</b>\n\n<i>Belum ada transaksi.</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📅 Bulan Lain", callback_data="cmd_pilihbulan")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )
        return

    total_pages = (len(txs) + per_page - 1) // per_page
    page = min(page, total_pages - 1)
    start = page * per_page
    page_txs = txs[start:start + per_page]

    buttons = []
    for tx in page_txs:
        emoji = "💰" if tx["type"] == "masuk" else "💸"
        desc = tx.get("description", "")[:18]
        amount = format_rupiah(tx["amount"])
        dt = parse_iso_date(tx.get("created_at", ""))
        date_str = format_tanggal(dt, short=True) if dt else ""
        label = f"{emoji} {desc} — {amount} ({date_str})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"edit_{tx['user_tx_no']}")])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Sebelumnya", callback_data=f"edittx_{year}_{month}_{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Selanjutnya ➡️", callback_data=f"edittx_{year}_{month}_{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton(f"📅 Kembali ke {month_name}", callback_data=f"viewbulan_{year}_{month}"),
        InlineKeyboardButton("🏠 Menu", callback_data="cmd_start"),
    ])

    await _safe_edit_or_reply(
        query.message,
        f"✏️ <b>Edit Transaksi — {month_name} {year}</b>\n"
        f"📝 {len(txs)} transaksi  •  Halaman {page + 1}/{total_pages}\n\n"
        f"Pilih transaksi yang ingin diedit 👇",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _handle_edit(query, data: str, user_id: int):
    """Tampilkan sub-menu pilihan field untuk diedit"""
    tx_id = int(data.split("_")[1])
    tx = get_transaction_by_id(tx_id, user_id)
    if tx:
        emoji = "💰" if tx["type"] == "masuk" else "💸"
        tipe = "Pemasukan" if tx["type"] == "masuk" else "Pengeluaran"
        await query.message.edit_text(
            f"✏️ <b>Edit Transaksi</b> <code>#{tx_id}</code>\n\n"
            f"┌ 📌 {tx['description']}\n"
            f"├ 💵 {format_rupiah(tx['amount'])}\n"
            f"├ 🗂️ {tx.get('category', 'Lainnya')}\n"
            f"└ {emoji} {tipe}\n\n"
            f"Pilih field yang ingin diubah 👇",
            parse_mode="HTML",
            reply_markup=edit_field_keyboard(tx_id),
        )
    else:
        await query.message.edit_text(
            f"❌ Transaksi <code>#{tx_id}</code> tidak ditemukan.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )


async def _handle_editfield(query, data: str, user_id: int, context):
    """User memilih field untuk diedit"""
    parts = data.split("_")
    tx_id = int(parts[1])
    field = parts[2]

    if field == "type":
        await query.message.edit_text(
            f"🔄 <b>Ubah Tipe</b> — Transaksi <code>#{tx_id}</code>\n\nPilih tipe baru 👇",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("💰 Masuk", callback_data=f"editset_{tx_id}_type_masuk"),
                    InlineKeyboardButton("💸 Keluar", callback_data=f"editset_{tx_id}_type_keluar"),
                ],
                [InlineKeyboardButton("⬅️ Kembali", callback_data=f"edit_{tx_id}")],
            ]),
        )
    elif field == "category":
        categories = list(CATEGORY_KEYWORDS.keys()) + ["Lainnya"]
        buttons = []
        row = []
        for cat in categories:
            row.append(InlineKeyboardButton(cat, callback_data=f"editset_{tx_id}_category_{cat}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data=f"edit_{tx_id}")])
        await query.message.edit_text(
            f"🗂️ <b>Ubah Kategori</b> — Transaksi <code>#{tx_id}</code>\n\nPilih kategori baru 👇",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    else:
        # amount & description: simpan state, minta user ketik
        context.user_data["edit_state"] = {"tx_id": tx_id, "field": field}
        prompts = {
            "amount": ("💵 Nominal", "Ketik nominal baru\n\n<i>Contoh: 30k, 50rb, 1.5jt</i>"),
            "description": ("📝 Deskripsi", "Ketik deskripsi baru"),
        }
        label, hint = prompts.get(field, (field, "Ketik nilai baru"))
        await query.message.edit_text(
            f"✏️ <b>Edit {label}</b> — Transaksi <code>#{tx_id}</code>\n\n{hint}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Batal", callback_data=f"canceledit_{tx_id}")],
            ]),
        )


async def _handle_editset(query, data: str, user_id: int):
    """Edit langsung via tombol (type & category)"""
    parts = data.split("_", 3)
    tx_id = int(parts[1])
    field = parts[2]
    value = parts[3]

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

    field_labels = {"type": "Tipe", "category": "Kategori"}
    old_values = {
        "type": "Pemasukan" if tx["type"] == "masuk" else "Pengeluaran",
        "category": tx.get("category", "Lainnya"),
    }
    old_display = old_values.get(field, "")

    success = update_transaction(tx_id, user_id, **{field: value})
    if success:
        new_display = "Pemasukan" if value == "masuk" else "Pengeluaran" if field == "type" else value
        await query.message.edit_text(
            f"✅ <b>Transaksi Diperbarui</b>\n\n"
            f"🔖 ID: <code>#{tx_id}</code>\n"
            f"📝 {field_labels.get(field, field)}: {old_display} → <b>{new_display}</b>",
            parse_mode="HTML",
            reply_markup=after_tx_keyboard(tx_id),
        )
    else:
        await query.message.edit_text(
            "❌ Gagal memperbarui transaksi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )


async def _handle_canceledit(query, data: str, user_id: int, context):
    """Batal edit → clear state, kembali ke konfirmasi transaksi"""
    tx_id = int(data.split("_")[1])
    context.user_data.pop("edit_state", None)
    tx = get_transaction_by_id(tx_id, user_id)
    if tx:
        await query.message.edit_text(
            tx_confirmation_message(tx),
            parse_mode="HTML",
            reply_markup=after_tx_keyboard(tx_id),
        )
    else:
        await query.message.edit_text(
            f"❌ Transaksi <code>#{tx_id}</code> tidak ditemukan.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )


async def _handle_back(query, data: str, user_id: int, context):
    """Kembali ke konfirmasi transaksi"""
    tx_id = int(data.split("_")[1])
    context.user_data.pop("edit_state", None)
    tx = get_transaction_by_id(tx_id, user_id)
    if tx:
        await query.message.edit_text(
            tx_confirmation_message(tx),
            parse_mode="HTML",
            reply_markup=after_tx_keyboard(tx_id),
        )
    else:
        await query.message.edit_text(
            f"❌ Transaksi <code>#{tx_id}</code> tidak ditemukan.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )


async def _handle_tgl(query, data: str, user_id: int):
    """Tampilkan pilihan bulan untuk ubah tanggal transaksi"""
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
        row.append(InlineKeyboardButton(label, callback_data=f"tglbulan_{tx_id}_{y}_{m}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data=f"back_{tx_id}")])

    emoji = "💰" if tx["type"] == "masuk" else "💸"
    await query.message.edit_text(
        f"📅 <b>Ubah Tanggal</b> — <code>#{tx_id}</code>\n\n"
        f"{emoji} {tx['description']} — <b>{format_rupiah(tx['amount'])}</b>\n\n"
        f"Pilih bulan 👇",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _handle_tglbulan(query, data: str):
    """Tampilkan grid tanggal untuk bulan yang dipilih"""
    parts = data.split("_")
    tx_id = int(parts[1])
    year = int(parts[2])
    month = int(parts[3])

    _, days_in_month = calendar.monthrange(year, month)
    month_name = BULAN.get(month, str(month))

    buttons = []
    row = []
    for day in range(1, days_in_month + 1):
        row.append(InlineKeyboardButton(str(day), callback_data=f"tglset_{tx_id}_{year}_{month}_{day}"))
        if len(row) == 7:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton("⬅️ Pilih Bulan", callback_data=f"tgl_{tx_id}"),
        InlineKeyboardButton("❌ Batal", callback_data=f"back_{tx_id}"),
    ])

    await query.message.edit_text(
        f"📅 <b>Pilih Tanggal — {month_name} {year}</b>\n\nKetuk tanggal yang diinginkan 👇",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _handle_tglset(query, data: str, user_id: int):
    """Simpan tanggal yang dipilih ke transaksi"""
    parts = data.split("_")
    tx_id = int(parts[1])
    year = int(parts[2])
    month = int(parts[3])
    day = int(parts[4])

    new_date = datetime(year, month, day, 12, 0, 0, tzinfo=WIB)
    success = update_transaction_date(tx_id, user_id, new_date)
    if success:
        await query.message.edit_text(
            f"✅ <b>Tanggal Diperbarui</b>\n\n"
            f"🔖 ID: <code>#{tx_id}</code>\n"
            f"📅 {format_tanggal(new_date)}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Lihat Hari Ini", callback_data="cmd_hariini")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )
    else:
        await query.message.edit_text(
            "❌ Gagal mengubah tanggal.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )
