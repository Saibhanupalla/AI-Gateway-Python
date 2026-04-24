# AI Gateway Python — Project Context

## What This Project Is

An enterprise-grade AI Gateway that acts as a centralized proxy between users/applications and LLM providers (OpenAI, Anthropic, Google). It intercepts every request to enforce security policies, mask PII, track costs, and provide observability — all before the prompt ever reaches the LLM.

## Tech Stack

- **Backend:** FastAPI (Python) — the core gateway API server
- **Frontend:** React dashboard (to be built, replacing legacy Streamlit app)
- **Database:** SQLite via SQLModel (migrating to PostgreSQL)
- **Auth:** JWT (python-jose) + passlib for password hashing
- **PII Detection:** Microsoft Presidio (AnalyzerEngine + AnonymizerEngine)
- **Token Counting:** tiktoken
- **LLM Client:** openai Python SDK

## Project Structure

```
AI-Gateway-Python/
├── main.py              # FastAPI app — all routes, policy engine, prompt handling
├── auth.py              # JWT auth, user creation, password hashing, RBAC
├── database.py          # SQLModel models (User, Role, Prompt, AuditLog, PolicyRule), init_db
├── PII.py               # Presidio-based PII detection & anonymization with mapping persistence
├── cost.py              # Standalone token counting & cost estimation (currently unused by main.py)
├── streamlit_app.py     # Legacy Streamlit frontend (being replaced by React dashboard)
├── test_main.py         # Pytest tests for auth, prompts, user creation
├── PII_edge_test.py     # Edge case tests for PII anonymization
├── pii_mapping.json     # Persisted forward/reverse PII entity mappings
├── ai_gateway.db        # SQLite database file
├── requirements.txt     # Dependencies (incomplete — needs all backend deps)
├── .env                 # Environment variables (OPENAI_API_KEY)
└── .gitignore
```

## Database Models (SQLModel)

