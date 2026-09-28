# RET-C2-313 - Unit tests: per-node success + error/edge paths.

import json

from framework.schemas.agent_status import AgentStatus

from src.nodes.intent_classify_node import IntentClassifyNode
from src.nodes.japan_policy_filter_node import JapanPolicyFilterNode
from src.nodes.policy_retrieve_node import PolicyRetrieveNode
from src.nodes.post_process_node import ResponseValidateNode
from src.nodes.pre_process_node import InputValidateNode
from src.nodes.resolution_synthesize_node import ResolutionSynthesizeNode
from src.schemas.state import from_json, to_json


class TestInputValidateNode:
    def test_success(self):
        state = {"user_input": "My product feed has a missing GTIN disapproval for 200 SKUs"}
        r = InputValidateNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        parsed = json.loads(r["validated_input"])
        assert parsed["gmc_topic"] in ("gtin", "disapproval")

    def test_empty_input(self):
        assert InputValidateNode().execute({"user_input": ""})["status"] == AgentStatus.ERROR

    def test_extra_gate_input_length_cap(self):
        out = InputValidateNode()._extra_security_gate_input({"validated_input": "x" * 5000})
        assert out["status"] == AgentStatus.ERROR

    def test_extra_gate_input_clean_passthrough(self):
        state = {"validated_input": "short"}
        assert InputValidateNode()._extra_security_gate_input(state) is state


class TestIntentClassifyNode:
    def test_success(self):
        state = {"user_input": json.dumps({"query": "GTIN missing for Japan SKUs", "gmc_topic": "gtin"})}
        r = IntentClassifyNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        assert r["intent"] == "gtin"

    def test_missing_query(self):
        assert IntentClassifyNode().execute({"user_input": "{}"})["status"] == AgentStatus.ERROR


class TestPolicyRetrieveNode:
    def test_success(self):
        state = {"user_input": json.dumps({"query": "missing GTIN Japan", "gmc_topic": "gtin"}), "gmc_topic": "gtin"}
        r = PolicyRetrieveNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        passages = from_json(r["retrieved_passages"], [])
        assert len(passages) >= 1
        live_refs = from_json(r["live_refs"], [])
        assert len(live_refs) == 1 and live_refs[0]["url"]

    def test_missing_query(self):
        assert PolicyRetrieveNode().execute({"user_input": "{}"})["status"] == AgentStatus.ERROR


class TestJapanPolicyFilterNode:
    def test_success(self):
        state = {"user_input": json.dumps({"query": "appi disclosure", "gmc_topic": "appi"}), "gmc_topic": "appi"}
        r = JapanPolicyFilterNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        overlay = from_json(r["japan_overlay"], {})
        assert overlay["appi_disclosure_required"] is True

    def test_missing_query(self):
        assert JapanPolicyFilterNode().execute({"user_input": "{}"})["status"] == AgentStatus.ERROR


