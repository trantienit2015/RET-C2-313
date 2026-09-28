"""AgentCore Platform v1.0 - RET-C2-313 ResponseValidateNode (outer post_process slot).

Step 6: S-3 non-suppressible citation-validity gate. Every citation the draft
answer references is re-checked here UNCONDITIONALLY against the retrieved
Tier-2 passages and the Tier-1 live URL - it never trusts a "validated" flag
carried in state from upstream nodes. A fabricated GMC policy citation FAILs
loudly (never silently passes).
"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json, to_json
from src.services.service import validate_citations


class ResponseValidateNode(FunctionNode):
    """S-3 non-suppressible citation-validity gate + final answer assembly."""

    # S-1: explicit by design, not inherited implicitly.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("status") in (AgentStatus.ERROR.value, AgentStatus.ERROR.value):
            return {"status": AgentStatus.ERROR.value}

        draft_answer = state.get("draft_answer", "")
        citations = from_json(state.get("citations"), [])
        passages = from_json(state.get("retrieved_passages"), [])
        live_refs = from_json(state.get("live_refs"), [])
        live_ref = live_refs[0] if live_refs else {"title": "", "url": ""}

        # Non-suppressible: always re-check, ignore any upstream "validated" attempt.
        if not validate_citations(citations, passages, live_ref):
            emit_trace_event(
                "response_validate_citation_rejected", {"correlation_id": state.get("correlation_id", "")}, state
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["S-3 gate: draft answer cites a policy reference not found in KB or live URL - rejected"],
            }

        formatted = {
            "answer": draft_answer,
            "gmc_topic": state.get("gmc_topic", ""),
            "policy_reference": live_ref,
            "japan_overlay": from_json(state.get("japan_overlay"), {}),
            "citations": citations,
        }

        emit_trace_event(
            "response_validated",
            {"citation_count": len(citations), "correlation_id": state.get("correlation_id", "")},
            state,
        )

        return {
            "formatted_output": formatted,
            "result": to_json(formatted),
            "status": AgentStatus.SUCCESS.value,
        }

    def _extra_security_gate_output(self, state: dict[str, Any]) -> dict[str, Any]:
        """S-3 domain hook: re-verify no citation was suppressed/emptied between execute() and the gate.

        Self-consistency check on the already-assembled `formatted_output` dict only
        (its own keys) - does NOT re-derive expected values from separately-read
        state fields (`retrieved_passages` / `live_refs`). Cross-referencing other
        state fields here is fragile against the real framework wheel (confirmed
        regression precedent) even though the pipeline's real non-suppressible
        check already ran once in execute() against fresh KB/live-ref data.
        """
        formatted = state.get("formatted_output")
        if not isinstance(formatted, dict):
            return state
        citations = formatted.get("citations") or []
        live_url = (formatted.get("policy_reference") or {}).get("url", "")
        if not citations or (live_url and live_url not in citations):
            emit_trace_event("response_validate_gate_suppression_blocked", {}, state)
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["S-3 gate: citation list empty or missing the live policy reference at output gate"],
            }
        return state
