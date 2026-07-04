#!/usr/bin/env python3
"""
Vera Bot - magicpin AI Challenge
==================================
A merchant AI assistant that composes contextual messages based on
category, merchant, trigger, and customer contexts.

Endpoints:
- GET /v1/healthz - Liveness probe
- GET /v1/metadata - Bot identity
- POST /v1/context - Receive context pushes
- POST /v1/tick - Periodic wake-up, bot can initiate
- POST /v1/reply - Receive replies from simulated merchant/customer
"""

import os
import time
import re
import json
from datetime import datetime
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field

from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel

# =============================================================================
# CONFIGURATION
# =============================================================================
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")

# =============================================================================
# FASTAPI APP
# =============================================================================
app = FastAPI(title="Vera Bot", version="1.0.0")
START_TIME = time.time()

# =============================================================================
# IN-MEMORY STORAGE
# =============================================================================
# Context storage: (scope, context_id) -> {version, payload}
contexts: Dict[tuple, Dict] = {}
# Conversation storage: conversation_id -> {turns: [], intent: str, action_data: {}}
conversations: Dict[str, Dict] = {}
# Suppression tracking: suppression_key -> timestamp sent
suppression_log: Dict[str, float] = {}
# Auto-reply detection: conversation_id -> {count, last_message}
auto_reply_tracker: Dict[str, Dict] = {}

# =============================================================================
# PYDANTIC MODELS
# =============================================================================
class ContextBody(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: Dict[str, Any]
    delivered_at: str

class TickBody(BaseModel):
    now: str
    available_triggers: List[str] = []

class ReplyBody(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str
    message: str
    received_at: str
    turn_number: int

# =============================================================================
# LLM PROVIDER INTERFACE
# =============================================================================
class LLMProvider:
    """Base class for LLM providers."""
    
    def complete(self, prompt: str, system: str = None) -> str:
        raise NotImplementedError

class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
    
    def complete(self, prompt: str, system: str = None) -> str:
        import urllib.request
        import urllib.error
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,  # Deterministic
            "max_tokens": 1000
        }).encode("utf-8")
        
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )
        
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            raise Exception(f"OpenAI API error: {e.code} - {e.read().decode()}")

class OpenRouterProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
    
    def complete(self, prompt: str, system: str = None) -> str:
        import urllib.request
        import urllib.error
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,  # Deterministic
            "max_tokens": 1000
        }).encode("utf-8")
        
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://magicpin.ai",
                "X-Title": "Vera Bot"
            }
        )
        
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            raise Exception(f"OpenRouter API error: {e.code} - {e.read().decode()}")

# Global LLM instance
llm_provider: Optional[LLMProvider] = None

def get_llm_provider() -> LLMProvider:
    global llm_provider
    if llm_provider is None:
        if LLM_PROVIDER == "openai":
            llm_provider = OpenAIProvider(LLM_API_KEY, LLM_MODEL)
        elif LLM_PROVIDER == "openrouter":
            llm_provider = OpenRouterProvider(LLM_API_KEY, LLM_MODEL)
        else:
            # Fallback to OpenRouter if no provider specified
            llm_provider = OpenRouterProvider(LLM_API_KEY, LLM_MODEL)
    return llm_provider

# =============================================================================
# AUTO-REPLY DETECTION
# =============================================================================
AUTO_REPLY_PATTERNS = [
    r"thank you for contacting",
    r"our team will respond shortly",
    r"this is an automated message",
    r"we will get back to you",
    r"your message is important",
]

def is_auto_reply(message: str) -> bool:
    """Detect if message is likely an auto-reply."""
    message_lower = message.lower()
    for pattern in AUTO_REPLY_PATTERNS:
        if re.search(pattern, message_lower):
            return True
    return False

def track_auto_reply(conversation_id: str, message: str) -> int:
    """Track auto-reply occurrences, return count."""
    if not is_auto_reply(message):
        # Reset if real message
        if conversation_id in auto_reply_tracker:
            del auto_reply_tracker[conversation_id]
        return 0
    
    tracker = auto_reply_tracker.get(conversation_id, {"count": 0})
    tracker["count"] += 1
    auto_reply_tracker[conversation_id] = tracker
    return tracker["count"]

