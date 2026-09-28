"""AgentCore Platform v1.0 - RET-C2-313 PolicyRetrieveNode (inner step 2)."""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import to_json
from src.services.service import live_reference, retrieve_policy


class PolicyRetrieveNode(FunctionNode):
    """Tier-2 KB retrieval (Japan additions + playbooks + APPI) + Tier-1 live reference."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, kb: dict[str, Any] | None = None) -> None:
        super().__init__()
        self._kb = kb

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("user_input", "")
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            parsed = None
        if not isinstance(parsed, dict) or not parsed.get("query"):
            return {"status": AgentStatus.ERROR.value, "error_log": ["PolicyRetrieveNode: missing query"]}

        gmc_topic = state.get("gmc_topic") or parsed.get("gmc_topic", "general")
        query = parsed["query"]

        passages = retrieve_policy(gmc_topic, query, self._kb)
        live_ref = live_reference(gmc_topic)

        emit_trace_event(
            "gmc_policy_retrieved",
            {"passage_count": len(passages), "correlation_id": state.get("correlation_id", "")},
            state,
        )
        return {
            "retrieved_passages": to_json(passages),
            "live_refs": to_json([live_ref]),
            "status": AgentStatus.SUCCESS.value,
        }
