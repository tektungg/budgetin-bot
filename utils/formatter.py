"""
Utility untuk format pesan Telegram
"""

from datetime import datetime, timezone, timedelta
from services.parser import format_rupiah

# Timezone WIB
WIB = timezone(timedelta(hours=7))


BULAN = {
    1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
    5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
    9: "September", 10: "Oktober", 11: "November", 12: "Desember",
}

BULAN_SHORT = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "Mei", 6: "Jun", 7: "Jul", 8: "Ags",
    9: "Sep", 10: "Okt", 11: "Nov", 12: "Des",
}

HARI = {
    0: "Senin", 1: "Selasa", 2: "Rabu", 3: "Kamis",
    4: "Jumat", 5: "Sabtu", 6: "Minggu",
}


def format_tanggal(dt: datetime, short: bool = False) -> str:
    """
    Format datetime ke tanggal Indonesia.
    short=False → "Sabtu, 22 Februari 2026"
    short=True  → "22 Feb"
    """
    if short:
        return f"{dt.day} {BULAN_SHORT.get(dt.month, '')}"
    hari = HARI.get(dt.weekday(), "")
    bulan = BULAN.get(dt.month, "")
    return f"{hari}, {dt.day} {bulan} {dt.year}"


def format_tanggal_waktu(dt: datetime) -> str:
    """Format datetime ke tanggal + waktu Indonesia: '22 Februari 2026, 14:30 WIB'"""
    bulan = BULAN.get(dt.month, "")
    return f"{dt.day} {bulan} {dt.year}, {dt.strftime('%H:%M')} WIB"


def parse_iso_date(iso_str: str) -> datetime | None:
    """Parse ISO date string dari Supabase ke datetime WIB"""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(WIB)
    except (ValueError, AttributeError):
        return None


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
        f"└ 🔖 <code>#{tx['user_tx_no']}</code>"
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
                dt = tx_date
            elif isinstance(tx_date, str):
                dt = parse_iso_date(tx_date)
            else:
                dt = None

            if dt:
                date_str = format_tanggal(dt, short=True)
                if date_str != current_date:
                    current_date = date_str
                    if lines:
                        lines.append("")
                    lines.append(f"<b>📅 {date_str}</b>")

        emoji = "💸" if tx["type"] == "keluar" else "💰"
        amount_str = format_rupiah(tx["amount"])
        raw_desc = tx.get("description", "")
        desc = raw_desc[:32] + "…" if len(raw_desc) > 35 else raw_desc
        tx_id = tx.get("user_tx_no", "")

        lines.append(f"  {emoji} {desc} — <b>{amount_str}</b>  <i>[#{tx_id}]</i>")

    return "\n".join(lines)
