"""
Guardrails — Pre-request and post-response validation.

Enforces content policies, input constraints, and output quality checks
before and after the LLM call.
"""
import re
import json
import logging
from typing import List, Optional, Tuple
from sqlmodel import select
from database import get_session, Guardrail

logger = logging.getLogger("ai_gateway.guardrails")


class GuardrailViolation(Exception):
    """Raised when a guardrail check fails."""
    def __init__(self, rule_name: str, message: str):
        self.rule_name = rule_name
        super().__init__(f"[{rule_name}] {message}")


# ─── Built-in check functions ───────────────────────────────────────────────

def _check_max_length(text: str, config: dict) -> Optional[str]:
    """Reject prompts exceeding a character limit."""
    max_chars = config.get("max_characters", 10000)
    if len(text) > max_chars:
        return f"Input exceeds maximum length ({len(text)}/{max_chars} characters)"
    return None


def _check_prohibited_topics(text: str, config: dict) -> Optional[str]:
    """Reject prompts containing prohibited keywords/phrases."""
    topics = config.get("topics", [])
    text_lower = text.lower()
    for topic in topics:
        if topic.lower() in text_lower:
            return f"Prohibited topic detected: '{topic}'"
    return None


def _check_regex_patterns(text: str, config: dict) -> Optional[str]:
    """Reject text matching any of the provided regex patterns."""
    patterns = config.get("patterns", [])
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return f"Text matches prohibited pattern: '{pattern}'"
    return None


def _check_json_output(text: str, config: dict) -> Optional[str]:
    """Validate that the output is valid JSON (if required)."""
    if config.get("require_json", False):
        try:
            json.loads(text)
        except json.JSONDecodeError:
            return "Output is not valid JSON as required"
    return None


def _check_min_length(text: str, config: dict) -> Optional[str]:
    """Reject responses that are too short (likely incomplete)."""
    min_chars = config.get("min_characters", 1)
    if len(text.strip()) < min_chars:
        return f"Output too short ({len(text.strip())}/{min_chars} characters)"
    return None


# Registry of built-in check functions
BUILTIN_CHECKS = {
    "max_length": _check_max_length,
    "prohibited_topics": _check_prohibited_topics,
    "regex_filter": _check_regex_patterns,
    "json_output": _check_json_output,
    "min_length": _check_min_length,
}


def run_pre_request_guardrails(
    prompt: str,
    model: Optional[str] = None,
    department: Optional[str] = None,
) -> List[str]:
    """
    Run all active pre-request guardrails against the prompt.
    Returns a list of violation messages (empty = all passed).
    """
    return _run_guardrails(prompt, stage="pre", model=model, department=department)


def run_post_response_guardrails(
    response: str,
    model: Optional[str] = None,
    department: Optional[str] = None,
) -> List[str]:
    """
    Run all active post-response guardrails against the LLM output.
    Returns a list of violation messages (empty = all passed).
    """
    return _run_guardrails(response, stage="post", model=model, department=department)


def _run_guardrails(
    text: str,
    stage: str,
    model: Optional[str] = None,
    department: Optional[str] = None,
) -> List[str]:
    """Internal: run all matching guardrails for a given stage."""
    session = get_session()
    violations = []
    try:
        query = select(Guardrail).where(
            Guardrail.stage == stage,
            Guardrail.is_active == True,
        )
        rules = session.exec(query).all()

        for rule in rules:
            # Scope filtering
            if rule.target_model and rule.target_model != model:
                continue
            if rule.target_department and rule.target_department != department:
                continue

            # Parse the JSON config for this rule
            try:
                config = json.loads(rule.config_json) if rule.config_json else {}
            except json.JSONDecodeError:
                logger.warning(f"Invalid config JSON for guardrail {rule.id}")
                continue

            # Run the check
            check_fn = BUILTIN_CHECKS.get(rule.check_type)
            if check_fn:
                result = check_fn(text, config)
                if result:
                    violations.append(f"[{rule.name}] {result}")
                    if rule.action == "block":
                        # Short-circuit: first blocking violation stops processing
                        break
            else:
                logger.warning(f"Unknown check type '{rule.check_type}' for guardrail {rule.id}")

    finally:
        session.close()

    return violations
