"""Диагностика: сырой ответ /chat/completions — куда уходят токены."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio

from main import build_ai_messages
import config
from db import get_user_astro_context

import aiohttp


async def test_variant(name: str, extra: dict):
    ctx = await get_user_astro_context(6771600924)
    messages = build_ai_messages(ctx, "Деньги и карьера", "Какие партнёры мне подходят и на что обратить внимание?")
    payload = {"model": config.AI_MODEL, "messages": messages, "temperature": 0.8, "max_tokens": 1024}
    payload.update(extra)
    headers = {
        "Authorization": f"Bearer {config.PLUSVIBE_API_KEY}",
        "Content-Type": "application/json"
    }
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as s:
        async with s.post(f"{config.PLUSVIBE_BASE_URL}/chat/completions", headers=headers, json=payload) as r:
            data = await r.json()
    if "choices" not in data:
        print(f"[{name}] ошибка:", json.dumps(data, ensure_ascii=False)[:200])
        return
    choice = data["choices"][0]
    msg = choice["message"]
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or ""
    print(f"[{name}] finish={choice.get('finish_reason')} content={len(content)} reasoning={len(reasoning)} usage={data['usage']['completion_tokens']}")
    if content:
        print("   →", content[:200].replace("\n", " "))


async def main():
    await test_variant("A: max_tokens=4096", {"max_tokens": 4096})
    await test_variant("B: reasoning_effort=low, 2048", {"max_tokens": 2048, "reasoning_effort": "low"})
    await test_variant("C: reasoning off", {"max_tokens": 1024, "reasoning_effort": "none"})

asyncio.run(main())
