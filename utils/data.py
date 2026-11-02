import os
import json
import sqlite3
import time
from typing import Optional

DATA_DIR = "data"
DB_FILE = os.path.join(DATA_DIR, "bot.db")
GUILDS_DIR = os.path.join(DATA_DIR, "guilds")  # legacy, только для миграции

DEFAULT_SHOP_POOL = {
    "🔑 Ключ от кейса «Денежный»": {"min": 1, "max": 3},
    "🔑 Ключ от кейса «Всё или ничего»": {"min": 1, "max": 2},
    "🔑 Ключ от кейса «Прайм»": {"min": 1, "max": 2},
    "🔑 Ключ от кейса «Ежедневный»": {"min": 2, "max": 5},
    "🔼 Буст уровня +25": {"min": 1, "max": 4},
    "⏫ Буст уровня +100": {"min": 1, "max": 2},
}

DEFAULT_ITEMS = {
    "🔑 Ключ от кейса «Денежный»": {
        "base_price": 10000, "type": "key", "effect": None,
        "description": "Позволяет открыть кейс «Денежный» и получить денежный приз.",
    },
    "🔑 Ключ от кейса «Всё или ничего»": {
        "base_price": 7777, "type": "key", "effect": None,
        "description": "Открывает кейс «Всё или ничего» – рискни и получишь либо всё, либо ничего.",
    },
    "🔑 Ключ от кейса «Прайм»": {
        "base_price": 50000, "type": "key", "effect": None,
        "description": "Элитный ключ для открытия кейса «Прайм» с ценными призами.",
    },
    "🔑 Ключ от кейса «Ежедневный»": {
        "base_price": 5000, "type": "key", "effect": None,
        "description": "Сбрасывает таймер ежедневного кейса, позволяя открыть его повторно.",
    },
    "🔼 Буст уровня +25": {
        "base_price": 25000, "type": "boost", "effect": {"level": 25},
        "description": "Мгновенно повышает ваш уровень на 25 единиц.",
    },
    "⏫ Буст уровня +100": {
        "base_price": 120000, "type": "boost", "effect": {"level": 100},
        "description": "Мощный буст, повышающий уровень сразу на 100.",
    },
}

_conn: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        _conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _init_schema(_conn)
        _migrate_json_to_sqlite()
    return _conn


