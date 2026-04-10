"""
AI service untuk menganalisis foto struk belanja menggunakan Groq (gratis, cepat).
Model: llama-3.2-11b-vision-preview
"""

import base64
import io
import logging
import json
import re
from PIL import Image
from groq import AsyncGroq
from config.settings import settings

logger = logging.getLogger(__name__)

client = AsyncGroq(api_key=settings.GROQ_API_KEY)
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

STRUK_PROMPT = """Kamu adalah asisten pencatat keuangan. Analisis gambar struk/nota/bukti pembayaran ini.

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
}"""


def _compress_image(image_bytes: bytes, max_b64_bytes: int = 3_500_000) -> bytes:
    """Resize + compress image agar base64-nya di bawah limit Groq (4MB)."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # Resize jika resolusi terlalu besar (max 2000px sisi terpanjang)
    max_side = 2000
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.LANCZOS)

    # Compress sampai ukuran base64 di bawah limit
    quality = 85
    while quality >= 40:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        raw = buf.getvalue()
        if len(base64.b64encode(raw)) <= max_b64_bytes:
            return raw
        quality -= 10

    return raw  # return hasil terkecil meski melebihi (fallback)


async def analyze_receipt(image_bytes: bytes) -> list[dict] | None:
    """
    Analisis foto struk menggunakan Groq Vision (llama-4-scout).
    Return list of transaction dicts atau None jika gagal.
    """
    try:
        logger.info(f"Image raw size: {len(image_bytes):,} bytes")
        compressed = _compress_image(image_bytes)
        image_b64 = base64.b64encode(compressed).decode("utf-8")
        logger.info(f"Image after compress: {len(compressed):,} bytes | b64: {len(image_b64):,} bytes")

        response = await client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            },
                        },
                        {
                            "type": "text",
                            "text": STRUK_PROMPT,
                        },
                    ],
                }
            ],
            temperature=0.1,
            max_tokens=1024,
        )

        raw = response.choices[0].message.content.strip()
        logger.info(f"Groq raw response: {raw[:500]}")
        raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`")

        data = json.loads(raw)
        transactions = data.get("transactions", [])
        receipt_date = data.get("date") or None

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

        logger.info(f"Groq extracted {len(valid)} transactions from receipt")
        return valid if valid else None

    except json.JSONDecodeError as e:
        logger.error(f"Groq returned invalid JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Groq error: {type(e).__name__}: {e}", exc_info=True)
        return None
