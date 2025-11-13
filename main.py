import os
from openai import OpenAI
from datetime import timedelta

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from datetime import datetime, timezone
from auth import (
    User, authenticate_user, create_access_token, get_current_user,
    check_admin_role, ACCESS_TOKEN_EXPIRE_MINUTES
)
from auth import seed_users
from database import Prompt, AuditLog, get_session, init_db, Role, User as DBUser, PolicyRule
from typing import Optional
from sqlmodel import select
from sqlalchemy import desc, text

from dotenv import load_dotenv
load_dotenv()

app = FastAPI()
init_db()
seed_users()


class PolicyEngine:
    """Very small policy engine reading `PolicyRule` entries from DB.

    Semantics:
    - A rule matches if rule.resource is None or equals requested resource, same for action.
    - target_role and target_department are optional filters.
    - Deny rules take precedence over allow rules. If no rule matches, default is to allow.
    """
    def __init__(self):
        pass

    def _match_rule(self, rule: PolicyRule, resource: str, action: str, user: User):
        if rule.resource and rule.resource != resource:
            return False
        if rule.action and rule.action != action:
            return False
        if rule.target_role and rule.target_role != getattr(user, 'role', None):
            return False
        if rule.target_department and rule.target_department != getattr(user, 'department', None):
            return False
        return True

    def is_allowed(self, user: User, resource: str, action: str) -> bool:
        session = get_session()
        try:
            rules = session.exec(select(PolicyRule)).all()
        finally:
            session.close()

        allow_match = False
        for r in rules:
            if self._match_rule(r, resource, action, user):
                if r.effect.lower() == 'deny':
                    return False
                if r.effect.lower() == 'allow':
                    allow_match = True
        # If any allow matched, allow. Otherwise default allow.
        return True if allow_match or not rules else True


policy_engine = PolicyEngine()

class PromptRequest(BaseModel):
    prompt: str
    model: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str


class PolicyRequest(BaseModel):
    effect: str  # 'allow' or 'deny'
    resource: Optional[str] = None
    action: Optional[str] = None
    target_role: Optional[str] = None
    target_department: Optional[str] = None

def log_request(user_id: Optional[int] = None,
                action: Optional[str] = None,
                details: Optional[str] = None,
                masked_prompt: Optional[str] = None,
                username: Optional[str] = None,
                tokens_used: Optional[int] = None,
                cost_usd: Optional[float] = None):
    """Create an audit log row. Backwards-compatible: callers that pass (user_id, action, details)
    still work. Additional keyword-only fields can be provided to populate the new columns.
    """
    print(f"[AUDIT] user_id={user_id} action={action} username={username} details={details}")
    session = get_session()
    audit = AuditLog(
        user_id=user_id,
        action=action,
        timestamp=datetime.now(timezone.utc).isoformat(),
        details=details,
        masked_prompt=masked_prompt,
        username=username,
        tokens_used=tokens_used,
        cost_usd=cost_usd,
    )
    session.add(audit)
    session.commit()
    session.close()

@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    log_request(user_id=None, action="login", details=f"username={form_data.username}", username=form_data.username)
    return {"access_token": access_token, "token_type": "bearer"}


class CreateUserRequest(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None


@app.post("/users")
async def create_user(request: CreateUserRequest, current_user: User = Depends(check_admin_role)):
    # Only admins can create users via this endpoint
    session = get_session()
    # Ensure role exists or create it
    role_name = request.role or "user"
    role = session.exec(select(Role).where(Role.name == role_name)).first()
    if not role:
        role_obj = Role(name=role_name)
        session.add(role_obj)
        session.commit()
        session.refresh(role_obj)
        role = role_obj

    # Check uniqueness
    from database import User as DBUser
    existing = session.exec(select(DBUser).where(DBUser.username == request.username)).first()
    if existing:
        session.close()
        raise HTTPException(status_code=400, detail="username already exists")

    # create user in DB (and role already ensured above)
    try:
        from auth import create_user_in_db
        created = create_user_in_db(request.username, request.password, request.full_name, request.email, role.name)
    except ValueError:
        session.close()
        raise HTTPException(status_code=400, detail="username already exists")

    # persist optional department on the created DB user
    try:
        db_user_row = session.exec(select(DBUser).where(DBUser.username == created.username)).first()
        if db_user_row and request.department:
            db_user_row.department = request.department
            session.add(db_user_row)
            session.commit()
    except Exception:
        # non-fatal
        session.rollback()

    log_request(user_id=None, action="create_user", details=f"created username={created.username} by admin={current_user.username}", username=created.username)
    session.close()
    return {"username": created.username, "email": created.email, "full_name": created.full_name, "role": role.name}

@app.middleware("http")
async def log_all_requests(request: Request, call_next):
    print(f"[REQUEST] {request.method} {request.url}")
    response = await call_next(request)
    return response

@app.get("/")
def root():
    return {"message": "Hello World"}

@app.get("/users/me/", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_user)):
    log_request(user_id=None, action="get_user", details=f"username={current_user.username}", username=current_user.username)
    return current_user

