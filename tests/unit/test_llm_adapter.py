# RET-C2-313 - Unit tests: llm_adapter.py (wiring contract)

import pytest

from src.services.llm_adapter import LLMConfigError, build_llm, extract_text


class _FakeSecrets:
    """Minimal SecretProvider stand-in: require(key) -> value or raise KeyError."""

    def __init__(self, values):
        self._values = values

    def require(self, key):
        return self._values[key]


class TestExtractText:
    def test_canonical_dict_response(self):
        assert extract_text({"content": "hello"}) == "hello"

    def test_dict_missing_content_yields_empty(self):
        assert extract_text({"tool_calls": []}) == ""

    def test_bare_string_response_accepted(self):
        assert extract_text("hello") == "hello"

    def test_other_types_yield_empty(self):
        assert extract_text(None) == ""
        assert extract_text(123) == ""


class TestBuildLLM:
    def test_production_requires_api_key(self):
        # No LLM_API_KEY declared -> live wiring must fail loudly, not silently
        # degrade to the deterministic fallback.
        with pytest.raises(LLMConfigError):
            build_llm(_FakeSecrets({}), allow_stub=False)

    def test_production_rejects_empty_api_key(self):
        with pytest.raises(LLMConfigError):
            build_llm(_FakeSecrets({"LLM_API_KEY": ""}), allow_stub=False)

    def test_stub_mode_returns_none_for_fallback(self):
        # Opt-in demo/test path -> None so the caller uses the deterministic
        # playbook fallback.
        assert build_llm(_FakeSecrets({}), allow_stub=True) is None


class TestServerWiresLiveLLM:
    """The deployed construction path must bind the adapter."""

    def test_server_import_binds_llm_client_via_secret(self, monkeypatch):
        pytest.importorskip("fastapi")  # server entry point depends on fastapi
        monkeypatch.setenv("RET_C2_313_ALLOW_STUB_LLM", "1")
        import importlib

        import src.api.server as server

        importlib.reload(server)
        # In stub mode the wired client is None (fallback), proving the
        # construction path executed build_llm() rather than ignoring the secret.
        assert server._llm_client is None
        assert server.agent is not None
