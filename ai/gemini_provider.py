"""
Optional Google Gemini AI Provider
CSE476 CA2 — Automated Code Review Board (Q14)
"""

import os
from typing import Dict, Any, Optional
import requests
import asyncio

from ai.base_provider import BaseAIProvider


class GeminiProvider(BaseAIProvider):
    """Optional cloud provider utilizing Google Gemini within free-tier bounds."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-1.5-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "").strip()
        self.model = model

    def is_available(self) -> bool:
        return bool(self.api_key)

    def get_provider_name(self) -> str:
        return "Google Gemini"

    def get_model_name(self) -> str:
        return self.model

    async def generate_explanation(self, prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
        if not self.is_available():
            return None

        def _call_gemini():
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": f"{system_prompt}\n\n{prompt}" if system_prompt else prompt}
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 1000,
                }
            }
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=30.0)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "").strip()
            except Exception:
                pass
            return None

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _call_gemini)

    def get_status_info(self) -> Dict[str, Any]:
        has_key = bool(self.api_key)
        return {
            "provider": "Gemini",
            "model": self.model,
            "status": "CONFIGURED" if has_key else "UNCONFIGURED",
            "message": "Gemini API key configured" if has_key else "GEMINI_API_KEY environment variable not set."
        }
