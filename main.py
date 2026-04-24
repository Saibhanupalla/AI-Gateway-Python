"""
AI Gateway — Main FastAPI Application

Enterprise-grade LLM proxy with multi-provider routing, PII masking,
rate limiting, response caching, guardrails, and audit logging.
"""
import os
import time
import logging
import json
from datetime import timedelta, datetime, timezone
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlmodel import select
from sqlalchemy import text

from dotenv import load_dotenv
load_dotenv()

from auth import (
    User, authenticate_user, create_access_token, get_current_user,
    check_admin_role, ACCESS_TOKEN_EXPIRE_MINUTES, seed_users
)
from database import (
    Prompt, AuditLog, get_session, init_db, Role,
    User as DBUser, PolicyRule, RateLimit, Guardrail, PromptTemplate, VirtualKey,
)
from cost import estimate_cost
from config import load_config
from router import route_request
from providers import LLMMessage
from rate_limiter import check_rate_limit, record_usage, RateLimitExceeded
from cache import get_cached_response, store_cached_response
from guardrails import run_pre_request_guardrails, run_post_response_guardrails

# ─── Logging Setup ───────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
logger = logging.getLogger("ai_gateway")

# ─── App Init ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI Gateway",
    description="Enterprise LLM Gateway with multi-provider routing, PII masking, and governance",
    version="2.0.0",
)

# CORS — allow the React dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Init DB and seed default users
init_db()
seed_users()

# Load gateway config
gateway_config = load_config()


# ─── Policy Engine ───────────────────────────────────────────────────────────

class PolicyEngine:
    """Reads PolicyRule entries from DB. Deny rules take precedence over allow."""

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

        for r in rules:
            if self._match_rule(r, resource, action, user):
                if r.effect.lower() == 'deny':
                    return False
        return True


policy_engine = PolicyEngine()


# ─── Request/Response Models ─────────────────────────────────────────────────

class PromptRequest(BaseModel):
    prompt: str
    model: Optional[str] = None
    template_id: Optional[int] = None
    template_vars: Optional[dict] = None

class Token(BaseModel):
    access_token: str
    token_type: str