- **Role** — `id`, `name` (e.g., "admin", "user")
- **User** — `id`, `username`, `full_name`, `email`, `hashed_password`, `disabled`, `role_id` (FK → Role), `department`
- **Prompt** — `id`, `user_id` (FK → User), `prompt_text`, `created_at`, `llm_response`, `model`, `tokens_used`, `cost_usd`
- **AuditLog** — `id`, `user_id`, `action`, `timestamp`, `details`, `prompt_text`, `masked_prompt`, `username`, `tokens_used`, `cost_usd`
- **PolicyRule** — `id`, `effect` (allow/deny), `resource`, `action`, `target_role`, `target_department`, `created_at`

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/token` | None | OAuth2 login, returns JWT |
| GET | `/` | None | Health check |
| GET | `/users/me/` | Bearer | Get current user info |
| POST | `/users` | Admin | Create new user |
| POST | `/prompt` | Bearer | Send prompt (PII masked → LLM → response) |
| POST | `/admin/prompt` | Admin | Send prompt without PII masking |
| GET | `/admin/policies` | Admin | List all policy rules |
| POST | `/admin/policies` | Admin | Create a policy rule |
| DELETE | `/admin/policies/{id}` | Admin | Delete a policy rule |
| GET | `/audit_logs` | Admin | List all audit logs |

## Seeded Users

- `admin` / `admin123` — role: admin
- `user` / `user123` — role: user

## Known Bugs (Must Fix Before New Features)

1. **PII.py crashes at runtime** — Presidio's spaCy model throws `IndexError: index 130541 is out of bounds for axis 0 with size 0`. The spaCy language model is either missing or incompatible.
2. **PII.py has dead code** — Lines 119–135 are duplicated anonymization logic unreachable after the `return` on line 117.
3. **PII index mapping is wrong** — After anonymization, the code uses original text indices (`start:end`) to slice the anonymized text, which has different length. This corrupts the mapping.
4. **cost.py is unused** — `main.py` defines its own inline `count_tokens_and_cost()` function instead of importing from `cost.py`. The two have different pricing tables.
5. **requirements.txt is incomplete** — Only lists `streamlit` and `requests`. Missing: `fastapi`, `uvicorn`, `openai`, `python-jose`, `passlib`, `sqlmodel`, `presidio-analyzer`, `presidio-anonymizer`, `tiktoken`, `python-dotenv`, `spacy`.
6. **Hardcoded JWT secret** — `auth.py` line 12: `SECRET_KEY = "your-secret-key-here"`. Must read from env.
7. **test_main.py assertions are wrong** — Tests check for `response.json()["response"]` key but the API returns `masked_prompt` and `llm_response` keys.
8. **`.env` uses `export` prefix** — Python's `dotenv` doesn't need the `export` keyword; it may cause parsing issues.

## Enterprise Features to Implement (Priority Order)

### P0 — Fix Existing Bugs
Fix all items listed above before building new features.

### P1 — Multi-Provider Routing & Fallback
- Create `providers/` module with adapters: `openai_provider.py`, `anthropic_provider.py`, `google_provider.py`
- Unified `LLMProvider` interface with `complete(model, messages)` method
- `gateway_config.yaml` for routing rules, fallback chains, retry with exponential backoff
- Circuit breaker pattern for unhealthy providers

### P1 — React Analytics Dashboard (Replace Streamlit)
- Full admin console: KPI cards, request volume charts, cost breakdown, model usage
- Request explorer with searchable/filterable log table
- User management with inline role editing
- Policy manager with visual rule builder
- PII monitor showing detected entities and confidence scores
- Dark mode, modern design (Inter/Outfit font, glassmorphism accents)

### P2 — Rate Limiting & Budget Controls
- Token-aware limits per user, department, and org-wide
- Store in DB, enforce in middleware
- Return 429 with `Retry-After` header
- Admin CRUD at `/admin/rate-limits`

### P2 — Response Caching
- Exact-match cache: hash(model + prompt) → stored response
- `cache` table with TTL
- `X-Cache: HIT/MISS` response headers
- Admin toggle per model

### P3 — API Key Management (Virtual Keys)
- `VirtualKey` model: friendly name → encrypted provider API key
- Admin UI for add/rotate/revoke per provider
- Gateway reads from DB, not `.env`

### P3 — Guardrails (Input/Output)
- Pre-request: prohibited topics, max prompt length, schema validation
- Post-response: hallucination detection, toxic content filter, JSON validation
- Configurable per model/department via `Guardrail` table

### P4 — Prompt Templates & Versioning
- `PromptTemplate` table: name, version, template text with `{{variable}}` placeholders
- API to render templates before sending
- Version history & rollback

### P4 — Containerization
- `Dockerfile` for FastAPI backend
- `docker-compose.yml` with: backend, React frontend, PostgreSQL, Redis
- `/health` and `/ready` endpoints
- Structured JSON logging (replace all `print()`)

## Coding Conventions

- **Python version:** 3.13+ (check venv)
- **ORM:** SQLModel (Pydantic + SQLAlchemy hybrid)
- **Auth pattern:** Dependency injection via `Depends(get_current_user)` and `Depends(check_admin_role)`
- **Session management:** `get_session()` returns a new `Session(engine)` — must be manually closed
- **Logging:** Currently `print()` — migrate to `structlog` or `logging` with JSON formatter
- **Environment:** `.env` loaded via `python-dotenv` at module level
- **Testing:** pytest with `TestClient` from FastAPI

## Important Notes

- The SQLite database (`ai_gateway.db`) contains runtime migration functions (`ensure_auditlog_columns`, `ensure_user_department_column`) that use raw `ALTER TABLE` for schema updates. These are SQLite-specific and must be replaced with Alembic migrations when moving to PostgreSQL.
- The `pii_mapping.json` file grows indefinitely as new PII entities are detected. It needs a cleanup/rotation strategy for production.
- The `PolicyEngine` default behavior (line 64) always returns `True` even when no rules match — this is permissive by default, which may not be desired in enterprise settings.
