"""
Handler untuk laporan keuangan — dengan layout bersih & inline keyboard
"""

import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.database import (
    get_today_transactions,
    get_month_transactions,
    get_category_summary,
    get_available_months,
    search_transactions,
)
from services.export import generate_excel, build_export_caption, MONTH_NAMES as EXPORT_MONTH_NAMES
from services.parser import format_rupiah
from utils.auth import require_auth
from utils.formatter import build_transaction_list, format_tanggal, parse_iso_date
from handlers.general import report_keyboard, _safe_edit_or_reply

logger = logging.getLogger(__name__)

MONTH_NAMES = {
    1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
    5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
    9: "September", 10: "Oktober", 11: "November", 12: "Desember",
}


def _summary_stats(transactions: list[dict]) -> tuple[int, int, int]:
    total_masuk = sum(t["amount"] for t in transactions if t["type"] == "masuk")
    total_keluar = sum(t["amount"] for t in transactions if t["type"] == "keluar")
    return total_masuk, total_keluar, total_masuk - total_keluar


def _build_summary_block(total_masuk: int, total_keluar: int, saldo: int) -> str:
    """Block ringkasan keuangan yang konsisten"""
    saldo_emoji = "📈" if saldo >= 0 else "📉"
    saldo_label = "Surplus" if saldo >= 0 else "Defisit"
    return (
        f"┌ 💰 Pemasukan   <b>{format_rupiah(total_masuk)}</b>\n"
        f"├ 💸 Pengeluaran <b>{format_rupiah(total_keluar)}</b>\n"
        f"└ {saldo_emoji} {saldo_label}      <b>{format_rupiah(abs(saldo))}</b>"
    )


# ── Shared logic (dipanggil dari command & callback) ───

async def _send_hari_ini(message, user_id: int, edit: bool = False):
    """Logic laporan hari ini — reusable dari command & callback"""
    txs = get_today_transactions(user_id)

    now = datetime.now()
    date_str = format_tanggal(now)
    kb = report_keyboard(now.year, now.month)

    if not txs:
        text = (
            f"📊 <b>Laporan Hari Ini</b>\n"
            f"📅 {date_str}\n\n"
            f"<i>Belum ada transaksi hari ini.</i>\n\n"
            f"💡 Ketik transaksi untuk mulai mencatat!"
        )
        if edit:
            await _safe_edit_or_reply(message, text, parse_mode="HTML", reply_markup=kb)
        else:
            await message.reply_text(text, parse_mode="HTML", reply_markup=kb)
        return

    total_masuk, total_keluar, saldo = _summary_stats(txs)

    lines = [
        f"📊 <b>Laporan Hari Ini</b>",
        f"📅 {date_str}  •  {len(txs)} transaksi\n",
        _build_summary_block(total_masuk, total_keluar, saldo),
        f"\n{'─' * 30}\n",
        build_transaction_list(txs),
    ]

    text = "\n".join(lines)
    if edit:
        await _safe_edit_or_reply(message, text, parse_mode="HTML", reply_markup=kb)
    else:
        await message.reply_text(text, parse_mode="HTML", reply_markup=kb)


async def _send_pilih_bulan(message, user_id: int, edit: bool = False):
    """Tampilkan pilihan bulan yang tersedia untuk dilihat ringkasannya"""
    months = get_available_months(user_id)

    now = datetime.now()
    current_key = (now.year, now.month)
    current_name = MONTH_NAMES.get(now.month, "")

    # Pastikan bulan ini selalu muncul di atas
    has_current = any(m["year"] == now.year and m["month"] == now.month for m in months)

    buttons = []
    # Tombol bulan ini selalu di atas
    buttons.append([InlineKeyboardButton(
        f"📅 {current_name} {now.year} (Bulan Ini)",
        callback_data=f"viewbulan_{now.year}_{now.month}",
    )])

    # Bulan lain yang ada datanya
    for m in months:
        if (m["year"], m["month"]) == current_key:
            continue  # sudah ditampilkan di atas
        month_name = MONTH_NAMES.get(m["month"], str(m["month"]))
        label = f"{month_name} {m['year']}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"viewbulan_{m['year']}_{m['month']}")])

    buttons.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")])

    text = "📅 <b>Laporan Bulanan</b>\n\nPilih bulan yang ingin dilihat 👇"
    keyboard = InlineKeyboardMarkup(buttons)

    if edit and message.text:
        await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