# =============================================================================
# INTENT DETECTION
# =============================================================================
INTENT_COMMITMENT_PATTERNS = [
    r"\byes\b",
    r"\byeah\b",
    r"\byep\b",
    r"\bsure\b",
    r"\bokay\b",
    r"\bok\b",
    r"\bdo it\b",
    r"let'?s do it",
    r"let'?s promote",
    r"sounds good",
    r"\bfine\b",
    r"please do",
    r"go ahead",
    r"proceed",
    r"yes please",
    r"confirm",
    r"start",
    r"send it",
]

def is_commitment_intent(message: str) -> bool:
    """Detect if merchant has committed to action."""
    message_lower = message.lower()
    for pattern in INTENT_COMMITMENT_PATTERNS:
        if re.search(pattern, message_lower):
            return True
    return False

INTENT_REJECTION_PATTERNS = [
    r"not interested",
    r"stop messaging",
    r"don'?t send",
    r"no more",
    r"leave me alone",
    r"useless",
    r"spam",
]

def is_rejection_intent(message: str) -> bool:
    """Detect if merchant is rejecting."""
    message_lower = message.lower()
    for pattern in INTENT_REJECTION_PATTERNS:
        if re.search(pattern, message_lower):
            return True
    return False

# =============================================================================
# MESSAGE COMPOSITION
# =============================================================================
def compose_message(
    category: Dict,
    merchant: Dict,
    trigger: Dict,
    customer: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Compose a message using LLM based on the 4 contexts.
    Returns dict with body, cta, send_as, suppression_key, rationale.
    """
    
    # Extract key information
    category_slug = category.get("slug", "")
    merchant_name = merchant.get("identity", {}).get("name", "")
    owner_name = merchant.get("identity", {}).get("owner_first_name", "")
    locality = merchant.get("identity", {}).get("locality", "")
    languages = merchant.get("identity", {}).get("languages", ["en"])
    
    # Performance metrics
    perf = merchant.get("performance", {})
    views = perf.get("views", 0)
    calls = perf.get("calls", 0)
    ctr = perf.get("ctr", 0)
    
    # Active offers
    active_offers = [
        o.get("title") for o in merchant.get("offers", [])
        if o.get("status") == "active"
    ]
    
    # Signals
    signals = merchant.get("signals", [])
    
    # Trigger info
    trigger_kind = trigger.get("kind", "")
    trigger_payload = trigger.get("payload", {})
    trigger_urgency = trigger.get("urgency", 1)
    
    # Category voice
    voice = category.get("voice", {})
    tone = voice.get("tone", "professional")
    vocab_allowed = voice.get("vocab_allowed", [])
    vocab_taboo = voice.get("vocab_taboo", [])
    
    # Digest items (for research/compliance triggers)
    digest_items = category.get("digest", [])
    digest_item = None
    if trigger_kind in ["research_digest", "regulation_change", "cde_opportunity"]:
        top_item_id = trigger_payload.get("top_item_id") or trigger_payload.get("digest_item_id")
        if top_item_id:
            digest_item = next((d for d in digest_items if d.get("id") == top_item_id), None)
    
    # Customer context (if present)
    customer_name = ""
    customer_state = ""
    customer_lang_pref = ""
    if customer:
        customer_name = customer.get("identity", {}).get("name", "")
        customer_state = customer.get("state", "")
        customer_lang_pref = customer.get("identity", {}).get("language_pref", "en")
    
    # Determine send_as
    send_as = "merchant_on_behalf" if customer else "vera"
    
    # Determine language preference
    use_hindi = "hi" in languages or (customer and "hi" in customer_lang_pref)
    
    # Build the prompt
    # IMPORTANT: The recipient is the MERCHANT, not customers (unless customer context is provided)
    recipient = f"{owner_name} (owner of {merchant_name})" if owner_name else f"owner of {merchant_name}"
    
    prompt = f"""You are Vera, magicpin's AI assistant for merchants. Compose a WhatsApp message.

CONTEXT:
Category: {category_slug}
Voice tone: {tone}
Allowed vocabulary: {', '.join(vocab_allowed[:5])}
Taboo words: {', '.join(vocab_taboo[:3])}

Merchant: {merchant_name}
Owner: {owner_name}
Locality: {locality}
Languages: {', '.join(languages)}
Performance: {views} views, {calls} calls, {ctr:.1%} CTR
Active offers: {', '.join(active_offers) if active_offers else 'None'}
Signals: {', '.join(signals[:3])}

Trigger: {trigger_kind}
Urgency: {trigger_urgency}/5
Trigger details: {json.dumps(trigger_payload, ensure_ascii=False)[:200]}

"""

    if digest_item:
        prompt += f"""
Research/Compliance item:
Title: {digest_item.get('title', '')}
Source: {digest_item.get('source', '')}
Summary: {digest_item.get('summary', '')[:150]}
"""

    if customer:
        prompt += f"""
Customer: {customer_name}
State: {customer_state}
Language preference: {customer_lang_pref}
"""

    prompt += f"""

REQUIREMENTS:
1. RECIPIENT: You are messaging {recipient}, not customers. Address the merchant/owner directly.
2. Be SPECIFIC - use real numbers, dates, prices from the context
3. Match category voice - {tone}
4. Explain WHY NOW - connect to the trigger
5. Recommend BUSINESS ACTIONS (promote offers, improve listing, reply to customers, etc.)
6. Single clear CTA - binary choice or open-ended question
7. Keep it concise - under 160 chars ideal, max 320 chars
8. Use Hindi-English mix naturally if Hindi is preferred
9. No fabrications - only use data from context
10. No taboo words: {', '.join(vocab_taboo)}

Return JSON only:
{{
  "body": "<message text>",
  "cta": "binary_yes_no" | "open_ended" | "multi_choice_slot" | "none",
  "rationale": "<why this message, what it achieves>"
}}
"""

    system_prompt = f"""You are Vera, a helpful AI assistant for Indian merchants. 
You compose contextual, specific messages that help merchants make business decisions.
Be concise, specific, and respectful. Match the merchant's language preference.
Category: {category_slug}, Tone: {tone}."""

    try:
        llm = get_llm_provider()
        response = llm.complete(prompt, system_prompt)
        
        # Parse JSON response
        match = re.search(r'\{[\s\S]*\}', response)
        if match:
            result = json.loads(match.group())
            body = result.get("body", "")
            cta = result.get("cta", "open_ended")
            rationale = result.get("rationale", "")
        else:
            # Fallback if JSON parsing fails
            body = response.strip()
            cta = "open_ended"
            rationale = "LLM response parsing failed, using raw output"
        
        # Generate suppression key
        suppression_key = trigger.get("suppression_key", f"{trigger_kind}:{merchant.get('merchant_id', '')}")
        
        return {
            "body": body,
            "cta": cta,
            "send_as": send_as,
            "suppression_key": suppression_key,
            "rationale": rationale
        }
        
    except Exception as e:
        # Fallback to rule-based composition
        return fallback_compose(category, merchant, trigger, customer)

def fallback_compose(
    category: Dict,
    merchant: Dict,
    trigger: Dict,
    customer: Optional[Dict] = None
) -> Dict[str, Any]:
    """Fallback rule-based composition if LLM fails."""
    
    merchant_name = merchant.get("identity", {}).get("name", "")
    owner_name = merchant.get("identity", {}).get("owner_first_name", "")
    trigger_kind = trigger.get("kind", "")
    
    if customer:
        customer_name = customer.get("identity", {}).get("name", "")
        body = f"Hi {customer_name}, checking in from {merchant_name}. How can we help you today?"
        cta = "open_ended"
        send_as = "merchant_on_behalf"
    else:
        body = f"Hi {owner_name}, quick update from Vera. Your profile has {merchant.get('performance', {}).get('views', 0)} views this month. Want tips to improve?"
        cta = "binary_yes_no"
        send_as = "vera"
    
    return {
        "body": body,
        "cta": cta,
        "send_as": send_as,
        "suppression_key": trigger.get("suppression_key", f"{trigger_kind}:fallback"),
        "rationale": "Fallback rule-based composition due to LLM error"
    }

# =============================================================================
# ENDPOINTS
# =============================================================================
@app.get("/v1/healthz")
async def healthz():
    """Liveness probe."""
    counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
    for (scope, _), _ in contexts.items():
        counts[scope] = counts.get(scope, 0) + 1
    
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME),
        "contexts_loaded": counts
    }

@app.get("/v1/metadata")
async def metadata():
    """Bot identity."""
    return {
        "team_name": "Vera Bot",
        "team_members": ["AI Assistant"],
        "model": LLM_MODEL,
        "approach": "LLM-based composition with auto-reply detection and intent handling",
        "contact_email": "bot@magicpin.ai",
        "version": "1.0.0",
        "submitted_at": datetime.utcnow().isoformat() + "Z"
    }

@app.post("/v1/context")
async def push_context(body: ContextBody):
    """Receive context push."""
    key = (body.scope, body.context_id)
    cur = contexts.get(key)
    
    # Idempotent check
    if cur and cur["version"] >= body.version:
        return {
            "accepted": False,
            "reason": "stale_version",
            "current_version": cur["version"]
        }
    
    # Store context
    contexts[key] = {
        "version": body.version,
        "payload": body.payload
    }
    
    return {
        "accepted": True,
        "ack_id": f"ack_{body.context_id}_v{body.version}",
        "stored_at": datetime.utcnow().isoformat() + "Z"
    }

@app.post("/v1/tick")
async def tick(body: TickBody):
    """Periodic wake-up - bot can initiate messages."""
    actions = []
    
    for trg_id in body.available_triggers:
        # Check if already suppressed
        trg_key = ("trigger", trg_id)
        trg = contexts.get(trg_key, {}).get("payload", {})
        
        if not trg:
            continue
        
        suppression_key = trg.get("suppression_key", "")
        if suppression_key in suppression_log:
            # Already sent recently, skip
            continue
        
        merchant_id = trg.get("merchant_id")
        if not merchant_id:
            continue
        
        # Get merchant context
        merchant = contexts.get(("merchant", merchant_id), {}).get("payload", {})
        if not merchant:
            continue
        
        # Get category context
        category_slug = merchant.get("category_slug", "")
        category = contexts.get(("category", category_slug), {}).get("payload", {})
        if not category:
            continue
        
        # Get customer context if applicable
        customer_id = trg.get("customer_id")
        customer = None
        if customer_id:
            customer = contexts.get(("customer", customer_id), {}).get("payload", {})
        
        # Compose message
        try:
            composed = compose_message(category, merchant, trg, customer)
            
            # Generate conversation ID
            conv_id = f"conv_{merchant_id}_{trg_id}"
            
            # Build action
            action = {
                "conversation_id": conv_id,
                "merchant_id": merchant_id,
                "customer_id": customer_id,
                "send_as": composed["send_as"],
                "trigger_id": trg_id,
                "template_name": f"vera_{trg.get('kind', 'generic')}_v1",
                "template_params": [merchant.get("identity", {}).get("name", "")],
                "body": composed["body"],
                "cta": composed["cta"],
                "suppression_key": composed["suppression_key"],
                "rationale": composed["rationale"]
            }
            
            actions.append(action)
            
            # Log suppression
            suppression_log[suppression_key] = time.time()
            
            # Initialize conversation with intent and action data
            conversations[conv_id] = {
                "turns": [{
                    "from": "vera",
                    "body": composed["body"],
                    "ts": datetime.utcnow().isoformat() + "Z"
                }],
                "intent": trg.get("kind", "generic"),
                "action_data": {
                    "trigger_id": trg_id,
                    "merchant_id": merchant_id,
                    "offer": merchant.get("offers", [{}])[0].get("title", "") if merchant.get("offers") else ""
                }
            }
            
        except Exception as e:
            # Log error but continue with other triggers
            print(f"Error composing for {trg_id}: {e}")
            continue
    
    return {"actions": actions}

@app.post("/v1/reply")
async def reply(body: ReplyBody):
    """Receive reply from simulated merchant/customer."""
    conv_id = body.conversation_id
    message = body.message
    merchant_id = body.merchant_id
    
    # Track conversation
    if conv_id not in conversations:
        conversations[conv_id] = {
            "turns": [],
            "intent": None,
            "action_data": {}
        }
    
    conversations[conv_id]["turns"].append({
        "from": body.from_role,
        "body": message,
        "ts": body.received_at
    })
    
    # Check for auto-reply
    if is_auto_reply(message):
        # Track by merchant_id since judge uses different conversation IDs
        merchant_key = body.merchant_id or conv_id
        tracker = auto_reply_tracker.get(merchant_key, {"count": 0})
        tracker["count"] += 1
        auto_reply_tracker[merchant_key] = tracker
        
        if tracker["count"] >= 3:
            # End conversation after 3 auto-replies
            return {
                "action": "end",
                "rationale": "Auto-reply detected 3 times consecutively. Ending conversation."
            }
        else:
            # Wait for owner to respond
            return {
                "action": "wait",
                "wait_seconds": 14400,  # 4 hours
                "rationale": "Auto-reply detected. Waiting for owner to respond."
            }
    else:
        # Reset counter on real message
        merchant_key = body.merchant_id or conv_id
        if merchant_key in auto_reply_tracker:
            del auto_reply_tracker[merchant_key]
    
    # Check for rejection
    if is_rejection_intent(message):
        return {
            "action": "end",
            "rationale": "Merchant expressed disinterest. Closing conversation gracefully."
        }
    
    # Check for commitment - switch to action mode
    if is_commitment_intent(message):
        # Use stored intent from conversation for deterministic response
        conv_data = conversations.get(conv_id, {})
        stored_intent = conv_data.get("intent", "generic")
        action_data = conv_data.get("action_data", {})
        
        # Load merchant context for contextual commitment response
        if merchant_id:
            merchant_ctx = contexts.get(("merchant", merchant_id))
            if merchant_ctx:
                merchant_payload = merchant_ctx["payload"]
                merchant_name = merchant_payload.get("identity", {}).get("name", "")
                offer = action_data.get("offer", "")
                
                # Build contextual response based on stored intent
                if stored_intent == "sales_dip" or "promote" in stored_intent.lower():
                    offer_text = f" {offer}" if offer else ""
                    response_body = f"Perfect! I'll start promoting{offer_text} to nearby customers right away. I'll update you once it's live."
                elif stored_intent == "listing_issue" or "improve" in stored_intent.lower():
                    response_body = f"Great! I'll help improve your {merchant_name} listing. I'll start working on it now."
                elif stored_intent == "new_offer" or "create" in stored_intent.lower():
                    response_body = f"Excellent! I'll create a new offer for {merchant_name}. I'll update you once it's ready."
                else:
                    response_body = f"Excellent! I'll proceed with this action for {merchant_name}. I'll update you once it's done."
                
                return {
                    "action": "send",
                    "body": response_body,
                    "cta": "none",
                    "rationale": f"Merchant committed to action. Executing stored intent: {stored_intent}"
                }
        
        # Fallback generic response
        return {
            "action": "send",
            "body": "Great! Proceeding with the action. I'll update you once it's done.",
            "cta": "none",
            "rationale": "Merchant committed to action. Switching to execution mode."
        }
    
    # Default: acknowledge and continue
    return {
        "action": "send",
        "body": "Got it. Let me know how you'd like to proceed.",
        "cta": "open_ended",
        "rationale": "Acknowledged merchant response. Awaiting further direction."
    }

# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    import uvicorn
    import sys
    import os
    # Use PORT environment variable if set (Render provides this), otherwise default to 8080
    port = int(os.getenv("PORT", sys.argv[1])) if len(sys.argv) > 1 else int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
