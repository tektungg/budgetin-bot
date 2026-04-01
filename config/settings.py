"""
Konfigurasi aplikasi Budgetin Bot — baca dari environment variables
"""

import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

# Load .env.local dulu (untuk testing), lalu fallback ke .env
_env_dir = Path(__file__).resolve().parent.parent
_local_env = _env_dir / ".env.local"
if _local_env.exists():
    load_dotenv(_local_env, override=True)
else:
    load_dotenv()


@dataclass
class Settings:
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # Supabase
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")  # service_role key

    # Allowed user IDs (kosongkan = semua orang bisa pakai)
    ALLOWED_USER_IDS: list[int] = None

    def __post_init__(self):
        raw = os.getenv("ALLOWED_USER_IDS", "")
        if raw.strip():
            self.ALLOWED_USER_IDS = [int(x.strip()) for x in raw.split(",")]

    def validate(self):
        """Validasi konfigurasi wajib"""
        errors = []
        if not self.TELEGRAM_TOKEN:
            errors.append("TELEGRAM_TOKEN belum diisi")
        if not self.SUPABASE_URL:
            errors.append("SUPABASE_URL belum diisi")
        if not self.SUPABASE_KEY:
            errors.append("SUPABASE_KEY belum diisi")
        if errors:
            raise ValueError(
                "Konfigurasi tidak lengkap:\n" + "\n".join(f"  - {e}" for e in errors)
            )


settings = Settings()
