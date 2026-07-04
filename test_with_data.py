#!/usr/bin/env python3
"""
Test bot with actual dataset data.
This loads real contexts and tests message composition.
"""

import json
import urllib.request
import urllib.error
from pathlib import Path

BOT_URL = "http://localhost:8082"
DATASET_DIR = Path("dataset")

def push_category_context(slug):
    """Push a category context."""
    cat_file = DATASET_DIR / "categories" / f"{slug}.json"
    with open(cat_file) as f:
        payload = json.load(f)
    
    body = {
        "scope": "category",
        "context_id": slug,
        "version": 1,
        "payload": payload,
        "delivered_at": "2026-04-26T10:00:00Z"
    }
    
    req = urllib.request.Request(
        f"{BOT_URL}/v1/context",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode())

def push_merchant_context(merchant_id):
    """Push a merchant context."""
    merchant_file = DATASET_DIR / "merchants_seed.json"
    with open(merchant_file) as f:
        data = json.load(f)
    
    merchant = next((m for m in data["merchants"] if m["merchant_id"] == merchant_id), None)
    if not merchant:
        raise ValueError(f"Merchant {merchant_id} not found")
    
    body = {
        "scope": "merchant",
        "context_id": merchant_id,
        "version": 1,
        "payload": merchant,
        "delivered_at": "2026-04-26T10:00:00Z"
    }
    
    req = urllib.request.Request(
        f"{BOT_URL}/v1/context",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode())

def push_trigger_context(trigger_id):
    """Push a trigger context."""
    trigger_file = DATASET_DIR / "triggers_seed.json"
    with open(trigger_file) as f:
        data = json.load(f)
    
    trigger = next((t for t in data["triggers"] if t["id"] == trigger_id), None)
    if not trigger:
        raise ValueError(f"Trigger {trigger_id} not found")
    
    body = {
        "scope": "trigger",
        "context_id": trigger_id,
        "version": 1,
        "payload": trigger,
        "delivered_at": "2026-04-26T10:00:00Z"
    }
    
    req = urllib.request.Request(
        f"{BOT_URL}/v1/context",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode())

def test_tick_with_trigger(trigger_id):
    """Test tick endpoint with a specific trigger."""
    body = {
        "now": "2026-04-26T10:00:00Z",
        "available_triggers": [trigger_id]
    }
    
    req = urllib.request.Request(
        f"{BOT_URL}/v1/tick",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode())

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Vera Bot with Real Dataset")
    print("=" * 60)
    
    try:
        # Test with Dr. Meera's dental clinic
        print("\n1. Pushing category context (dentists)...")
        result = push_category_context("dentists")
        print(f"   ✓ Category pushed: {result['accepted']}")
        
        print("\n2. Pushing merchant context (Dr. Meera)...")
        result = push_merchant_context("m_001_drmeera_dentist_delhi")
        print(f"   ✓ Merchant pushed: {result['accepted']}")
        
        print("\n3. Pushing trigger context (research digest)...")
        result = push_trigger_context("trg_001_research_digest_dentists")
        print(f"   ✓ Trigger pushed: {result['accepted']}")
        
        print("\n4. Testing tick with trigger...")
        result = test_tick_with_trigger("trg_001_research_digest_dentists")
        
        actions = result.get("actions", [])
        print(f"   ✓ Tick returned {len(actions)} action(s)")
        
        if actions:
            print("\n   Generated message:")
            for action in actions:
                print(f"   Body: {action.get('body', '')[:100]}...")
                print(f"   CTA: {action.get('cta', '')}")
                print(f"   Rationale: {action.get('rationale', '')[:80]}...")
        else:
            print("   Note: No actions returned (may need LLM API key for composition)")
        
        print("\n" + "=" * 60)
        print("Dataset test completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