async def _send_bulan_ini(
    message, user_id: int, year: int = None, month: int = None, edit: bool = False
):
    """Logic laporan bulanan — reusable"""
    now = datetime.now()
    year = year or now.year
    month = month or now.month

    txs = get_month_transactions(user_id, year, month)
    month_name = MONTH_NAMES.get(month, str(month))
    kb = report_keyboard(year, month)

    if not txs:
        text = (
            f"📅 <b>Laporan {month_name} {year}</b>\n\n"
            f"<i>Belum ada transaksi bulan ini.</i>"
        )
        if edit:
            await _safe_edit_or_reply(message, text, parse_mode="HTML", reply_markup=kb)
        else:
            await message.reply_text(text, parse_mode="HTML", reply_markup=kb)
        return

    total_masuk, total_keluar, saldo = _summary_stats(txs)

    lines = [
        f"📅 <b>Laporan {month_name} {year}</b>",
        f"📝 {len(txs)} transaksi tercatat\n",
        _build_summary_block(total_masuk, total_keluar, saldo),
        f"\n{'─' * 30}\n",
        build_transaction_list(txs, limit=20),
    ]

    if len(txs) > 20:
        lines.append(f"\n<i>... dan {len(txs) - 20} transaksi lainnya</i>")

    text = "\n".join(lines)
    if edit:
        await _safe_edit_or_reply(message, text, parse_mode="HTML", reply_markup=kb)
    else:
        await message.reply_text(text, parse_mode="HTML", reply_markup=kb)


async def _send_kategori(
    message, user_id: int, year: int = None, month: int = None, edit: bool = False
):
    """Logic ringkasan kategori — reusable"""
    now = datetime.now()
    year = year or now.year
    month = month or now.month

    summary = get_category_summary(user_id, year, month)
    month_name = MONTH_NAMES.get(month, str(month))
    kb = report_keyboard(year, month)

    if not summary:
        text = (
            f"🗂️ <b>Kategori — {month_name} {year}</b>\n\n"
            f"<i>Belum ada transaksi.</i>"
        )
        if edit:
            await _safe_edit_or_reply(message, text, parse_mode="HTML", reply_markup=kb)
        else:
            await message.reply_text(text, parse_mode="HTML", reply_markup=kb)
        return

    keluar_rows = [r for r in summary if r["type"] == "keluar"]
    masuk_rows = [r for r in summary if r["type"] == "masuk"]

    lines = [
        f"🗂️ <b>Kategori — {month_name} {year}</b>\n",
    ]

    if masuk_rows:
        total_masuk = sum(r["total"] for r in masuk_rows)
        lines.append(f"💰 <b>PEMASUKAN</b>  ({format_rupiah(total_masuk)})")
        for row in masuk_rows:
            lines.append(f"   ├ {row['category']}: <b>{format_rupiah(row['total'])}</b> ({row['count']}x)")
        lines.append("")

    if keluar_rows:
        total_keluar = sum(r["total"] for r in keluar_rows)
        lines.append(f"💸 <b>PENGELUARAN</b>  ({format_rupiah(total_keluar)})")
        for i, row in enumerate(keluar_rows):
            pct = int(row["total"] / total_keluar * 100) if total_keluar > 0 else 0
            bar_len = max(1, pct // 10)
            bar = "█" * bar_len + "░" * (10 - bar_len)
            prefix = "└" if i == len(keluar_rows) - 1 else "├"
            lines.append(
                f"   {prefix} {row['category']}\n"
                f"     {bar} <b>{format_rupiah(row['total'])}</b> ({pct}%)"
            )

    text = "\n".join(lines)
    if edit:
        await _safe_edit_or_reply(message, text, parse_mode="HTML", reply_markup=kb)
    else:
        await message.reply_text(text, parse_mode="HTML", reply_markup=kb)


async def _send_export(message, user_id: int, edit: bool = False):
    """Tampilkan pilihan bulan yang tersedia untuk export"""
    months = get_available_months(user_id)

    if not months:
        text = "📤 <b>Export</b>\n\n<i>Belum ada transaksi untuk di-export.</i>"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
        ])
        if edit and message.text:
            await _safe_edit_or_reply(message, text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
        return

    # Buat tombol untuk setiap bulan yang ada datanya
    buttons = []
    row = []
    for m in months:
        month_name = MONTH_NAMES.get(m["month"], str(m["month"]))
        label = f"{month_name} {m['year']}"
        callback = f"doexport_{m['year']}_{m['month']}"
        row.append(InlineKeyboardButton(label, callback_data=callback))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")])

    text = "📤 <b>Export ke Excel</b>\n\nPilih bulan yang ingin di-export 👇"
    keyboard = InlineKeyboardMarkup(buttons)

    if edit and message.text:
        await _safe_edit_or_reply(message, text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


async def _do_export(message, user_id: int, year: int, month: int):
    """Export transaksi bulan tertentu ke file Excel"""
    month_name = MONTH_NAMES.get(month, str(month))
    txs = get_month_transactions(user_id, year, month)

    if not txs:
        await message.edit_text(
            f"📤 Tidak ada transaksi untuk {month_name} {year}.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Pilih Bulan Lain", callback_data="cmd_export")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )
        return

    # Loading state
    try:
        await message.edit_text("⏳ Menyiapkan file...")
        await message.delete()
    except Exception:
        pass

    # Generate & kirim Excel
    excel_file = generate_excel(txs, month_name, year)
    caption = build_export_caption(txs, month_name, year)

    await message.reply_document(
        document=excel_file,
        caption=caption,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Export Bulan Lain", callback_data="cmd_export")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
        ]),
    )


