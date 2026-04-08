"""
Gemini service untuk menganalisis foto struk belanja.
Menggunakan Google Gemini Vision API (gratis tier generous).
"""

import logging
import json
import re
import google.generativeai as genai
from PIL import Image
import io
from config.settings import settings

logger = logging.getLogger(__name__)

genai.configure(api_key=settings.GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

STRUK_PROMPT = """
Kamu adalah asisten pencatat keuangan. Analisis gambar struk/nota/bukti pembayaran ini.

Ekstrak semua transaksi yang ada. Untuk setiap transaksi, tentukan:
1. type: "keluar" (pembayaran/belanja) atau "masuk" (penerimaan/pendapatan)
2. amount: nominal dalam integer rupiah (tanpa titik/koma)
3. category: kategori yang paling sesuai dari:
   Makanan & Minuman, Transportasi, Belanja, Tagihan & Utilitas,
   Kesehatan, Hiburan, Gaji & Pendapatan, Freelance, Transfer, Investasi, Lainnya
4. description: deskripsi singkat transaksi

Jika ada beberapa item dalam satu struk (misal struk belanja supermarket),
GABUNGKAN menjadi SATU transaksi dengan total keseluruhan dan description berisi nama toko/merchant.

Deteksi tanggal pada struk — cari di seluruh area gambar dengan berbagai format:
- DD/MM/YYYY atau DD-MM-YYYY (contoh: 08/04/2026, 08-04-2026)
- DD MMM YYYY atau DD MMMM YYYY (contoh: 08 Apr 2026, 08 April 2026)
- YYYY-MM-DD atau YYYY/MM/DD (contoh: 2026-04-08)
- Timestamp (contoh: 2026-04-08 14:30:00 → ambil tanggalnya saja)
- Format pendek DD/MM atau DD-MM (asumsikan tahun sekarang)
- Label seperti "Tgl:", "Date:", "Tanggal:", "Waktu:", "Printed:" sebelum angka tanggal
Jika tanggal ditemukan, konversi ke format YYYY-MM-DD. Jika tidak ada → null.

Contoh jika struk dari Alfamart total 45.500 tanggal 8 April 2026:
{
  "transactions": [{"type": "keluar", "amount": 45500, "category": "Belanja", "description": "Belanja Alfamart"}],
  "merchant": "Alfamart",
  "date": "2026-04-08",
  "confidence": "high"
}

Jangan catat kembalian sebagai transaksi masuk.
Kembalikan HANYA JSON valid, tidak ada teks lain.
Format:
{
  "transactions": [
    {"type": "keluar" | "masuk", "amount": 50000, "category": "...", "description": "..."}
  ],
  "merchant": "nama merchant (jika ada)",
  "date": "YYYY-MM-DD atau null",
  "confidence": "high" | "medium" | "low"
}
"""


TEXT_MULTI_PROMPT = """
Kamu adalah asisten pencatat keuangan. Parse setiap baris teks berikut sebagai transaksi terpisah.

Aturan parsing:
- Prefix "keluar/bayar/beli/out/-" → type: "keluar"
- Prefix "masuk/terima/dapat/in/+" → type: "masuk"
- Nominal: angka + suffix k/rb/ribu/jt/juta/m/b (contoh: 5k=5000, 2jt=2000000, 15rb=15000)
- Tanggal: DD/MM/YYYY, DD/MM, "tgl N", "kemarin", "hari ini" → format ISO 8601 (YYYY-MM-DD)
- Jika tidak ada tanggal → gunakan tanggal hari ini ({today})
- Kategori harus salah satu dari:
  Makanan & Minuman, Transportasi, Belanja, Tagihan & Utilitas,
  Kesehatan, Hiburan, Gaji & Pendapatan, Freelance, Transfer, Investasi, Lainnya
- Deskripsi: nama item/keterangan transaksi (tanpa prefix keluar/masuk dan tanpa nominal/tanggal)
- Abaikan baris kosong
- Hari ini: {today}

Kembalikan HANYA JSON array valid (tanpa markdown, tanpa teks lain):
[
  {{"type": "keluar", "amount": 63000, "category": "Belanja", "description": "Shopee Food dan sabun kime", "date": "2026-04-02"}},
  {{"type": "masuk", "amount": 250000, "category": "Freelance", "description": "Freelance", "date": "2026-04-05"}}
]

Teks transaksi:
{text}
"""


async def analyze_text_transactions(text: str) -> list[dict] | None:
    """
    Parse teks multi-baris menjadi list transaksi menggunakan Gemini.
    Return list of transaction dicts atau None jika gagal.
    """
    from datetime import date
    try:
        today = date.today().strftime("%Y-%m-%d")
        prompt = TEXT_MULTI_PROMPT.format(text=text, today=today)
        response = model.generate_content(prompt)
        raw = response.text.strip()

        # Bersihkan jika ada markdown code block
        raw = re.sub(r"```(?:json)?", "", raw).strip()

        transactions = json.loads(raw)
        if not isinstance(transactions, list):
            logger.error("Gemini text response is not a list")
            return None

        valid = []
        for tx in transactions:
            if tx.get("type") in ("masuk", "keluar") and tx.get("amount", 0) > 0:
                valid.append({
                    "type": tx["type"],
                    "amount": int(tx["amount"]),
                    "category": tx.get("category", "Lainnya"),
                    "description": tx.get("description", "Transaksi"),
                    "date": tx.get("date") or today,
                })

        logger.info(f"Gemini parsed {len(valid)} transactions from text")
        return valid if valid else None

    except json.JSONDecodeError as e:
        logger.error(f"Gemini text returned invalid JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Gemini text analysis error: {e}")
        return None


async def analyze_receipt(image_bytes: bytes) -> list[dict] | None:
    """
    Analisis foto struk menggunakan Gemini Vision.
    Return list of transaction dicts atau None jika gagal.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))

        response = model.generate_content([STRUK_PROMPT, image])
        raw = response.text.strip()

        # Bersihkan jika ada markdown code block
        raw = re.sub(r"```(?:json)?", "", raw).strip()

        data = json.loads(raw)
        transactions = data.get("transactions", [])
        receipt_date = data.get("date") or None  # YYYY-MM-DD atau None

        # Validasi
        valid = []
        for tx in transactions:
            if tx.get("type") in ("masuk", "keluar") and tx.get("amount", 0) > 0:
                valid.append({
                    "type": tx["type"],
                    "amount": int(tx["amount"]),
                    "category": tx.get("category", "Lainnya"),
                    "description": tx.get("description", "Dari struk"),
                    "date": receipt_date,
                })

        logger.info(f"Gemini extracted {len(valid)} transactions from receipt")
        return valid if valid else None

    except json.JSONDecodeError as e:
        logger.error(f"Gemini returned invalid JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return None
