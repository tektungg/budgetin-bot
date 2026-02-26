"""
Handler umum: /start, /help, /hapus, /edit
Dengan inline keyboard untuk navigasi interaktif.
"""

import logging
import platform
import time
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.database import delete_transaction, update_transaction, get_transaction_by_id
from services.parser import parse_amount, detect_category, format_rupiah
from utils.auth import require_auth

logger = logging.getLogger(__name__)

# Waktu bot pertama kali start
_BOT_START_TIME = time.time()


# ── Inline Keyboard Menus ──────────────────────────────

def main_menu_keyboard():
    """Keyboard menu utama"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Hari Ini", callback_data="cmd_hariini"),
            InlineKeyboardButton("📅 Bulan Ini", callback_data="cmd_bulanini"),
        ],
        [
            InlineKeyboardButton("🗂️ Kategori", callback_data="cmd_kategori"),
            InlineKeyboardButton("📤 Export", callback_data="cmd_export"),
        ],
        [
            InlineKeyboardButton("❓ Bantuan", callback_data="cmd_help"),
        ],
    ])


def after_tx_keyboard(tx_id: int):
    """Keyboard setelah transaksi berhasil dicatat"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Hari Ini", callback_data="cmd_hariini"),
            InlineKeyboardButton("✏️ Edit", callback_data=f"edit_{tx_id}"),
            InlineKeyboardButton("🗑️ Hapus", callback_data=f"hapus_{tx_id}"),
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
            InlineKeyboardButton("⬅️ Kembali", callback_data=f"back_{tx_id}"),
        ],
    ])


def report_keyboard():
    """Keyboard di bawah laporan"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗂️ Per Kategori", callback_data="cmd_kategori"),
        InlineKeyboardButton("📤 Export", callback_data="cmd_export"),
        ],
        [
            InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start"),
        ],
    ])


# ── Text Templates ─────────────────────────────────────

START_TEXT = """
<b>BUDGETIN BOT</b>
━━━━━━━━━━━━━━━━━━━━

Hai, <b>{name}</b>! 👋
Saya asisten pencatat keuangan pribadimu.

<b>⚡ Cara Pakai:</b>
┌ Ketik langsung transaksimu
├ <code>keluar makan siang 25k</code>
├ <code>masuk gaji 3jt</code>
└ Atau kirim 📸 <b>foto struk</b>

Pilih menu di bawah untuk mulai 👇
"""

HELP_TEXT = """
<b>PANDUAN LENGKAP</b>
━━━━━━━━━━━━━━━━━━━━

<b>📝 CATAT TRANSAKSI</b>
<i>Ketik langsung dengan format natural:</i>
┌ <code>keluar makan siang 25k</code>
├ <code>keluar grab 15000</code>
├ <code>keluar belanja alfamart 87.5rb</code>
├ <code>masuk gaji 3jt</code>
├ <code>masuk freelance desain 500rb</code>
└ <code>masuk transfer dari kakak 200k</code>

<b>📸 FOTO STRUK</b>
<i>Kirim foto struk/nota → otomatis dicatat!</i>

<b>💡 FORMAT NOMINAL</b>
┌ <code>5000</code> = <code>5k</code> = <code>5rb</code> → Rp 5.000
└ <code>2000000</code> = <code>2m</code> = <code>2jt</code> → Rp 2.000.000

<b>✏️ EDIT & HAPUS</b>
┌ <code>/hapus 42</code> — hapus transaksi #42
├ <code>/edit 42 amount 30k</code>
├ <code>/edit 42 category Transportasi</code>
└ <code>/edit 42 description grab ke kantor</code>

<b>📊 LAPORAN</b>
┌ /hariini — transaksi hari ini
├ /bulanini — ringkasan bulan ini
├ /bulanini <code>1 2025</code> — bulan tertentu
├ /kategori — ringkasan per kategori
├ /export — export bulan ini ke Excel
└ /export <code>1 2025</code> — export bulan tertentu

