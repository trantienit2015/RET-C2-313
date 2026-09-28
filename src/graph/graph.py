"""AgentCore Platform v1.0 - RET-C2-313 outer graph (Cat 2).

Cat 2: outer AgentBaseGraph with the fixed 5-node backbone. Domain complexity is
encapsulated in GmcOperationsGraphNode (the `main` slot), which wraps the inner
GmcOperationsWorkflowGraph. Do NOT override add_edges().

Backbone: initialize -> pre_process(InputValidate) -> main(GraphNode) -> post_process(ResponseValidate) -> finalize

GmcOperationsGraphNode lives here (not under src/nodes/) - the PB-6 invoke-order
test only discovers BaseNode subclasses under src/nodes/, and a GraphNode's
__call__ intentionally skips the standard S-2/S-4/S-3 lifecycle (gating is
delegated to the inner subgraph).
"""

from typing import Any, ClassVar, cast

from framework.graph.agent_base_graph import AgentBaseGraph
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.nodes.post_process_node import ResponseValidateNode
from src.nodes.pre_process_node import InputValidateNode
from src.schemas.state import State


class GmcOperationsGraphNode(GraphNode):
    """Wraps the inner GMC/Google Shopping operations Q&A workflow (Cat 2 composition)."""

    # S-1 (outer main-slot wrapper - first node in the outer backbone to receive
    # caller input after pre_process): matches agent.yaml required_trust_level
    # (declared explicitly rather than inheriting the framework's permissive
    # ANONYMOUS default).
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL
    # "propagate": re-raise inner errors as SubgraphError (fail fast - default).
    error_strategy: ClassVar[str] = "propagate"
    # No HITL in this template.
    propagate_hitl: ClassVar[bool] = False

    def __init__(self, kb: dict[str, Any] | None = None, llm: Any = None) -> None:
        super().__init__()
        self._kb = kb
        self._llm = llm

    def get_subgraph(self) -> Any:
        from src.graph.domain_workflow_graph import GmcOperationsWorkflowGraph

        sg = GmcOperationsWorkflowGraph(config=self._parent_config())
        sg.compile()
        return sg

    def extract_input(self, state: AgentState) -> str:
        emit_trace_event("gmc_operations_dispatched", {"correlation_id": state.get("correlation_id", "")}, state)
        return cast(str, state.get("validated_input", state.get("user_input", "")))

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        emit_trace_event(
            "gmc_operations_completed",
            {"correlation_id": state.get("correlation_id", ""), "status": str(sub_result.get("status"))},
            state,
        )
        return {
            "gmc_topic": sub_result.get("gmc_topic", ""),
            "retrieved_passages": sub_result.get("retrieved_passages"),
            "live_refs": sub_result.get("live_refs"),
            "japan_overlay": sub_result.get("japan_overlay"),
            "draft_answer": sub_result.get("draft_answer"),
            "citations": sub_result.get("citations"),
            "status": sub_result.get("status"),
        }

    def _parent_config(self) -> dict[str, Any]:
        return {"kb": self._kb, "llm": self._llm}


class RetailGmcOperationsQAGraph(AgentBaseGraph):
    """RET-C2-313 - Retail Google Merchant Center & Google Shopping Operations Q&A Agent (Cat 2)."""

    @property
    def name(self) -> str:
        return "ret-c2-313"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # injects initialize + finalize

        kb = self.config.get("kb")
        llm = self.config.get("llm")

        self._nodes["pre_process"] = InputValidateNode()
        self._nodes["main"] = GmcOperationsGraphNode(kb=kb, llm=llm)
        self._nodes["post_process"] = ResponseValidateNode()

    # add_edges() is NOT overridden - backbone wiring belongs to the framework.


# Alias for agent.yaml module:"src.graph" resolution (AgentRegistry / api/server.py).
Graph = RetailGmcOperationsQAGraph
