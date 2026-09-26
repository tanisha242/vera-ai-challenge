# Vera — magicpin AI Challenge Assistant

Vera is an autonomous, vertical-aware merchant AI assistant built for the **magicpin AI Challenge**. Vera drives proactive customer engagement and handles incoming turn interactions across five key SMB retail and services categories in India: Restaurants, Gyms, Salons, Dentists, and Pharmacies.

---

## 1. Project Overview & Problem Statement

Merchant engagement on WhatsApp requires precise domain context, timely proactive outreach, and accurate conversational handling without introducing hallucinations, spamming customers, or sending invalid messages.

Vera addresses these challenges through:
- **Scope-Isolated Context Storage**: Dynamic context updates across categories, merchants, customers, and triggers with atomic optimistic versioning.
- **Deduplication & Suppression**: Synthesized suppression keys (`{merchant_id}:{trigger_id}`), configurable suppression windows, and persistent opt-out handling (`STOP`, `UNSUBSCRIBE`).
- **Domain-Aware Vertical Safeguards**: Programmatic rules for 5 vertical categories designed to enforce domain-specific constraints (e.g., medical taboo word filtering for dentists, pharmacy batch recall alerts, gym seasonal reframing).
- **Canned Auto-Reply Loop Suppression**: Detection of merchant bot auto-replies across turns to prevent infinite looping.
- **Hybrid Rule-Based + Optional LLM Architecture**: Operates in deterministic rule-based mode by default, with an optional provider-agnostic LLM message composition layer (`OpenAI`, `Anthropic`, `Gemini`, `DeepSeek`, `Groq`) paired with instant fallback.

---

## 2. Architecture & Main Components

```
                     ┌───────────────────────────────┐
                     │   FastAPI Endpoints (main.py) │
                     └───────────────┬───────────────┘
                                     │
                     ┌───────────────▼───────────────┐
                     │  Vera Engine (controller.py)  │
                     └───────┬───────────────┬───────┘
                             │               │
      ┌──────────────────────▼──────┐   ┌────▼─────────────────────────┐
      │  ContextStore (store.py)    │   │ SuppressionEngine            │
      │  - Scope Isolation          │   │ (suppression.py)             │
      │  - Optimistic Versioning    │   │ - Key Deduplication & Expiry │
      └─────────────────────────────┘   │ - Explicit Opt-Out Tracking  │
                                        └──────────────────────────────┘
                             │
      ┌──────────────────────▼─────────────────────────┐
      │  DecisionEngine & State Machine                │
      │  - Urgency Ranking & Trigger Freshness         │
      │  - Turn State & Bot Auto-Reply Loop Protection │
      └──────────────────────┬─────────────────────────┘
                             │
      ┌──────────────────────▼─────────────────────────┐
      │  HybridMessageComposer (composer/)             │
      │  - Optional Provider-Agnostic LLM              │
      │  - Deterministic Vertical Domain Strategies    │
      │  - Taboo & Price Factual Grounding Validation │
      └────────────────────────────────────────────────┘
```

### Module Overview
- **`main.py`**: FastAPI application exposing `/v1/healthz`, `/v1/metadata`, `/v1/context`, `/v1/tick`, `/v1/reply`, and `/v1/teardown`.
- **`config.py`**: Centralized system configurations, environment variable defaults, bot metadata placeholders, and LLM toggles.
- **`core/models.py`**: Pydantic data schemas for contexts, triggers, actions, API payloads, and response models.
- **`core/store.py`**: Thread-safe in-memory store for contexts (`category`, `merchant`, `customer`, `trigger`) with version checking (`stale_conflict`).
- **`core/suppression.py`**: Deduplication state, key expiry manager, and opt-out memory.
- **`engine/decision.py`**: Decision engine filtering triggers based on freshness, opt-out consent, suppression keys, and ranking by urgency.
- **`engine/state_machine.py`**: Conversation turn state machine (`INITIAL`, `ENGAGED`, `OPTED_OUT`, `HANDOFF`), auto-reply detection counter per merchant, and intent classification.
- **`engine/controller.py`**: Main `VeraEngine` coordinator linking store, suppression, state machine, decision engine, and composer.
- **`strategies/`**: Vertical strategies (`restaurant.py`, `gym.py`, `salon.py`, `dentist.py`, `pharmacy.py`) handling domain reframing, taboo words, and factual grounding.
- **`composer/`**: `MessageComposer` and `LLMComposer` supporting deterministic formatting, URL sanitization, CTA verification, and LLM output validation.
- **`judge_simulator.py`**: Local judge simulator running evaluation benchmark scenarios.

---

## 3. Decision & Action Flow

### 1. Context Update (`POST /v1/context`)
When a context push arrives:
1. `ContextStore` checks the scope (`category`, `merchant`, `customer`, `trigger`).
2. Validates atomic versioning: if `version <= existing_version`, rejects with `409 Conflict` (`stale_version`).
3. Stores update and returns `200 OK` (`ContextPushAck`).

