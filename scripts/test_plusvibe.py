"""Быстрый тест PlusVibeAPI: /models и /chat/completions (sandbox)."""
import json
import urllib.error
import urllib.request

import config


def request(path: str, payload: dict | None = None):
    headers = {
        "Authorization": f"Bearer {config.PLUSVIBE_API_KEY}",
        "Content-Type": "application/json"
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        f"{config.PLUSVIBE_BASE_URL}{path}",
        data=data,
        headers=headers,
        method="POST" if payload is not None else "GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", "replace"))


# 1. Проверка ключа / режима
status, data = request("/models")
print(f"GET /models -> HTTP {status}: {json.dumps(data, ensure_ascii=False)[:300]}")

# 2. Тестовый чат
payload = {
    "model": config.AI_MODEL,
    "messages": [
        {"role": "system", "content": "Ты — тестовый ассистент. Отвечай кратко."},
        {"role": "user", "content": "Привет! Проверка связи. Ответь одним словом."}
    ],
    "max_tokens": 64
}
status, data = request("/chat/completions", payload)
print(f"\nPOST /chat/completions (model={config.AI_MODEL}) -> HTTP {status}")
if status == 200:
    msg = data["choices"][0]["message"]["content"]
    print("Ответ модели:", msg)
    print("finish_reason:", data["choices"][0].get("finish_reason"))
    print("_sandbox:", data.get("_sandbox"))
else:
    print(json.dumps(data, ensure_ascii=False)[:1000])
