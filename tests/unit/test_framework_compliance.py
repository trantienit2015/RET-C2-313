# RET-C2-313 - Framework compliance tests TC-01..TC-08, written for
# this template's real architecture (Cat 2: outer pre/post FunctionNode +
# GraphNode-wrapped inner intent-classify -> policy-retrieve -> japan-overlay -> synthesize subgraph).

import os
import re

import pytest
from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.graph.graph import GmcOperationsGraphNode
from src.nodes import (
    intent_classify_node,
    japan_policy_filter_node,
    policy_retrieve_node,
    post_process_node,
    pre_process_node,
    resolution_synthesize_node,
)
from src.schemas.state import State

_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
TRUST = TrustLevel.VERIFIED_EXTERNAL.value


def _src_files():
    for root, _d, files in os.walk(_SRC):
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


# TC-01 - State is a flat TypedDict extending AgentState, added fields are NotRequired.
class TestTC01StateContract:
    def test_state_is_typeddict_extending_agent_state(self):
        assert hasattr(State, "__annotations__")
        assert "gmc_topic" in State.__annotations__
        assert set(AgentState.__annotations__).issubset(set(State.__annotations__))

    def test_added_fields_are_notrequired(self):
        added = [k for k in State.__annotations__ if k not in AgentState.__annotations__]
        assert added, "State must declare agent-specific fields"
        src = open(os.path.join(_SRC, "schemas", "state.py"), encoding="utf-8").read()
        for name in added:
            assert f"{name}: NotRequired[" in src, f"{name} must be wrapped in NotRequired[...]"


# TC-02 - Empty/missing input yields a fail-closed ERROR outcome, no raise.
class TestTC02Validation:
    def test_empty_input_no_raise(self):
        node = pre_process_node.InputValidateNode()
        out = node.execute({"user_input": ""})
        assert out["status"] == AgentStatus.ERROR.value
        assert out["error_log"]

    def test_inner_node_missing_query_no_raise(self):
        node = policy_retrieve_node.PolicyRetrieveNode()
        out = node.execute({"user_input": "{}"})
        assert out["status"] == AgentStatus.ERROR.value
        assert out["error_log"]


# TC-03 - No JWT / API keys / secrets in src/; no direct os.environ reads outside the
# documented entry-point exception.
class TestTC03NoCredentials:
    def test_no_credential_literals(self):
        pat = re.compile(r"(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)")
        offenders = []
        for fp in _src_files():
            with open(fp, encoding="utf-8") as f:
                if pat.search(f.read()):
                    offenders.append(fp)
        assert offenders == []

    def test_no_os_environ_secret_reads(self):
        # src/api/server.py is the sole permitted os.environ call site (S-3
        # entry-point exception): INVOKE_AUTH_TOKEN (caller-auth, pre-InvocationContext)
        # and RET_C2_313_ALLOW_STUB_LLM (boolean demo/test opt-in flag) are not
        # credentials - the LLM_API_KEY secret itself is read exclusively via
        # ctx.secrets.require() inside llm_adapter.py.
        exempt = os.path.join("api", "server.py")
        pat = re.compile(r"os\.environ\s*(\[|\.\w+\()")
        offenders = []
        for fp in _src_files():
            if fp.replace(os.sep, "/").endswith(exempt.replace(os.sep, "/")):
                continue
            with open(fp, encoding="utf-8") as f:
                if pat.search(f.read()):
                    offenders.append(fp)
        assert offenders == []


# TC-04 - InvocationContext is never stored in State after invoke.
class TestTC04ContextIsolation:
    def test_no_invocationcontext_in_state_after_invoke(self):
        from src.graph.graph import Graph

        agent = Graph(config={"max_retry": 1})
        agent.compile()
        ctx = InvocationContext(session_id="tc04", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="staff-tc04")
        result = agent.invoke("My product feed has a missing GTIN disapproval", ctx=ctx)
        for v in result.values():
            assert not isinstance(v, InvocationContext)

    def test_from_state_available(self):
        assert hasattr(InvocationContext, "from_state")


