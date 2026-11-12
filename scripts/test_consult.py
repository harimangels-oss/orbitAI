"""Тест эндпоинта /api/consult локального сервера (sandbox PlusVibe)."""
import json
import urllib.error
import urllib.request

payload = {
    "telegram_id": 6771600924,
    "topic": "Любовь и отношения",
    "question": "Какие партнёры мне подходят и на что обратить внимание в отношениях?"
}
req = urllib.request.Request(
    "http://127.0.0.1:8080/api/consult",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST"
)
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)
    print("HTTP", r.status)
    print("status:", data.get("status"))
    print("answer:")
    print(data.get("answer", "")[:600])
except urllib.error.HTTPError as e:
    print("HTTP", e.code)
    print(e.read().decode("utf-8", "replace")[:800])