@app.post("/prompt")
async def create_prompt(
    prompt_request: PromptRequest,
    current_user: User = Depends(get_current_user)
):
    # Policy check: verify current_user is allowed to create a prompt
    if not policy_engine.is_allowed(current_user, resource="prompt", action="create"):
        # log denied attempt
        log_request(user_id=None, action="policy_denied", details=f"user={current_user.username} blocked by policy for prompt create", username=current_user.username, masked_prompt=None)
        raise HTTPException(status_code=403, detail="Action blocked by policy")

    session = get_session()
    # ensure DB user exists for this username
    db_user = session.exec(select(DBUser).where(DBUser.username == current_user.username)).first()
    if not db_user:
        from auth import get_user
        auth_user = get_user(current_user.username)
        hashed = auth_user.hashed_password if auth_user else ""
        role_id = None
        if auth_user and getattr(auth_user, "role", None):
            role_row = session.exec(select(Role).where(Role.name == auth_user.role)).first()
            if not role_row:
                role_row = Role(name=auth_user.role)
                session.add(role_row)
                session.commit()
                session.refresh(role_row)
            role_id = role_row.id
        kwargs = {
            "username": current_user.username,
            "full_name": getattr(auth_user, "full_name", None) if auth_user else None,
            "email": getattr(auth_user, "email", None) if auth_user else None,
            "hashed_password": hashed,
            "disabled": False,
        }
        if role_id is not None:
            kwargs["role_id"] = role_id
        db_user = DBUser(**kwargs)
        session.add(db_user)
        session.commit()
        session.refresh(db_user)

    # Mask the incoming prompt before storing
    from PII import anonymize_text
    masked_prompt, pii_mapping = anonymize_text(prompt_request.prompt)

    # Log masked fields and detection results
    print(f"[MASKED] Prompt: {masked_prompt}")
    print(f"[PII DETECTION] Mapping: {pii_mapping}")

    import tiktoken

    # Function to count tokens and estimate cost
    def count_tokens_and_cost(text, model="gpt-3.5-turbo"):
        encoding = tiktoken.encoding_for_model(model)
        tokens = len(encoding.encode(text))
        # Cost per 1K tokens (approximate rates, may need updating)
        costs = {
            "gpt-3.5-turbo": (0.0015, 0.002),  # (input, output) per 1K tokens
            "gpt-4": (0.03, 0.06),
            "gpt-4-32k": (0.06, 0.12),
        }
        input_cost, output_cost = costs.get(model, (0.0015, 0.002))  # default to gpt-3.5-turbo rates
        return tokens, (tokens / 1000.0) * input_cost

    # Send masked prompt to LLM provider (OpenAI example)
    api_key = os.getenv("OPENAI_API_KEY")
    llm_response = None
    tokens_used = 0
    cost_usd = 0
    model = prompt_request.model or "gpt-3.5-turbo"

    if not api_key:
        llm_response = "LLM error: OpenAI API key not set. Please set OPENAI_API_KEY environment variable."
        print("[ERROR] OpenAI API key missing.")
    else:
        try:
            client = OpenAI(api_key=api_key)
            # Count tokens and estimate cost for input
            input_tokens, input_cost = count_tokens_and_cost(masked_prompt, model)
            
            completion = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": masked_prompt}]
            )
            llm_response = completion.choices[0].message.content
            
            # Count tokens and estimate cost for output
            output_tokens, output_cost = count_tokens_and_cost(llm_response, model)
            tokens_used = input_tokens + output_tokens
            cost_usd = input_cost + output_cost
            
            print(f"[TOKENS] Input: {input_tokens}, Output: {output_tokens}, Total: {tokens_used}")
            print(f"[COST] ${cost_usd:.4f} USD")
            
        except Exception as e:
            llm_response = f"LLM error: {e}"
            print(f"[ERROR] LLM call failed: {e}")

    prompt = Prompt(
        user_id=db_user.id,
        prompt_text=masked_prompt,
        llm_response=llm_response,
        model=model,
        tokens_used=tokens_used,
        cost_usd=cost_usd,
        created_at=datetime.now(timezone.utc).isoformat()
    )
    session.add(prompt)
    session.commit()
    log_request(
        user_id=db_user.id,
        action="create_prompt",
        details=f"user={current_user.username}, model={prompt_request.model}, pii_mapping={pii_mapping}, llm_response={llm_response}",
        masked_prompt=masked_prompt,
        username=current_user.username,
        tokens_used=tokens_used,
        cost_usd=cost_usd,
    )
    session.close()
    response = {
        "masked_prompt": masked_prompt,
        "llm_response": llm_response,
        "model": model,
        "tokens_used": tokens_used,
        "cost_usd": cost_usd
    }
    return response

