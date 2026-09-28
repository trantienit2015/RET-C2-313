"""AgentCore Platform v1.0 - RET-C2-313 InputValidateNode (outer pre_process slot).

Step 1: S-1/S-2 input sanitization + deterministic GMC topic classification
(feed/disapproval/ads/structured-data/japan-policy/appi). Serializes to
validated_input (JSON string) so the inner domain workflow graph can
reconstruct the query + topic.
"""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.service import classify_gmc_topic, sanitize_query


class InputValidateNode(FunctionNode):
    """S-1/S-2 input validation + GMC topic extraction for the inner graph."""

    # S-1: explicit by design, not inherited implicitly.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        user_input = state.get("user_input", "")

        emit_trace_event(
            "gmc_operator_query_received",
            {"correlation_id": state.get("correlation_id", "")},
            state,
        )

        if not isinstance(user_input, str) or not user_input.strip():
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["InputValidateNode: user_input is empty or missing"],
            }

        sanitized = sanitize_query(user_input.strip())
        gmc_topic = classify_gmc_topic(sanitized)

        return {
            "gmc_topic": gmc_topic,
            "validated_input": json.dumps({"query": sanitized, "gmc_topic": gmc_topic}, ensure_ascii=False),
            "status": AgentStatus.SUCCESS.value,
        }

    def _extra_security_gate_input(self, state: dict[str, Any]) -> dict[str, Any]:
        """S-2 domain hook: re-scan the normalized query at the gate boundary."""
        payload = state.get("validated_input") or state.get("user_input") or ""
        if isinstance(payload, str) and len(payload) > 4000:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["S-2 gate: input exceeds maximum length"],
            }
        return state
