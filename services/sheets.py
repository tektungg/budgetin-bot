"""
Google Sheets export service.
Menggunakan service account untuk menulis ke Google Sheets.
"""

import logging
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from config.settings import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_sheets_service():
    creds = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds)


def export_to_sheets(transactions: list[dict], sheet_name: str = None) -> str | None:
    """
    Export transaksi ke Google Sheets.
    Return URL sheet atau None jika gagal.
    """
    if not settings.GOOGLE_SHEET_ID:
        logger.warning("GOOGLE_SHEET_ID not set, skipping export")
        return None

    try:
        service = get_sheets_service()
        sheet_id = settings.GOOGLE_SHEET_ID

        if not sheet_name:
            sheet_name = datetime.now().strftime("%B %Y")

        # Cek apakah tab/sheet sudah ada, jika tidak buat baru
        spreadsheet = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        existing_sheets = [s["properties"]["title"] for s in spreadsheet["sheets"]]

        if sheet_name not in existing_sheets:
            body = {
                "requests": [{
                    "addSheet": {
                        "properties": {"title": sheet_name}
                    }
                }]
            }
            service.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id, body=body
            ).execute()

        # Siapkan data
        headers = ["ID", "Tanggal", "Tipe", "Jumlah (Rp)", "Kategori", "Deskripsi", "Sumber"]
        rows = [headers]

        for tx in transactions:
            date_str = tx["created_at"].strftime("%d/%m/%Y %H:%M") if tx.get("created_at") else ""
            rows.append([
                tx.get("id", ""),
                date_str,
                "Pemasukan" if tx["type"] == "masuk" else "Pengeluaran",
                tx["amount"],
                tx.get("category", ""),
                tx.get("description", ""),
                tx.get("source", "text"),
            ])

        # Tambahkan baris total di bawah
        total_masuk = sum(t["amount"] for t in transactions if t["type"] == "masuk")
        total_keluar = sum(t["amount"] for t in transactions if t["type"] == "keluar")
        rows.append([])
        rows.append(["", "", "TOTAL MASUK", total_masuk, "", "", ""])
        rows.append(["", "", "TOTAL KELUAR", total_keluar, "", "", ""])
        rows.append(["", "", "SALDO", total_masuk - total_keluar, "", "", ""])

        # Tulis ke sheet
        range_name = f"{sheet_name}!A1"
        body = {"values": rows}
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            body=body,
        ).execute()

        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        logger.info(f"Exported {len(transactions)} transactions to Sheets: {url}")
        return url

    except Exception as e:
        logger.error(f"Sheets export error: {e}")
        return None
