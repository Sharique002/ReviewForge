"""
Local Ollama AI Provider
CSE476 CA2 — Automated Code Review Board (Q14)
"""

import os
import requests
from typing import Dict, Any, Optional
import asyncio

from ai.base_provider import BaseAIProvider


class OllamaProvider(BaseAIProvider):
    """Local-first AI provider connecting to an Ollama server."""

    def __init__(self, host: Optional[str] = None, model: Optional[str] = None):
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        self.model = model or os.environ.get("OLLAMA_MODEL", "llama3.2")
        self._last_health_check = 0.0
        self._is_online = False

    def is_available(self) -> bool:
        """Pings Ollama /api/tags with a 2-second timeout."""
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=2.0)
            self._is_online = (resp.status_code == 200)
        except Exception:
            self._is_online = False
        return self._is_online

    def get_provider_name(self) -> str:
        return "Local Ollama"

    def get_model_name(self) -> str:
        return self.model

    async def generate_explanation(self, prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
        """Calls Ollama generate API asynchronously using an executor."""
        if not self.is_available():
            return None

        def _call_api():
            url = f"{self.host}/api/generate"
            payload = {
                "model": self.model,
                "prompt": prompt,
                "system": system_prompt or "You are an expert AI code reviewer. Ground all explanations in concrete evidence.",
                "stream": False
            }
            try:
                res = requests.post(url, json=payload, timeout=60.0)
                if res.status_code == 200:
                    data = res.json()
                    return data.get("response", "").strip()
            except Exception:
                pass
            return None

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _call_api)

    def get_status_info(self) -> Dict[str, Any]:
        online = self.is_available()
        return {
            "provider": "Ollama",
            "host": self.host,
            "model": self.model,
            "status": "ONLINE" if online else "OFFLINE",
            "message": "Local Ollama daemon ready" if online else "Ollama server unreachable at configured endpoint."
        }
