import json
from datetime import datetime, timedelta, timezone
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

            CREATE TABLE IF NOT EXISTS synastry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                partner_name TEXT NOT NULL,
                partner_birth_date TEXT NOT NULL,
                partner_birth_time TEXT NOT NULL,
                partner_city TEXT NOT NULL,
                score INTEGER NOT NULL,
                aspects_json TEXT NOT NULL,
                answer TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS daily_forecast (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                forecast_date TEXT NOT NULL,
                score INTEGER NOT NULL,
                transits_json TEXT NOT NULL,
                answer TEXT NOT NULL,
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


async def save_chat_message(telegram_id: int, role: str, message: str):
    """Сохраняет сообщение консультации в таблицу chat_history."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            return  # пользователя ещё нет — нечего сохранять
        await db.execute(
            "INSERT INTO chat_history (user_id, role, message) VALUES (?, ?, ?)",
            (row[0], role, message)
        )
        await db.commit()


# ---------- Синастрия: совместимость двух натальных карт ----------

# Мажорные межкартовые аспекты. Оценка: гармоничные — плюс, напряжённые — минус.
SYNASTRY_ASPECTS = {
    "conjunction": {"degree": 0,   "label": "соединение", "score": 2.0},
    "sextile":     {"degree": 60,  "label": "секстиль",   "score": 1.5},
    "square":      {"degree": 90,  "label": "квадрат",    "score": -2.0},
    "trine":       {"degree": 120, "label": "трин",       "score": 2.0},
    "opposition":  {"degree": 180, "label": "оппозиция",  "score": -1.5},
}

# Орбис (допуск точности) и вес планеты: светила и личные планеты важнее
PLANET_ORB = {
    "Sun": 8, "Moon": 8, "Mercury": 6, "Venus": 6, "Mars": 6,
    "Jupiter": 5, "Saturn": 5, "Uranus": 4, "Neptune": 4, "Pluto": 4,
}
PLANET_WEIGHT = {
    "Sun": 3, "Moon": 3, "Mercury": 2, "Venus": 3, "Mars": 3,
    "Jupiter": 2, "Saturn": 2, "Uranus": 1, "Neptune": 1, "Pluto": 1,
}


def _angular_distance(a: float, b: float) -> float:
    """Кратчайший угол между двумя долготами (0..180)."""
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d


def _house_of(degree: float, cusps: list) -> int | None:
    """Определяет номер дома (1..12), в который попадает градус."""
    n = len(cusps)
    if not n:
        return None
    for i in range(n):
        start = cusps[i]
        end = cusps[(i + 1) % n]
        if start <= end:
            if start <= degree < end:
                return i + 1
        elif degree >= start or degree < end:
            return i + 1
    return None


def calculate_synastry(
    own_planets: dict,
    own_cusps: list | None,
    partner_planets: dict,
) -> dict:
    """Считает межкартовые аспекты двух карт и общий балл совместимости.

    own_planets / partner_planets: {"Sun": {"ru_name": "Солнце", "degree": 12.3, "sign": "..."}, ...}
    own_cusps: 12 куспидов домов первой карты (для наложения домов), может быть None.
    """
    aspects = []

    for a_name, a in own_planets.items():
        for b_name, b in partner_planets.items():
            dist = _angular_distance(a["degree"], b["degree"])
            orb = min(PLANET_ORB.get(a_name, 5), PLANET_ORB.get(b_name, 5))

            for key, cfg in SYNASTRY_ASPECTS.items():
                delta = abs(dist - cfg["degree"])
                if delta > orb:
                    continue
                strength = 1 - delta / orb          # 1.0 — точный аспект, 0 — на границе орбиса
                weight = (PLANET_WEIGHT.get(a_name, 1) + PLANET_WEIGHT.get(b_name, 1)) / 2
                points = cfg["score"] * weight * (0.4 + 0.6 * strength)
                aspects.append({
                    "key": key,
                    "aspect": cfg["label"],
                    "planet_a": a_name,
                    "planet_a_ru": a.get("ru_name", a_name),
                    "planet_a_sign": a.get("sign", ""),
                    "planet_b": b_name,
                    "planet_b_ru": b.get("ru_name", b_name),
                    "planet_b_sign": b.get("sign", ""),
                    "orb": round(delta, 1),
                    "harmony": cfg["score"] > 0,
                    "points": round(points, 2),
                })

    aspects.sort(key=lambda x: abs(x["points"]), reverse=True)

    harmony = sum(a["points"] for a in aspects if a["points"] > 0)
    tension = sum(-a["points"] for a in aspects if a["points"] < 0)
    total = harmony + tension
    ratio = harmony / total if total else 0.5
    score = round(30 + 60 * ratio)          # 30..90 — без крайностей и приговоров

    # Наложение домов: планеты партнёра в домах первой карты
    overlay = []
    if own_cusps:
        for b_name, b in partner_planets.items():
            house = _house_of(b["degree"], own_cusps)
            if house:
                overlay.append({"planet": b.get("ru_name", b_name), "house": house})

    return {
        "score": score,
        "harmony": round(harmony, 1),
        "tension": round(tension, 1),
        "aspects": aspects[:10],
        "aspect_count": len(aspects),
        "overlay": overlay,
    }


async def save_synastry(
    telegram_id: int,
    partner: dict,
    score: int,
    aspects: list,
    answer: str,
) -> int | None:
    """Сохраняет результат проверки совместимости."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        cursor = await db.execute("""
            INSERT INTO synastry (
                user_id, partner_name, partner_birth_date, partner_birth_time,
                partner_city, score, aspects_json, answer
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row[0],
            partner.get("name", "Партнёр"),
            partner.get("birthDate", ""),
            partner.get("birthTime", ""),
            partner.get("city", ""),
            score,
            json.dumps(aspects, ensure_ascii=False),
            answer,
        ))
        await db.commit()
        return cursor.lastrowid


