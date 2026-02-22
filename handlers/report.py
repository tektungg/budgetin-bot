"""
Handler untuk laporan keuangan
"""

import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from services.database import (
    get_today_transactions,
    get_month_transactions,
    get_category_summary,
)
from services.sheets import export_to_sheets
from services.parser import format_rupiah
from utils.auth import require_auth
from utils.formatter import build_transaction_list

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


@require_auth
async def cmd_hari_ini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Laporan hari ini"""
    user_id = update.effective_user.id
    txs = get_today_transactions(user_id)

    now = datetime.now()
    title = f"📊 Laporan Hari Ini — {now.strftime('%d %B %Y')}"

    if not txs:
        await update.message.reply_text(f"{title}\n\nBelum ada transaksi hari ini.")
        return

    total_masuk, total_keluar, saldo = _summary_stats(txs)

    lines = [f"<b>{title}</b>\n"]
    lines.append(build_transaction_list(txs))
    lines.append(f"\n{'─' * 28}")
    lines.append(f"💰 Pemasukan  : <b>{format_rupiah(total_masuk)}</b>")
    lines.append(f"💸 Pengeluaran: <b>{format_rupiah(total_keluar)}</b>")
    saldo_emoji = "✅" if saldo >= 0 else "⚠️"
    lines.append(f"{saldo_emoji} Saldo       : <b>{format_rupiah(saldo)}</b>")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


@require_auth
async def cmd_bulan_ini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Laporan bulan ini (atau bulan tertentu: /bulanini 1 2025)"""
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
                "Format: /bulanini [bulan] [tahun]\nContoh: /bulanini 1 2025"
            )
            return

    txs = get_month_transactions(user_id, year, month)
    month_name = MONTH_NAMES.get(month, str(month))
    title = f"📊 Laporan {month_name} {year}"

    if not txs:
        await update.message.reply_text(f"{title}\n\nBelum ada transaksi bulan ini.")
        return

    total_masuk, total_keluar, saldo = _summary_stats(txs)

    lines = [f"<b>{title}</b>"]
    lines.append(f"Total {len(txs)} transaksi\n")
    lines.append(build_transaction_list(txs, limit=20))

    if len(txs) > 20:
        lines.append(f"\n<i>... dan {len(txs) - 20} transaksi lainnya</i>")

    lines.append(f"\n{'─' * 28}")
    lines.append(f"💰 Pemasukan  : <b>{format_rupiah(total_masuk)}</b>")
    lines.append(f"💸 Pengeluaran: <b>{format_rupiah(total_keluar)}</b>")
    saldo_emoji = "✅" if saldo >= 0 else "⚠️"
    lines.append(f"{saldo_emoji} Saldo       : <b>{format_rupiah(saldo)}</b>")
    lines.append(f"\n💡 Gunakan /kategori untuk ringkasan per kategori")
    lines.append(f"💡 Gunakan /export untuk export ke Google Sheets")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


@require_auth
async def cmd_kategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ringkasan per kategori bulan ini"""
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

    summary = get_category_summary(user_id, year, month)
    month_name = MONTH_NAMES.get(month, str(month))
    title = f"🗂️ Ringkasan Kategori — {month_name} {year}"

    if not summary:
        await update.message.reply_text(f"{title}\n\nBelum ada transaksi.")
        return

    keluar_rows = [r for r in summary if r["type"] == "keluar"]
    masuk_rows = [r for r in summary if r["type"] == "masuk"]

    lines = [f"<b>{title}</b>\n"]

    if masuk_rows:
        lines.append("💰 <b>PEMASUKAN</b>")
        for row in masuk_rows:
            lines.append(f"  {row['category']}: <b>{format_rupiah(row['total'])}</b> ({row['count']}x)")
        total_masuk = sum(r["total"] for r in masuk_rows)
        lines.append(f"  <i>Total: {format_rupiah(total_masuk)}</i>\n")

    if keluar_rows:
        lines.append("💸 <b>PENGELUARAN</b>")
        for row in keluar_rows:
            # Bar chart mini
            pct = int(row["total"] / sum(r["total"] for r in keluar_rows) * 10)
            bar = "█" * pct + "░" * (10 - pct)
            lines.append(
                f"  {row['category']}\n"
                f"  {bar} <b>{format_rupiah(row['total'])}</b> ({row['count']}x)"
            )
        total_keluar = sum(r["total"] for r in keluar_rows)
        lines.append(f"\n  <i>Total: {format_rupiah(total_keluar)}</i>")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


@require_auth
async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export ke Google Sheets"""
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

    txs = get_month_transactions(user_id, year, month)
    month_name = MONTH_NAMES.get(month, str(month))

    if not txs:
        await update.message.reply_text(f"Tidak ada transaksi untuk {month_name} {year}.")
        return

    await update.message.reply_text(f"⏳ Mengexport {len(txs)} transaksi ke Google Sheets...")

    sheet_name = f"{month_name} {year}"
    url = export_to_sheets(txs, sheet_name=sheet_name)

    if url:
        await update.message.reply_text(
            f"✅ Export berhasil!\n\n"
            f"📊 <b>{len(txs)} transaksi</b> {month_name} {year}\n"
            f"🔗 <a href='{url}'>Buka Google Sheets</a>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            "❌ Export gagal. Pastikan GOOGLE_SHEET_ID sudah diisi di .env "
            "dan service account sudah diberi akses ke spreadsheet."
        )
