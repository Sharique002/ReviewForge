"""
Execution Context Model
CSE476 CA2 — Automated Code Review Board (Q14)
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import time


class ExecutionContext(BaseModel):
    """Holds runtime execution context and configurations for a review session."""
    review_id: str
    workspace_path: str
    base_path: Optional[str] = None
    proposed_path: Optional[str] = None
    review_mode: str = "CHANGE_REVIEW"
    created_at: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)