### 2. Proactive Tick (`POST /v1/tick`)
When the system ticks at timestamp $T$:
1. Evaluates available active triggers against current store contexts.
2. Filters out expired triggers (`expires_at < T`), suppressed triggers (active key window), and opted-out entities.
3. Ranks remaining triggers by urgency score.
4. Generates proactive `Action` items with grounded body text, CTA, template params, and suppression keys.

### 3. Turn Reply (`POST /v1/reply`)
When a user or merchant replies:
1. State machine evaluates incoming role (`merchant` or `customer`) and message content.
2. Checks for opt-out intent (`STOP`, `UNSUBSCRIBE`) and transitions state to `OPTED_OUT`.
3. Detects automated canned bot replies; if consecutive canned responses reach threshold ($\ge 2$), auto-replies are suppressed to prevent bot-to-bot loops.
4. Returns `ReplyResponse` containing action (`send`, `wait`, `end`), message body, CTA, and rationale.

---

## 4. Environment & Setup Instructions

### Environment Prerequisites
- Python 3.10+ (Python 3.11 recommended)
- Windows PowerShell / Command Prompt / Linux Terminal

### Setup Steps (Windows PowerShell)

1. **Navigate to Project Directory**:
   ```powershell
   cd d:\magicpin-ai-challenge
   ```

2. **Activate Existing Virtual Environment**:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

3. **Install / Verify Dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```

4. **Run Server**:
   ```powershell
   python main.py
   ```
   *The server runs locally at `http://0.0.0.0:8080` by default.*

---

## 5. API Endpoints & Request/Response Examples

*(Note: Request and response payloads below use illustrative example data.)*

### `GET /v1/healthz`
Liveness check returning process uptime and active context counts per scope.

**Illustrative Response (`200 OK`)**:
```json
{
  "status": "ok",
  "uptime_seconds": 124,
  "contexts_loaded": {
    "category": 5,
    "merchant": 10,
    "customer": 25,
    "trigger": 0
  }
}
```

---

### `GET /v1/metadata`
Returns bot metadata including team name, model identifier, approach summary, and contact information.

*(Note: Values shown are configurable defaults set in `config.py` / environment variables. Update with actual credentials prior to final submission.)*

**Illustrative Response (`200 OK`)**:
```json
{
  "team_name": "Team Vera",
  "team_members": ["Vera Developer"],
  "model": "gemini-1.5-flash",
  "approach": "Deterministic Rule-Based State Machine + Vertical-Aware Grounded Composer",
  "contact_email": "vera-team@example.com",
  "version": "1.0.0",
  "submitted_at": "2026-04-26T08:00:00Z"
}
```

---

### `POST /v1/context`
Pushes context records into memory.

**Illustrative Success Request (`200 OK`)**:
```json
{
  "scope": "merchant",
  "context_id": "m_salon_01",
  "version": 1,
  "payload": {
    "merchant_id": "m_salon_01",
    "category_slug": "salons",
    "identity": {"name": "Glow Spa", "owner_first_name": "Anita"}
  },
  "delivered_at": "2026-09-27T00:00:00Z"
}
```
**Illustrative Success Response (`200 OK`)**:
```json
{
  "accepted": true,
  "ack_id": "ack_merchant_m_salon_01_v1",
  "stored_at": "2026-09-27T00:00:00.000000Z"
}
```

**Illustrative Stale Version Rejection (`409 Conflict`)**:
```json
{
  "accepted": false,
  "reason": "stale_version",
  "current_version": 1
}
```

**Illustrative Invalid Scope Error (`400 Bad Request`)**:
```json
{
  "accepted": false,
  "reason": "invalid_scope",
  "details": "Scope 'invalid_scope' is invalid. Allowed scopes: category, merchant, customer, trigger."
}
```

---

### `POST /v1/tick`
Evaluates active triggers and returns proactive actions.

**Illustrative Request**:
```json
{
  "now": "2026-09-27T10:00:00Z",
  "available_triggers": ["trig_001"]
}
```

**Illustrative Response (`200 OK`)**:
```json
{
  "actions": [
    {
      "conversation_id": "conv_m_salon_01_trig_001",
      "merchant_id": "m_salon_01",
      "customer_id": "c_101",
      "send_as": "vera",
      "trigger_id": "trig_001",
      "template_name": "salon_nudge",
      "template_params": ["Anita"],
      "body": "Hi Anita! Bridal season is peaking in your area. Would you like to launch your weekend package?",
      "cta": "binary_yes_no",
      "suppression_key": "m_salon_01:trig_001",
      "rationale": "High-urgency seasonal peak trigger for salon merchant."
    }
  ]
}
```

---

### `POST /v1/reply`
Processes an incoming message turn in a conversation.

