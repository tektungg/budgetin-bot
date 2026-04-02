"""
Database service menggunakan Supabase Python SDK.

Best practices:
- Singleton client instance (connection pooling via Supabase infra)
- Semua query via PostgREST API (supabase-py query builder)
- Aggregation via RPC (PostgreSQL function)
- RLS diaktifkan di level database
"""

import logging
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client
from config.settings import settings

logger = logging.getLogger(__name__)

# Timezone Asia/Jakarta (UTC+7)
WIB = timezone(timedelta(hours=7))

# Singleton Supabase client
_client: Client | None = None


def get_client() -> Client:
    """Get atau buat Supabase client (singleton)"""
    global _client
    if _client is None:
        _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        logger.info("Supabase client initialized")
    return _client


def check_connection():
    """Verifikasi koneksi ke Supabase bisa dilakukan"""
    try:
        client = get_client()
        # Test query ringan untuk pastikan koneksi OK
        client.table("transactions").select("id", count="exact").limit(1).execute()
        logger.info("Supabase connection verified")
    except Exception as e:
        logger.error(f"Supabase connection failed: {e}")
        raise


def insert_transaction(
    user_id: int,
    tx_type: str,
    amount: int,
    category: str,
    description: str,
    source: str = "text",
    created_at: datetime = None,
) -> dict:
    """Insert transaksi baru, return data yang tersimpan"""
    client = get_client()
    data = {
        "user_id": user_id,
        "type": tx_type,
        "amount": amount,
        "category": category,
        "description": description,
        "source": source,
    }
    if created_at:
        data["created_at"] = created_at.isoformat()
    result = (
        client.table("transactions")
        .insert(data)
        .execute()
    )
    return result.data[0]


def get_today_transactions(user_id: int) -> list[dict]:
    """Ambil transaksi hari ini (timezone Asia/Jakarta) via RPC"""
    client = get_client()
    result = client.rpc("get_today_transactions", {"p_user_id": user_id}).execute()
    return result.data


def get_month_transactions(
    user_id: int, year: int = None, month: int = None
) -> list[dict]:
    """Ambil transaksi bulan tertentu"""
    now = datetime.now(WIB)
    year = year or now.year
    month = month or now.month

    # Hitung range tanggal awal & akhir bulan dalam WIB, convert ke UTC
    start_of_month = datetime(year, month, 1, tzinfo=WIB)
    if month == 12:
        end_of_month = datetime(year + 1, 1, 1, tzinfo=WIB)
    else:
        end_of_month = datetime(year, month + 1, 1, tzinfo=WIB)

    client = get_client()
    result = (
        client.table("transactions")
        .select("*")
        .eq("user_id", user_id)
        .gte("created_at", start_of_month.isoformat())
        .lt("created_at", end_of_month.isoformat())
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


def get_category_summary(
    user_id: int, year: int = None, month: int = None
) -> list[dict]:
    """Ringkasan per kategori via RPC (GROUP BY + SUM di PostgreSQL)"""
    now = datetime.now(WIB)
    year = year or now.year
    month = month or now.month

    client = get_client()
    result = client.rpc(
        "get_category_summary",
        {"p_user_id": user_id, "p_year": year, "p_month": month},
    ).execute()
    return result.data


def delete_transaction(tx_id: int, user_id: int) -> bool:
    """Hapus transaksi (soft-delete) berdasarkan ID dan user_id"""
    client = get_client()
    now_iso = datetime.now(timezone.utc).isoformat()
    result = (
        client.table("transactions")
        .update({"deleted_at": now_iso})
        .eq("id", tx_id)
        .eq("user_id", user_id)
        .execute()
    )
    return len(result.data) > 0


def restore_transaction(tx_id: int, user_id: int) -> bool:
    """Pulihkan transaksi yang di-soft-delete berdasarkan ID dan user_id"""
    client = get_client()
    result = (
        client.table("transactions")
        .update({"deleted_at": None})
        .eq("id", tx_id)
        .eq("user_id", user_id)
        .execute()
    )
    return len(result.data) > 0


def update_transaction(tx_id: int, user_id: int, **kwargs) -> bool:
    """Update transaksi — hanya field yang diizinkan"""
    allowed = {"type", "amount", "category", "description"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False

    client = get_client()
    result = (
        client.table("transactions")
        .update(updates)
        .eq("id", tx_id)
        .eq("user_id", user_id)
        .execute()
    )
    return len(result.data) > 0


def update_transaction_date(tx_id: int, user_id: int, new_date: datetime) -> bool:
    """Update tanggal transaksi (created_at)"""
    client = get_client()
    result = (
        client.table("transactions")
        .update({"created_at": new_date.isoformat()})
        .eq("id", tx_id)
        .eq("user_id", user_id)
        .execute()
    )
    return len(result.data) > 0


def get_transaction_by_id(tx_id: int, user_id: int) -> dict | None:
    """Ambil satu transaksi berdasarkan ID"""
    client = get_client()
    result = (
        client.table("transactions")
        .select("*")
        .eq("id", tx_id)
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    return result.data


def get_recent_transactions(user_id: int, limit: int = 10) -> list[dict]:
    """Ambil transaksi terbaru untuk user"""
    client = get_client()
    result = (
        client.table("transactions")
        .select("*")
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


def get_available_months(user_id: int) -> list[dict]:
    """Ambil daftar bulan & tahun yang memiliki transaksi (distinct year-month)"""
    client = get_client()
    result = (
        client.table("transactions")
        .select("created_at")
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .execute()
    )

    seen = set()
    months = []
    for row in result.data:
        created = row["created_at"]
        if isinstance(created, str):
            # Normalize fractional seconds to 6 digits for Python 3.10 compat
            import re
            created = re.sub(
                r"(\.\d{1,6})\d*",
                lambda m: m.group(1).ljust(7, "0"),
                created.replace("Z", "+00:00"),
            )
            dt = datetime.fromisoformat(created).astimezone(WIB)
        else:
            dt = created
        key = (dt.year, dt.month)
        if key not in seen:
            seen.add(key)
            months.append({"year": dt.year, "month": dt.month})
    return months


def search_transactions(user_id: int, keyword: str, limit: int = 20) -> list[dict]:
    """Cari transaksi berdasarkan keyword di description atau category"""
    client = get_client()
    result = (
        client.table("transactions")
        .select("*")
        .eq("user_id", user_id)
        .or_(f"description.ilike.%{keyword}%,category.ilike.%{keyword}%")
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


def get_transactions_by_category(
    user_id: int, year: int, month: int, tx_type: str, category: str
) -> list[dict]:
    """Ambil transaksi bulan tertentu berdasarkan kategori dan tipe (Drill-down)"""
    now = datetime.now(WIB)
    year = year or now.year
    month = month or now.month

    start_of_month = datetime(year, month, 1, tzinfo=WIB)
    if month == 12:
        end_of_month = datetime(year + 1, 1, 1, tzinfo=WIB)
    else:
        end_of_month = datetime(year, month + 1, 1, tzinfo=WIB)

    client = get_client()
    result = (
        client.table("transactions")
        .select("*")
        .eq("user_id", user_id)
        .eq("type", tx_type)
        .eq("category", category)
        .gte("created_at", start_of_month.isoformat())
        .lt("created_at", end_of_month.isoformat())
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data
