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
)
from services.export import generate_excel, build_export_caption, MONTH_NAMES as EXPORT_MONTH_NAMES
from services.parser import format_rupiah
from utils.auth import require_auth
from utils.formatter import build_transaction_list, format_tanggal, parse_iso_date
from handlers.general import report_keyboard

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

    if not txs:
        text = (
            f"📊 <b>Laporan Hari Ini</b>\n"
            f"📅 {date_str}\n\n"
            f"<i>Belum ada transaksi hari ini.</i>\n\n"
            f"💡 Ketik transaksi untuk mulai mencatat!"
        )
        if edit:
            await message.edit_text(text, parse_mode="HTML", reply_markup=report_keyboard())
        else:
            await message.reply_text(text, parse_mode="HTML", reply_markup=report_keyboard())
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
        await message.edit_text(text, parse_mode="HTML", reply_markup=report_keyboard())
    else:
        await message.reply_text(text, parse_mode="HTML", reply_markup=report_keyboard())


async def _send_bulan_ini(
    message, user_id: int, year: int = None, month: int = None, edit: bool = False
):
    """Logic laporan bulanan — reusable"""
    now = datetime.now()
    year = year or now.year
    month = month or now.month

    txs = get_month_transactions(user_id, year, month)
    month_name = MONTH_NAMES.get(month, str(month))

    if not txs:
        text = (
            f"📅 <b>Laporan {month_name} {year}</b>\n\n"
            f"<i>Belum ada transaksi bulan ini.</i>"
        )
        if edit:
            await message.edit_text(text, parse_mode="HTML", reply_markup=report_keyboard())
        else:
            await message.reply_text(text, parse_mode="HTML", reply_markup=report_keyboard())
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
        await message.edit_text(text, parse_mode="HTML", reply_markup=report_keyboard())
    else:
        await message.reply_text(text, parse_mode="HTML", reply_markup=report_keyboard())


async def _send_kategori(
    message, user_id: int, year: int = None, month: int = None, edit: bool = False
):
    """Logic ringkasan kategori — reusable"""
    now = datetime.now()
    year = year or now.year
    month = month or now.month

    summary = get_category_summary(user_id, year, month)
    month_name = MONTH_NAMES.get(month, str(month))

    if not summary:
        text = (
            f"🗂️ <b>Kategori — {month_name} {year}</b>\n\n"
            f"<i>Belum ada transaksi.</i>"
        )
        if edit:
            await message.edit_text(text, parse_mode="HTML", reply_markup=report_keyboard())
        else:
            await message.reply_text(text, parse_mode="HTML", reply_markup=report_keyboard())
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

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅 Bulan Ini", callback_data="cmd_bulanini"),
            InlineKeyboardButton("📤 Export", callback_data="cmd_export"),
        ],
        [
            InlineKeyboardButton("🏠 Menu Utama", callback_data="cmd_start"),
        ],
    ])

    text = "\n".join(lines)
    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


async def _send_export(message, user_id: int, year: int = None, month: int = None, edit: bool = False):
    """Export transaksi ke file CSV → kirim ke chat"""
    now = datetime.now()
    year = year or now.year
    month = month or now.month

    txs = get_month_transactions(user_id, year, month)
    month_name = MONTH_NAMES.get(month, str(month))

    if not txs:
        text = f"📤 Tidak ada transaksi untuk {month_name} {year}."
        if edit:
            await message.edit_text(text, reply_markup=report_keyboard())
        else:
            await message.reply_text(text, reply_markup=report_keyboard())
        return

    # Generate Excel
    excel_file = generate_excel(txs, month_name, year)
    caption = build_export_caption(txs, month_name, year)

    # Hapus pesan loading jika dari callback
    if edit:
        try:
            await message.edit_text("⏳ Menyiapkan file...")
            await message.delete()
        except Exception:
            pass

    # Kirim file Excel ke chat
    await message.reply_document(
        document=excel_file,
        caption=caption,
        parse_mode="HTML",
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

    await _send_export(update.message, user_id, year, month)