# TC-05 - Domain events: every node emits >=1 domain event; no node under src/nodes/ or
# src/graph/ ever re-emits a framework backbone lifecycle event.
class TestTC05Audit:
    def test_response_validate_emits_domain_event(self, monkeypatch):
        events = []
        monkeypatch.setattr(post_process_node, "emit_trace_event", lambda e, p, s: events.append(e))
        state = {
            "gmc_topic": "gtin",
            "draft_answer": "Set identifier_exists=false and resubmit.",
            "citations": '["jp-gtin-exemption-001", "https://support.google.com/merchants/answer/6219078"]',
            "retrieved_passages": '[{"doc_id": "jp-gtin-exemption-001", "tier": "2", "source": "s", "text": "t"}]',
            "live_refs": '[{"title": "GMC GTIN", "url": "https://support.google.com/merchants/answer/6219078"}]',
            "japan_overlay": "{}",
        }
        out = post_process_node.ResponseValidateNode().execute(state)
        assert out["status"] == AgentStatus.SUCCESS.value
        assert len(events) >= 1
        assert "response_validated" in events
        assert not ({"node_start", "node_complete", "node_error", "node_skip"} & set(events))

    def test_source_has_no_backbone_events(self):
        pat = re.compile(r'emit_trace_event\(\s*["\'](node_start|node_complete|node_error|node_skip)["\']')
        offenders = []
        for fp in _src_files():
            with open(fp, encoding="utf-8") as f:
                if pat.search(f.read()):
                    offenders.append(fp)
        assert offenders == []


# TC-06 / TC-07 - S-2/S-3 gates are @final on FunctionNode (overriding raises TypeError at class def).
class TestTC0607FinalGates:
    def test_input_gate_is_final(self):
        with pytest.raises(TypeError):

            class BadIn(FunctionNode):  # noqa: N801
                def _security_gate_input(self, state):
                    return state

    def test_output_gate_is_final(self):
        with pytest.raises(TypeError):

            class BadOut(FunctionNode):  # noqa: N801
                def _security_gate_output(self, result):
                    return result

    def test_extra_input_hook_is_overridable(self):
        assert pre_process_node.InputValidateNode._extra_security_gate_input is not FunctionNode._extra_security_gate_input

    def test_extra_output_hook_is_overridable(self):
        assert post_process_node.ResponseValidateNode._extra_security_gate_output is not FunctionNode._extra_security_gate_output

    def test_output_gate_blocks_credentials(self):
        node = post_process_node.ResponseValidateNode()
        with pytest.raises(Exception):
            node._security_gate_output({"result": "token AKIAIOSFODNN7EXAMPLE leaked"})


# TC-08 - required_trust_level enforced: insufficient trust -> ERROR state, no raise.
class TestTC08TrustGate:
    def test_declared_trust_levels_valid(self):
        for cls in (
            pre_process_node.InputValidateNode,
            intent_classify_node.IntentClassifyNode,
            policy_retrieve_node.PolicyRetrieveNode,
            japan_policy_filter_node.JapanPolicyFilterNode,
            resolution_synthesize_node.ResolutionSynthesizeNode,
            post_process_node.ResponseValidateNode,
            GmcOperationsGraphNode,
        ):
            assert cls.required_trust_level in (TrustLevel.ANONYMOUS, TrustLevel.VERIFIED_EXTERNAL, TrustLevel.INTERNAL)

    def test_insufficient_trust_returns_error(self):
        # GmcOperationsGraphNode is the outer main-slot wrapper - it requires
        # VERIFIED_EXTERNAL; an ANONYMOUS caller must be denied by BaseNode.__call__
        # before execute()/get_subgraph() ever run.
        node = GmcOperationsGraphNode()
        out = node({"caller_trust_level": TrustLevel.ANONYMOUS.value, "validated_input": '{"query": "x", "gmc_topic": "general"}'})
        assert str(out.get("status")).lower().endswith("error")

    def test_sufficient_trust_succeeds(self):
        node = pre_process_node.InputValidateNode()
        out = node({"caller_trust_level": TRUST, "user_input": "My product feed has a missing GTIN disapproval"})
        assert out["status"] == AgentStatus.SUCCESS.value