**Illustrative Request**:
```json
{
  "conversation_id": "conv_101",
  "merchant_id": "m_salon_01",
  "customer_id": "c_101",
  "from_role": "customer",
  "message": "Yes, let's set that up!",
  "received_at": "2026-09-27T10:05:00Z",
  "turn_number": 2
}
```

**Illustrative Response (`200 OK`)**:
```json
{
  "action": "send",
  "body": "Great! Package promotion scheduled for Saturday morning.",
  "cta": "open_ended",
  "wait_seconds": null,
  "rationale": "Affirmative customer reply; confirmed action."
}
```

---

### `POST /v1/teardown`
Resets all context records, suppression keys, state machine history, and merchant auto-reply counters.

**Illustrative Response (`200 OK`)**:
```json
{
  "status": "ok",
  "cleared": true
}
```

---

## 6. Running Tests & Judge Simulator

### Running Pytest Suite
Run the full automated unit and integration scenario test suite:
```powershell
pytest -v
```
*(All 65 tests in `tests/` execute in-process using FastAPI TestClient.)*

### Running Judge Simulator
Start the API server in one terminal:
```powershell
python main.py
```

In a second terminal, execute the local judge simulator:
```powershell
python judge_simulator.py
```
*(By default, `judge_simulator.py` runs in offline heuristic mode and evaluates scenarios including `warmup`, `auto_reply`, `intent`, and `hostile`.)*

To run the `phase2_short` scenario or other specific scenarios in the simulator:
```powershell
$env:TEST_SCENARIO="phase2_short"
python judge_simulator.py
```
*(The complete scenario set—including `phase2_short`—is also fully exercised in-process via `pytest tests/test_simulator_scenarios.py`.)*

---

## 7. Configuration & Environment Variables

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `HOST` | `0.0.0.0` | HTTP server host binding |
| `PORT` | `8080` | HTTP server listening port |
| `TEAM_NAME` | `Team Vera` | Configurable metadata default for `/v1/metadata` |
| `MODEL_NAME` | `gemini-1.5-flash` | Configurable metadata default for `/v1/metadata` |
| `CONTACT_EMAIL` | `vera-team@example.com` | Configurable metadata default for `/v1/metadata` |
| `DATASET_DIR` | `./dataset_expanded` | Dataset directory location |
| `VERA_LLM_ENABLED` | `false` | Enable/disable optional LLM message composition (`true`/`false`) |
| `VERA_LLM_PROVIDER` | `openai` | LLM provider: `openai`, `anthropic`, `gemini`, `deepseek`, `groq` |
| `VERA_LLM_API_KEY` | `""` | API key for optional LLM provider (unverified in offline mode) |
| `VERA_LLM_MODEL` | `""` | Specific LLM model name (defaults per provider) |

*(Note: `TEAM_NAME`, `MODEL_NAME`, and `CONTACT_EMAIL` represent configurable defaults. Replace with actual submission team details in production/submission environments.)*

---

## 8. Deterministic Fallback & Optional LLM Composition

By default, Vera operates in **offline deterministic mode** (`VERA_LLM_ENABLED=false`), using rule-based vertical domain strategies (`strategies/`).

When optional LLM composition is enabled (`VERA_LLM_ENABLED=true`), generated responses are evaluated by `LLMMessageValidator`:
1. **Length Validation**: Body text must be $\le 1000$ characters.
2. **URL Sanitization**: Bare `http://` / `https://` URLs are stripped.
3. **Taboo Word Enforcement**: Prohibited clinical or unverified claims (e.g., "cure", "guaranteed") trigger fallback.
4. **Price Factual Grounding**: Any price mentioned (e.g., `₹499`) must match verified context figures; ungrounded price claims trigger fallback.
5. **CTA Verification**: Must belong to approved CTA set (`open_ended`, `binary_yes_no`, `binary_confirm_cancel`, `multi_choice_slot`, `none`).

### Fallback Behavior
If `VERA_LLM_ENABLED` is `false`, no API key is set, an API network call times out (>10s) or fails, or validation fails, Vera **falls back to deterministic vertical strategy outputs**. This design ensures graceful fallback to rule-based responses without crashing the request loop.

*(Note: Live provider API integrations have not been tested with live external endpoints in the automated offline suite and must be verified independently if enabled.)*

---

## 9. Limitations & Key Assumptions

1. **In-Memory Storage**: Contexts and state are stored in-memory. Process restarts clear state unless repopulated via `POST /v1/context` or `/v1/teardown`.
2. **Auto-Reply Counter Threshold**: Canned bot auto-reply detection tracks up to $\ge 2$ consecutive canned responses per merchant before suppressing outgoing automated turns.
3. **Offline Evaluation Default**: Standard test suites and evaluation benchmarks run in offline deterministic mode by default. Live external LLM calls require outbound network connectivity and valid third-party API keys.
4. **Vertical Safeguards vs Legal Audits**: The vertical domain strategies implement programmatic heuristics and taboo filters to sanitize messages. They do not constitute formal legal compliance certifications.