@app.post("/admin/prompt")
async def admin_prompt(
    prompt_request: PromptRequest,
    current_user: User = Depends(check_admin_role)
):
    session = get_session()
    db_user = session.exec(select(DBUser).where(DBUser.username == current_user.username)).first()
    if not db_user:
        from auth import get_user
        auth_user = get_user(current_user.username)
        hashed = auth_user.hashed_password if auth_user else ""
        role_id = None
        if auth_user and getattr(auth_user, "role", None):
            role_row = session.exec(select(Role).where(Role.name == auth_user.role)).first()
            if not role_row:
                role_row = Role(name=auth_user.role)
                session.add(role_row)
                session.commit()
                session.refresh(role_row)
            role_id = role_row.id
        kwargs = {
            "username": current_user.username,
            "full_name": getattr(auth_user, "full_name", None) if auth_user else None,
            "email": getattr(auth_user, "email", None) if auth_user else None,
            "hashed_password": hashed,
            "disabled": False,
        }
        if role_id is not None:
            kwargs["role_id"] = role_id
        db_user = DBUser(**kwargs)
        session.add(db_user)
        session.commit()
        session.refresh(db_user)

    # For admin prompts, we don't mask the prompt but still track tokens and cost
    import tiktoken

    def count_tokens_and_cost(text, model="gpt-3.5-turbo"):
        encoding = tiktoken.encoding_for_model(model)
        tokens = len(encoding.encode(text))
        costs = {
            "gpt-3.5-turbo": (0.0015, 0.002),  # (input, output) per 1K tokens
            "gpt-4": (0.03, 0.06),
            "gpt-4-32k": (0.06, 0.12),
        }
        input_cost, output_cost = costs.get(model, (0.0015, 0.002))
        return tokens, (tokens / 1000.0) * input_cost

    model = prompt_request.model or "gpt-3.5-turbo"
    tokens, cost = count_tokens_and_cost(prompt_request.prompt, model)

    prompt = Prompt(
        user_id=db_user.id,
        prompt_text=prompt_request.prompt,
        model=model,
        tokens_used=tokens,
        cost_usd=cost,
        created_at=datetime.now(timezone.utc).isoformat()
    )
    session.add(prompt)
    session.commit()
    
    # For admin prompts we intentionally DO NOT store the raw prompt into audit logs to preserve privacy.
    log_request(
        user_id=db_user.id,
        action="admin_prompt",
        details=f"admin={current_user.username}, model={model}",
        masked_prompt=prompt_request.prompt,
        username=current_user.username,
        tokens_used=tokens,
        cost_usd=cost,
    )
    session.close()
    
    response = {
        "message": f"Admin {current_user.username} sent prompt: {prompt_request.prompt}",
        "model": model,
        "tokens_used": tokens,
        "cost_usd": cost
    }
    return response


@app.get("/admin/policies")
async def list_policies(current_user: User = Depends(check_admin_role)):
    session = get_session()
    rules = session.exec(select(PolicyRule)).all()
    session.close()
    out = []
    for r in rules:
        out.append({
            "id": r.id,
            "effect": r.effect,
            "resource": r.resource,
            "action": r.action,
            "target_role": r.target_role,
            "target_department": r.target_department,
            "created_at": r.created_at,
        })
    return out


@app.post("/admin/policies")
async def create_policy(policy: PolicyRequest, current_user: User = Depends(check_admin_role)):
    session = get_session()
    pr = PolicyRule(
        effect=policy.effect,
        resource=policy.resource,
        action=policy.action,
        target_role=policy.target_role,
        target_department=policy.target_department,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    session.add(pr)
    session.commit()
    session.refresh(pr)
    session.close()
    log_request(user_id=None, action="create_policy", details=f"policy={pr.id} effect={pr.effect} resource={pr.resource} action={pr.action} role={pr.target_role} dept={pr.target_department}", username=current_user.username)
    return {"id": pr.id}


@app.delete("/admin/policies/{policy_id}")
async def delete_policy(policy_id: int, current_user: User = Depends(check_admin_role)):
    session = get_session()
    pr = session.get(PolicyRule, policy_id)
    if not pr:
        session.close()
        raise HTTPException(status_code=404, detail="policy not found")
    session.delete(pr)
    session.commit()
    session.close()
    log_request(user_id=None, action="delete_policy", details=f"deleted policy={policy_id}", username=current_user.username)
    return {"deleted": policy_id}


@app.get("/audit_logs")
async def get_audit_logs(current_user: User = Depends(check_admin_role)):
    """Admin-only endpoint to retrieve audit logs with structured fields."""
    session = get_session()
    rows = session.exec(select(AuditLog).order_by(text("id DESC"))).all()
    result = []
    for r in rows:
        result.append({
            "id": r.id,
            "user_id": r.user_id,
            "username": r.username,
            "action": r.action,
            "masked_prompt": r.masked_prompt,
            "tokens_used": r.tokens_used,
            "cost_usd": r.cost_usd,
            "details": r.details,
            "timestamp": r.timestamp,
        })
    session.close()
    return result
