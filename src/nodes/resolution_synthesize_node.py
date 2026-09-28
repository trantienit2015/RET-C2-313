"""AgentCore Platform v1.0 - RET-C2-313 ResolutionSynthesizeNode (inner step 4)."""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json, to_json
from src.services.service import LLMSynthesisError, synthesize_resolution


class ResolutionSynthesizeNode(FunctionNode):
    """LLM-essential step-by-step resolution synthesis with citations.

    Deterministic fallback (playbook-based draft) keeps the pipeline runnable
    without an LLM.
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, llm: Any = None) -> None:
        super().__init__()
        self._llm = llm

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("user_input", "")
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            parsed = None
        if not isinstance(parsed, dict) or not parsed.get("query"):
            return {"status": AgentStatus.ERROR.value, "error_log": ["ResolutionSynthesizeNode: missing query"]}

        passages = from_json(state.get("retrieved_passages"), [])
        live_refs = from_json(state.get("live_refs"), [])
        overlay = from_json(state.get("japan_overlay"), {})
        live_ref = live_refs[0] if live_refs else {"title": "", "url": ""}

        if self._llm is not None and hasattr(self._llm, "complete"):
            emit_trace_event("resolution_synth_llm_call", {"correlation_id": state.get("correlation_id", "")}, state)
        try:
            draft_answer, citations = synthesize_resolution(parsed["query"], passages, live_ref, overlay, self._llm)
        except LLMSynthesisError as exc:
            # A configured LLM failed/returned nothing - this must surface as an
            # error, not silently degrade to the deterministic playbook path
            # (that fallback is reserved for llm is None - see LLMSynthesisError).
            emit_trace_event(
                "resolution_synth_llm_failed",
                {"correlation_id": state.get("correlation_id", ""), "reason": str(exc)},
                state,
            )
            return {"status": AgentStatus.ERROR.value, "error_log": [f"ResolutionSynthesizeNode: {exc}"]}

        emit_trace_event(
            "resolution_synthesized",
            {"citation_count": len(citations), "correlation_id": state.get("correlation_id", "")},
            state,
        )
        return {"draft_answer": draft_answer, "citations": to_json(citations), "status": AgentStatus.SUCCESS.value}
