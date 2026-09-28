# RET-C2-313 - Integration test: full graph compile + invoke (Cat 2 outer + inner).

from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.graph.graph import Graph


class TestAgentIntegration:
    def test_gtin_disapproval_full_pipeline(self):
        agent = Graph(config={"max_retry": 1})
        agent.compile()
        ctx = InvocationContext(session_id="it-1", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="ec-operator")
        result = agent.invoke("My product feed has a missing GTIN disapproval for 200 Japan SKUs", ctx=ctx)

        assert result["status"] == "success"
        assert len(result.get("node_history", [])) >= 5
        output = result.get("output")
        assert isinstance(output, dict)
        assert output["gmc_topic"] in ("gtin", "disapproval")
        assert output["citations"]

    def test_appi_disclosure_query(self):
        agent = Graph(config={"max_retry": 1})
        agent.compile()
        ctx = InvocationContext(session_id="it-2", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="ec-operator")
        result = agent.invoke("Do I need to disclose Google Shopping AI recommendation under APPI 2026?", ctx=ctx)

        assert result["status"] == "success"
        output = result.get("output")
        assert output["japan_overlay"]["appi_disclosure_required"] is True

    def test_empty_input_error(self):
        agent = Graph(config={"max_retry": 1})
        agent.compile()
        ctx = InvocationContext(session_id="it-3", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="ec-operator")
        result = agent.invoke("", ctx=ctx)
        assert result["status"] in ("error", "cancelled")