class CreateUserRequest(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None

class PolicyRequest(BaseModel):
    effect: str
    resource: Optional[str] = None
    action: Optional[str] = None
    target_role: Optional[str] = None
    target_department: Optional[str] = None

class RateLimitRequest(BaseModel):
    scope: str  # 'user', 'department', 'global'
    target: Optional[str] = None
    window: str = "hour"
    max_tokens: Optional[int] = None
    max_requests: Optional[int] = None

class GuardrailRequest(BaseModel):
    name: str
    stage: str  # 'pre' or 'post'
    check_type: str
    config_json: Optional[str] = None
    action: str = "block"
    target_model: Optional[str] = None
    target_department: Optional[str] = None

class TemplateRequest(BaseModel):
    name: str
    template_text: str
    model_hint: Optional[str] = None
    description: Optional[str] = None

class VirtualKeyRequest(BaseModel):
    provider: str
    key_name: str
    api_key: str


# ─── Helpers ─────────────────────────────────────────────────────────────────

def log_audit(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    details: Optional[str] = None,
    masked_prompt: Optional[str] = None,
    username: Optional[str] = None,
    tokens_used: Optional[int] = None,
    cost_usd: Optional[float] = None,
):
    """Write a structured audit log entry."""
    logger.info(f"[AUDIT] user={username} action={action} tokens={tokens_used} cost={cost_usd}")
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


def _ensure_db_user(current_user: User) -> DBUser:
    """Get or create the DB row for an authenticated user."""
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
    session.close()
    return db_user


# ─── Middleware ───────────────────────────────────────────────────────────────

@app.middleware("http")
async def request_logger(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed = round((time.time() - start) * 1000, 2)
    logger.info(f"{request.method} {request.url.path} → {response.status_code} ({elapsed}ms)")
    return response


# ─── Auth Endpoints ──────────────────────────────────────────────────────────

@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    log_audit(action="login", details=f"username={form_data.username}", username=form_data.username)
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/users")
async def create_user(request: CreateUserRequest, current_user: User = Depends(check_admin_role)):
    session = get_session()
    role_name = request.role or "user"
    role = session.exec(select(Role).where(Role.name == role_name)).first()
    if not role:
        role = Role(name=role_name)
        session.add(role)
        session.commit()
        session.refresh(role)

    existing = session.exec(select(DBUser).where(DBUser.username == request.username)).first()
    if existing:
        session.close()
        raise HTTPException(status_code=400, detail="username already exists")

    from auth import create_user_in_db
    try:
        created = create_user_in_db(request.username, request.password, request.full_name, request.email, role.name)
    except ValueError:
        session.close()
        raise HTTPException(status_code=400, detail="username already exists")

    if request.department:
        db_user_row = session.exec(select(DBUser).where(DBUser.username == created.username)).first()
        if db_user_row:
            db_user_row.department = request.department
            session.add(db_user_row)
            session.commit()

    log_audit(action="create_user", details=f"created={created.username} by={current_user.username}", username=created.username)
    session.close()
    return {"username": created.username, "email": created.email, "full_name": created.full_name, "role": role.name}


# ─── Health & Info ───────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "AI Gateway v2.0", "status": "running"}


@app.get("/health")
def health():
    """Health check for container orchestrators."""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/ready")
def readiness():
    """Readiness probe — checks DB connectivity."""
    try:
        session = get_session()
        session.exec(select(Role)).first()
        session.close()
        return {"status": "ready"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "not ready", "error": str(e)})


@app.get("/users/me/", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user


@app.get("/gateway/config")
async def get_gateway_info(current_user: User = Depends(check_admin_role)):
    """Return the current gateway configuration (admin only)."""
    config = load_config()
    return {
        "providers": {
            name: {
                "models": p.models,
                "enabled": p.enabled,
                "has_key": bool(p.api_key),
            }
            for name, p in config.providers.items()
        },
        "routing": {
            "default_model": config.routing.default_model,
            "fallback_chain": config.routing.fallback_chain,
            "retry_max_attempts": config.routing.retry.max_attempts,
        },
        "cache": {
            "enabled": config.cache.enabled,
            "ttl_seconds": config.cache.ttl_seconds,
        },
    }


# ─── Core Prompt Endpoint ───────────────────────────────────────────────────

@app.post("/prompt")
async def create_prompt(
    prompt_request: PromptRequest,
    current_user: User = Depends(get_current_user),
):
    start_time = time.time()
    config = load_config()

    # 1. Policy check
    if not policy_engine.is_allowed(current_user, resource="prompt", action="create"):
        log_audit(action="policy_denied", username=current_user.username,
                  details=f"blocked by policy for prompt create")
        raise HTTPException(status_code=403, detail="Action blocked by policy")

    # 2. Rate limit check
    try:
        check_rate_limit(current_user.username, getattr(current_user, 'department', None))
    except RateLimitExceeded as e:
        log_audit(action="rate_limited", username=current_user.username, details=str(e))
        return JSONResponse(
            status_code=429,
            content={"detail": str(e)},
            headers={"Retry-After": str(e.retry_after_seconds)},
        )

    # 3. Resolve prompt (template or raw)
    prompt_text = prompt_request.prompt
    if prompt_request.template_id:
        session = get_session()
        template = session.get(PromptTemplate, prompt_request.template_id)
        if template and template.is_active:
            prompt_text = template.template_text
            if prompt_request.template_vars:
                for key, val in prompt_request.template_vars.items():
                    prompt_text = prompt_text.replace("{{" + key + "}}", str(val))
        session.close()

    model = prompt_request.model or config.routing.default_model

    # 4. Pre-request guardrails
    pre_violations = run_pre_request_guardrails(
        prompt_text, model=model, department=getattr(current_user, 'department', None)
    )
    if pre_violations:
        log_audit(action="guardrail_blocked", username=current_user.username,
                  details=f"pre-request: {pre_violations}")
        raise HTTPException(status_code=422, detail={"guardrail_violations": pre_violations})

    # 5. PII masking
    masked_prompt = prompt_text
    pii_mapping = {}
    try:
        from PII import anonymize_text
        masked_prompt, pii_mapping = anonymize_text(prompt_text)
    except Exception as e:
        logger.warning(f"PII masking failed (proceeding with raw prompt): {e}")

    # 6. Cache check
    cache_hit = False
    if config.cache.enabled:
        cached = get_cached_response(model, masked_prompt, config.cache.ttl_seconds)
        if cached:
            cache_hit = True
            latency_ms = round((time.time() - start_time) * 1000)
            db_user = _ensure_db_user(current_user)

            session = get_session()
            prompt_row = Prompt(
                user_id=db_user.id,
                prompt_text=masked_prompt,
                llm_response=cached["llm_response"],
                model=cached["model"],
                provider="cache",
                tokens_used=cached["tokens_used"],
                cost_usd=0.0,  # No cost for cached responses
                cache_hit=True,
                latency_ms=latency_ms,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            session.add(prompt_row)
            session.commit()
            session.close()

            log_audit(
                user_id=db_user.id, action="prompt_cached",
                username=current_user.username, masked_prompt=masked_prompt,
                tokens_used=cached["tokens_used"], cost_usd=0.0,
            )
            return {
                "masked_prompt": masked_prompt,
                "llm_response": cached["llm_response"],
                "model": cached["model"],
                "provider": "cache",
                "tokens_used": cached["tokens_used"],
                "cost_usd": 0.0,
                "cache_hit": True,
                "latency_ms": latency_ms,
            }

    # 7. Route to LLM provider
    llm_response = None
    provider_name = "unknown"
    try:
        messages = [LLMMessage(role="user", content=masked_prompt)]
        result = route_request(model=model, messages=messages, config=config)
        llm_response = result.content
        provider_name = result.provider
        model = result.model  # may differ if fallback used a different model
    except RuntimeError as e:
        llm_response = f"Gateway error: {e}"
        logger.error(f"All providers failed: {e}")

    # 8. Post-response guardrails
    if llm_response and not llm_response.startswith("Gateway error"):
        post_violations = run_post_response_guardrails(
            llm_response, model=model, department=getattr(current_user, 'department', None)
        )
        if post_violations:
            logger.warning(f"Post-response guardrail warnings: {post_violations}")
            # We don't block on post-response, just log (action='warn' in most cases)

    # 9. Cost estimation
    cost_info = estimate_cost(masked_prompt, llm_response or "", model)
    tokens_used = cost_info["total_tokens"]
    cost_usd = cost_info["total_cost_usd"]
    latency_ms = round((time.time() - start_time) * 1000)

    # 10. Store in DB
    db_user = _ensure_db_user(current_user)
    session = get_session()
    prompt_row = Prompt(
        user_id=db_user.id,
        prompt_text=masked_prompt,
        llm_response=llm_response,
        model=model,
        provider=provider_name,
        tokens_used=tokens_used,
        cost_usd=cost_usd,
        cache_hit=False,
        latency_ms=latency_ms,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    session.add(prompt_row)
    session.commit()
    session.close()

    # 11. Cache the response
    if config.cache.enabled and llm_response and not llm_response.startswith("Gateway error"):
        store_cached_response(model, masked_prompt, llm_response, tokens_used, cost_usd, provider_name)

    # 12. Record rate limit usage
    record_usage(current_user.username, tokens_used, getattr(current_user, 'department', None))

    # 13. Audit log
    log_audit(
        user_id=db_user.id,
        action="create_prompt",
        details=f"model={model} provider={provider_name} pii={list(pii_mapping.keys())}",
        masked_prompt=masked_prompt,
        username=current_user.username,
        tokens_used=tokens_used,
        cost_usd=cost_usd,
    )

    return {
        "masked_prompt": masked_prompt,
        "llm_response": llm_response,
        "model": model,
        "provider": provider_name,
        "tokens_used": tokens_used,
        "cost_usd": cost_usd,
        "cache_hit": False,
        "latency_ms": latency_ms,
    }


# ─── Admin Prompt (no PII masking) ──────────────────────────────────────────

@app.post("/admin/prompt")
async def admin_prompt(
    prompt_request: PromptRequest,
    current_user: User = Depends(check_admin_role),
):
    start_time = time.time()
    config = load_config()
    model = prompt_request.model or config.routing.default_model
    db_user = _ensure_db_user(current_user)

    try:
        messages = [LLMMessage(role="user", content=prompt_request.prompt)]
        result = route_request(model=model, messages=messages, config=config)
        llm_response = result.content
        provider_name = result.provider
    except RuntimeError as e:
        llm_response = f"Gateway error: {e}"
        provider_name = "error"

    cost_info = estimate_cost(prompt_request.prompt, llm_response or "", model)
    latency_ms = round((time.time() - start_time) * 1000)

    session = get_session()
    prompt_row = Prompt(
        user_id=db_user.id,
        prompt_text=prompt_request.prompt,
        llm_response=llm_response,
        model=model,
        provider=provider_name,
        tokens_used=cost_info["total_tokens"],
        cost_usd=cost_info["total_cost_usd"],
        latency_ms=latency_ms,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    session.add(prompt_row)
    session.commit()
    session.close()

    log_audit(
        user_id=db_user.id, action="admin_prompt",
        details=f"admin={current_user.username} model={model} provider={provider_name}",
        username=current_user.username,
        tokens_used=cost_info["total_tokens"],
        cost_usd=cost_info["total_cost_usd"],
    )

    return {
        "llm_response": llm_response,
        "model": model,
        "provider": provider_name,
        "tokens_used": cost_info["total_tokens"],
        "cost_usd": cost_info["total_cost_usd"],
        "latency_ms": latency_ms,
    }


# ─── Policy CRUD ─────────────────────────────────────────────────────────────

@app.get("/admin/policies")
async def list_policies(current_user: User = Depends(check_admin_role)):
    session = get_session()
    rules = session.exec(select(PolicyRule)).all()
    session.close()
    return [
        {"id": r.id, "effect": r.effect, "resource": r.resource, "action": r.action,
         "target_role": r.target_role, "target_department": r.target_department, "created_at": r.created_at}
        for r in rules
    ]


@app.post("/admin/policies")
async def create_policy(policy: PolicyRequest, current_user: User = Depends(check_admin_role)):
    session = get_session()
    pr = PolicyRule(
        effect=policy.effect, resource=policy.resource, action=policy.action,
        target_role=policy.target_role, target_department=policy.target_department,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    session.add(pr)
    session.commit()
    session.refresh(pr)
    session.close()
    log_audit(action="create_policy", details=f"policy={pr.id} effect={pr.effect}", username=current_user.username)
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
    log_audit(action="delete_policy", details=f"deleted policy={policy_id}", username=current_user.username)
    return {"deleted": policy_id}


# ─── Rate Limit CRUD ─────────────────────────────────────────────────────────

@app.get("/admin/rate-limits")
async def list_rate_limits(current_user: User = Depends(check_admin_role)):
    session = get_session()
    rules = session.exec(select(RateLimit)).all()
    session.close()
    return [
        {"id": r.id, "scope": r.scope, "target": r.target, "window": r.window,
         "max_tokens": r.max_tokens, "max_requests": r.max_requests, "created_at": r.created_at}
        for r in rules
    ]


@app.post("/admin/rate-limits")
async def create_rate_limit(rl: RateLimitRequest, current_user: User = Depends(check_admin_role)):
    session = get_session()
    rule = RateLimit(
        scope=rl.scope, target=rl.target, window=rl.window,
        max_tokens=rl.max_tokens, max_requests=rl.max_requests,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    session.close()
    log_audit(action="create_rate_limit", details=f"scope={rl.scope} target={rl.target}", username=current_user.username)
    return {"id": rule.id}


@app.delete("/admin/rate-limits/{limit_id}")
async def delete_rate_limit(limit_id: int, current_user: User = Depends(check_admin_role)):
    session = get_session()
    rule = session.get(RateLimit, limit_id)
    if not rule:
        session.close()
        raise HTTPException(status_code=404, detail="rate limit not found")
    session.delete(rule)
    session.commit()
    session.close()
    return {"deleted": limit_id}


# ─── Guardrails CRUD ─────────────────────────────────────────────────────────

@app.get("/admin/guardrails")
async def list_guardrails(current_user: User = Depends(check_admin_role)):
    session = get_session()
    rules = session.exec(select(Guardrail)).all()
    session.close()
    return [
        {"id": g.id, "name": g.name, "stage": g.stage, "check_type": g.check_type,
         "config_json": g.config_json, "action": g.action, "target_model": g.target_model,
         "target_department": g.target_department, "is_active": g.is_active, "created_at": g.created_at}
        for g in rules
    ]


@app.post("/admin/guardrails")
async def create_guardrail(gr: GuardrailRequest, current_user: User = Depends(check_admin_role)):
    session = get_session()
    rule = Guardrail(
        name=gr.name, stage=gr.stage, check_type=gr.check_type,
        config_json=gr.config_json, action=gr.action,
        target_model=gr.target_model, target_department=gr.target_department,
        is_active=True, created_at=datetime.now(timezone.utc).isoformat(),
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    session.close()
    log_audit(action="create_guardrail", details=f"name={gr.name} stage={gr.stage}", username=current_user.username)
    return {"id": rule.id}


@app.delete("/admin/guardrails/{guardrail_id}")
async def delete_guardrail(guardrail_id: int, current_user: User = Depends(check_admin_role)):
    session = get_session()
    rule = session.get(Guardrail, guardrail_id)
    if not rule:
        session.close()
        raise HTTPException(status_code=404, detail="guardrail not found")
    session.delete(rule)
    session.commit()
    session.close()
    return {"deleted": guardrail_id}


# ─── Virtual Key Management CRUD ─────────────────────────────────────────────

@app.get("/admin/keys")
async def list_virtual_keys(current_user: User = Depends(check_admin_role)):
    from key_manager import list_virtual_keys
    return list_virtual_keys()


@app.post("/admin/keys")
async def create_virtual_key(req: VirtualKeyRequest, current_user: User = Depends(check_admin_role)):
    from key_manager import store_virtual_key
    key_id = store_virtual_key(req.provider, req.key_name, req.api_key, current_user.username)
    log_audit(action="create_virtual_key", details=f"provider={req.provider} name={req.key_name}", username=current_user.username)
    return {"id": key_id}


@app.delete("/admin/keys/{key_id}")
async def revoke_key(key_id: int, current_user: User = Depends(check_admin_role)):
    from key_manager import revoke_virtual_key
    success = revoke_virtual_key(key_id)
    if not success:
        raise HTTPException(status_code=404, detail="key not found")
    log_audit(action="revoke_key", details=f"key_id={key_id}", username=current_user.username)
    return {"revoked": key_id}


# ─── Prompt Templates CRUD ───────────────────────────────────────────────────

@app.get("/templates")
async def list_templates(current_user: User = Depends(get_current_user)):
    session = get_session()
    templates = session.exec(select(PromptTemplate).where(PromptTemplate.is_active == True)).all()
    session.close()
    return [
        {"id": t.id, "name": t.name, "version": t.version, "template_text": t.template_text,
         "model_hint": t.model_hint, "description": t.description, "created_by": t.created_by}
        for t in templates
    ]


@app.post("/templates")
async def create_template(req: TemplateRequest, current_user: User = Depends(check_admin_role)):
    session = get_session()
    t = PromptTemplate(
        name=req.name, version=1, template_text=req.template_text,
        model_hint=req.model_hint, description=req.description,
        created_by=current_user.username, is_active=True,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    session.add(t)
    session.commit()
    session.refresh(t)
    session.close()
    log_audit(action="create_template", details=f"name={req.name}", username=current_user.username)
    return {"id": t.id, "name": t.name, "version": t.version}


@app.delete("/templates/{template_id}")
async def delete_template(template_id: int, current_user: User = Depends(check_admin_role)):
    session = get_session()
    t = session.get(PromptTemplate, template_id)
    if not t:
        session.close()
        raise HTTPException(status_code=404, detail="template not found")
    t.is_active = False
    session.add(t)
    session.commit()
    session.close()
    return {"deactivated": template_id}


@app.post("/templates/{template_id}/render")
async def render_template(template_id: int, variables: dict, current_user: User = Depends(get_current_user)):
    """Preview a template with variable substitution without sending to LLM."""
    session = get_session()
    t = session.get(PromptTemplate, template_id)
    if not t or not t.is_active:
        session.close()
        raise HTTPException(status_code=404, detail="template not found")
    rendered = t.template_text
    for key, val in variables.items():
        rendered = rendered.replace("{{" + key + "}}", str(val))
    session.close()
    return {"rendered": rendered, "model_hint": t.model_hint}


# ─── Audit Logs ──────────────────────────────────────────────────────────────

@app.get("/audit_logs")
async def get_audit_logs(current_user: User = Depends(check_admin_role)):
    session = get_session()
    rows = session.exec(select(AuditLog).order_by(text("id DESC"))).all()
    session.close()
    return [
        {"id": r.id, "user_id": r.user_id, "username": r.username,
         "action": r.action, "masked_prompt": r.masked_prompt,
         "tokens_used": r.tokens_used, "cost_usd": r.cost_usd,
         "details": r.details, "timestamp": r.timestamp}
        for r in rows
    ]


# ─── Analytics Endpoints (for dashboard) ─────────────────────────────────────

@app.get("/analytics/summary")
async def analytics_summary(current_user: User = Depends(check_admin_role)):
    """Aggregate stats for the dashboard KPI cards."""
    session = get_session()
    prompts = session.exec(select(Prompt)).all()
    users = session.exec(select(DBUser)).all()
    session.close()

    total_requests = len(prompts)
    total_tokens = sum(p.tokens_used or 0 for p in prompts)
    total_cost = sum(p.cost_usd or 0.0 for p in prompts)
    cache_hits = sum(1 for p in prompts if p.cache_hit)
    avg_latency = (
        round(sum(p.latency_ms or 0 for p in prompts) / total_requests, 1)
        if total_requests > 0 else 0
    )

    # Model breakdown
    model_usage = {}
    provider_usage = {}
    for p in prompts:
        model_usage[p.model or "unknown"] = model_usage.get(p.model or "unknown", 0) + 1
        provider_usage[p.provider or "unknown"] = provider_usage.get(p.provider or "unknown", 0) + 1

    return {
        "total_requests": total_requests,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 6),
        "total_users": len(users),
        "cache_hit_rate": round(cache_hits / total_requests * 100, 1) if total_requests > 0 else 0,
        "avg_latency_ms": avg_latency,
        "model_usage": model_usage,
        "provider_usage": provider_usage,
    }


@app.get("/analytics/requests")
async def analytics_requests(
    limit: int = 50,
    current_user: User = Depends(check_admin_role),
):
    """Paginated request log for the dashboard request explorer."""
    session = get_session()
    prompts = session.exec(
        select(Prompt).order_by(text("id DESC")).limit(limit)
    ).all()

    # Build user lookup
    user_ids = {p.user_id for p in prompts if p.user_id}
    users = {}
    for uid in user_ids:
        u = session.get(DBUser, uid)
        if u:
            users[uid] = u.username

    session.close()

    return [
        {
            "id": p.id,
            "username": users.get(p.user_id, "unknown"),
            "model": p.model,
            "provider": p.provider,
            "tokens_used": p.tokens_used,
            "cost_usd": p.cost_usd,
            "cache_hit": p.cache_hit,
            "latency_ms": p.latency_ms,
            "created_at": p.created_at,
            "prompt_preview": (p.prompt_text or "")[:100],
            "response_preview": (p.llm_response or "")[:200],
        }
        for p in prompts
    ]


@app.get("/analytics/users")
async def analytics_users(current_user: User = Depends(check_admin_role)):
    """Per-user usage stats for user management."""
    session = get_session()
    users = session.exec(select(DBUser)).all()
    prompts = session.exec(select(Prompt)).all()
    session.close()

    # Aggregate per user
    user_stats = {}
    for u in users:
        role_name = "user"
        if u.role_id:
            s = get_session()
            role = s.get(Role, u.role_id)
            if role:
                role_name = role.name
            s.close()
        user_stats[u.id] = {
            "id": u.id,
            "username": u.username,
            "full_name": u.full_name,
            "email": u.email,
            "role": role_name,
            "department": u.department,
            "disabled": u.disabled,
            "total_requests": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
        }

    for p in prompts:
        if p.user_id in user_stats:
            user_stats[p.user_id]["total_requests"] += 1
            user_stats[p.user_id]["total_tokens"] += p.tokens_used or 0
            user_stats[p.user_id]["total_cost_usd"] += p.cost_usd or 0.0

    return list(user_stats.values())