def _init_schema(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS items (
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            base_price INTEGER NOT NULL DEFAULT 0,
            type TEXT NOT NULL DEFAULT 'custom',
            effect TEXT,
            description TEXT DEFAULT '',
            PRIMARY KEY (guild_id, name)
        );

        CREATE TABLE IF NOT EXISTS profiles (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            balance INTEGER NOT NULL DEFAULT 0,
            level INTEGER NOT NULL DEFAULT 0,
            inventory TEXT NOT NULL DEFAULT '[]',
            statuses TEXT NOT NULL DEFAULT '[]',
            honors TEXT NOT NULL DEFAULT '[]',
            last_daily INTEGER NOT NULL DEFAULT 0,
            last_work INTEGER NOT NULL DEFAULT 0,
            daily_streak INTEGER NOT NULL DEFAULT 0,
            last_daily_day INTEGER NOT NULL DEFAULT 0,
            calendar_start INTEGER NOT NULL DEFAULT 0,
            calendar_day INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS market (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            item TEXT NOT NULL,
            price INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS shop (
            guild_id INTEGER PRIMARY KEY,
            items TEXT NOT NULL DEFAULT '[]',
            buyback TEXT NOT NULL DEFAULT '[]',
            last_restock INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS shop_pool (
            guild_id INTEGER NOT NULL,
            item TEXT NOT NULL,
            min_qty INTEGER NOT NULL DEFAULT 1,
            max_qty INTEGER NOT NULL DEFAULT 3,
            PRIMARY KEY (guild_id, item)
        );

        CREATE TABLE IF NOT EXISTS events (
            guild_id INTEGER PRIMARY KEY,
            double_daily_until INTEGER NOT NULL DEFAULT 0,
            giveaway TEXT
        );
    """)
    conn.commit()


# ==================== Items ====================
def load_items(guild_id: int) -> dict:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT name, base_price, type, effect, description FROM items WHERE guild_id = ?",
        (guild_id,),
    ).fetchall()
    if not rows:
        save_items(guild_id, dict(DEFAULT_ITEMS))
        return dict(DEFAULT_ITEMS)
    result = {}
    for row in rows:
        result[row["name"]] = {
            "base_price": row["base_price"],
            "type": row["type"],
            "effect": json.loads(row["effect"]) if row["effect"] else None,
            "description": row["description"] or "",
        }
    return result


def save_items(guild_id: int, data: dict):
    conn = _get_conn()
    with conn:
        conn.execute("DELETE FROM items WHERE guild_id = ?", (guild_id,))
        for name, info in data.items():
            effect = info.get("effect")
            effect_json = json.dumps(effect, ensure_ascii=False) if effect is not None else None
            conn.execute(
                "INSERT INTO items (guild_id, name, base_price, type, effect, description) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (guild_id, name, info.get("base_price", 0), info.get("type", "custom"),
                 effect_json, info.get("description", "")),
            )


# ==================== Profiles ====================
def _row_to_profile(row) -> dict:
    return {
        "balance": row["balance"],
        "level": row["level"],
        "inventory": json.loads(row["inventory"]) if row["inventory"] else [],
        "statuses": json.loads(row["statuses"]) if row["statuses"] else [],
        "honors": json.loads(row["honors"]) if row["honors"] else [],
        "last_daily": row["last_daily"],
        "last_work": row["last_work"],
        "daily_streak": row["daily_streak"],
        "last_daily_day": row["last_daily_day"],
        "calendar_start": row["calendar_start"],
        "calendar_day": row["calendar_day"],
    }


def _upsert_profile_inner(conn, guild_id: int, user_id: int, profile: dict):
    conn.execute("""
        INSERT INTO profiles (
            guild_id, user_id, balance, level, inventory, statuses, honors,
            last_daily, last_work, daily_streak, last_daily_day,
            calendar_start, calendar_day
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET
            balance=excluded.balance,
            level=excluded.level,
            inventory=excluded.inventory,
            statuses=excluded.statuses,
            honors=excluded.honors,
            last_daily=excluded.last_daily,
            last_work=excluded.last_work,
            daily_streak=excluded.daily_streak,
            last_daily_day=excluded.last_daily_day,
            calendar_start=excluded.calendar_start,
            calendar_day=excluded.calendar_day
    """, (
        guild_id, user_id,
        profile.get("balance", 0),
        profile.get("level", 0),
        json.dumps(profile.get("inventory", []), ensure_ascii=False),
        json.dumps(profile.get("statuses", []), ensure_ascii=False),
        json.dumps(profile.get("honors", []), ensure_ascii=False),
        profile.get("last_daily", 0),
        profile.get("last_work", 0),
        profile.get("daily_streak", 0),
        profile.get("last_daily_day", 0),
        profile.get("calendar_start", 0),
        profile.get("calendar_day", 0),
    ))


def get_profile(guild_id: int, user_id: int) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM profiles WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    ).fetchone()
    return _row_to_profile(row) if row else None


def update_profile(guild_id: int, user_id: int, profile: dict):
    conn = _get_conn()
    with conn:
        _upsert_profile_inner(conn, guild_id, user_id, profile)


def delete_profile(guild_id: int, user_id: int):
    conn = _get_conn()
    with conn:
        conn.execute(
            "DELETE FROM profiles WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )


def create_profile_if_missing(guild_id: int, user_id: int) -> dict:
    existing = get_profile(guild_id, user_id)
    if existing is not None:
        return existing
    profile = {
        "balance": 0,
        "inventory": [],
        "statuses": [{"name": "Участник", "priority": 0}],
        "level": 0,
        "last_daily": 0,
        "last_work": 0,
        "honors": [],
        "daily_streak": 0,
        "last_daily_day": 0,
        "calendar_start": 0,
        "calendar_day": 0,
    }
    update_profile(guild_id, user_id, profile)
    return profile


def load_profiles(guild_id: int) -> dict:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM profiles WHERE guild_id = ?", (guild_id,)
    ).fetchall()
    return {str(row["user_id"]): _row_to_profile(row) for row in rows}


def save_profiles(guild_id: int, data: dict):
    conn = _get_conn()
    with conn:
        conn.execute("DELETE FROM profiles WHERE guild_id = ?", (guild_id,))
        for uid_str, profile in data.items():
            try:
                uid = int(uid_str)
            except (ValueError, TypeError):
                continue
            _upsert_profile_inner(conn, guild_id, uid, profile)


# ==================== Market ====================
def load_market(guild_id: int) -> list:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT seller_id, item, price FROM market WHERE guild_id = ?",
        (guild_id,),
    ).fetchall()
    return [
        {"seller_id": r["seller_id"], "item": r["item"], "price": r["price"]}
        for r in rows
    ]


def save_market(guild_id: int, market: list):
    conn = _get_conn()
    with conn:
        conn.execute("DELETE FROM market WHERE guild_id = ?", (guild_id,))
        for entry in market:
            conn.execute(
                "INSERT INTO market (guild_id, seller_id, item, price) VALUES (?, ?, ?, ?)",
                (guild_id, entry["seller_id"], entry["item"], entry["price"]),
            )


# ==================== Shop ====================
def load_shop(guild_id: int) -> dict:
    conn = _get_conn()
    row = conn.execute(
        "SELECT items, buyback, last_restock FROM shop WHERE guild_id = ?",
        (guild_id,),
    ).fetchone()
    if not row:
        return {"items": [], "buyback": [], "last_restock": 0}
    return {
        "items": json.loads(row["items"]) if row["items"] else [],
        "buyback": json.loads(row["buyback"]) if row["buyback"] else [],
        "last_restock": row["last_restock"],
    }


def save_shop(guild_id: int, data: dict):
    conn = _get_conn()
    with conn:
        conn.execute("""
            INSERT INTO shop (guild_id, items, buyback, last_restock)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                items=excluded.items,
                buyback=excluded.buyback,
                last_restock=excluded.last_restock
        """, (
            guild_id,
            json.dumps(data.get("items", []), ensure_ascii=False),
            json.dumps(data.get("buyback", []), ensure_ascii=False),
            data.get("last_restock", 0),
        ))


# ==================== Shop Pool ====================
def load_shop_pool(guild_id: int) -> dict:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT item, min_qty, max_qty FROM shop_pool WHERE guild_id = ?",
        (guild_id,),
    ).fetchall()
    if not rows:
        save_shop_pool(guild_id, DEFAULT_SHOP_POOL)
        return dict(DEFAULT_SHOP_POOL)
    return {r["item"]: {"min": r["min_qty"], "max": r["max_qty"]} for r in rows}


def save_shop_pool(guild_id: int, pool: dict):
    conn = _get_conn()
    with conn:
        conn.execute("DELETE FROM shop_pool WHERE guild_id = ?", (guild_id,))
        for item, r in pool.items():
            conn.execute(
                "INSERT INTO shop_pool (guild_id, item, min_qty, max_qty) VALUES (?, ?, ?, ?)",
                (guild_id, item, r.get("min", 1), r.get("max", 3)),
            )


# ==================== Events ====================
def load_events(guild_id: int) -> dict:
    conn = _get_conn()
    row = conn.execute(
        "SELECT double_daily_until, giveaway FROM events WHERE guild_id = ?",
        (guild_id,),
    ).fetchone()
    if not row:
        return {"double_daily_until": 0, "giveaway": None}
    return {
        "double_daily_until": row["double_daily_until"],
        "giveaway": json.loads(row["giveaway"]) if row["giveaway"] else None,
    }


def save_events(guild_id: int, data: dict):
    conn = _get_conn()
    giveaway = data.get("giveaway")
    giveaway_json = json.dumps(giveaway, ensure_ascii=False) if giveaway else None
    with conn:
        conn.execute("""
            INSERT INTO events (guild_id, double_daily_until, giveaway)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                double_daily_until=excluded.double_daily_until,
                giveaway=excluded.giveaway
        """, (guild_id, data.get("double_daily_until", 0), giveaway_json))


# ==================== Utility ====================
def has_active_status(profile: dict, status_name: str) -> bool:
    if not profile:
        return False
    now = int(time.time())
    for s in profile.get("statuses", []):
        if s.get("name") == status_name:
            if s.get("expiry", 0) == 0 or s["expiry"] > now:
                return True
    return False


def list_guild_ids() -> list:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT DISTINCT guild_id FROM profiles "
        "UNION SELECT DISTINCT guild_id FROM events"
    ).fetchall()
    return [r["guild_id"] for r in rows]


# ==================== Migration ====================
def _migrate_json_to_sqlite():
    marker = os.path.join(DATA_DIR, ".migrated_to_sqlite")
    if os.path.exists(marker):
        return

    print("🔄 Проверка старых JSON-файлов для миграции...")
    migrated_any = False

    if os.path.isdir(GUILDS_DIR):
        for gid_str in os.listdir(GUILDS_DIR):
            try:
                gid = int(gid_str)
            except ValueError:
                continue
            folder = os.path.join(GUILDS_DIR, gid_str)
            if not os.path.isdir(folder):
                continue
            _migrate_guild_folder(gid, folder)
            migrated_any = True

    legacy_items = os.path.join(DATA_DIR, "items.json")
    if os.path.exists(legacy_items):
        try:
            with open(legacy_items, 'r', encoding='utf-8') as f:
                items_data = json.load(f)
            target_gid = None
            if os.path.isdir(GUILDS_DIR):
                for gid_str in sorted(os.listdir(GUILDS_DIR)):
                    try:
                        target_gid = int(gid_str)
                        break
                    except ValueError:
                        continue
            if target_gid is not None:
                save_items(target_gid, items_data)
                print(f"📦 Старый items.json перенесён в гильдию {target_gid}")
            os.rename(legacy_items, legacy_items + ".migrated")
        except Exception as e:
            print(f"⚠️ Ошибка миграции общего items.json: {e}")

    with open(marker, 'w', encoding='utf-8') as f:
        f.write(str(int(time.time())))

    if migrated_any:
        print("✅ Миграция JSON → SQLite завершена")
    else:
        print("ℹ️ Старых JSON-файлов не найдено — миграция не требуется")


def _migrate_guild_folder(guild_id: int, folder: str):
    def _read(name):
        p = os.path.join(folder, name)
        if not os.path.exists(p):
            return None
        try:
            with open(p, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Ошибка чтения {name} ({guild_id}): {e}")
            return None

    mapping = {
        "items.json": lambda d: save_items(guild_id, d),
        "profiles.json": lambda d: save_profiles(guild_id, d),
        "marketplace.json": lambda d: save_market(guild_id, d),
        "shop_items.json": lambda d: save_shop(guild_id, d),
        "shop_pool.json": lambda d: save_shop_pool(guild_id, d),
        "events.json": lambda d: save_events(guild_id, d),
    }
    for filename, saver in mapping.items():
        data = _read(filename)
        if data is None:
            continue
        try:
            saver(data)
            os.rename(os.path.join(folder, filename),
                      os.path.join(folder, filename + ".migrated"))
        except Exception as e:
            print(f"⚠️ Ошибка миграции {filename} ({guild_id}): {e}")