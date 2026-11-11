import json
from datetime import datetime, timedelta
import aiosqlite
import swisseph as swe

DB_NAME = "astro.db"

ZODIAC_SIGNS = [
    "Овен", "Телец", "Близнецы", "Рак",
    "Лев", "Дева", "Весы", "Скорпион",
    "Стрелец", "Козерог", "Водолей", "Рыбы"
]

PLANET_LIST = {
    "Sun": ("Солнце", swe.SUN),
    "Moon": ("Луна", swe.MOON),
    "Mercury": ("Меркурий", swe.MERCURY),
    "Venus": ("Венера", swe.VENUS),
    "Mars": ("Марс", swe.MARS),
    "Jupiter": ("Юпитер", swe.JUPITER),
    "Saturn": ("Сатурн", swe.SATURN),
    "Uranus": ("Уран", swe.URANUS),
    "Neptune": ("Нептун", swe.NEPTUNE),
    "Pluto": ("Плутон", swe.PLUTO),
}


def deg_to_sign_name(lon: float) -> str:
    idx = int(lon // 30) % 12
    deg = lon % 30
    return f"{ZODIAC_SIGNS[idx]} ({deg:.1f}°)"


def calculate_natal_chart(
    birth_date: str,
    birth_time: str,
    is_exact_time: bool,
    lat: float,
    lon: float,
    tz_offset: float = 3.0
) -> dict:
    """Расчёт натальной карты через Swiss Ephemeris (pyswisseph)."""
    # Если время неизвестно, берём середину выбранного периода или 12:00
    approx_map = {
        "Утро": "09:00",
        "День": "15:00",
        "Вечер": "21:00",
        "Ночь": "03:00"
    }
    clean_time = birth_time if is_exact_time else approx_map.get(birth_time, "12:00")
    if ":" not in clean_time:
        clean_time = "12:00"

    # Переводим локальное время рождения в UTC
    dt_local = datetime.strptime(f"{birth_date} {clean_time}", "%Y-%m-%d %H:%M")
    dt_utc = dt_local - timedelta(hours=tz_offset)
    hour_utc = dt_utc.hour + dt_utc.minute / 60.0

    # Юлианский день
    jd = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, hour_utc)

    planets_chart = {}   # Формат для отрисовки в AstroChart: {"Sun": [deg], ...}
    planets_ai = {}      # Подробный формат для БД и ИИ-астролога

    for eng_name, (ru_name, pid) in PLANET_LIST.items():
        pos, _ = swe.calc_ut(jd, pid)
        deg = round(pos[0], 2)
        is_retro = pos[3] < 0
        planets_chart[eng_name] = [deg]
        planets_ai[eng_name] = {
            "ru_name": ru_name,
            "degree": deg,
            "sign": deg_to_sign_name(deg),
            "retrograde": is_retro
        }

    # Считаем куспиды 12 домов по системе Плацидуса
    cusps, ascmc = swe.houses(jd, lat, lon, b'P')
    houses_cusps = [round(c, 2) for c in (cusps[1:13] if len(cusps) == 13 else cusps[:12])]

    asc_deg = round(ascmc[0], 2)
    ascendant_str = deg_to_sign_name(asc_deg) if is_exact_time else "Неизвестно (нет точного времени)"

    houses_ai = {
        f"House_{i + 1}": {
            "degree": houses_cusps[i],
            "sign": deg_to_sign_name(houses_cusps[i])
        }
        for i in range(12)
    }

    return {
        "sun_sign": planets_ai["Sun"]["sign"],
        "moon_sign": planets_ai["Moon"]["sign"],
        "ascendant": ascendant_str,
        "planets_ai": planets_ai,
        "houses_ai": houses_ai,
        "chart_render": {
            "planets": planets_chart,
            "cusps": houses_cusps
        }
    }


async def init_db():
    """Создаёт 4 таблицы в SQLite, если их ещё нет."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id BIGINT UNIQUE NOT NULL,
                username TEXT,
                name TEXT NOT NULL,
                gender TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS birth_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                birth_date TEXT NOT NULL,
                birth_time TEXT NOT NULL,
                is_exact_time BOOLEAN NOT NULL,
                city TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                timezone TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS natal_charts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                sun_sign TEXT NOT NULL,
                moon_sign TEXT NOT NULL,
                ascendant TEXT NOT NULL,
                planets_json TEXT NOT NULL,
                houses_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
        """)
        await db.commit()


async def save_full_natal_profile(payload: dict, chart_data: dict) -> int:
    """Сохраняет или обновляет пользователя, данные рождения и расчёт карты в БД."""
    telegram_id = int(payload.get("telegram_id", 0))
    username = payload.get("username", "")
    name = payload.get("name", "Гость")
    gender = payload.get("gender", "Женский")

    async with aiosqlite.connect(DB_NAME) as db:
        # 1. Сохраняем или обновляем пользователя в таблице users
        await db.execute("""
            INSERT INTO users (telegram_id, username, name, gender)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                name = excluded.name,
                gender = excluded.gender
        """, (telegram_id, username, name, gender))

        async with db.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)) as cursor:
            row = await cursor.fetchone()
            user_id = row[0]

        # 2. Сохраняем данные рождения в таблицу birth_data
        await db.execute("""
            INSERT INTO birth_data (
                user_id, birth_date, birth_time, is_exact_time,
                city, latitude, longitude, timezone
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                birth_date = excluded.birth_date,
                birth_time = excluded.birth_time,
                is_exact_time = excluded.is_exact_time,
                city = excluded.city,
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                timezone = excluded.timezone
        """, (
            user_id,
            payload["birthDate"],
            payload["birthTime"],
            not payload.get("unknownTime", False),
            payload["city"],
            float(payload.get("latitude", 55.7558)),
            float(payload.get("longitude", 37.6173)),
            payload.get("timezone", "Europe/Moscow")
        ))

        # 3. Сохраняем рассчитанную натальную карту в таблицу natal_charts
        await db.execute("""
            INSERT INTO natal_charts (
                user_id, sun_sign, moon_sign, ascendant, planets_json, houses_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                sun_sign = excluded.sun_sign,
                moon_sign = excluded.moon_sign,
                ascendant = excluded.ascendant,
                planets_json = excluded.planets_json,
                houses_json = excluded.houses_json,
                updated_at = CURRENT_TIMESTAMP
        """, (
            user_id,
            chart_data["sun_sign"],
            chart_data["moon_sign"],
            chart_data["ascendant"],
            json.dumps(chart_data["planets_ai"], ensure_ascii=False),
            json.dumps(chart_data["houses_ai"], ensure_ascii=False)
        ))

        await db.commit()
        return user_id


async def get_user_astro_context(telegram_id: int) -> dict | None:
    """Достаёт полный паспорт натальной карты из БД для промпта ИИ."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT u.id as user_id, u.name, u.gender,
                   b.birth_date, b.birth_time, b.is_exact_time, b.city,
                   n.sun_sign, n.moon_sign, n.ascendant, n.planets_json, n.houses_json
            FROM users u
            JOIN birth_data b ON u.id = b.user_id
            JOIN natal_charts n ON u.id = n.user_id
            WHERE u.telegram_id = ?
        """, (telegram_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None