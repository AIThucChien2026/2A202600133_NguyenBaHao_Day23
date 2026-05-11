"""Node skeletons for the LangGraph workflow.

Each function should be small, testable, and return a partial state update. Avoid mutating the
input state in place.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import BaseModel, Field

from .state import AgentState, ApprovalDecision, Route, make_event

logger = logging.getLogger(__name__)

# ── LLM Configuration ─────────────────────────────────────────────────────────

LLM_MAX_RETRIES = 3        # Max retry attempts for LLM calls
LLM_TIMEOUT_SEC = 30   # Seconds before giving up on one attempt
LLM_BACKOFF_BASE = 2       # Exponential backoff base (seconds)


def get_llm(temperature: float = 0) -> Any:  # noqa: ANN401
    """Build and return a Gemini LLM instance."""
    import os

    from dotenv import load_dotenv
    load_dotenv()
    from langchain_google_genai import ChatGoogleGenerativeAI
    api_key = os.getenv("GEMINI_API")
    model_name = os.getenv("MODEL_NAME", "gemini-2.0-flash")
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=temperature,
        timeout=LLM_TIMEOUT_SEC,
        max_retries=0,  # We handle retries ourselves below
    )


def llm_invoke_with_retry(
    llm: Any, prompt: str, *, max_retries: int = LLM_MAX_RETRIES,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    """Invoke an LLM with exponential-backoff retry on transient errors.

    Args:
        llm: A LangChain chat model (may be wrapped with .with_structured_output).
        prompt: The prompt string to send.
        max_retries: Number of retry attempts before raising.

    Returns:
        The raw LLM response object.

    Raises:
        RuntimeError: If all retries are exhausted.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            start = time.monotonic()
            response = llm.invoke(prompt)
            elapsed = time.monotonic() - start
            logger.debug("LLM call succeeded in %.2fs (attempt %d)", elapsed, attempt)
            return response
        except Exception as exc:  # noqa: BLE001
            wait = LLM_BACKOFF_BASE ** attempt
            logger.warning(
                "LLM call failed (attempt %d/%d): %s — retrying in %.0fs",
                attempt, max_retries, exc, wait,
            )
            last_exc = exc
            if attempt < max_retries:
                time.sleep(wait)
    raise RuntimeError(f"LLM call failed after {max_retries} retries") from last_exc


def intake_node(state: AgentState) -> dict:
    """Normalize raw query into state fields.
    Performs basic normalization and mock PII redaction.
    """
    query = state.get("query", "").strip()
    query = query.replace("SSN", "[REDACTED_SSN]")
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized and PII checked")],
    }


def classify_node(state: AgentState) -> dict:
    """Classify the query into a route using a real LLM with Structured Output."""
    query = state.get("query", "")
    
    class ClassificationResult(BaseModel):
        route: str = Field(
            description="One of: 'simple', 'tool', 'missing_info', 'risky', 'error'."
        )
        risk_level: str = Field(
            description="Must be 'high' if route is 'risky', else 'low'."
        )
        
    llm = get_llm(temperature=0).with_structured_output(ClassificationResult)
    
    prompt = (
        f'Classify this support query: "{query}"\n\n'
        "Rules for routing:\n"
        "1. 'risky': Actions that modify data (refund, delete, send, cancel, remove, revoke)."
        " Highest priority.\n"
        "2. 'tool': Retrieve information (status, order, lookup, check, track, find, search).\n"
        "3. 'missing_info': Very short/vague queries (< 5 words) using pronouns like 'it'.\n"
        "4. 'error': Reports of failures, timeouts, crashes (e.g. 'Timeout failure...').\n"
        "5. 'simple': General questions that don't fit above.\n\n"
        "Return exactly one route string and the appropriate risk level."
    )
    
    try:
        result = llm_invoke_with_retry(llm, prompt)
        route = result.route
        risk_level = result.risk_level
    except Exception:
        # Fallback in case of structured output parsing error or all retries exhausted
        route = "simple"
        risk_level = "low"
        
    if route not in ["simple", "tool", "missing_info", "risky", "error"]:
        route = "simple"
        
    return {
        "route": route,
        "risk_level": risk_level,
        "events": [make_event("classify", "completed", f"LLM classified route={route}")],
    }


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information using an LLM."""
    query = state.get("query", "")
    llm = get_llm(temperature=0.7)
    
    prompt = (
        f"The user asked: '{query}'. This is too vague. "
        "Write a polite, single sentence asking for more specific context or an ID."
    )
    response = llm_invoke_with_retry(llm, prompt)
    question = _extract_text(response)
    
    return {
        "pending_question": question,
        "final_answer": question,
        "events": [make_event("clarify", "completed", "LLM generated missing info request")],
    }


def tool_node(state: AgentState) -> dict:
    """Call a mock tool, simulating transient failures for the error route."""
    attempt = int(state.get("attempt", 0))
    sid = state.get("scenario_id", "unknown")
    if state.get("route") == Route.ERROR.value and attempt < 2:
        result = f"ERROR: transient failure attempt={attempt} scenario={sid}"
    else:
        result = f"mock-tool-result for scenario={sid} attempt={attempt}"
    return {
        "tool_results": [result],
        "events": [make_event("tool", "completed", f"tool executed attempt={attempt}")],
    }


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action for approval."""
    query = state.get("query", "").lower()
    if "refund" in query:
        action_type = "refund"
    elif "delete" in query:
        action_type = "deletion"
    else:
        action_type = "high-risk external action"
    proposed_action = f"Proposed {action_type}. Justification: requested by user. Risk: High."
    return {
        "proposed_action": proposed_action,
        "events": [make_event("risky_action", "pending_approval", "approval required")],
    }


