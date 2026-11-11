#!/usr/bin/env python3
"""
Keep-alive pinger for free-tier hosting (Render / Fly.io).
Pings /health every 5 minutes so the container doesn't sleep.

Usage:
    python scripts/keep_alive.py --url https://your-backend.onrender.com

Run this as a separate process, a cron job, or from a GitHub Action.
"""

from __future__ import annotations

import argparse
import time

import httpx


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True, help="Base URL of the backend")
    p.add_argument("--interval", type=int, default=300, help="Seconds between pings")
    args = p.parse_args()

    health_url = f"{args.url.rstrip('/')}/health"
    print(f"Pinging {health_url} every {args.interval}s …\n")

    while True:
        try:
            r = httpx.get(health_url, timeout=10)
            print(f"[{time.strftime('%H:%M:%S')}] {r.status_code} {r.json()}")
        except Exception as exc:
            print(f"[{time.strftime('%H:%M:%S')}] ERROR: {exc}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
