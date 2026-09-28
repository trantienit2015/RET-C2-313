"""AgentCore Platform v1.0 - RET-C2-313 inner domain workflow graph.

Cat 2 inner graph: GMC-topic classification -> Tier-2/Tier-1 policy retrieval ->
Japan-locale policy overlay -> step-by-step resolution synthesis. Instantiated by
GmcOperationsGraphNode.get_subgraph() in graph.py.

Pipeline (linear, fail-fast on ERROR):
    START -> intent_classify -> policy_retrieve -> japan_policy_filter -> resolution_synthesize -> END
"""

from typing import Any
from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus

from src.nodes.intent_classify_node import IntentClassifyNode
from src.nodes.japan_policy_filter_node import JapanPolicyFilterNode
from src.nodes.policy_retrieve_node import PolicyRetrieveNode
from src.nodes.resolution_synthesize_node import ResolutionSynthesizeNode
from src.schemas.state import State


class GmcOperationsWorkflowGraph(BaseGraph):
    """Inner graph for the RET-C2-313 GMC/Google Shopping operations Q&A workflow."""

    @property
    def name(self) -> str:
        return "gmc-operations-workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        # No mandatory config: kb / llm are optional (deterministic fallbacks exist).
        pass

    def register_nodes(self) -> None:
        # No super() - BaseGraph.register_nodes() is abstract.
        kb = self.config.get("kb")
        llm = self.config.get("llm")

        self._nodes["intent_classify"] = IntentClassifyNode()
        self._nodes["policy_retrieve"] = PolicyRetrieveNode(kb=kb)
        self._nodes["japan_policy_filter"] = JapanPolicyFilterNode()
        self._nodes["resolution_synthesize"] = ResolutionSynthesizeNode(llm=llm)

    def add_edges(self) -> None:
        self._sg.add_edge(START, "intent_classify")
        self._sg.add_conditional_edges(
            "intent_classify",
            lambda s: END if self._is_error(s) else "policy_retrieve",
            {"policy_retrieve": "policy_retrieve", END: END},
        )
        self._sg.add_conditional_edges(
            "policy_retrieve",
            lambda s: END if self._is_error(s) else "japan_policy_filter",
            {"japan_policy_filter": "japan_policy_filter", END: END},
        )
        self._sg.add_conditional_edges(
            "japan_policy_filter",
            lambda s: END if self._is_error(s) else "resolution_synthesize",
            {"resolution_synthesize": "resolution_synthesize", END: END},
        )
        self._sg.add_edge("resolution_synthesize", END)

    @staticmethod
    def _is_error(state: AgentState) -> bool:
        return state.get("status") in (AgentStatus.ERROR.value, AgentStatus.ERROR.value)

    def route(self, state: AgentState) -> str:
        return END if self._is_error(state) else "resolution_synthesize"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "gmc_topic": state.get("gmc_topic", ""),
            "retrieved_passages": state.get("retrieved_passages"),
            "live_refs": state.get("live_refs"),
            "japan_overlay": state.get("japan_overlay"),
            "draft_answer": state.get("draft_answer"),
            "citations": state.get("citations"),
            "status": state.get("status"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
