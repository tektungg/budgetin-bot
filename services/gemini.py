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

Contoh jika struk dari Alfamart total 45.500:
{
  "transactions": [
    {
      "type": "keluar",
      "amount": 45500,
      "category": "Belanja",
      "description": "Belanja Alfamart"
    }
  ]
}

Contoh jika ada kembalian/uang masuk:
Jangan catat kembalian sebagai transaksi masuk.
Hanya catat nominal yang benar-benar dibayar.

Kembalikan HANYA JSON valid, tidak ada teks lain.
Format:
{
  "transactions": [
    {
      "type": "keluar" | "masuk",
      "amount": 50000,
      "category": "...",
      "description": "..."
    }
  ],
  "merchant": "nama merchant (jika ada)",
  "date": "tanggal pada struk (jika ada, format YYYY-MM-DD)",
  "confidence": "high" | "medium" | "low"
}
"""


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

        # Validasi
        valid = []
        for tx in transactions:
            if tx.get("type") in ("masuk", "keluar") and tx.get("amount", 0) > 0:
                valid.append({
                    "type": tx["type"],
                    "amount": int(tx["amount"]),
                    "category": tx.get("category", "Lainnya"),
                    "description": tx.get("description", "Dari struk"),
                })

        logger.info(f"Gemini extracted {len(valid)} transactions from receipt")
        return valid if valid else None

    except json.JSONDecodeError as e:
        logger.error(f"Gemini returned invalid JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return None