<b>🔍 PENCARIAN</b>
┌ <code>/cari makan</code> — cari di deskripsi
└ <code>/cari Transportasi</code> — cari di kategori
"""


@require_auth
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "User"
    await update.message.reply_text(
        START_TEXT.format(name=name),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


@require_auth
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        HELP_TEXT,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


@require_auth
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan status & health bot"""
    WIB = timezone(timedelta(hours=7))
    now = datetime.now(WIB)

    # Uptime
    uptime_sec = int(time.time() - _BOT_START_TIME)
    days, rem = divmod(uptime_sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    uptime_parts = []
    if days:
        uptime_parts.append(f"{days}h")
    if hours:
        uptime_parts.append(f"{hours}j")
    uptime_parts.append(f"{minutes}m")
    uptime_str = " ".join(uptime_parts)

    from utils.formatter import BULAN
    bulan = BULAN.get(now.month, "")

    text = (
        f"🤖 <b>STATUS BOT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"┌ ⏱️ Uptime: <b>{uptime_str}</b>\n"
        f"├ 🐍 Python {platform.python_version()}\n"
        f"└ 🕐 {now.strftime('%d')} {bulan} {now.year}, {now.strftime('%H:%M')} WIB"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


@require_auth
async def cmd_hapus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hapus transaksi berdasarkan ID"""
    user_id = update.effective_user.id
    args = context.args

    if not args:
        await update.message.reply_text(
            "🗑️ <b>Hapus Transaksi</b>\n\n"
            "Format: <code>/hapus [id]</code>\n"
            "Contoh: <code>/hapus 42</code>\n\n"
            "<i>💡 ID terlihat di laporan dalam format [#42]</i>",
            parse_mode="HTML",
        )
        return

    try:
        tx_id = int(args[0].lstrip("#"))
    except ValueError:
        await update.message.reply_text("⚠️ ID harus berupa angka.\nContoh: <code>/hapus 42</code>", parse_mode="HTML")
        return

    tx = get_transaction_by_id(tx_id, user_id)
    if not tx:
        await update.message.reply_text(f"❌ Transaksi <code>#{tx_id}</code> tidak ditemukan.", parse_mode="HTML")
        return

    success = delete_transaction(tx_id, user_id)
    if success:
        emoji = "💰" if tx["type"] == "masuk" else "💸"
        tipe = "Pemasukan" if tx["type"] == "masuk" else "Pengeluaran"
        await update.message.reply_text(
            f"✅ <b>Transaksi Dihapus</b>\n\n"
            f"{emoji} {tx['description']}\n"
            f"💵 {format_rupiah(tx['amount'])} ({tipe})\n"
            f"🔖 ID: <code>#{tx_id}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📊 Lihat Hari Ini", callback_data="cmd_hariini"),
            ]]),
        )
    else:
        await update.message.reply_text("❌ Gagal menghapus transaksi.")


@require_auth
async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Edit transaksi: /edit [id] [field] [nilai]"""
    user_id = update.effective_user.id
    args = context.args

    if len(args) < 3:
        await update.message.reply_text(
            "✏️ <b>Edit Transaksi</b>\n\n"
            "Format: <code>/edit [id] [field] [nilai]</code>\n\n"
            "<b>Field yang bisa diubah:</b>\n"
            "┌ <code>amount</code> — nominal\n"
            "├ <code>category</code> — kategori\n"
            "├ <code>description</code> — deskripsi\n"
            "└ <code>type</code> — masuk/keluar\n\n"
            "<b>Contoh:</b>\n"
            "┌ <code>/edit 42 amount 30k</code>\n"
            "├ <code>/edit 42 category Transportasi</code>\n"
            "└ <code>/edit 42 description grab ke kantor</code>",
            parse_mode="HTML",
        )
        return

    try:
        tx_id = int(args[0].lstrip("#"))
    except ValueError:
        await update.message.reply_text("⚠️ ID harus berupa angka.", parse_mode="HTML")
        return

    field = args[1].lower()
    value_raw = " ".join(args[2:])

    allowed_fields = {"amount", "category", "description", "type"}
    if field not in allowed_fields:
        await update.message.reply_text(
            f"⚠️ Field <code>{field}</code> tidak valid.\n\n"
            f"Gunakan: <code>{', '.join(sorted(allowed_fields))}</code>",
            parse_mode="HTML",
        )
        return

    if field == "amount":
        value = parse_amount(value_raw)
        if not value:
            await update.message.reply_text("⚠️ Format nominal tidak valid.", parse_mode="HTML")
            return
    elif field == "type":
        if value_raw not in ("masuk", "keluar"):
            await update.message.reply_text(
                "⚠️ Tipe harus <code>masuk</code> atau <code>keluar</code>.",
                parse_mode="HTML",
            )
            return
        value = value_raw
    else:
        value = value_raw

    tx = get_transaction_by_id(tx_id, user_id)
    if not tx:
        await update.message.reply_text(f"❌ Transaksi <code>#{tx_id}</code> tidak ditemukan.", parse_mode="HTML")
        return

    success = update_transaction(tx_id, user_id, **{field: value})
    if success:
        # Map field names ke label Indo
        field_labels = {
            "amount": "Nominal",
            "category": "Kategori",
            "description": "Deskripsi",
            "type": "Tipe",
        }
        await update.message.reply_text(
            f"✅ <b>Transaksi Diperbarui</b>\n\n"
            f"🔖 ID: <code>#{tx_id}</code>\n"
            f"📝 {field_labels.get(field, field)}: <code>{value_raw}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📊 Lihat Hari Ini", callback_data="cmd_hariini"),
            ]]),
        )
    else:
        await update.message.reply_text("❌ Gagal memperbarui transaksi.")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses"""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    # Import di sini untuk hindari circular import
    from handlers.report import (
        _send_hari_ini,
        _send_bulan_ini,
        _send_kategori,
        _send_export,
    )

    if data == "cmd_start":
        name = query.from_user.first_name or "User"
        await query.message.edit_text(
            START_TEXT.format(name=name),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
    elif data == "cmd_help":
        await query.message.edit_text(
            HELP_TEXT,
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
    elif data == "cmd_hariini":
        await _send_hari_ini(query.message, user_id, edit=True)
    elif data == "cmd_bulanini":
        await _send_bulan_ini(query.message, user_id, edit=True)
    elif data == "cmd_kategori":
        await _send_kategori(query.message, user_id, edit=True)
    elif data == "cmd_export":
        await _send_export(query.message, user_id, edit=True)
    elif data.startswith("edit_"):
        # Tampilkan sub-menu pilihan field
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
            )
    elif data.startswith("editfield_"):
        # User memilih field → tampilkan instruksi
        parts = data.split("_")
        tx_id = int(parts[1])
        field = parts[2]

        field_info = {
            "amount": ("💵 Nominal", "Ketik nominal baru", f"/edit {tx_id} amount 30k"),
            "category": ("🗂️ Kategori", "Ketik kategori baru", f"/edit {tx_id} category Transportasi"),
            "type": ("🔄 Tipe", "Ketik tipe baru (masuk/keluar)", f"/edit {tx_id} type keluar"),
            "description": ("📝 Deskripsi", "Ketik deskripsi baru", f"/edit {tx_id} description grab ke kantor"),
        }

        label, hint, example = field_info.get(field, (field, "", ""))

        await query.message.edit_text(
            f"✏️ <b>Edit {label}</b> — Transaksi <code>#{tx_id}</code>\n\n"
            f"{hint}. Kirim perintah berikut:\n\n"
            f"<code>{example}</code>\n\n"
            f"<i>💡 Salin perintah di atas, ubah nilainya, lalu kirim.</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Kembali", callback_data=f"edit_{tx_id}")],
            ]),
        )
    elif data.startswith("back_"):
        # Kembali ke konfirmasi transaksi
        tx_id = int(data.split("_")[1])
        tx = get_transaction_by_id(tx_id, user_id)
        if tx:
            from utils.formatter import tx_confirmation_message
            await query.message.edit_text(
                tx_confirmation_message(tx),
                parse_mode="HTML",
                reply_markup=after_tx_keyboard(tx_id),
            )
        else:
            await query.message.edit_text(
                f"❌ Transaksi <code>#{tx_id}</code> tidak ditemukan.",
                parse_mode="HTML",
            )
    elif data.startswith("hapus_"):
        tx_id = int(data.split("_")[1])
        tx = get_transaction_by_id(tx_id, user_id)
        if tx:
            success = delete_transaction(tx_id, user_id)
            if success:
                await query.message.edit_text(
                    f"✅ <b>Transaksi <code>#{tx_id}</code> dibatalkan</b>\n\n"
                    f"💸 {tx['description']} — {format_rupiah(tx['amount'])}",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("📊 Lihat Hari Ini", callback_data="cmd_hariini"),
                        InlineKeyboardButton("🏠 Menu", callback_data="cmd_start"),
                    ]]),
                )
            else:
                await query.message.edit_text("❌ Gagal menghapus transaksi.")
        else:
            await query.message.edit_text(
                f"❌ Transaksi <code>#{tx_id}</code> tidak ditemukan.",
                parse_mode="HTML",
            )
