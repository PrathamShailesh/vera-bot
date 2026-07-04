# Vera Bot - magicpin AI Challenge Submission

## Overview

Vera Bot is an AI-powered merchant assistant that composes contextual messages for merchants across 5 categories: dentists, salons, restaurants, gyms, and pharmacies. The bot uses a 4-context framework (category, merchant, trigger, customer) to generate specific, relevant, and engaging messages.

## Architecture

### Core Components

1. **FastAPI HTTP Server** - Implements 5 required endpoints
2. **LLM-based Composer** - Uses OpenAI GPT-4o-mini for message composition
3. **Auto-reply Detection** - Identifies and handles WhatsApp Business auto-replies
4. **Intent Recognition** - Detects commitment and rejection signals
5. **Context Management** - In-memory storage for all context types

### Endpoints

- `GET /v1/healthz` - Liveness probe with context counts
- `GET /v1/metadata` - Bot identity and approach information
- `POST /v1/context` - Idempotent context push with version control
- `POST /v1/tick` - Periodic wake-up for proactive message initiation
- `POST /v1/reply` - Handle merchant/customer replies with action routing

## Message Composition Strategy

### LLM Prompt Engineering

The bot uses a structured prompt that includes:

1. **Category Context** - Voice tone, allowed vocabulary, taboos, peer stats
2. **Merchant Context** - Name, locality, performance metrics, active offers, signals
3. **Trigger Context** - Kind, urgency, payload details
4. **Customer Context** (optional) - Name, state, language preference

### Key Features

- **Specificity First**: Anchors messages on verifiable facts (numbers, dates, prices)
- **Category Voice Matching**: Adapts tone per category (clinical for dentists, warm for salons)
- **Trigger Relevance**: Explains "why now" for each message
- **Single Clear CTA**: Binary choice or open-ended question
- **Hindi-English Mix**: Natural code-mixing when Hindi is preferred
- **No Fabrications**: Only uses data from provided contexts

### Auto-reply Handling

Detects common auto-reply patterns:
- "Thank you for contacting"
- "Our team will respond shortly"
- "This is an automated message"

After 3 consecutive auto-replies, the bot gracefully ends the conversation.

### Intent Transition

Detects commitment signals:
- "let's do it", "go ahead", "proceed", "yes please"

When detected, switches from qualification mode to action mode immediately.

Detects rejection signals:
- "not interested", "stop messaging", "useless"

When detected, ends conversation gracefully.

## Setup

### Prerequisites

- Python 3.9+
- OpenAI API key

### Installation

```bash
pip install -r requirements.txt
```

### Configuration

Set environment variables:

```bash
export LLM_PROVIDER=openai
export LLM_API_KEY=your_openai_api_key
export LLM_MODEL=gpt-4o-mini
```

Or create a `.env` file:

```
LLM_PROVIDER=openai
LLM_API_KEY=your_openai_api_key
LLM_MODEL=gpt-4o-mini
```

## Running the Bot

### Local Development

```bash
python bot.py
```

Server runs on `http://localhost:8080`

### Using uvicorn directly

```bash
uvicorn bot:app --host 0.0.0.0 --port 8080 --reload
```

## Testing with Judge Simulator

1. Configure the judge simulator:

Edit `judge_simulator.py`:
```python
BOT_URL = "http://localhost:8080"
LLM_PROVIDER = "openai"
LLM_API_KEY = "your_openai_api_key"
LLM_MODEL = "gpt-4o-mini"
```

2. Run the simulator:

```bash
python judge_simulator.py
```

3. Test scenarios:
- `warmup` - Test context push and health checks
- `phase2_short` - Test tick and message composition
- `auto_reply_hell` - Test auto-reply detection
- `intent_transition` - Test intent handling
- `hostile` - Test rejection handling
- `all` - Run all scenarios

## Deployment

### Quick Deployment Options

1. **Render** (Recommended for free tier)
   - Connect GitHub repo
   - Set environment variables in Render dashboard
   - Deploy as web service

2. **Railway**
   - New project → Deploy from GitHub
   - Add environment variables
   - Railway handles the rest

3. **Fly.io**
   ```bash
   fly launch
   fly secrets set LLM_API_KEY=your_key
   fly deploy
   ```

4. **ngrok** (For local testing)
   ```bash
   ngrok http 8080
   ```

### Environment Variables Required

- `LLM_PROVIDER` - "openai" (default)
- `LLM_API_KEY` - Your OpenAI API key
- `LLM_MODEL` - Model to use (default: gpt-4o-mini)

## Tradeoffs

### Strengths

1. **Deterministic Composition** - Temperature=0 ensures consistent outputs
2. **Context-Aware** - Uses all 4 context dimensions effectively
3. **Robust Error Handling** - Fallback to rule-based composition if LLM fails
4. **Auto-reply Detection** - Prevents wasted turns on auto-replies
5. **Intent Recognition** - Quick action mode switching

### Limitations

1. **In-Memory Storage** - Contexts lost on restart (acceptable for challenge)
2. **Single LLM Provider** - Currently only OpenAI supported
3. **No Retrieval** - Digest items matched by ID, not semantic search
4. **Simple Fallback** - Rule-based fallback is basic

### Future Improvements

1. Add semantic search over digest items
2. Support multiple LLM providers (Anthropic, Gemini)
3. Add persistent storage (Redis/SQLite)
4. Implement conversation state machine
5. Add A/B testing for message variants

## Submission

### Public Bot URL

Deploy your bot and submit the public URL via the magicpin submission portal.

Example: `https://your-bot.vercel.app`

### What Judges Will Test

1. **Warmup** - Context loading and health checks
2. **Composition Quality** - 5-dimension scoring on 30 test pairs
3. **Adaptive Context** - Handling new context injected mid-test
4. **Replay Scenarios** - Auto-reply, intent transition, hostile handling

## Performance Targets

- **Response Time**: < 30s per endpoint (target: < 10s)
- **Uptime**: Must stay live during evaluation window
- **Determinism**: Same input → same output

## License

This submission is for the magicpin AI Challenge only.

## Contact

For questions about this submission, contact: bot@magicpin.ai
