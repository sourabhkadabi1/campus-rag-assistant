#!/usr/bin/env python3
"""
List available model IDs from Gemini and Groq APIs.

Usage:
    python scripts/list_models.py

Requires GEMINI_API_KEY and/or GROQ_API_KEY in .env or environment.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Allow running from the backend/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed.  Run: pip install httpx")
    sys.exit(1)

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


def list_gemini_models() -> list[str]:
    """Fetch model IDs from the Gemini 'list models' endpoint."""
    if not GEMINI_API_KEY:
        print("[Gemini] GEMINI_API_KEY not set — skipping\n")
        return []

    url = "https://generativelanguage.googleapis.com/v1beta/models"
    try:
        resp = httpx.get(url, params={"key": GEMINI_API_KEY}, timeout=30)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"[Gemini] API error: {exc}\n")
        return []

    models = resp.json().get("models", [])
    ids = sorted(m.get("name", "").removeprefix("models/") for m in models)

    print(f"[Gemini] {len(ids)} models available:")
    for mid in ids:
        print(f"  • {mid}")
    print()
    return ids


def list_groq_models() -> list[str]:
    """Fetch model IDs from the Groq 'list models' endpoint."""
    if not GROQ_API_KEY:
        print("[Groq] GROQ_API_KEY not set — skipping\n")
        return []

    url = "https://api.groq.com/openai/v1/models"
    try:
        resp = httpx.get(
            url,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            timeout=30,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"[Groq] API error: {exc}\n")
        return []

    models = resp.json().get("data", [])
    ids = sorted(m.get("id", "") for m in models)

    print(f"[Groq] {len(ids)} models available:")
    for mid in ids:
        print(f"  • {mid}")
    print()
    return ids


def main():
    print("=" * 60)
    print("  Model ID Discovery")
    print("=" * 60 + "\n")

    gemini_ids = list_gemini_models()
    groq_ids = list_groq_models()

    # Cross-check with MODEL_CHAIN
    model_chain_raw = os.getenv(
        "MODEL_CHAIN",
        "gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-2.5-flash-lite,"
        "gemini-3.6-flash,gemini-3.8-flash,gemma-4-26b,gemma-4-31b,"
        "groq:openai/gpt-oss-20b",
    )
    chain = [m.strip() for m in model_chain_raw.split(",") if m.strip()]

    print("-" * 60)
    print("MODEL_CHAIN verification:\n")
    for entry in chain:
        if entry.startswith("groq:"):
            groq_id = entry.removeprefix("groq:")
            found = groq_id in groq_ids
            status = "✓ found" if found else "✗ NOT FOUND"
            print(f"  {entry:40s}  {status}  (Groq)")
        else:
            found = entry in gemini_ids
            status = "✓ found" if found else "✗ NOT FOUND"
            if not found and gemini_ids:
                # Suggest closest match
                close = [g for g in gemini_ids if entry.split("-")[0] in g]
                if close:
                    print(f"  {entry:40s}  {status}  (Gemini)  — try: {close[:3]}")
                    continue
            print(f"  {entry:40s}  {status}  (Gemini)")

    print()


if __name__ == "__main__":
    main()
