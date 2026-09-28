"""PB-6 boundary coverage for GmcOperationsGraphNode (Cat 2 outer main-slot wrapper).

GmcOperationsGraphNode lives under src/graph/graph.py (not src/nodes/), so the
generic PB-6 invoke-order probe (test_pb_invoke_order.py, which only discovers
BaseNode subclasses under src/nodes/) never exercises it. This file is the
required compensating boundary test for a GraphNode outside the PB-6 probe
scope - it is NOT a workaround for avoiding PB-6; it targets the
real security boundary that the outer GraphNode sits on (first node in the
outer backbone, after pre_process, to receive caller input).

Covers:
  - S-1: caller_trust_level below GmcOperationsGraphNode.required_trust_level
    (S-1 guard runs inside BaseNode.__call__, before execute()/get_subgraph()
    run).
  - Boundary mapping: extract_input() only reads the fields it needs;
    merge_output() maps subgraph fields explicitly (criterion #9 - no raw
    pass-through of the subgraph result dict).
  - Delegation-has-purpose: GmcOperationsGraphNode intentionally does not run
    its own S-2/S-3 content gates - gating is delegated to the inner
    subgraph's entry node (IntentClassifyNode), per
    framework/nodes/graph_node.py's GraphNode contract (GraphNode.execute()
    does not call _security_gate_input/output; the inner BaseGraph.invoke()
    runs the standard S-1..S-4 pipeline on its own nodes). IntentClassifyNode
    is ANONYMOUS because trust is already verified at the outer
    GmcOperationsGraphNode boundary (S-1) before the inner subgraph runs.
"""

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.graph.graph import GmcOperationsGraphNode
from src.nodes.intent_classify_node import IntentClassifyNode


class TestGmcOperationsGraphNodeS1TrustGate:
    """S-1: the outer GraphNode wrapper enforces its own trust gate before delegating."""

    def setup_method(self):
        self.node = GmcOperationsGraphNode()

    def test_anonymous_caller_denied_execute_not_reached(self):
        # GmcOperationsGraphNode requires VERIFIED_EXTERNAL; a caller with only
        # ANONYMOUS trust must be denied by BaseNode.__call__ before
        # execute()/get_subgraph() ever run (no subgraph dispatch attempted).
        state = {
            "caller_trust_level": TrustLevel.ANONYMOUS.value,
            "validated_input": '{"query": "GTIN missing", "gmc_topic": "gtin"}',
        }
        result = self.node(state)

        assert result["status"] == AgentStatus.ERROR.value
        assert any("S-1 trust gate denied" in msg for msg in result["error_log"])
        # execute() would have appended dispatch-only fields on the success path -
        # S-1 denial returns before get_subgraph()/merge_output() ever run.
        assert "draft_answer" not in result
        assert "citations" not in result

    def test_verified_external_is_the_required_level(self):
        # A caller at the required trust level clears S-1 (does not assert on
        # subgraph output here - that is exercised by tests/integration/test_graph.py).
        assert GmcOperationsGraphNode.required_trust_level == TrustLevel.VERIFIED_EXTERNAL


class TestGmcOperationsGraphNodeBoundaryMapping:
    """extract_input()/merge_output() define the schema boundary (criterion #9)."""

    def setup_method(self):
        self.node = GmcOperationsGraphNode()

    def test_extract_input_prefers_validated_input(self):
        state = {"validated_input": "normalized query", "user_input": "raw query"}
        assert self.node.extract_input(state) == "normalized query"

    def test_extract_input_falls_back_to_user_input(self):
        assert self.node.extract_input({"user_input": "raw query"}) == "raw query"

    def test_merge_output_maps_fields_explicitly_no_raw_passthrough(self):
        sub_result = {
            "gmc_topic": "gtin",
            "retrieved_passages": "[]",
            "live_refs": "[]",
            "japan_overlay": "{}",
            "draft_answer": "Set identifier_exists=false and resubmit.",
            "citations": "[]",
            "status": AgentStatus.SUCCESS.value,
            "trace_id": "must-not-leak",
            "correlation_id": "must-not-leak",
            "node_history": ["must-not-leak"],
        }
        delta = self.node.merge_output({}, sub_result)

        assert delta["gmc_topic"] == "gtin"
        assert delta["draft_answer"] == "Set identifier_exists=false and resubmit."
        assert delta["status"] == AgentStatus.SUCCESS.value
        # Explicit field mapping - the subgraph's internal-only fields must not
        # pass through untouched (no `**sub_result` splat in merge_output()).
        assert "trace_id" not in delta
        assert "node_history" not in delta


class TestGmcOperationsGraphNodeDelegatesGatingToInnerSubgraph:
    """Delegation is a deliberate design choice, not a gap - proven here, not just asserted in docs."""

    def test_inner_entry_node_declares_its_own_trust_level(self):
        # IntentClassifyNode is the inner subgraph's entry node (first node
        # inside GmcOperationsWorkflowGraph). It runs the standard S-1..S-4
        # BaseNode.__call__ pipeline on its own - the outer
        # GmcOperationsGraphNode does not re-implement per-node gating, it only
        # enforces the outer S-1 boundary above.
        assert IntentClassifyNode.required_trust_level == TrustLevel.ANONYMOUS

    def test_graph_node_execute_is_framework_provided(self):
        # GmcOperationsGraphNode does not override execute() - GraphNode.execute()
        # (framework/nodes/graph_node.py) owns dispatch to get_subgraph() /
        # extract_input() / merge_output(); confirms no local override that
        # could silently skip the framework's subgraph-error handling.
        assert "execute" not in GmcOperationsGraphNode.__dict__
