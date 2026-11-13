#!/usr/bin/env python3
"""
Apply SQL migrations to the database.

Usage:
    python scripts/run_migrations.py
    python scripts/run_migrations.py --dry-run   # print SQL only

Reads DATABASE_URL from .env or environment.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()


MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


async def run(dry_run: bool = False) -> None:
    from app.config import settings

    if not settings.database_url:
        print("ERROR: DATABASE_URL is not set. Add it to .env")
        sys.exit(1)

    # Collect migration files in order
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        print("No migration files found in", MIGRATIONS_DIR)
        return

    print(f"Found {len(sql_files)} migration(s):\n")
    for f in sql_files:
        print(f"  • {f.name}")
    print()

    if dry_run:
        for f in sql_files:
            print(f"── {f.name} ──")
            print(f.read_text())
            print()
        print("(dry run — nothing executed)")
        return

    import asyncpg

    conn = await asyncpg.connect(dsn=settings.database_url, statement_cache_size=0)
    try:
        for f in sql_files:
            sql = f.read_text()
            print(f"Running {f.name} …", end=" ")
            try:
                await conn.execute(sql)
                print("✓")
            except Exception as exc:
                print(f"✗\n  {exc}")
                sys.exit(1)
    finally:
        await conn.close()

    print("\nAll migrations applied successfully.")


def main():
    p = argparse.ArgumentParser(description="Run SQL migrations")
    p.add_argument("--dry-run", action="store_true",
                   help="Print SQL without executing")
    args = p.parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
