"""Тест эндпоинта /api/daily — прогноз на день по транзитам."""
import json
import urllib.error
import urllib.request

payload = {"telegram_id": 6771600924}
req = urllib.request.Request(
    "http://127.0.0.1:8080/api/daily",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST"
)
try:
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.load(r)
    print("HTTP", r.status)
    print("date:", data.get("date"), "| score:", data.get("score"))
    print("moon:", data.get("moon_sign"), "| house:", data.get("moon_house"),
          "|", data.get("moon_house_theme"))
    print("transits:", len(data.get("transits") or []))
    for t in (data.get("transits") or [])[:6]:
        print(f"  - {t['planet_ru']} — {t['natal_planet_ru']}: {t['aspect']}, орб {t['orb']}°")
    print("=" * 60)
    print(data.get("answer", ""))
except urllib.error.HTTPError as e:
    print("HTTP", e.code)
    print(e.read().decode("utf-8", "replace")[:1500])
