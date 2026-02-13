"""Ollama model client - Layer 2. Local model inference.

Manages model lifecycle (check/pull), sends structured prompts,
receives and parses skill/memory markdown output.
"""

from __future__ import annotations

import json
import subprocess
import time
from typing import Any

import httpx

DEFAULT_MODEL = "qwen2.5-coder:7b"
OLLAMA_BASE_URL = "http://localhost:11434"
PULL_TIMEOUT = 600  # 10 minutes for model download
GENERATE_TIMEOUT = 300  # 5 minutes per generation (CI runners are slow)


class ModelError(Exception):
    """Error communicating with the model."""


class OllamaClient:
    """Client for Ollama REST API."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = OLLAMA_BASE_URL,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=GENERATE_TIMEOUT)

    def is_ollama_running(self) -> bool:
        """Check if Ollama server is reachable."""
        try:
            resp = self._client.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    def start_ollama(self) -> bool:
        """Attempt to start Ollama server."""
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Wait for server to start
            for _ in range(15):
                time.sleep(1)
                if self.is_ollama_running():
                    return True
            return False
        except FileNotFoundError:
            return False

    def is_model_available(self) -> bool:
        """Check if the configured model is downloaded."""
        try:
            resp = self._client.get(f"{self.base_url}/api/tags", timeout=10)
            if resp.status_code != 200:
                return False
            data = resp.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            # Check exact match or with :latest suffix
            return any(
                self.model == m
                or self.model == m.split(":")[0]
                or f"{self.model}:latest" == m
                for m in models
            )
        except Exception:
            return False

    def pull_model(self, progress_callback=None) -> bool:
        """Download the model. Returns True on success."""
        try:
            with httpx.Client(timeout=PULL_TIMEOUT) as client:
                with client.stream(
                    "POST",
                    f"{self.base_url}/api/pull",
                    json={"name": self.model},
                    timeout=PULL_TIMEOUT,
                ) as resp:
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            status = data.get("status", "")
                            if progress_callback:
                                total = data.get("total", 0)
                                completed = data.get("completed", 0)
                                progress_callback(status, completed, total)
                        except json.JSONDecodeError:
                            pass
            return self.is_model_available()
        except Exception as e:
            raise ModelError(f"Failed to pull model {self.model}: {e}")

    def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """Generate text from prompt. Returns raw text response."""
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system:
            payload["system"] = system

        try:
            resp = self._client.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=GENERATE_TIMEOUT,
            )
            if resp.status_code != 200:
                raise ModelError(
                    f"Ollama returned {resp.status_code}: {resp.text[:200]}"
                )
            data = resp.json()
            return data.get("response", "")
        except httpx.TimeoutException:
            raise ModelError(f"Model generation timed out after {GENERATE_TIMEOUT}s")
        except httpx.ConnectError:
            raise ModelError(
                "Cannot connect to Ollama. Is it running? Try: ollama serve"
            )

    def generate_json(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.2,
    ) -> dict:
        """Generate and parse JSON response."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": temperature,
                "num_predict": 4096,
            },
        }
        if system:
            payload["system"] = system

        try:
            resp = self._client.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=GENERATE_TIMEOUT,
            )
            if resp.status_code != 200:
                raise ModelError(
                    f"Ollama returned {resp.status_code}: {resp.text[:200]}"
                )
            data = resp.json()
            text = data.get("response", "")
            return json.loads(text)
        except json.JSONDecodeError:
            raise ModelError(f"Model returned invalid JSON: {text[:200]}")
        except httpx.TimeoutException:
            raise ModelError(f"Model generation timed out after {GENERATE_TIMEOUT}s")

    def ensure_ready(self, progress_callback=None) -> None:
        """Ensure Ollama is running and model is available."""
        if not self.is_ollama_running():
            if progress_callback:
                progress_callback("Starting Ollama server...", 0, 0)
            if not self.start_ollama():
                raise ModelError(
                    "Ollama is not installed or cannot start.\n"
                    "Install: brew install ollama  (macOS)\n"
                    "         curl -fsSL https://ollama.com/install.sh | sh  (Linux)\n"
                    "Then run: ollama serve"
                )

        if not self.is_model_available():
            if progress_callback:
                progress_callback(
                    f"Downloading {self.model} (one-time, ~4.5GB)...", 0, 0
                )
            self.pull_model(progress_callback)
