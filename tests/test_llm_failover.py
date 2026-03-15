"""TEST-6: LLM provider failover tests."""

import pytest
from unittest.mock import patch, MagicMock
from backend.llm_translator import LLMTranslator


class TestLLMProviderFailover:
    """TEST-6: LLM provider selection and error handling."""

    def test_lm_studio_connection_error_is_handled(self):
        """If LM Studio is not running, english_to_json should raise (not hang)."""
        translator = LLMTranslator(mode="lm_studio", lm_studio_url="http://localhost:9999")
        # Should raise a connection error quickly (no retries make it slow)
        with pytest.raises(Exception):
            translator.english_to_json("Build a research agent", retries=0)

    def test_extract_json_direct_parse(self):
        """_extract_json should return raw JSON string when input is already valid JSON."""
        translator = LLMTranslator(mode="lm_studio")
        raw = '{"graph_name": "test", "nodes": []}'
        result = translator._extract_json(raw)
        assert isinstance(result, str)
        import json
        parsed = json.loads(result)
        assert parsed["graph_name"] == "test"

    def test_extract_json_code_fence(self):
        """_extract_json should extract JSON from a markdown code fence."""
        import json
        translator = LLMTranslator(mode="lm_studio")
        raw = '```json\n{"graph_name": "fenced", "nodes": []}\n```'
        result = translator._extract_json(raw)
        parsed = json.loads(result)
        assert parsed["graph_name"] == "fenced"

    def test_extract_json_brace_scan(self):
        """_extract_json should find the first {...} block in a mixed string."""
        import json
        translator = LLMTranslator(mode="lm_studio")
        raw = 'Here is the output: {"graph_name": "scanned"} and some text after.'
        result = translator._extract_json(raw)
        parsed = json.loads(result)
        assert parsed["graph_name"] == "scanned"

    def test_extract_json_invalid_raises(self):
        """_extract_json should raise ValueError for completely unparseable input."""
        translator = LLMTranslator(mode="lm_studio")
        with pytest.raises(ValueError, match="Could not extract valid JSON"):
            translator._extract_json("this is not json at all")

    def test_lm_studio_url_base_is_configurable(self):
        """LM Studio base URL should be overridable via constructor."""
        custom_base = "http://custom-host:12345"
        translator = LLMTranslator(mode="lm_studio", lm_studio_url=custom_base)
        assert translator.lm_studio_base_url == custom_base
        assert translator.lm_studio_url.startswith(custom_base)

    def test_get_prompt_returns_string_with_instructions(self):
        """get_prompt should embed instructions in the prompt string."""
        translator = LLMTranslator(mode="lm_studio")
        prompt = translator.get_prompt("Build a research agent")
        assert "research agent" in prompt
        assert "JSON" in prompt

    def test_parse_llm_response_valid_json(self):
        """parse_llm_response should parse a valid JSON string to a dict."""
        translator = LLMTranslator(mode="lm_studio")
        raw = '{"graph_name": "parsed", "nodes": [{"id": "a1", "type": "agent", "next": "END"}]}'
        result = translator.parse_llm_response(raw)
        assert isinstance(result, dict)
        assert result["graph_name"] == "parsed"

    @patch("backend.llm_translator.requests.post")
    def test_lm_studio_uses_chat_endpoint(self, mock_post):
        """LM Studio translator should call /v1/chat/completions."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"graph_name": "mocked", "nodes": [{"id": "n1", "type": "agent", "next": "END"}]}'}}]
        }
        mock_post.return_value = mock_resp

        translator = LLMTranslator(mode="lm_studio", lm_studio_url="http://fake:1234")
        result = translator.english_to_json("test")
        assert isinstance(result, dict)
        # Verify the chat endpoint was hit
        called_url = mock_post.call_args[0][0]
        assert "chat/completions" in called_url

    @patch("backend.llm_translator.requests.post")
    def test_lm_studio_retries_on_json_error(self, mock_post):
        """On a bad JSON response, english_to_json should retry up to `retries` times."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "not json"}}]}
        mock_post.return_value = mock_resp

        translator = LLMTranslator(mode="lm_studio", lm_studio_url="http://fake:1234")
        with pytest.raises(Exception):
            translator.english_to_json("test", retries=1)
        # Called twice: 1 original + 1 retry
        assert mock_post.call_count >= 2
