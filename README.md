# 💰 Budgetin Bot

Bot Telegram untuk pencatatan keuangan pribadi secara otomatis. Catat pemasukan & pengeluaran cukup dengan mengetik pesan atau mengirim foto struk.

## ✨ Fitur

- **📝 Catat transaksi** — ketik natural language seperti `keluar makan 25k`
- **📸 Scan struk** — kirim foto struk/nota, otomatis dicatat (Gemini AI)
- **📊 Laporan** — harian, bulanan, dan per kategori
- **📤 Export Excel** — download file `.xlsx` dengan format rapi & berwarna
- **✏️ Edit & Hapus** — kelola transaksi langsung dari chat
- **🔘 Menu interaktif** — navigasi mudah via inline keyboard
- **🔒 Private** — hanya user yang diizinkan bisa akses

## 📱 Cara Pakai

### Catat Transaksi
```
keluar makan siang 25k
keluar grab 15000
masuk gaji 3jt
masuk freelance desain 500rb
```

### Format Nominal
| Input | Hasil |
|-------|-------|
| `5k` / `5rb` | Rp 5.000 |
| `2jt` / `2m` | Rp 2.000.000 |
| `1.5jt` | Rp 1.500.000 |

### Foto Struk
Kirim foto struk/nota → bot menganalisis dengan AI dan mencatat otomatis.

### Perintah
| Perintah | Fungsi |
|----------|--------|
| `/start` | Menu utama |
| `/help` | Panduan lengkap |
| `/hariini` | Laporan hari ini |
| `/bulanini` | Laporan bulan ini |
| `/bulanini 1 2025` | Laporan bulan tertentu |
| `/kategori` | Ringkasan per kategori |
| `/export` | Export ke file Excel |
| `/hapus 42` | Hapus transaksi #42 |
| `/edit 42 amount 30k` | Edit nominal transaksi |

---

## 🚀 Self-Hosting

### Prasyarat
- Python 3.10+
- Akun [Supabase](https://supabase.com) (gratis)
- Bot Telegram dari [@BotFather](https://t.me/BotFather)
- API key [Google AI Studio](https://aistudio.google.com) (untuk scan struk)

### 1. Clone & Install

```bash
git clone https://github.com/username/budgetin-bot.git
cd budgetin-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Setup Supabase

1. Buat project baru di [supabase.com](https://supabase.com)
2. Buka **SQL Editor** di Dashboard
3. Buat tabel `transactions`:

```sql
CREATE TABLE IF NOT EXISTS transactions (
    id          SERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL,
    type        VARCHAR(10) NOT NULL CHECK (type IN ('masuk', 'keluar')),
    amount      BIGINT NOT NULL CHECK (amount > 0),
    category    VARCHAR(100),
    description TEXT,
    source      VARCHAR(20) DEFAULT 'text',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_user_created ON transactions(user_id, created_at DESC);
```

4. Buat function untuk laporan harian:

```sql
CREATE OR REPLACE FUNCTION get_today_transactions(p_user_id BIGINT)
RETURNS SETOF transactions AS $$
BEGIN
    RETURN QUERY
    SELECT * FROM transactions t
    WHERE t.user_id = p_user_id
      AND DATE(t.created_at AT TIME ZONE 'Asia/Jakarta') = (NOW() AT TIME ZONE 'Asia/Jakarta')::DATE
    ORDER BY t.created_at DESC;
END;
$$ LANGUAGE plpgsql;
```

5. Buat function untuk ringkasan kategori:

```sql
CREATE OR REPLACE FUNCTION get_category_summary(
    p_user_id BIGINT, p_year INTEGER, p_month INTEGER
)
RETURNS TABLE (type VARCHAR(10), category VARCHAR(100), total BIGINT, count BIGINT) AS $$
BEGIN
    RETURN QUERY
    SELECT t.type, COALESCE(t.category, 'Lainnya')::VARCHAR(100),
           SUM(t.amount)::BIGINT, COUNT(*)::BIGINT
    FROM transactions t
    WHERE t.user_id = p_user_id
      AND EXTRACT(YEAR FROM t.created_at AT TIME ZONE 'Asia/Jakarta') = p_year
      AND EXTRACT(MONTH FROM t.created_at AT TIME ZONE 'Asia/Jakarta') = p_month
    GROUP BY t.type, t.category
    ORDER BY t.type, SUM(t.amount) DESC;
END;
$$ LANGUAGE plpgsql;
```

6. (Opsional) Buat auto-update trigger:

```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$ LANGUAGE plpgsql;

CREATE TRIGGER set_updated_at BEFORE UPDATE ON transactions
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

### 3. Konfigurasi Environment

```bash
cp .env.example .env
```

Edit `.env`:
```env
TELEGRAM_TOKEN=token-dari-botfather
GEMINI_API_KEY=key-dari-aistudio
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
ALLOWED_USER_IDS=your-telegram-user-id
```

> 💡 Cara cek Telegram User ID: chat ke [@userinfobot](https://t.me/userinfobot)

> 💡 Supabase Key: Dashboard → Settings → API → `service_role` key

### 4. Jalankan Bot

```bash
python main.py
```

---

## 📁 Struktur Project

```
budgetin-bot/
├── main.py                 # Entry point
├── config/
│   └── settings.py         # Konfigurasi environment
├── handlers/
│   ├── general.py          # /start, /help, /edit, /hapus, callback
│   ├── report.py           # /hariini, /bulanini, /kategori, /export
│   └── transaction.py      # Handle teks & foto
├── services/
│   ├── database.py         # Supabase client & query
│   ├── export.py           # Generate Excel (.xlsx)
│   ├── gemini.py           # Analisis struk via AI
│   └── parser.py           # Parser input natural
├── utils/
│   ├── auth.py             # Autentikasi user
│   └── formatter.py        # Format pesan & tanggal
├── .github/
│   └── workflows/
│       └── keep-alive.yml  # Cron ping Supabase
├── requirements.txt
└── .env.example
```

## 🛡️ Keamanan

- Set `ALLOWED_USER_IDS` di `.env` agar hanya kamu yang bisa pakai bot
- Gunakan `service_role` key Supabase (jangan expose ke publik)
- Jangan commit file `.env` ke Git

## 📄 Lisensi

MIT License