def approval_node(state: AgentState) -> dict:
    """Human approval step with optional LangGraph interrupt().
    """
    import os

    if os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true":
        from langgraph.types import interrupt

        value = interrupt({
            "proposed_action": state.get("proposed_action"),
            "risk_level": state.get("risk_level"),
        })
        if isinstance(value, dict):
            decision = ApprovalDecision(**value)
        else:
            decision = ApprovalDecision(approved=bool(value))
    else:
        decision = ApprovalDecision(approved=True, comment="mock approval for lab workflow")
    return {
        "approval": decision.model_dump(),
        "events": [make_event("approval", "completed", f"approved={decision.approved}")],
    }


def _extract_text(response: Any) -> str:  # noqa: ANN401
    """Safely extract text from a LangChain LLM response regardless of content type."""
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        # Gemini may return a list of content parts
        parts = [p.get("text", "") if isinstance(p, dict) else str(p) for p in content]
        return "".join(parts).strip()
    return str(content).strip()

def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt with simulated exponential backoff."""
    attempt = int(state.get("attempt", 0)) + 1
    backoff_ms = (2 ** attempt) * 100
    errors = [f"transient failure attempt={attempt}"]
    event = make_event(
        "retry", "completed",
        f"retry attempt recorded, backoff {backoff_ms}ms",
        attempt=attempt,
    )
    return {"attempt": attempt, "errors": errors, "events": [event]}


def answer_node(state: AgentState) -> dict:
    """Produce a final response grounded in tool results using an LLM."""
    query = state.get("query", "")
    tool_results = state.get("tool_results", [])
    llm = get_llm(temperature=0.7)
    
    if tool_results:
        latest_result = tool_results[-1]
        prompt = (
            f"The user asked: '{query}'. The system returned: '{latest_result}'. "
            "Write a polite, concise final response summarizing this result."
        )
    else:
        prompt = (
            f"The user asked: '{query}'. "
            "Write a polite, concise response confirming the request has been processed."
        )
    response = llm_invoke_with_retry(llm, prompt)
    answer = _extract_text(response)
    
    return {
        "final_answer": answer,
        "events": [make_event("answer", "completed", "LLM generated final answer")],
    }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool results — simple string check (tool output is deterministic mock).

    Checks whether the latest tool result contains 'ERROR'. If so, signals a retry.
    When tool_node is replaced with a real API client, upgrade this to an LLM-as-judge.
    """
    tool_results = state.get("tool_results", [])
    latest = tool_results[-1] if tool_results else ""
    eval_res = "needs_retry" if "ERROR" in latest else "success"
    return {
        "evaluation_result": eval_res,
        "events": [make_event("evaluate", "completed", f"eval={eval_res} (string check)")],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Log unresolvable failures for manual review in a dead-letter queue."""
    attempt = state.get("attempt", 0)
    scenario = state.get("scenario_id", "unknown")
    dlq_msg = f"DLQ: scenario={scenario}, failed after {attempt} attempts."
    return {
        "final_answer": "System failure: cannot recover. Logged for manual review.",
        "events": [make_event(
            "dead_letter", "completed",
            f"max retries exceeded, attempt={attempt}. {dlq_msg}",
        )],
    }


def finalize_node(state: AgentState) -> dict:
    """Finalize the run and emit a final audit event."""
    return {"events": [make_event("finalize", "completed", "workflow finished")]}
