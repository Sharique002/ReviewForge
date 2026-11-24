"""
High-Level Review Workflow Pipeline
CSE476 CA2 — Automated Code Review Board (Q14)
"""

import os
import uuid
import asyncio
from typing import Dict, Any, Optional

from memory.shared_change_state import SharedChangeState
from memory.persistence import JsonlAuditLogger, DatabaseManager
from services.extraction_service import ExtractionService
from services.archive_validator import ArchiveValidationError
from services.sandbox_service import SandboxService
from orchestration.fanout_fanin import FanOutFanInOrchestrator


class ReviewWorkflow:
    """Manages the full lifecycle of an automated code review."""

    def __init__(self, workspace_base_dir: Optional[str] = None,
                 sandbox_service: Optional[SandboxService] = None,
                 db_path: Optional[str] = None,
                 log_dir: Optional[str] = None):
        self.logger = JsonlAuditLogger(log_dir=log_dir or "logs")
        self.db = DatabaseManager(db_path=db_path or "data/reviews.db")
        self.sandbox_service = sandbox_service or SandboxService()
        self.extraction_service = ExtractionService(base_workspace_dir=workspace_base_dir)
        self.orchestrator = FanOutFanInOrchestrator(
            sandbox_service=self.sandbox_service,
            logger=self.logger,
            db=self.db
        )

    async def execute_review_pipeline(self, zip_path: str,
                                      review_id: Optional[str] = None,
                                      project_name: Optional[str] = None) -> SharedChangeState:
        """
        Executes end-to-end review:
        1. Validate ZIP
        2. Extract snapshots into isolated temporary workspace
        3. Initialize SharedChangeState
        4. Execute multi-agent orchestration
        5. Return populated SharedChangeState
        """
        rev_id = review_id or f"REV-{uuid.uuid4().hex[:8].upper()}"
        self.logger.log_event(rev_id, "REVIEW_CREATED", metadata={"zip_path": zip_path})

        # Step 1 & 2: Validate and extract archive
        extracted_info = self.extraction_service.extract_archive(zip_path, rev_id)
        self.logger.log_event(rev_id, "ARCHIVE_VALIDATED",
                              metadata={"mode": extracted_info["mode"], "files": extracted_info["file_count"]})

        manifest = extracted_info.get("manifest", {})
        proj_name = project_name or manifest.get("project_name", "Submitted Project")

        # Step 3: Initialize Shared Change State
        state = SharedChangeState(review_id=rev_id, project_name=proj_name)
        state.base_path = extracted_info["base_dir"]
        state.proposed_path = extracted_info["proposed_dir"]
        state.review_mode = extracted_info["mode"]
        state.manifest_data = manifest

        # Save initial state in DB
        self.db.save_review_state(state)

        # Step 4: Execute multi-agent orchestration
        completed_state = await self.orchestrator.execute_review(state)

        return completed_state
