"""
Database models and engine setup for the AI Gateway.

All SQLModel table definitions live here. Runtime migrations for SQLite
are handled in init_db() — these will be replaced by Alembic when
migrating to PostgreSQL.
"""
from sqlmodel import Field, SQLModel, create_engine, Session
from typing import Optional

# ─── Core Models ─────────────────────────────────────────────────────────────

class Role(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    hashed_password: str
    disabled: bool = False
    role_id: int = Field(foreign_key="role.id")
    department: Optional[str] = None


class Prompt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    prompt_text: str
    created_at: Optional[str] = None
    llm_response: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None
    cache_hit: bool = False
    latency_ms: Optional[int] = None


class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    action: str
    timestamp: Optional[str] = None
    details: Optional[str] = None
    # Structured audit fields
    prompt_text: Optional[str] = None
    masked_prompt: Optional[str] = None
    username: Optional[str] = None
    tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None


# ─── Policy Engine ───────────────────────────────────────────────────────────

class PolicyRule(SQLModel, table=True):
    """Simple allow/deny rule for access control."""
    id: Optional[int] = Field(default=None, primary_key=True)
    effect: str  # 'allow' or 'deny'
    resource: Optional[str] = None
    action: Optional[str] = None
    target_role: Optional[str] = None
    target_department: Optional[str] = None
    created_at: Optional[str] = None


# ─── Rate Limiting ───────────────────────────────────────────────────────────

class RateLimit(SQLModel, table=True):
    """Rate limit rule. Scope can be 'user', 'department', or 'global'."""
    id: Optional[int] = Field(default=None, primary_key=True)
    scope: str  # 'user', 'department', 'global'
    target: Optional[str] = None  # username or department name (None for global)
    window: str = "hour"  # 'minute', 'hour', 'day'
    max_tokens: Optional[int] = None
    max_requests: Optional[int] = None
    created_at: Optional[str] = None


class RateLimitUsage(SQLModel, table=True):
    """Tracks per-request token usage for rate limit enforcement."""
    id: Optional[int] = Field(default=None, primary_key=True)
    rate_limit_id: int = Field(foreign_key="ratelimit.id")
    username: str
    tokens_used: int = 0
    timestamp: Optional[str] = None


# ─── Response Cache ──────────────────────────────────────────────────────────

class CacheEntry(SQLModel, table=True):
    """Cached LLM responses keyed by hash(model + prompt)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    cache_key: str = Field(index=True, unique=True)
    model: str
    prompt_hash: str
    response_text: str
    tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None
    provider: Optional[str] = None
    created_at: Optional[str] = None


# ─── Virtual Key Management ──────────────────────────────────────────────────

class VirtualKey(SQLModel, table=True):
    """Encrypted API keys for LLM providers."""
    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str  # 'openai', 'anthropic', 'google'
    key_name: str  # friendly label, e.g. "Production OpenAI Key"
    encrypted_key: str
    is_active: bool = True
    created_by: Optional[str] = None
    created_at: Optional[str] = None


# ─── Guardrails ──────────────────────────────────────────────────────────────

class Guardrail(SQLModel, table=True):
    """Configurable input/output validation rules."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str  # e.g. "Block profanity", "Enforce JSON output"
    stage: str  # 'pre' (before LLM) or 'post' (after LLM)
    check_type: str  # 'max_length', 'prohibited_topics', 'regex_filter', 'json_output', 'min_length'
    config_json: Optional[str] = None  # JSON blob with check-specific configuration
    action: str = "block"  # 'block' or 'warn'
    target_model: Optional[str] = None  # apply to specific model only
    target_department: Optional[str] = None  # apply to specific department
    is_active: bool = True
    created_at: Optional[str] = None


# ─── Prompt Templates ────────────────────────────────────────────────────────

class PromptTemplate(SQLModel, table=True):
    """Reusable prompt templates with variable substitution and versioning."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    version: int = 1
    template_text: str  # Contains {{variable}} placeholders
    model_hint: Optional[str] = None  # Suggested model for this template
    description: Optional[str] = None
    created_by: Optional[str] = None
    is_active: bool = True
    created_at: Optional[str] = None


# ─── Roles Enum ──────────────────────────────────────────────────────────────

class roles:
    ADMIN = "admin"
    USER = "user"


# ─── Database Setup ──────────────────────────────────────────────────────────

DATABASE_URL = "sqlite:///ai_gateway.db"  # Change to postgres URL for production
engine = create_engine(DATABASE_URL, echo=False)


def init_db():
    """Create all tables and run lightweight SQLite migrations."""
    SQLModel.metadata.create_all(engine)
    _ensure_columns("auditlog", {
        "prompt_text": "TEXT",
        "masked_prompt": "TEXT",
        "username": "TEXT",
        "tokens_used": "INTEGER",
        "cost_usd": "REAL",
    })
    _ensure_columns("user", {
        "department": "TEXT",
    })
    _ensure_columns("prompt", {
        "provider": "TEXT",
        "cache_hit": "BOOLEAN DEFAULT 0",
        "latency_ms": "INTEGER",
    })


def get_session():
    return Session(engine)


def _ensure_columns(table: str, columns: dict):
    """Add missing columns to a table (SQLite runtime ALTER)."""
    from sqlalchemy import text
    conn = engine.connect()
    try:
        res = conn.execute(text(f"PRAGMA table_info('{table}')"))
        existing = {row[1] for row in res.fetchall()} if res else set()
        for col, coltype in columns.items():
            if col not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}"))
        conn.commit()
    finally:
        conn.close()