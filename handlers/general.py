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
from services.parser import parse_amount, format_rupiah
from utils.auth import require_auth
from handlers.keyboards import (
    main_menu_keyboard,
    help_keyboard,
    _safe_edit_or_reply,
)
from handlers.report import (
    _send_hari_ini,
    _send_bulan_ini,
    _send_pilih_bulan,
    _send_kategori,
    _send_export,
    _do_export,
    _send_category_drilldown,
    _send_search,
    _send_search_month,
    MONTH_NAMES as _MONTH_NAMES,
)

logger = logging.getLogger(__name__)

# Waktu bot pertama kali start
_BOT_START_TIME = time.time()


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

<b>📅 CATAT KE TANGGAL LALU</b>
<i>Tambahkan tanggal di akhir pesan:</i>
┌ <code>keluar makan 25k 15/3</code>
└ <code>masuk freelance 500rb 1/2/2025</code>

<b>💡 FORMAT NOMINAL</b>
┌ <code>5000</code> = <code>5k</code> = <code>5rb</code> → Rp 5.000
└ <code>2000000</code> = <code>2m</code> = <code>2jt</code> → Rp 2.000.000

<b>✏️ EDIT & HAPUS</b>
<i>Klik tombol ✏️ Edit setelah catat transaksi,
lalu pilih field yang ingin diubah:</i>
┌ 💵 Nominal — ketik nilai baru
├ 🗂️ Kategori — pilih dari daftar
├ 🔄 Tipe — pilih masuk/keluar
├ 📝 Deskripsi — ketik teks baru
└ 📅 Tanggal — pilih tanggal lain

<i>Atau gunakan perintah:</i>
┌ <code>/hapus 42</code> — hapus transaksi #42
└ <code>/batal</code> — batalkan proses edit

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

<b>⚙️ LAINNYA</b>
└ /status — cek status & uptime bot
"""


@require_auth
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "User"
    await update.message.reply_text(
        START_TEXT.format(name=name),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


async def cmd_batal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Batalkan proses edit yang sedang berlangsung"""
    edit_state = context.user_data.pop("edit_state", None)
    if edit_state:
        await update.message.reply_text(
            "❌ Edit dibatalkan.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            "Tidak ada proses yang sedang berjalan.",
            reply_markup=main_menu_keyboard(),
        )


