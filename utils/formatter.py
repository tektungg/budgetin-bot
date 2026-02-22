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
    """Pesan konfirmasi setelah transaksi dicatat — layout bersih"""
    is_keluar = tx["type"] == "keluar"
    emoji = "💸" if is_keluar else "💰"
    tipe = "Pengeluaran" if is_keluar else "Pemasukan"
    amount_str = format_rupiah(tx["amount"])

    return (
        f"{emoji} <b>{tipe} Dicatat!</b>\n\n"
        f"┌ 📌 {tx['description']}\n"
        f"├ 💵 {amount_str}\n"
        f"├ 🗂️ {tx.get('category', 'Lainnya')}\n"
        f"└ 🔖 <code>#{tx['id']}</code>"
    )


def build_transaction_list(transactions: list[dict], limit: int = None) -> str:
    """Bangun daftar transaksi untuk ditampilkan — grouped by date"""
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
            elif isinstance(tx_date, str):
                # Parse ISO string dari Supabase
                try:
                    dt = datetime.fromisoformat(tx_date.replace("Z", "+00:00"))
                    date_str = dt.strftime("%d %b")
                except (ValueError, AttributeError):
                    date_str = None
            else:
                date_str = None

            if date_str and date_str != current_date:
                current_date = date_str
                if lines:
                    lines.append("")  # spacing antar tanggal
                lines.append(f"<b>📅 {date_str}</b>")

        emoji = "💸" if tx["type"] == "keluar" else "💰"
        amount_str = format_rupiah(tx["amount"])
        desc = tx.get("description", "")[:35]
        tx_id = tx.get("id", "")

        lines.append(f"  {emoji} {desc} — <b>{amount_str}</b>  <i>[#{tx_id}]</i>")

    return "\n".join(lines)
