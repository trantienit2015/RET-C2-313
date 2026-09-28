"""AgentCore Platform v1.0 - RET-C2-313 JapanPolicyFilterNode (inner step 3)."""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import to_json
from src.services.service import apply_japan_overlay


class JapanPolicyFilterNode(FunctionNode):
    """Apply Japan-locale policy overlay: encoding, GTIN exemptions, JPY format, APPI disclosure."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("user_input", "")
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            parsed = None
        if not isinstance(parsed, dict) or not parsed.get("query"):
            return {"status": AgentStatus.ERROR.value, "error_log": ["JapanPolicyFilterNode: missing query"]}

        gmc_topic = state.get("gmc_topic") or parsed.get("gmc_topic", "general")
        overlay = apply_japan_overlay(gmc_topic, parsed["query"])

        emit_trace_event(
            "japan_policy_overlay_applied",
            {"gmc_topic": gmc_topic, "correlation_id": state.get("correlation_id", "")},
            state,
        )
        return {"japan_overlay": to_json(overlay), "status": AgentStatus.SUCCESS.value}
