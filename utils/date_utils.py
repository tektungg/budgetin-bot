"""
Utilitas tanggal/waktu yang dipakai bersama di seluruh codebase.
"""

from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))


def month_range_wib(year: int, month: int) -> tuple[datetime, datetime]:
    """Return (awal_bulan, awal_bulan_berikutnya) dalam timezone WIB."""
    start = datetime(year, month, 1, tzinfo=WIB)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=WIB)
    else:
        end = datetime(year, month + 1, 1, tzinfo=WIB)
    return start, end
