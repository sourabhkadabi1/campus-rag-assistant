"""
Helper script to test the running RAG Assistant backend on Windows or any OS.

Works around PowerShell's curl alias by sending proper HTTP requests directly.

Usage:
    python backend/scripts/test_ask.py health
    python backend/scripts/test_ask.py margin
    python backend/scripts/test_ask.py ask "What is normalization?"
    python backend/scripts/test_ask.py ask "Explain B-trees in detail"
    python backend/scripts/test_ask.py ask "Derive merge sort complexity" --thinking
"""

import sys
import json
import httpx

BASE_URL = "http://127.0.0.1:8000"


def test_health():
    print(f"\n--- Testing GET {BASE_URL}/health ---")
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=5.0)
        print(f"Status: {r.status_code}")
        print(json.dumps(r.json(), indent=2))
    except Exception as exc:
        print(f"Error connecting to backend: {exc}")
        print("Make sure uvicorn is running: uvicorn app.main:app --app-dir backend --reload --port 8000")


def test_margin():
    print(f"\n--- Testing GET {BASE_URL}/admin/margin ---")
    try:
        r = httpx.get(f"{BASE_URL}/admin/margin", timeout=5.0)
        print(f"Status: {r.status_code}")
        print(json.dumps(r.json(), indent=2))
    except Exception as exc:
        print(f"Error connecting to backend: {exc}")


def test_ask(question: str, thinking: bool = False, is_paid: bool = False):
    print(f"\n--- Testing POST {BASE_URL}/ask ---")
    print(f"Question: {question}")
    print(f"Thinking: {thinking} | Paid: {is_paid}")

    headers = {
        "Content-Type": "application/json",
        "X-User-Id": "00000000-0000-0000-0000-000000000001",
        "X-Semester": "3",
        "X-Department": "CSE",
    }
    payload = {
        "question": question,
        "thinking": thinking,
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            with client.stream("POST", f"{BASE_URL}/ask", json=payload, headers=headers) as response:
                print(f"HTTP Status: {response.status_code}")
                current_event = None
                for line in response.iter_lines():
                    if line.startswith("event: "):
                        current_event = line[7:].strip()
                    elif line.startswith("data: "):
                        data_str = line[6:].strip()
                        try:
                            data = json.loads(data_str)
                            if current_event == "token":
                                sys.stdout.write(data.get("text", ""))
                                sys.stdout.flush()
                            elif current_event == "filter":
                                print(f"\n[filter] subject={data.get('subject')}, chapter={data.get('chapter_no')}")
                            elif current_event == "route":
                                print(f"[route] {data.get('route')}")
                            elif current_event == "done":
                                print(f"\n[done] units_charged={data.get('units_charged')}, detailed={data.get('detected_detailed')}, thinking={data.get('thinking_mode')}, hint={data.get('hint')}")
                            elif current_event == "error":
                                print(f"\n[error] {data.get('error')}")
                        except Exception:
                            print(f"\n[{current_event}] {data_str}")
        print()
    except Exception as exc:
        print(f"Error connecting to backend: {exc}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "health":
        test_health()
    elif args[0] == "margin":
        test_margin()
    elif args[0] == "ask":
        q = args[1] if len(args) > 1 else "What is normalization?"
        th = "--thinking" in args
        test_ask(q, thinking=th)
    else:
        test_health()
        test_margin()
        test_ask("What is normalization?")