# ---------- Прогноз на день: транзиты к натальной карте ----------

# В транзитах орбисы значительно уже натальных: аспект привязан ко времени.
# Чем быстрее планета, тем уже допуск (Луна живёт в орбе часы, Плутон — месяцы).
TRANSIT_ORB = {
    "Moon": 1.5, "Sun": 2.0, "Mercury": 1.5, "Venus": 1.5, "Mars": 2.0,
    "Jupiter": 2.5, "Saturn": 2.5, "Uranus": 2.0, "Neptune": 2.0, "Pluto": 2.0,
}

# Вес транзитной планеты для дневного прогноза: Луна задаёт день,
# светила и личные планеты — триггеры, внешние — только фоновый оттенок.
TRANSIT_WEIGHT = {
    "Moon": 3.0, "Sun": 2.5, "Venus": 2.5, "Mars": 2.5,
    "Mercury": 2.0, "Jupiter": 1.5, "Saturn": 1.5,
    "Uranus": 1.0, "Neptune": 1.0, "Pluto": 1.0,
}

# Соединение в транзите — это интенсивность, а не «плюс»: даём небольшой вес.
TRANSIT_ASPECTS = {
    "conjunction": {"degree": 0,   "label": "соединение", "score": 1.0},
    "sextile":     {"degree": 60,  "label": "секстиль",   "score": 1.5},
    "square":      {"degree": 90,  "label": "квадрат",    "score": -2.0},
    "trine":       {"degree": 120, "label": "трин",       "score": 2.0},
    "opposition":  {"degree": 180, "label": "оппозиция",  "score": -1.5},
}

# Смысл домов — чтобы модель знала, какой сферы касается день
HOUSE_THEMES = {
    1: "ты сам, тело, внешность, инициатива",
    2: "деньги, ресурсы, самооценка",
    3: "общение, поездки, учёба, ближний круг",
    4: "дом, семья, безопасность, корни",
    5: "творчество, влюблённость, дети, радость",
    6: "работа, рутина, здоровье, обязанности",
    7: "партнёрство, отношения, договоры",
    8: "общие ресурсы, кризисы, трансформация",
    9: "смыслы, обучение, дальние поездки",
    10: "карьера, статус, цели, публичность",
    11: "друзья, сообщества, планы на будущее",
    12: "отдых, тишина, завершение, восстановление",
}


