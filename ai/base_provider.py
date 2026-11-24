"""
Base AI Provider Interface
CSE476 CA2 — Automated Code Review Board (Q14)
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseAIProvider(ABC):
    """Abstract interface for LLM narrative providers."""

    @abstractmethod
    def is_available(self) -> bool:
        """Checks if the provider endpoint is healthy and accessible."""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Returns the human-readable provider name."""
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Returns the active model name."""
        pass

    @abstractmethod
    async def generate_explanation(self, prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
        """Generates a natural language explanation or patch reasoning."""
        pass

    @abstractmethod
    def get_status_info(self) -> Dict[str, Any]:
        """Returns structured status information for dashboard display."""
        pass