# ── Command Handlers (entry point dari /command) ───────

@require_auth
async def cmd_hari_ini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await _send_hari_ini(update.message, user_id)


@require_auth
async def cmd_bulan_ini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    year = datetime.now().year
    month = datetime.now().month

    if args:
        try:
            if len(args) >= 1:
                month = int(args[0])
            if len(args) >= 2:
                year = int(args[1])
        except ValueError:
            await update.message.reply_text(
                "⚠️ Format: <code>/bulanini [bulan] [tahun]</code>\n"
                "Contoh: <code>/bulanini 1 2025</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
                ]),
            )
            return

    await _send_bulan_ini(update.message, user_id, year, month)


@require_auth
async def cmd_kategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    year = datetime.now().year
    month = datetime.now().month

    if args:
        try:
            if len(args) >= 1:
                month = int(args[0])
            if len(args) >= 2:
                year = int(args[1])
        except ValueError:
            pass

    await _send_kategori(update.message, user_id, year, month)


@require_auth
async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if args:
        # Direct export jika user ketik /export bulan tahun
        year = datetime.now().year
        month = datetime.now().month
        try:
            if len(args) >= 1:
                month = int(args[0])
            if len(args) >= 2:
                year = int(args[1])
        except ValueError:
            pass

        month_name = MONTH_NAMES.get(month, str(month))
        txs = get_month_transactions(user_id, year, month)
        if not txs:
            await update.message.reply_text(
                f"📤 Tidak ada transaksi untuk {month_name} {year}.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📤 Pilih Bulan Lain", callback_data="cmd_export")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
                ]),
            )
            return
        excel_file = generate_excel(txs, month_name, year)
        caption = build_export_caption(txs, month_name, year)
        await update.message.reply_document(
            document=excel_file,
            caption=caption,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Export Bulan Lain", callback_data="cmd_export")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )
    else:
        # Tampilkan pilihan bulan
        await _send_export(update.message, user_id)


@require_auth
async def cmd_cari(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /cari <keyword>"""
    user_id = update.effective_user.id
    args = context.args

    if not args:
        await update.message.reply_text(
            "🔍 <b>Cara pakai:</b>\n\n"
            "<code>/cari makan</code>\n"
            "<code>/cari grab</code>\n"
            "<code>/cari gaji</code>\n\n"
            "<i>Cari di deskripsi dan kategori transaksi.</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
            ]),
        )
        return

    keyword = " ".join(args)
    await _send_search(update.message, user_id, keyword)


async def _send_search(message, user_id: int, keyword: str, edit: bool = False):
    """Logic pencarian transaksi — reusable dari command & callback"""
    txs = search_transactions(user_id, keyword)

    if not txs:
        text = (
            f"🔍 <b>Hasil Pencarian</b>\n\n"
            f"Keyword: <code>{keyword}</code>\n\n"
            f"<i>Tidak ditemukan transaksi yang cocok.</i>"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start")],
        ])
        if edit:
            await _safe_edit_or_reply(message, text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
        return

    total_masuk, total_keluar, saldo = _summary_stats(txs)

    lines = [
        f"🔍 <b>Hasil Pencarian</b>",
        f"Keyword: <code>{keyword}</code>  •  {len(txs)} ditemukan\n",
        _build_summary_block(total_masuk, total_keluar, saldo),
        f"\n{'─' * 30}\n",
        build_transaction_list(txs),
    ]

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Hari Ini", callback_data="cmd_hariini"),
            InlineKeyboardButton("📅 Bulan Ini", callback_data="cmd_bulanini"),
        ],
        [
            InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start"),
        ],
    ])

    text = "\n".join(lines)
    if edit:
        await _safe_edit_or_reply(message, text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)

