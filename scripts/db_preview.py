"""Быстрый просмотр содержимого astro.db: таблицы, схема, превью данных."""
import sqlite3
import sys

con = sqlite3.connect("astro.db")
cur = con.cursor()

tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
print("Таблицы:", tables)
print()
for table in tables:
    print("=" * 60)
    print(f"Таблица: {table}")
    cur.execute(f"PRAGMA table_info({table})")
    cols = [(r[1], r[2]) for r in cur.fetchall()]
    for name, ctype in cols:
        print(f"  {name} ({ctype})")
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    count = cur.fetchone()[0]
    print(f"  --- строк: {count}")
    if count and (len(sys.argv) < 2 or sys.argv[1] == "--rows"):
        cur.execute(f"SELECT * FROM {table} LIMIT 5")
        colnames = [c[0] for c in cur.description]
        for row in cur.fetchall():
            print(" ")
            for n, v in zip(colnames, row):
                text = str(v)
                text = text if len(text) <= 300 else text[:300] + "…"
                print(f"    {n}: {text}")
    print()

con.close()