@require_auth
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        HELP_TEXT,
        parse_mode="HTML",
        reply_markup=help_keyboard(),
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
        reply_markup=help_keyboard(),
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
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )
        return

    try:
        tx_id = int(args[0].lstrip("#"))
    except ValueError:
        await update.message.reply_text(
            "⚠️ ID harus berupa angka.\nContoh: <code>/hapus 42</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )
        return

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
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Lihat Hari Ini", callback_data="cmd_hariini")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )
    else:
        await update.message.reply_text(
            "❌ Gagal menghapus transaksi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )


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
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )
        return

    try:
        tx_id = int(args[0].lstrip("#"))
    except ValueError:
        await update.message.reply_text(
            "⚠️ ID harus berupa angka.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )
        return

    field = args[1].lower()
    value_raw = " ".join(args[2:])

    allowed_fields = {"amount", "category", "description", "type"}
    if field not in allowed_fields:
        await update.message.reply_text(
            f"⚠️ Field <code>{field}</code> tidak valid.\n\n"
            f"Gunakan: <code>{', '.join(sorted(allowed_fields))}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )
        return

    if field == "amount":
        value = parse_amount(value_raw)
        if not value:
            await update.message.reply_text(
                "⚠️ Format nominal tidak valid.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
                ]),
            )
            return
    elif field == "type":
        if value_raw not in ("masuk", "keluar"):
            await update.message.reply_text(
                "⚠️ Tipe harus <code>masuk</code> atau <code>keluar</code>.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
                ]),
            )
            return
        value = value_raw
    else:
        value = value_raw

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

    # Simpan nilai lama sebelum update
    field_labels = {
        "amount": "Nominal",
        "category": "Kategori",
        "description": "Deskripsi",
        "type": "Tipe",
    }
    old_values = {
        "amount": format_rupiah(tx["amount"]),
        "category": tx.get("category", "Lainnya"),
        "description": tx.get("description", ""),
        "type": "Pemasukan" if tx["type"] == "masuk" else "Pengeluaran",
    }
    old_display = old_values.get(field, "")

    success = update_transaction(tx_id, user_id, **{field: value})
    if success:
        # Format nilai baru untuk display
        if field == "amount":
            new_display = format_rupiah(value)
        elif field == "type":
            new_display = "Pemasukan" if value == "masuk" else "Pengeluaran"
        else:
            new_display = value_raw

        await update.message.reply_text(
            f"✅ <b>Transaksi Diperbarui</b>\n\n"
            f"🔖 ID: <code>#{tx_id}</code>\n"
            f"📝 {field_labels.get(field, field)}: {old_display} → <b>{new_display}</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Lihat Hari Ini", callback_data="cmd_hariini")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )
    else:
        await update.message.reply_text(
            "❌ Gagal memperbarui transaksi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses — router tipis ke sub-handler per domain."""
    from handlers.callbacks_delete import handle_delete_callbacks
    from handlers.callbacks_receipt import handle_receipt_callbacks
    from handlers.callbacks_edit import handle_edit_callbacks

    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    # Jika ada countdown undo aktif dan user melakukan aksi lain → stop UI update
    # Hard delete tetap jalan di background via task yang sudah berjalan
    if not data.startswith("undel_"):
        active_tid = context.bot_data.get(f"active_undo_{user_id}")
        if active_tid:
            context.bot_data[f"undo_stop_{active_tid}"] = "nav"
            context.bot_data.pop(f"active_undo_{user_id}", None)

    # Delegasikan ke domain-specific handlers
    if await handle_receipt_callbacks(query, data, user_id, context):
        return
    if await handle_delete_callbacks(query, data, user_id, context):
        return
    if await handle_edit_callbacks(query, data, user_id, context):
        return

    # ── Navigation & Report Callbacks ──────────────────
    if data == "cmd_start":
        context.user_data.pop("search_state", None)
        name = query.from_user.first_name or "User"
        await _safe_edit_or_reply(
            query.message,
            START_TEXT.format(name=name),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
    elif data == "cmd_cari_global":
        context.user_data["search_state"] = {"scope": "global"}
        await _safe_edit_or_reply(
            query.message,
            "🔍 <b>Cari Transaksi</b>\n\nKetik kata kunci yang ingin dicari di seluruh transaksi 👇",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Batal", callback_data="cmd_start")],
            ]),
        )
    elif data.startswith("cmd_cari_month_"):
        parts = data.split("_")
        year, month = int(parts[3]), int(parts[4])
        context.user_data["search_state"] = {"scope": "month", "year": year, "month": month}
        month_name = _MONTH_NAMES.get(month, str(month))
        await _safe_edit_or_reply(
            query.message,
            f"🔍 <b>Cari di {month_name} {year}</b>\n\nKetik kata kunci yang ingin dicari 👇",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Batal", callback_data=f"viewbulan_{year}_{month}")],
            ]),
        )
    elif data == "cmd_help":
        await _safe_edit_or_reply(
            query.message,
            HELP_TEXT,
            parse_mode="HTML",
            reply_markup=help_keyboard(),
        )
    elif data == "cmd_hariini":
        await _send_hari_ini(query.message, user_id, edit=True)
    elif data == "cmd_bulanini":
        await _send_bulan_ini(query.message, user_id, edit=True)
    elif data == "cmd_pilihbulan":
        await _send_pilih_bulan(query.message, user_id, edit=True)
    elif data.startswith("viewbulan_"):
        parts = data.split("_")
        year = int(parts[1])
        month = int(parts[2])
        await _send_bulan_ini(query.message, user_id, year=year, month=month, edit=True)
    elif data.startswith("viewbulanp_"):
        parts = data.split("_")
        year = int(parts[1])
        month = int(parts[2])
        page = int(parts[3])
        await _send_bulan_ini(query.message, user_id, year=year, month=month, page=page, edit=True)
    elif data.startswith("cmd_kategori"):
        if data == "cmd_kategori":
            await _send_kategori(query.message, user_id, edit=True)
        elif data.startswith("cmd_kategori_back_"):
            parts = data.split("_")
            year = int(parts[3])
            month = int(parts[4])
            await _send_kategori(query.message, user_id, year=year, month=month, edit=True)
        else:
            parts = data.split("_")
            if len(parts) >= 4:
                year = int(parts[2])
                month = int(parts[3])
                await _send_kategori(query.message, user_id, year=year, month=month, edit=True)
    elif data.startswith("catdrill_"):
        parts = data.split("_")
        year = int(parts[1])
        month = int(parts[2])
        tx_type = parts[3]
        cat_name = "_".join(parts[4:-1])
        page = int(parts[-1])
        await _send_category_drilldown(query.message, user_id, year, month, tx_type, cat_name, page)
    elif data.startswith("srchg_"):
        # srchg_{page}_{keyword}
        _, page_str, keyword = data.split("_", 2)
        await _send_search(query.message, user_id, keyword, page=int(page_str), edit=True)
    elif data.startswith("srchm_"):
        # srchm_{year}_{month}_{page}_{keyword}
        _, year_str, month_str, page_str, keyword = data.split("_", 4)
        await _send_search_month(query.message, user_id, keyword, int(year_str), int(month_str), page=int(page_str), edit=True)
    elif data == "cmd_export":
        await _send_export(query.message, user_id, edit=True)
    elif data.startswith("doexport_"):
        # Format: doexport_YYYY_MM
        parts = data.split("_")
        year = int(parts[1])
        month = int(parts[2])
        await _do_export(query.message, user_id, year, month)

