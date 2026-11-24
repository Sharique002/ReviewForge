"""
API Request & Response Schemas
CSE476 CA2 — Automated Code Review Board (Q14)
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "HEALTHY"
    version: str = "1.0.0"
    python_version: str
    semantic_kernel_version: str
    active_provider: str


class ReviewSummaryResponse(BaseModel):
    review_id: str
    project_name: str
    review_mode: str
    status: str
    recommendation: Optional[str]
    diff_summary: Optional[str]
    created_at: float
    updated_at: float


class AgentMetadata(BaseModel):
    name: str
    role: str
    tools: List[str]
    description: str
