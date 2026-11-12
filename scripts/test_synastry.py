"""Тест эндпоинта /api/synastry — проверка совместимости двух карт."""
import json
import urllib.error
import urllib.request

payload = {
    "telegram_id": 6771600924,
    "partner": {
        "name": "Артём",
        "birthDate": "1995-07-14",
        "birthTime": "08:30",
        "unknownTime": False,
        "approxPeriod": "Утро",
        "city": "Москва",
        "latitude": 55.7558,
        "longitude": 37.6173,
        "timezone": "Europe/Moscow",
        "tzOffset": 3.0
    },
    "question": ""
}
req = urllib.request.Request(
    "http://127.0.0.1:8080/api/synastry",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST"
)
try:
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.load(r)
    print("HTTP", r.status)
    print("score:", data.get("score"))
    print("own:", data.get("own_name"), "| partner:", data.get("partner_name"))
    print("partner chart:", json.dumps(data.get("partner_chart"), ensure_ascii=False))
    print("aspects:", len(data.get("aspects") or []))
    for a in (data.get("aspects") or [])[:5]:
        print(f"  - {a['planet_a_ru']} — {a['planet_b_ru']}: {a['aspect']}, орб {a['orb']}°")
    print("overlay:", data.get("overlay"))
    print("=" * 60)
    print(data.get("answer", ""))
except urllib.error.HTTPError as e:
    print("HTTP", e.code)
    print(e.read().decode("utf-8", "replace")[:1500])
