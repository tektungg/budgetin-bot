"""
Parser untuk input teks natural dari pengguna.

Format yang didukung:
  keluar makan 5000
  keluar makan 5k
  keluar makan 5rb
  keluar makan 5jt
  masuk gaji 2000000
  masuk gaji 2m
  masuk gaji 2jt
  keluar transport grab 15.5k
  masuk freelance desain logo 500rb
"""

import re
import logging

logger = logging.getLogger(__name__)

# Kategori otomatis berdasarkan kata kunci
CATEGORY_KEYWORDS = {
    "Makanan & Minuman": [
        "makan", "minum", "kopi", "coffee", "lunch", "dinner", "breakfast",
        "sarapan", "siang", "malam", "snack", "jajan", "warung", "restoran",
        "cafe", "bakso", "nasi", "mi", "mie", "ayam", "soto", "gado",
        "indomie", "pizza", "burger", "kfc", "mcdo", "starbucks", "bubble",
    ],
    "Transportasi": [
        "grab", "gojek", "ojol", "taxi", "taksi", "bensin", "bbm", "parkir",
        "tol", "busway", "transjakarta", "mrt", "lrt", "kereta", "bus",
        "angkot", "ojek", "motor", "mobil", "uber",
    ],
    "Belanja": [
        "belanja", "beli", "shopee", "tokopedia", "lazada", "blibli",
        "alfamart", "indomaret", "hypermart", "carrefour", "supermarket",
        "minimarket", "pasar", "toko", "online",
    ],
    "Tagihan & Utilitas": [
        "listrik", "pln", "air", "pdam", "internet", "wifi", "indihome",
        "firstmedia", "biznet", "telkom", "pulsa", "paket data", "tagihan",
        "cicilan", "kredit", "token",
    ],
    "Kesehatan": [
        "dokter", "obat", "apotek", "klinik", "rumah sakit", "rs",
        "vitamin", "suplemen", "bpjs", "asuransi",
    ],
    "Hiburan": [
        "netflix", "spotify", "youtube", "game", "bioskop", "cinema",
        "hiburan", "nonton", "main",
    ],
    "Gaji & Pendapatan": [
        "gaji", "salary", "upah", "thr", "bonus",
    ],
    "Freelance": [
        "freelance", "proyek", "project", "klien", "client", "jasa",
    ],
    "Transfer": [
        "transfer", "tf", "kirim", "bagi", "bayar ke",
    ],
    "Investasi": [
        "investasi", "saham", "reksa dana", "crypto", "nabung", "tabungan",
    ],
}


def parse_amount(raw: str) -> int | None:
    """
    Konversi string nominal ke integer (rupiah).
    Contoh: '5k' → 5000, '2m' / '2jt' → 2000000, '15rb' → 15000
    """
    raw = raw.strip().lower().replace(",", ".").replace("_", "")

    multiplier = 1
    if raw.endswith(("rb", "ribu")):
        multiplier = 1_000
        raw = re.sub(r"(rb|ribu)$", "", raw)
    elif raw.endswith(("k",)):
        multiplier = 1_000
        raw = raw[:-1]
    elif raw.endswith(("jt", "juta", "m")):
        multiplier = 1_000_000
        raw = re.sub(r"(jt|juta|m)$", "", raw)
    elif raw.endswith(("b", "miliar", "mrd")):
        multiplier = 1_000_000_000
        raw = re.sub(r"(b|miliar|mrd)$", "", raw)

    try:
        return int(float(raw) * multiplier)
    except ValueError:
        return None


def detect_category(description: str) -> str:
    """Deteksi kategori otomatis dari deskripsi"""
    desc_lower = description.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in desc_lower:
                return category
    return "Lainnya"


def parse_date(text: str) -> tuple[str, "datetime | None"]:
    """
    Deteksi dan ekstrak tanggal dari akhir teks input.
    Format yang didukung: 15/3, 15/3/2025, 15-3, 15-3-2025
    Return (teks tanpa tanggal, datetime atau None).
    """
    from datetime import datetime, timezone, timedelta
    WIB = timezone(timedelta(hours=7))

    # Pattern tanggal di akhir teks: dd/mm, dd/mm/yyyy, dd-mm, dd-mm-yyyy
    date_pattern = re.compile(
        r"\s+(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?\s*$"
    )
    m = date_pattern.search(text)
    if not m:
        return text, None

    day = int(m.group(1))
    month = int(m.group(2))
    year_str = m.group(3)

    now = datetime.now(WIB)
    if year_str:
        year = int(year_str)
        if year < 100:
            year += 2000
    else:
        year = now.year

    try:
        dt = datetime(year, month, day, 12, 0, 0, tzinfo=WIB)  # Siang hari
        # Jangan terima tanggal di masa depan
        if dt.date() > now.date():
            return text, None
        clean_text = text[:m.start()].strip()
        return clean_text, dt
    except ValueError:
        return text, None


def parse_transaction(text: str) -> dict | None:
    """
    Parse teks natural menjadi data transaksi.
    Return dict {type, amount, category, description, date (optional)} atau None jika gagal.

    Mendukung tanggal opsional di akhir: keluar makan 25k 15/3
    """
    text = text.strip()
    lower = text.lower()

    # Tentukan tipe transaksi
    tx_type = None
    if lower.startswith(("keluar", "out", "bayar", "beli", "-")):
        tx_type = "keluar"
    elif lower.startswith(("masuk", "in", "terima", "dapat", "income", "+")):
        tx_type = "masuk"
    else:
        return None

    # Hapus prefix tipe
    prefixes = ["keluar", "masuk", "bayar", "beli", "terima", "dapat", "income", "out", "in"]
    for prefix in sorted(prefixes, key=len, reverse=True):
        if lower.startswith(prefix):
            text = text[len(prefix):].strip()
            break

    # Deteksi tanggal di akhir teks (sebelum parse nominal)
    text, tx_date = parse_date(text)

    # Cari nominal: pola angka (dengan opsional desimal dan suffix)
    # Contoh cocok: 5000, 5k, 5.5k, 2jt, 15rb, 1.5m
    amount_pattern = re.compile(
        r"(\d+(?:[.,]\d+)?(?:k|rb|ribu|jt|juta|m|b|miliar|mrd)?)",
        re.IGNORECASE,
    )

    match = None
    amount = None
    for m in amount_pattern.finditer(text):
        parsed = parse_amount(m.group(1))
        if parsed and parsed >= 100:  # minimal 100 rupiah
            match = m
            amount = parsed
            break

    if not amount:
        return None

    # Deskripsi = semua teks KECUALI nominal
    before = text[: match.start()].strip()
    after = text[match.end() :].strip()
    description = " ".join(filter(None, [before, after])).strip()
    if not description:
        description = "Tidak ada keterangan"

    category = detect_category(description)

    result = {
        "type": tx_type,
        "amount": amount,
        "category": category,
        "description": description,
    }
    if tx_date:
        result["date"] = tx_date

    return result


def format_amount(amount: int) -> str:
    """Format integer ke string rupiah yang readable"""
    if amount >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.1f}M".rstrip("0").rstrip(".")
    if amount >= 1_000_000:
        val = amount / 1_000_000
        return f"Rp {val:.1f}jt".replace(".0jt", "jt")
    if amount >= 1_000:
        val = amount / 1_000
        return f"Rp {val:.1f}rb".replace(".0rb", "rb")
    return f"Rp {amount:,}"


def format_rupiah(amount: int) -> str:
    """Format ke Rp 1.000.000"""
    return f"Rp {amount:,.0f}".replace(",", ".")
