"""
AI Health Check Service
CSE476 CA2 — Automated Code Review Board (Q14)
"""

from typing import Dict, Any
from ai.ollama_provider import OllamaProvider
from ai.gemini_provider import GeminiProvider
from ai.provider_factory import AIProviderFactory


class AIHealthCheck:
    """Provides unified health check report across all supported AI providers."""

    @staticmethod
    def check_all() -> Dict[str, Any]:
        ollama = OllamaProvider()
        gemini = GeminiProvider()
        active = AIProviderFactory.get_provider()

        ollama_info = ollama.get_status_info()
        gemini_info = gemini.get_status_info()
        has_llm = ollama.is_available() or gemini.is_available()

        return {
            "active_provider": active.get_provider_name(),
            "active_model": active.get_model_name(),
            "mode": "ONLINE_LLM" if has_llm else "OFFLINE_DETERMINISTIC",
            "ollama": ollama_info,
            "gemini": gemini_info,
            "deterministic_fallback_ready": True,
            "explanation": (
                f"Connected to {active.get_provider_name()}." if has_llm else
                "Running in zero-cost deterministic offline mode. All 6 agents perform full static analysis (Bandit, Ruff, detect-secrets, pytest) without cloud dependencies."
            )
        }
