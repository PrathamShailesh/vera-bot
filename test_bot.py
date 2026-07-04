#!/usr/bin/env python3
"""
Simple test script to verify bot endpoints without full judge simulator.
Run this after starting the bot: py bot.py
"""

import json
import urllib.request
import urllib.error

BOT_URL = "http://localhost:8082"

def test_healthz():
    print("Testing /v1/healthz...")
    try:
        with urllib.request.urlopen(f"{BOT_URL}/v1/healthz", timeout=5) as response:
            data = json.loads(response.read().decode())
            print(f"✓ Healthz OK: {data}")
            return True
    except Exception as e:
        print(f"✗ Healthz failed: {e}")
        return False

def test_metadata():
    print("\nTesting /v1/metadata...")
    try:
        with urllib.request.urlopen(f"{BOT_URL}/v1/metadata", timeout=5) as response:
            data = json.loads(response.read().decode())
            print(f"✓ Metadata OK: {data}")
            return True
    except Exception as e:
        print(f"✗ Metadata failed: {e}")
        return False

def test_context_push():
    print("\nTesting /v1/context...")
    test_payload = {
        "scope": "category",
        "context_id": "test_category",
        "version": 1,
        "payload": {"slug": "test", "voice": {"tone": "professional"}},
        "delivered_at": "2026-04-26T10:00:00Z"
    }
    
    try:
        req = urllib.request.Request(
            f"{BOT_URL}/v1/context",
            data=json.dumps(test_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            print(f"✓ Context push OK: {data}")
            return True
    except Exception as e:
        print(f"✗ Context push failed: {e}")
        return False

def test_tick():
    print("\nTesting /v1/tick...")
    test_payload = {
        "now": "2026-04-26T10:00:00Z",
        "available_triggers": []
    }
    
    try:
        req = urllib.request.Request(
            f"{BOT_URL}/v1/tick",
            data=json.dumps(test_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            print(f"✓ Tick OK: {data}")
            return True
    except Exception as e:
        print(f"✗ Tick failed: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("Vera Bot Endpoint Test")
    print("=" * 50)
    
    results = []
    results.append(("Healthz", test_healthz()))
    results.append(("Metadata", test_metadata()))
    results.append(("Context Push", test_context_push()))
    results.append(("Tick", test_tick()))
    
    print("\n" + "=" * 50)
    print("Summary")
    print("=" * 50)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{name:20} {status}")
    
    all_passed = all(passed for _, passed in results)
    print("\n" + ("All tests passed!" if all_passed else "Some tests failed."))
