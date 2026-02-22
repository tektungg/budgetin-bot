"""
Utility untuk format pesan Telegram
"""

from datetime import datetime
from services.parser import format_rupiah

MONTH_NAMES = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "Mei", 6: "Jun", 7: "Jul", 8: "Ags",
    9: "Sep", 10: "Okt", 11: "Nov", 12: "Des",
}


def tx_confirmation_message(tx: dict) -> str:
    """Pesan konfirmasi setelah transaksi dicatat"""
    emoji = "💸" if tx["type"] == "keluar" else "💰"
    tipe = "Pengeluaran" if tx["type"] == "keluar" else "Pemasukan"
    amount_str = format_rupiah(tx["amount"])

    return (
        f"{emoji} <b>{tipe} dicatat!</b>\n\n"
        f"📌 <b>{tx['description']}</b>\n"
        f"💵 {amount_str}\n"
        f"🗂️ {tx.get('category', 'Lainnya')}\n"
        f"🔖 ID: <code>#{tx['id']}</code>\n\n"
        f"<i>Ketik /hapus {tx['id']} untuk membatalkan</i>"
    )


def build_transaction_list(transactions: list[dict], limit: int = None) -> str:
    """Bangun daftar transaksi untuk ditampilkan"""
    if limit:
        display = transactions[:limit]
    else:
        display = transactions

    lines = []
    current_date = None

    for tx in display:
        # Group by date
        if tx.get("created_at"):
            tx_date = tx["created_at"]
            if hasattr(tx_date, "date"):
                date_str = tx_date.strftime("%d %b")
                if date_str != current_date:
                    current_date = date_str
                    lines.append(f"\n<b>📅 {date_str}</b>")

        emoji = "💸" if tx["type"] == "keluar" else "💰"
        amount_str = format_rupiah(tx["amount"])
        desc = tx.get("description", "")[:40]  # truncate panjang
        tx_id = tx.get("id", "")

        lines.append(f"{emoji} {desc} — <b>{amount_str}</b> <i>[#{tx_id}]</i>")

    return "\n".join(lines)
