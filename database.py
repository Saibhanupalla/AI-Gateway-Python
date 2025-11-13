from sqlmodel import Field, SQLModel, create_engine, Session
from typing import Optional

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
    # optional department field for policy targeting
    department: Optional[str] = None

class Prompt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    prompt_text: str
    created_at: Optional[str] = None
    llm_response: Optional[str] = None
    model: Optional[str] = None
    tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None

class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    action: str
    timestamp: Optional[str] = None
    details: Optional[str] = None
    # New fields to track prompt/audit information
    prompt_text: Optional[str] = None
    masked_prompt: Optional[str] = None
    username: Optional[str] = None
    tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None


class PolicyRule(SQLModel, table=True):
    """Simple allow/deny rule.

    Fields:
    - id
    - effect: 'allow' or 'deny'
    - resource: e.g., 'prompt'
    - action: e.g., 'create'
    - target_role: apply to role name (optional)
    - target_department: apply to department (optional)
    - created_at
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    effect: str  # 'allow' or 'deny'
    resource: Optional[str] = None
    action: Optional[str] = None
    target_role: Optional[str] = None
    target_department: Optional[str] = None
    created_at: Optional[str] = None

# Roles enum
class roles:
    ADMIN = "admin"
    USER = "user"

# Database setup
DATABASE_URL = "sqlite:///ai_gateway.db"  # Change to postgres URL for production
engine = create_engine(DATABASE_URL, echo=True)

def init_db():
    SQLModel.metadata.create_all(engine)
    # Ensure auditlog has the new columns added in recent schema updates.
    ensure_auditlog_columns()
    # Ensure user table has department column
    ensure_user_department_column()

def get_session():
    return Session(engine)


def ensure_auditlog_columns():
    """Add missing columns to the auditlog table if they don't exist.
    This is a lightweight runtime migration useful for development with SQLite.
    """
    from sqlalchemy import text

    conn = engine.connect()
    try:
        # Get existing columns
        res = conn.execute(text("PRAGMA table_info('auditlog')"))
        existing = {row[1] for row in res.fetchall()} if res is not None else set()

        # Define desired columns and the SQL types to add
        desired = {
            'prompt_text': 'TEXT',
            'masked_prompt': 'TEXT',
            'username': 'TEXT',
            'tokens_used': 'INTEGER',
            'cost_usd': 'REAL',
        }

        for col, coltype in desired.items():
            if col not in existing:
                alter_sql = f"ALTER TABLE auditlog ADD COLUMN {col} {coltype}"
                conn.execute(text(alter_sql))
    finally:
        conn.close()


def ensure_user_department_column():
    """Ensure the `department` column exists on the `user` table (SQLite runtime alter).
    """
    from sqlalchemy import text

    conn = engine.connect()
    try:
        res = conn.execute(text("PRAGMA table_info('user')"))
        existing = {row[1] for row in res.fetchall()} if res is not None else set()
        if 'department' not in existing:
            conn.execute(text("ALTER TABLE user ADD COLUMN department TEXT"))
    finally:
        conn.close()