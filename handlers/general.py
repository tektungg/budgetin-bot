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
from services.database import delete_transaction, update_transaction, update_transaction_date, get_transaction_by_id, get_month_transactions
from services.parser import parse_amount, detect_category, format_rupiah, CATEGORY_KEYWORDS
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
            InlineKeyboardButton("📅 Bulanan", callback_data="cmd_pilihbulan"),
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
    from datetime import datetime as _dt
    now = _dt.now()
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
            InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start"),
        ],
    ])
    
    return InlineKeyboardMarkup(buttons)


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
lalu pilih field yang ingin diubah.</i>
┌ 💵 Nominal — ketik nilai baru
├ 🗂️ Kategori — pilih dari daftar
├ 🔄 Tipe — pilih masuk/keluar
├ 📝 Deskripsi — ketik teks baru
└ 📅 Tanggal — pilih tanggal lain

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


async def _safe_edit_or_reply(message, text: str, **kwargs):
    """edit_text jika pesan adalah teks, reply_text jika dokumen/foto"""
    if message.text:
        await message.edit_text(text, **kwargs)
    else:
        await message.reply_text(text, **kwargs)


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
        _send_pilih_bulan,
        _send_kategori,
        _send_export,
        _do_export,
    )

    if data == "cmd_start":
        name = query.from_user.first_name or "User"
        await _safe_edit_or_reply(
            query.message,
            START_TEXT.format(name=name),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
    elif data == "cmd_help":
        await _safe_edit_or_reply(
            query.message,
            HELP_TEXT,
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
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
        from handlers.report import _send_category_drilldown
        await _send_category_drilldown(query.message, user_id, year, month, tx_type, cat_name, page)

    elif data == "rcpt_ok":
        context.user_data.pop("pending_receipt_title", None)
        items = context.user_data.pop("pending_receipt", [])
        if not items:
            await query.message.edit_text("❌ Gagal: Tidak ada data struk tersimpan.")
            return
            
        saved = []
        for tx_data in items:
            from services.database import insert_transaction
            tx = insert_transaction(
                user_id=user_id,
                tx_type=tx_data["type"],
                amount=tx_data["amount"],
                category=tx_data["category"],
                description=tx_data["description"],
                source="photo",
                created_at=tx_data.get("date"),
            )
            saved.append(tx)
            
        if len(saved) == 1:
            from utils.formatter import tx_confirmation_message
            await query.message.edit_text(
                "📸 <b>Struk Berhasil Dicatat!</b>\n\n" + tx_confirmation_message(saved[0]),
                parse_mode="HTML",
                reply_markup=after_tx_keyboard(saved[0]["id"]),
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
    elif data == "rcpt_no":
        context.user_data.pop("pending_receipt", None)
        context.user_data.pop("pending_receipt_title", None)
        await query.message.edit_text(
            "🚫 <b>Penyimpanan Struk Dibatalkan</b>",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard()
        )
    elif data.startswith("rcpt_del_"):
        idx = int(data.split("_")[-1])
        items = context.user_data.get("pending_receipt", [])
        if idx < len(items):
            items.pop(idx)
            if not items:
                context.user_data.pop("pending_receipt", None)
                await query.message.edit_text(
                    "🚫 <b>Penyimpanan Struk Dibatalkan</b> (semua item dihapus)",
                    parse_mode="HTML",
                    reply_markup=main_menu_keyboard()
                )
                return
            context.user_data["pending_receipt"] = items
            from handlers.transaction import _render_receipt_preview
            _title = context.user_data.get("pending_receipt_title")
            msg, kb = _render_receipt_preview(items, title=_title) if _title else _render_receipt_preview(items)
            await query.message.edit_text(msg, parse_mode="HTML", reply_markup=kb)
    elif data.startswith("rcpt_edit_"):
        idx = int(data.split("_")[-1])
        items = context.user_data.get("pending_receipt", [])
        if idx < len(items):
            item = items[idx]
            from utils.formatter import format_tanggal, parse_iso_date
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
    elif data.startswith("rcpt_editfield_"):
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
            from services.parser import CATEGORY_KEYWORDS
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
            # Tampilkan pilihan bulan (mirip tgl_{tx_id})
            WIB = timezone(timedelta(hours=7))
            now = datetime.now(WIB)
            from utils.formatter import BULAN
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
    elif data.startswith("rcpt_tglbulan_"):
        parts = data.split("_")
        idx = int(parts[2])
        year = int(parts[3])
        month = int(parts[4])
        import calendar
        _, days_in_month = calendar.monthrange(year, month)
        from utils.formatter import BULAN
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
    elif data.startswith("rcpt_tglset_"):
        parts = data.split("_")
        idx = int(parts[2])
        year = int(parts[3])
        month = int(parts[4])
        day = int(parts[5])
        items = context.user_data.get("pending_receipt", [])
        if idx < len(items):
            from datetime import date as _date
            items[idx]["date"] = _date(year, month, day).strftime("%Y-%m-%d")
            context.user_data["pending_receipt"] = items
            from handlers.transaction import _render_receipt_preview
            _title = context.user_data.get("pending_receipt_title")
            msg, kb = _render_receipt_preview(items, title=_title) if _title else _render_receipt_preview(items)
            await query.message.edit_text(msg, parse_mode="HTML", reply_markup=kb)
    elif data.startswith("rcpt_editset_"):
        parts = data.split("_", 4)  # ["rcpt", "editset", "{idx}", "{field}", "{value}"]
        idx = int(parts[2])
        field = parts[3]
        value = parts[4]
        items = context.user_data.get("pending_receipt", [])
        if idx < len(items):
            items[idx][field] = value
            context.user_data["pending_receipt"] = items
            from handlers.transaction import _render_receipt_preview
            _title = context.user_data.get("pending_receipt_title")
            msg, kb = _render_receipt_preview(items, title=_title) if _title else _render_receipt_preview(items)
            await query.message.edit_text(msg, parse_mode="HTML", reply_markup=kb)
    elif data == "rcpt_back_preview":
        items = context.user_data.get("pending_receipt", [])
        if items:
            from handlers.transaction import _render_receipt_preview
            _title = context.user_data.get("pending_receipt_title")
            msg, kb = _render_receipt_preview(items, title=_title) if _title else _render_receipt_preview(items)
            await query.message.edit_text(msg, parse_mode="HTML", reply_markup=kb)

    elif data == "cmd_export":
        await _send_export(query.message, user_id, edit=True)
    elif data.startswith("doexport_"):
        # Format: doexport_YYYY_MM
        parts = data.split("_")
        year = int(parts[1])
        month = int(parts[2])
        await _do_export(query.message, user_id, year, month)
    elif data.startswith("edittx_"):
        # Format: edittx_{year}_{month}_{page}
        parts = data.split("_")
        year = int(parts[1])
        month = int(parts[2])
        page = int(parts[3])

        from utils.formatter import parse_iso_date, format_tanggal, BULAN
        from handlers.report import MONTH_NAMES

        per_page = 5
        txs = get_month_transactions(user_id, year, month)
        month_name = MONTH_NAMES.get(month, str(month))

        if not txs:
            await _safe_edit_or_reply(
                query.message,
                f"✏️ <b>Edit Transaksi — {month_name} {year}</b>\n\n"
                f"<i>Belum ada transaksi.</i>",
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
            buttons.append([InlineKeyboardButton(label, callback_data=f"edit_{tx['id']}")])

        # Pagination buttons
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
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
                ]),
            )
    elif data.startswith("editfield_"):
        # User memilih field untuk diedit
        parts = data.split("_")
        tx_id = int(parts[1])
        field = parts[2]

        if field == "type":
            # Tampilkan tombol masuk/keluar langsung
            await query.message.edit_text(
                f"🔄 <b>Ubah Tipe</b> — Transaksi <code>#{tx_id}</code>\n\n"
                f"Pilih tipe baru 👇",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("💰 Masuk", callback_data=f"editset_{tx_id}_type_masuk"),
                        InlineKeyboardButton("💸 Keluar", callback_data=f"editset_{tx_id}_type_keluar"),
                    ],
                    [
                        InlineKeyboardButton("⬅️ Kembali", callback_data=f"edit_{tx_id}"),
                    ],
                ]),
            )
        elif field == "category":
            # Tampilkan grid tombol kategori
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
                f"🗂️ <b>Ubah Kategori</b> — Transaksi <code>#{tx_id}</code>\n\n"
                f"Pilih kategori baru 👇",
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
                f"✏️ <b>Edit {label}</b> — Transaksi <code>#{tx_id}</code>\n\n"
                f"{hint}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Batal", callback_data=f"canceledit_{tx_id}")],
                ]),
            )
    elif data.startswith("editset_"):
        # Edit langsung via tombol (type & category)
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
            if field == "type":
                new_display = "Pemasukan" if value == "masuk" else "Pengeluaran"
            else:
                new_display = value

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
    elif data.startswith("canceledit_"):
        # Batal edit → clear state, kembali ke transaksi
        tx_id = int(data.split("_")[1])
        context.user_data.pop("edit_state", None)
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
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
                ]),
            )
    elif data.startswith("back_"):
        # Kembali ke konfirmasi transaksi
        tx_id = int(data.split("_")[1])
        context.user_data.pop("edit_state", None)
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
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
                ]),
            )
    elif data.startswith("hapus_"):
        # Tampilkan konfirmasi dulu, belum hapus
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
    elif data.startswith("konfirmhapus_"):
        # User sudah konfirmasi → (soft) hapus sekarang
        tx_id = int(data.split("_")[1])
        tx = get_transaction_by_id(tx_id, user_id)
        if tx:
            success = delete_transaction(tx_id, user_id)
            if success:
                msg = await query.message.edit_text(
                    f"🗑️ Transaksi <code>#{tx_id}</code> berhasil dihapus.\n\n"
                    f"💸 {tx['description']} — {format_rupiah(tx['amount'])}",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("↩️ Batal (Undo)", callback_data=f"undel_{tx_id}")],
                        [
                            InlineKeyboardButton("📊 Lihat Hari Ini", callback_data="cmd_hariini"),
                            InlineKeyboardButton("🏠 Menu", callback_data="cmd_start"),
                        ],
                    ]),
                )
                
                # Schedule removal of undo button after 30 seconds
                async def remove_undo(context_arg: ContextTypes.DEFAULT_TYPE):
                    try:
                        await msg.edit_reply_markup(
                            reply_markup=InlineKeyboardMarkup([
                                [
                                    InlineKeyboardButton("📊 Lihat Hari Ini", callback_data="cmd_hariini"),
                                    InlineKeyboardButton("🏠 Menu", callback_data="cmd_start"),
                                ],
                            ])
                        )
                    except Exception:
                        pass
                
                context.job_queue.run_once(remove_undo, 30.0)
            else:
                await query.message.edit_text(
                    "❌ Gagal menghapus transaksi.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
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
    elif data.startswith("undel_"):
        tx_id = int(data.split("_")[1])
        # Restore transaction
        from services.database import restore_transaction
        success = restore_transaction(tx_id, user_id)
        if success:
            tx = get_transaction_by_id(tx_id, user_id)
            from utils.formatter import tx_confirmation_message
            await query.message.edit_text(
                tx_confirmation_message(tx),
                parse_mode="HTML",
                reply_markup=after_tx_keyboard(tx_id)
            )
        else:
            await query.message.edit_text(
                "❌ Gagal memulihkan transaksi.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
                ]),
            )
    elif data.startswith("tgl_"):
        # Tampilkan pilihan bulan untuk ubah tanggal
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

        WIB = timezone(timedelta(hours=7))
        now = datetime.now(WIB)

        # Tampilkan 6 bulan terakhir
        from utils.formatter import BULAN
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
    elif data.startswith("tglbulan_"):
        # User pilih bulan → tampilkan grid tanggal
        parts = data.split("_")
        tx_id = int(parts[1])
        year = int(parts[2])
        month = int(parts[3])

        import calendar
        _, days_in_month = calendar.monthrange(year, month)

        from utils.formatter import BULAN
        month_name = BULAN.get(month, str(month))

        # Grid tanggal 7 kolom
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
            f"📅 <b>Pilih Tanggal — {month_name} {year}</b>\n\n"
            f"Ketuk tanggal yang diinginkan 👇",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    elif data.startswith("tglset_"):
        # User pilih tanggal → update created_at
        parts = data.split("_")
        tx_id = int(parts[1])
        year = int(parts[2])
        month = int(parts[3])
        day = int(parts[4])

        WIB = timezone(timedelta(hours=7))
        new_date = datetime(year, month, day, 12, 0, 0, tzinfo=WIB)

        success = update_transaction_date(tx_id, user_id, new_date)
        if success:
            from utils.formatter import format_tanggal
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