class TestResolutionSynthesizeNode:
    def test_deterministic_fallback(self):
        state = {
            "user_input": json.dumps({"query": "missing GTIN Japan", "gmc_topic": "gtin"}),
            "retrieved_passages": to_json([{"doc_id": "jp-gtin-exemption-001", "tier": "2", "source": "s", "text": "t"}]),
            "live_refs": to_json([{"title": "GMC GTIN", "url": "https://support.google.com/merchants/answer/6219078"}]),
            "japan_overlay": to_json({"gtin_exemption_applicable": True}),
        }
        r = ResolutionSynthesizeNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        citations = from_json(r["citations"], [])
        assert "jp-gtin-exemption-001" in citations
        assert "https://support.google.com/merchants/answer/6219078" in citations

    def test_missing_query(self):
        assert ResolutionSynthesizeNode().execute({"user_input": "{}"})["status"] == AgentStatus.ERROR

    def _base_state(self) -> dict:
        return {
            "user_input": json.dumps({"query": "missing GTIN Japan", "gmc_topic": "gtin"}),
            "retrieved_passages": to_json([{"doc_id": "jp-gtin-exemption-001", "tier": "2", "source": "s", "text": "t"}]),
            "live_refs": to_json([{"title": "GMC GTIN", "url": "https://support.google.com/merchants/answer/6219078"}]),
            "japan_overlay": to_json({"gtin_exemption_applicable": True}),
        }

    def test_llm_configured_canonical_dict_response_used(self):
        """A configured LLM's canonical `{"content": ...}` dict response is used verbatim (3m)."""

        class DictLLM:
            def complete(self, messages):
                assert isinstance(messages, list) and messages[0]["role"] == "user"
                return {"content": "LLM-authored resolution."}

        r = ResolutionSynthesizeNode(llm=DictLLM()).execute(self._base_state())
        assert r["status"] == AgentStatus.SUCCESS
        assert r["draft_answer"] == "LLM-authored resolution."

    def test_llm_configured_empty_response_is_error_not_silent_fallback(self):
        """Configured-but-empty LLM response must surface as ERROR, not a silent deterministic SUCCESS (3m)."""

        class EmptyLLM:
            def complete(self, messages):
                return {"content": ""}

        r = ResolutionSynthesizeNode(llm=EmptyLLM()).execute(self._base_state())
        assert r["status"] == AgentStatus.ERROR
        assert r["error_log"]

    def test_llm_configured_raising_is_error_not_silent_fallback(self):
        """Configured-but-raising LLM must surface as ERROR, not be swallowed into a fallback SUCCESS (3m)."""

        class RaisingLLM:
            def complete(self, messages):
                raise ConnectionError("provider unreachable")

        r = ResolutionSynthesizeNode(llm=RaisingLLM()).execute(self._base_state())
        assert r["status"] == AgentStatus.ERROR
        assert r["error_log"]


class TestResponseValidateNode:
    def test_clean_success(self):
        state = {
            "gmc_topic": "gtin",
            "draft_answer": "Set identifier_exists=false and resubmit.",
            "citations": to_json(["jp-gtin-exemption-001", "https://support.google.com/merchants/answer/6219078"]),
            "retrieved_passages": to_json([{"doc_id": "jp-gtin-exemption-001", "tier": "2", "source": "s", "text": "t"}]),
            "live_refs": to_json([{"title": "GMC GTIN", "url": "https://support.google.com/merchants/answer/6219078"}]),
            "japan_overlay": to_json({}),
        }
        r = ResponseValidateNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        assert r["formatted_output"]["citations"]

    def test_fabricated_citation_rejected(self):
        state = {
            "gmc_topic": "gtin",
            "draft_answer": "Fabricated answer.",
            "citations": to_json(["not-a-real-doc-id"]),
            "retrieved_passages": to_json([{"doc_id": "jp-gtin-exemption-001", "tier": "2", "source": "s", "text": "t"}]),
            "live_refs": to_json([{"title": "GMC GTIN", "url": "https://support.google.com/merchants/answer/6219078"}]),
            "japan_overlay": to_json({}),
        }
        assert ResponseValidateNode().execute(state)["status"] == AgentStatus.ERROR

    def test_upstream_error_short_circuits(self):
        assert ResponseValidateNode().execute({"status": AgentStatus.ERROR})["status"] == AgentStatus.ERROR

    def test_extra_gate_blocks_suppression(self):
        """If citations were emptied out, or the live policy URL was dropped, the S-3 hook fails.

        Self-consistency check on formatted_output's own keys only (citations vs.
        policy_reference.url) - no cross-reference to other state fields.
        """
        state = {
            "formatted_output": {
                "citations": ["jp-gtin-exemption-001"],
                "policy_reference": {"title": "GMC GTIN", "url": "https://support.google.com/merchants/answer/6219078"},
            },
        }
        out = ResponseValidateNode()._extra_security_gate_output(state)
        assert out["status"] == AgentStatus.ERROR

    def test_extra_gate_passthrough_when_consistent(self):
        state = {
            "formatted_output": {
                "citations": ["jp-gtin-exemption-001", "https://support.google.com/merchants/answer/6219078"],
                "policy_reference": {"title": "GMC GTIN", "url": "https://support.google.com/merchants/answer/6219078"},
            },
        }
        assert ResponseValidateNode()._extra_security_gate_output(state) is state
