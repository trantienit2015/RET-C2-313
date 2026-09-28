"""AgentCore Platform v1.0 - RET-C2-313 state schema."""

# ADR-005: State must be a flat TypedDict - never Pydantic BaseModel.
# LangGraph checkpoints use msgpack serialization; Pydantic objects (and nested
# dict/list containers) are not msgpack-safe. Extend AgentState with agent-specific
# fields only. Nested list[dict]/dict fields are stored as JSON strings and
# (de)serialized at the node boundary via to_json/from_json below. Do NOT add
# credentials, secrets, or Pydantic models.

from __future__ import annotations

import json
from typing import Any, NotRequired, Optional

from framework.schemas.agent_state import AgentState


def to_json(value: Any) -> Optional[str]:
    """Serialize a list/dict State value to a compact JSON string (ADR-005, msgpack-safe)."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def from_json(value: Any, default: Any) -> Any:
    """Deserialize a JSON-string State value back to its list/dict form (tolerant)."""
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


# Type-check note: the wheel ships no py.typed, so mypy resolves AgentState to Any
# and reports every NotRequired below as valid-type. The fields are correct (the state
# contract requires NotRequired) -- the report is a packaging artifact, suppressed per field.
# Drop these ignores once the wheel ships py.typed.
class State(AgentState):
    """GMC / Google Shopping operations Q&A agent state (Japan-policy overlay).

    Shared fields (user_input, validated_input, status, session_id, node_history,
    error_log, result, formatted_output, hitl_*, etc.) are inherited from AgentState.
    Only agent-specific, flat, JSON-serializable fields are declared below; all are
    NotRequired (written mid-pipeline - C8).
    """

    gmc_topic: NotRequired[str]  # type: ignore[valid-type]  # feed | disapproval | ads | structured_data | japan_policy | appi | general
    # JSON list[{doc_id, tier, source, text}] - Tier-2 KB retrieval results.
    retrieved_passages: NotRequired[str | None]  # type: ignore[valid-type]
    # JSON list[{title, url}] - Tier-1 live GMC/Shopping reference URLs (not ingested).
    live_refs: NotRequired[str | None]  # type: ignore[valid-type]
    # JSON dict{encoding, gtin_exemption, jpy_format, appi_disclosure} - Japan-locale overlay notes.
    japan_overlay: NotRequired[str | None]  # type: ignore[valid-type]
    draft_answer: NotRequired[str | None]  # type: ignore[valid-type]
    # JSON list[str] - citation ids/urls the draft answer references.
    citations: NotRequired[str | None]  # type: ignore[valid-type]
