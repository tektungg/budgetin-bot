"""
Handler umum: /start, /help, /hapus, /edit
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from services.database import delete_transaction, update_transaction, get_transaction_by_id
from services.parser import parse_amount, detect_category, format_rupiah
from utils.auth import require_auth

logger = logging.getLogger(__name__)

HELP_TEXT = """
<b>💰 Budgetin Bot — Panduan Penggunaan</b>

<b>📝 Catat Transaksi (ketik biasa):</b>
• <code>keluar makan siang 25k</code>
• <code>keluar grab 15000</code>
• <code>keluar belanja alfamart 87.5rb</code>
• <code>masuk gaji 3jt</code>
• <code>masuk freelance desain logo 500rb</code>
• <code>masuk transfer dari kakak 200k</code>

<b>📸 Foto Struk:</b>
Kirim foto struk/nota → dicatat otomatis

<b>📊 Laporan:</b>
• /hariini — transaksi hari ini
• /bulanini — ringkasan bulan ini
• /bulanini 1 2025 — bulan & tahun tertentu
• /kategori — ringkasan per kategori
• /export — export ke Google Sheets

<b>✏️ Edit & Hapus:</b>
• /hapus [id] — hapus transaksi
  Contoh: <code>/hapus 42</code>
• /edit [id] [field] [nilai] — ubah transaksi
  Contoh: <code>/edit 42 amount 30000</code>
  Contoh: <code>/edit 42 category Transportasi</code>
  Contoh: <code>/edit 42 description grab ke kantor</code>

<b>💡 Format Nominal:</b>
5000 = 5k = 5rb = 5ribu → Rp 5.000
2000000 = 2m = 2jt = 2juta → Rp 2.000.000
"""

START_TEXT = """
👋 Halo! Saya <b>Budgetin Bot</b> — asisten pencatat keuangan pribadimu.

Langsung ketik transaksi kamu, contoh:
• <code>keluar makan 25k</code>
• <code>masuk gaji 3jt</code>
• Atau kirim <b>foto struk</b> 📸

Ketik /help untuk panduan lengkap.
"""


@require_auth
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(START_TEXT, parse_mode="HTML")


@require_auth
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="HTML")


@require_auth
async def cmd_hapus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hapus transaksi berdasarkan ID"""
    user_id = update.effective_user.id
    args = context.args

    if not args:
        await update.message.reply_text(
            "Gunakan: /hapus [id]\nContoh: <code>/hapus 42</code>\n\n"
            "ID transaksi terlihat di laporan dalam format [#42]",
            parse_mode="HTML",
        )
        return

    try:
        tx_id = int(args[0].lstrip("#"))
    except ValueError:
        await update.message.reply_text("ID harus berupa angka. Contoh: /hapus 42")
        return

    tx = get_transaction_by_id(tx_id, user_id)
    if not tx:
        await update.message.reply_text(f"Transaksi #{tx_id} tidak ditemukan.")
        return

    success = delete_transaction(tx_id, user_id)
    if success:
        tipe = "pemasukan" if tx["type"] == "masuk" else "pengeluaran"
        await update.message.reply_text(
            f"🗑️ Transaksi #{tx_id} dihapus.\n"
            f"{tx['description']} — {format_rupiah(tx['amount'])} ({tipe})"
        )
    else:
        await update.message.reply_text("Gagal menghapus transaksi.")


@require_auth
async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Edit transaksi: /edit [id] [field] [nilai]"""
    user_id = update.effective_user.id
    args = context.args

    if len(args) < 3:
        await update.message.reply_text(
            "Gunakan: /edit [id] [field] [nilai]\n\n"
            "Field yang bisa diubah:\n"
            "• <code>amount</code> — nominal (contoh: 30000 atau 30k)\n"
            "• <code>category</code> — kategori\n"
            "• <code>description</code> — deskripsi\n"
            "• <code>type</code> — masuk atau keluar\n\n"
            "Contoh: <code>/edit 42 amount 30k</code>",
            parse_mode="HTML",
        )
        return

    try:
        tx_id = int(args[0].lstrip("#"))
    except ValueError:
        await update.message.reply_text("ID harus berupa angka.")
        return

    field = args[1].lower()
    value_raw = " ".join(args[2:])

    allowed_fields = {"amount", "category", "description", "type"}
    if field not in allowed_fields:
        await update.message.reply_text(
            f"Field tidak valid. Gunakan: {', '.join(allowed_fields)}"
        )
        return

    # Konversi nilai sesuai field
    if field == "amount":
        value = parse_amount(value_raw)
        if not value:
            await update.message.reply_text("Format nominal tidak valid.")
            return
    elif field == "type":
        if value_raw not in ("masuk", "keluar"):
            await update.message.reply_text("Tipe harus 'masuk' atau 'keluar'.")
            return
        value = value_raw
    else:
        value = value_raw

    tx = get_transaction_by_id(tx_id, user_id)
    if not tx:
        await update.message.reply_text(f"Transaksi #{tx_id} tidak ditemukan.")
        return

    success = update_transaction(tx_id, user_id, **{field: value})
    if success:
        await update.message.reply_text(
            f"✅ Transaksi #{tx_id} diperbarui.\n"
            f"<b>{field}</b> → <code>{value_raw}</code>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("Gagal memperbarui transaksi.")
