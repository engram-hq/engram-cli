"""Tests for the Ollama model client."""

from unittest.mock import MagicMock, patch

import pytest

from engram_cli.model import OllamaClient, ModelError, DEFAULT_MODEL


class TestOllamaClient:
    """Test OllamaClient methods."""

    def test_default_config(self):
        client = OllamaClient()
        assert client.model == DEFAULT_MODEL
        assert "11434" in client.base_url

    def test_custom_model(self):
        client = OllamaClient(model="codellama:13b")
        assert client.model == "codellama:13b"

    @patch("httpx.Client.get")
    def test_is_ollama_running_true(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp
        client = OllamaClient()
        assert client.is_ollama_running() is True

    @patch("httpx.Client.get")
    def test_is_ollama_running_false(self, mock_get):
        from httpx import ConnectError

        mock_get.side_effect = ConnectError("connection refused")
        client = OllamaClient()
        assert client.is_ollama_running() is False

    @patch("httpx.Client.get")
    def test_is_model_available_true(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [
                {"name": "qwen2.5-coder:7b"},
                {"name": "llama3:latest"},
            ]
        }
        mock_get.return_value = mock_resp
        client = OllamaClient(model="qwen2.5-coder:7b")
        assert client.is_model_available() is True

    @patch("httpx.Client.get")
    def test_is_model_available_false(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "llama3:latest"}]}
        mock_get.return_value = mock_resp
        client = OllamaClient(model="qwen2.5-coder:7b")
        assert client.is_model_available() is False

    @patch("httpx.Client.post")
    def test_generate_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response": "# Architecture\n\nThis is a web app.",
        }
        mock_post.return_value = mock_resp
        client = OllamaClient()
        result = client.generate("Analyze this repo")
        assert "Architecture" in result
        assert "web app" in result

    @patch("httpx.Client.post")
    def test_generate_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal server error"
        mock_post.return_value = mock_resp
        client = OllamaClient()
        with pytest.raises(ModelError, match="500"):
            client.generate("test prompt")

    @patch("httpx.Client.post")
    def test_generate_timeout(self, mock_post):
        from httpx import TimeoutException

        mock_post.side_effect = TimeoutException("timed out")
        client = OllamaClient()
        with pytest.raises(ModelError, match="timed out"):
            client.generate("test prompt")

    @patch("httpx.Client.post")
    def test_generate_json_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response": '{"skills": 3, "memories": 2}',
        }
        mock_post.return_value = mock_resp
        client = OllamaClient()
        result = client.generate_json("test")
        assert result["skills"] == 3
        assert result["memories"] == 2
