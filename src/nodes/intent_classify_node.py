"""AgentCore Platform v1.0 - RET-C2-313 IntentClassifyNode (inner step 1)."""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.service import classify_gmc_topic


class IntentClassifyNode(FunctionNode):
    """Classify the operator query into a GMC sub-domain for KB routing."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("user_input", "")
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            parsed = None
        if not isinstance(parsed, dict) or not parsed.get("query"):
            return {"status": AgentStatus.ERROR.value, "error_log": ["IntentClassifyNode: missing query"]}

        query = parsed["query"]
        gmc_topic = parsed.get("gmc_topic") or classify_gmc_topic(query)

        emit_trace_event(
            "gmc_intent_classified",
            {"gmc_topic": gmc_topic, "correlation_id": state.get("correlation_id", "")},
            state,
        )
        return {"intent": gmc_topic, "gmc_topic": gmc_topic, "status": AgentStatus.SUCCESS.value}
