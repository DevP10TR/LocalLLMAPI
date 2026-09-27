import sqlite3
import os
import time

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Tabela kluczy API
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            api_key TEXT UNIQUE NOT NULL,
            created_at REAL,
            engine TEXT DEFAULT 'vulkan'
        )
    """)
    try:
        cursor.execute("ALTER TABLE api_keys ADD COLUMN engine TEXT DEFAULT 'vulkan'")
    except sqlite3.OperationalError:
        pass
    # Tabela logów (z referencją do klucza)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS request_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key_id INTEGER,
            timestamp REAL,
            model TEXT,
            elapsed_seconds REAL,
            total_tokens INTEGER,
            tokens_per_second REAL,
            ttft REAL DEFAULT 0.0,
            min_tps REAL,
            max_tps REAL,
            FOREIGN KEY (api_key_id) REFERENCES api_keys (id)
        )
    """)
    try:
        cursor.execute("ALTER TABLE request_logs ADD COLUMN ttft REAL DEFAULT 0.0")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()
    init_settings()


def create_api_key(name: str, api_key: str, engine: str = "vulkan"):
    """Tworzy nowy klucz (o zadanej wartości). Rzuca wyjątek, jeśli klucz już istnieje."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO api_keys (name, api_key, created_at, engine)
            VALUES (?, ?, ?, ?)
        """,
            (name, api_key, time.time(), engine),
        )
        conn.commit()
        key_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        raise ValueError("Taki klucz API już istnieje. Wymyśl inną, unikalną wartość.")
    finally:
        conn.close()
    return key_id


def get_api_keys_stats():
    """Zwraca listę kluczy wraz z podsumowaniem (ostatnie użycie, łącznie tokenów)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            k.id, k.name, k.api_key, k.created_at, k.engine,
            MAX(l.timestamp) as last_used,
            SUM(l.total_tokens) as total_tokens
        FROM api_keys k
        LEFT JOIN request_logs l ON k.id = l.api_key_id
        GROUP BY k.id
        ORDER BY k.created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    keys = []
    for row in rows:
        keys.append(
            {
                "id": row[0],
                "name": row[1],
                "api_key": row[2],
                "created_at": row[3],
                "engine": row[4],
                "last_used": row[5],
                "total_tokens": row[6] or 0,
            }
        )
    return keys


def get_api_key_by_value(api_key: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM api_keys WHERE api_key = ?", (api_key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_engine_for_key(key_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT engine FROM api_keys WHERE id = ?", (key_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "vulkan"


def add_log(
    api_key_id: int,
    model: str,
    elapsed: float,
    tokens: int,
    tps: float,
    min_tps: float = 0.0,
    max_tps: float = 0.0,
    ttft: float = 0.0,
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO request_logs (api_key_id, timestamp, model, elapsed_seconds, total_tokens, tokens_per_second, min_tps, max_tps, ttft)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (api_key_id, time.time(), model, elapsed, tokens, tps, min_tps, max_tps, ttft),
    )
    conn.commit()
    conn.close()


def get_logs_for_key(api_key_id: int, limit=200):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT timestamp, model, elapsed_seconds, total_tokens, tokens_per_second, min_tps, max_tps, ttft
        FROM request_logs
        WHERE api_key_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    """,
        (api_key_id, limit),
    )
    rows = cursor.fetchall()
    conn.close()

    logs = []
    for row in reversed(rows):
        logs.append(
            {
                "timestamp": row[0],
                "model": row[1],
                "elapsed_seconds": row[2],
                "total_tokens": row[3],
                "tokens_per_second": row[4],
                "min_tps": row[5] if len(row) > 5 and row[5] is not None else row[4],
                "max_tps": row[6] if len(row) > 6 and row[6] is not None else row[4],
                "ttft": row[7] if len(row) > 7 and row[7] is not None else 0.0,
            }
        )
    return logs


def init_settings():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.commit()
    # Domyślne sloty: 1=vulkan, 2=cpu, 3=cpu
    defaults = [
        ("slot_1_device", "vulkan"),
        ("slot_2_device", "cpu"),
        ("slot_3_device", "cpu"),
    ]
    for k, v in defaults:
        cursor.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v)
        )
    conn.commit()
    conn.close()


def get_slot_devices():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT key, value FROM settings WHERE key LIKE ?", ("slot_%_device",)
    )
    rows = cursor.fetchall()
    conn.close()
    result = {}
    for k, v in rows:
        idx = k.split("_")[1]
        result[int(idx)] = v
    return result


def update_slot_device(slot_index: int, device: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE settings SET value = ? WHERE key = ?",
        (device, f"slot_{slot_index}_device"),
    )
    conn.commit()
    conn.close()


def delete_api_key(key_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Usuń kaskadowo logi przypisane do klucza
    cursor.execute("DELETE FROM request_logs WHERE api_key_id = ?", (key_id,))
    # Usuń sam klucz
    cursor.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
    conn.commit()
    conn.close()


def update_api_key(
    key_id: int, new_name: str, new_api_key: str = None, new_engine: str = "vulkan"
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if new_api_key:
        cursor.execute(
            "UPDATE api_keys SET name = ?, api_key = ?, engine = ? WHERE id = ?",
            (new_name, new_api_key, new_engine, key_id),
        )
    else:
        cursor.execute(
            "UPDATE api_keys SET name = ?, engine = ? WHERE id = ?",
            (new_name, new_engine, key_id),
        )
    conn.commit()
    conn.close()
