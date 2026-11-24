"""
AI Provider Factory & Offline Fallback
CSE476 CA2 — Automated Code Review Board (Q14)
"""

from typing import Optional, Dict, Any

from ai.base_provider import BaseAIProvider
from ai.ollama_provider import OllamaProvider
from ai.gemini_provider import GeminiProvider


class OfflineFallbackProvider(BaseAIProvider):
    """Deterministic offline fallback provider when no LLM daemon or API key is accessible."""

    def is_available(self) -> bool:
        return True

    def get_provider_name(self) -> str:
        return "Deterministic Offline Engine"

    def get_model_name(self) -> str:
        return "Deterministic Rules"

    async def generate_explanation(self, prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
        # Return structured message that explanation was generated deterministically from tools
        return (
            "[Deterministic Static Analysis] LLM provider offline. "
            "Report and decisions are grounded strictly in scanner and tool evidence."
        )

    def get_status_info(self) -> Dict[str, Any]:
        return {
            "provider": "Offline Fallback",
            "model": "Rule-based Engine",
            "status": "ACTIVE",
            "message": "Deterministic mode active (Zero external AI dependencies)."
        }


class AIProviderFactory:
    """Selects the best available AI provider according to priority: Ollama -> Gemini -> Offline Fallback."""

    @staticmethod
    def get_provider() -> BaseAIProvider:
        # Priority 1: Local Ollama
        ollama = OllamaProvider()
        if ollama.is_available():
            return ollama

        # Priority 2: Optional Gemini if key is provided
        gemini = GeminiProvider()
        if gemini.is_available():
            return gemini

        # Priority 3: Offline Fallback
        return OfflineFallbackProvider()