def calculate_daily_transits(
    natal_planets: dict,
    natal_cusps: list | None,
    moment_utc: datetime | None = None,
) -> dict:
    """Считает транзиты планет на заданный момент к натальной карте.

    natal_planets: {"Sun": {"ru_name": "Солнце", "degree": 12.3, "sign": "..."}, ...}
    natal_cusps: 12 куспидов домов (для определения дома транзитной Луны), может быть None.
    """
    if moment_utc is None:
        moment_utc = datetime.now(timezone.utc)

    hour_utc = moment_utc.hour + moment_utc.minute / 60.0
    jd = swe.julday(moment_utc.year, moment_utc.month, moment_utc.day, hour_utc)

    # Позиции планет на сегодня
    transiting = {}
    for eng_name, (ru_name, pid) in PLANET_LIST.items():
        pos, _ = swe.calc_ut(jd, pid)
        transiting[eng_name] = {
            "ru_name": ru_name,
            "degree": round(pos[0], 2),
            "sign": deg_to_sign_name(pos[0]),
            "retrograde": pos[3] < 0,
        }

    transits = []
    for t_name, t in transiting.items():
        orb = TRANSIT_ORB.get(t_name, 2.0)
        weight = TRANSIT_WEIGHT.get(t_name, 1.0)
        for n_name, n in natal_planets.items():
            dist = _angular_distance(t["degree"], n["degree"])
            for key, cfg in TRANSIT_ASPECTS.items():
                delta = abs(dist - cfg["degree"])
                if delta > orb:
                    continue
                strength = 1 - delta / orb
                points = cfg["score"] * weight * (0.35 + 0.65 * strength)
                transits.append({
                    "key": key,
                    "aspect": cfg["label"],
                    "planet": t_name,
                    "planet_ru": t["ru_name"],
                    "planet_sign": t["sign"],
                    "retrograde": t["retrograde"],
                    "natal_planet": n_name,
                    "natal_planet_ru": n.get("ru_name", n_name),
                    "natal_planet_sign": n.get("sign", ""),
                    "orb": round(delta, 1),
                    "harmony": cfg["score"] > 0,
                    "points": round(points, 2),
                })

    transits.sort(key=lambda x: abs(x["points"]), reverse=True)

    harmony = sum(t["points"] for t in transits if t["points"] > 0)
    tension = sum(-t["points"] for t in transits if t["points"] < 0)
    total = harmony + tension
    ratio = harmony / total if total else 0.5
    score = round(20 + 65 * ratio)          # 20..85 — день не бывает «идеальным» или «провальным»

    moon_house = None
    if natal_cusps:
        moon_house = _house_of(transiting["Moon"]["degree"], natal_cusps)

    return {
        "score": score,
        "harmony": round(harmony, 1),
        "tension": round(tension, 1),
        "transits": transits[:10],
        "transit_count": len(transits),
        "moon_sign": transiting["Moon"]["sign"],
        "moon_house": moon_house,
        "moon_house_theme": HOUSE_THEMES.get(moon_house, ""),
        "moon_retrograde": transiting["Moon"]["retrograde"],
        "transiting": transiting,
        "moment": moment_utc.strftime("%Y-%m-%d %H:%M UTC"),
    }


async def save_daily_forecast(
    telegram_id: int,
    forecast_date: str,
    score: int,
    transits: list,
    answer: str,
) -> int | None:
    """Сохраняет прогноз на день."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        cursor = await db.execute("""
            INSERT INTO daily_forecast (
                user_id, forecast_date, score, transits_json, answer
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            row[0],
            forecast_date,
            score,
            json.dumps(transits, ensure_ascii=False),
            answer,
        ))
        await db.commit()
        return cursor.lastrowid