"""Печать последнего полного ответа астролога из БД."""
import os
import sqlite3
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "astro.db")
c = sqlite3.connect(db_path)
row = c.execute(
    "SELECT message FROM chat_history WHERE role='assistant' ORDER BY id DESC LIMIT 1"
).fetchone()
print(row[0])
