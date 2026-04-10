"""
Keyboard builders dan UI helpers yang dipakai bersama oleh semua handlers.
Dipisah ke sini agar tidak ada circular import antara general.py ↔ report.py.
"""

from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard():
    """Keyboard menu utama"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Hari Ini", callback_data="cmd_hariini"),
            InlineKeyboardButton("📅 Bulanan", callback_data="cmd_pilihbulan"),
        ],
        [
            InlineKeyboardButton("🗂️ Kategori", callback_data="cmd_kategori"),
            InlineKeyboardButton("📤 Export", callback_data="cmd_export"),
        ],
        [
            InlineKeyboardButton("🔍 Cari", callback_data="cmd_cari_global"),
            InlineKeyboardButton("❓ Bantuan", callback_data="cmd_help"),
        ],
    ])


def help_keyboard():
    """Keyboard di halaman bantuan — hanya tombol kembali ke menu utama"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start"),
        ],
    ])


def after_tx_keyboard(tx_id: int):
    """Keyboard setelah transaksi berhasil dicatat"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Hari Ini", callback_data="cmd_hariini"),
            InlineKeyboardButton("✏️ Edit", callback_data=f"edit_{tx_id}"),
        ],
        [
            InlineKeyboardButton("📅 Ubah Tanggal", callback_data=f"tgl_{tx_id}"),
            InlineKeyboardButton("🗑️ Hapus", callback_data=f"hapus_{tx_id}"),
        ],
        [
            InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start"),
        ],
    ])


def edit_field_keyboard(tx_id: int):
    """Keyboard pilihan field untuk edit transaksi"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💵 Nominal", callback_data=f"editfield_{tx_id}_amount"),
            InlineKeyboardButton("🗂️ Kategori", callback_data=f"editfield_{tx_id}_category"),
        ],
        [
            InlineKeyboardButton("🔄 Tipe", callback_data=f"editfield_{tx_id}_type"),
            InlineKeyboardButton("📝 Deskripsi", callback_data=f"editfield_{tx_id}_description"),
        ],
        [
            InlineKeyboardButton("📅 Tanggal", callback_data=f"tgl_{tx_id}"),
        ],
        [
            InlineKeyboardButton("⬅️ Kembali", callback_data=f"back_{tx_id}"),
            InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start"),
        ],
    ])


def report_keyboard(year: int = None, month: int = None, page: int = 0, total_pages: int = 1):
    """Keyboard di bawah laporan — year/month untuk konteks edit dan navigasi page"""
    now = datetime.now()
    y = year or now.year
    m = month or now.month

    buttons = []

    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"viewbulanp_{y}_{m}_{page-1}"))
        else:
            nav_row.append(InlineKeyboardButton("➖", callback_data="noop"))

        nav_row.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))

        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"viewbulanp_{y}_{m}_{page+1}"))
        else:
            nav_row.append(InlineKeyboardButton("➖", callback_data="noop"))

        buttons.append(nav_row)

    buttons.extend([
        [
            InlineKeyboardButton("🗂️ Per Kategori", callback_data=f"cmd_kategori_{y}_{m}"),
            InlineKeyboardButton("📤 Export", callback_data="cmd_export"),
        ],
        [
            InlineKeyboardButton("📅 Bulan Lain", callback_data="cmd_pilihbulan"),
            InlineKeyboardButton("✏️ Edit Transaksi", callback_data=f"edittx_{y}_{m}_0"),
        ],
        [
            InlineKeyboardButton("🔍 Cari di Bulan Ini", callback_data=f"cmd_cari_month_{y}_{m}"),
        ],
        [
            InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start"),
        ],
    ])

    return InlineKeyboardMarkup(buttons)


async def _safe_edit_or_reply(message, text: str, **kwargs):
    """edit_text jika pesan adalah teks, reply_text jika dokumen/foto"""
    if message.text:
        await message.edit_text(text, **kwargs)
    else:
        await message.reply_text(text, **kwargs)
