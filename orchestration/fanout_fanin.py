"""
Fan-Out / Fan-In Orchestrator
CSE476 CA2 — Automated Code Review Board (Q14)

Coordinates concurrent multi-agent execution with fault isolation,
state synchronization, and strict failure classification.
"""

import asyncio
import time
from typing import Dict, Any, List, Optional

from memory.shared_change_state import SharedChangeState
from memory.persistence import JsonlAuditLogger, DatabaseManager
from services.sandbox_service import SandboxService
from agents.diff_agent import DiffAgent
from agents.style_agent import StyleAgent
from agents.security_agent import SecurityAgent
from agents.test_coverage_agent import TestCoverageAgent
from agents.reviewer_manager import ReviewerManager
from agents.fix_suggestion_agent import FixSuggestionAgent


class FanOutFanInOrchestrator:
    """Orchestrates concurrent execution of specialist agents followed by fan-in consolidation."""

    def __init__(
        self,
        sandbox_service: Optional[SandboxService] = None,
        logger: Optional[JsonlAuditLogger] = None,
        db: Optional[DatabaseManager] = None
    ):
        self.logger = logger or JsonlAuditLogger()
        self.db = db or DatabaseManager()
        self.sandbox_service = sandbox_service or SandboxService()

        # Instantiate the 6 agents with proper dependency injection
        self.diff_agent = DiffAgent(logger=self.logger)
        self.style_agent = StyleAgent(logger=self.logger)
        self.security_agent = SecurityAgent(logger=self.logger)
        self.test_coverage_agent = TestCoverageAgent(
            sandbox_service=self.sandbox_service,
            logger=self.logger
        )
        self.reviewer_manager = ReviewerManager(logger=self.logger)
        self.fix_suggestion_agent = FixSuggestionAgent(logger=self.logger)

    async def execute_review(self, shared_state: SharedChangeState) -> SharedChangeState:
        """
        Executes complete multi-agent review workflow:
        1. Pre-step: Diff Agent identifies changed files and populates change metadata.
        2. Fan-out: 3 Specialist Agents (Style, Security, Test-Coverage) execute concurrently.
        3. Fan-in: Reviewer Manager collects, deduplicates, ranks findings, and decides merge recommendation.
        4. Extension: Fix-Suggestion Agent targets single highest-severity finding and generates validated patch.
        5. Failure Handling: Accurately sets review status (COMPLETED, PARTIAL, FAILED) based on agent outcomes.
        6. Persistence: State is committed to SQLite and JSONL audit log.
        """
        shared_state.status = "RUNNING"
        shared_state.progress = 5
        self.logger.log_event(shared_state.review_id, "REVIEW_STARTED",
                              metadata={"project": shared_state.project_name, "mode": shared_state.review_mode})

        # --- STEP 1: INITIAL DIFF DISCOVERY ---
        # Run diff agent first so that style, security, and coverage agents have exact changed_files
        try:
            async for _ in self.diff_agent.invoke(shared_state=shared_state):
                pass
        except Exception as e:
            shared_state.update_agent_status("Diff Agent", "FAILED", error=str(e))
            self.logger.log_event(shared_state.review_id, "AGENT_FAILED", agent="Diff Agent",
                                  status="FAILED", metadata={"error": str(e)})

        shared_state.progress = 25

        # --- STEP 2: CONCURRENT SPECIALIST FAN-OUT ---
        # Three specialist agents execute concurrently with exception isolation
        async def run_specialist(agent, name):
            try:
                async for _ in agent.invoke(shared_state=shared_state):
                    pass
            except Exception as e:
                shared_state.update_agent_status(name, "FAILED", error=str(e))
                self.logger.log_event(shared_state.review_id, "AGENT_FAILED", agent=name,
                                      status="FAILED", metadata={"error": str(e)})

        self.logger.log_event(shared_state.review_id, "FAN_OUT_STARTED",
                              metadata={"members": ["Style Agent", "Security Agent", "Test-Coverage Agent"]})

        specialist_tasks = [
            run_specialist(self.style_agent, "Style Agent"),
            run_specialist(self.security_agent, "Security Agent"),
            run_specialist(self.test_coverage_agent, "Test-Coverage Agent"),
        ]

        # Concurrently gather all 3 specialist agent executions
        await asyncio.gather(*specialist_tasks, return_exceptions=True)
        shared_state.progress = 65

        # --- STEP 3: REVIEWER MANAGER FAN-IN ---
        # Reviewer Manager consolidates findings, deduplicates, and decides
        try:
            async for _ in self.reviewer_manager.invoke(shared_state=shared_state):
                pass
        except Exception as e:
            shared_state.update_agent_status("Reviewer Manager", "FAILED", error=str(e))
            self.logger.log_event(shared_state.review_id, "AGENT_FAILED", agent="Reviewer Manager",
                                  status="FAILED", metadata={"error": str(e)})

        shared_state.progress = 85

        # --- STEP 4: FIX-SUGGESTION AGENT EXTENSION ---
        # Propose patch for the single highest-severity finding
        try:
            async for _ in self.fix_suggestion_agent.invoke(shared_state=shared_state):
                pass
        except Exception as e:
            shared_state.update_agent_status("Fix-Suggestion Agent", "FAILED", error=str(e))
            self.logger.log_event(shared_state.review_id, "AGENT_FAILED", agent="Fix-Suggestion Agent",
                                  status="FAILED", metadata={"error": str(e)})

        shared_state.progress = 100

        # --- STEP 5: ACCURATE FAILURE CLASSIFICATION & STATE DECISION ---
        # Mandatory review agents: Diff Agent, Style Agent, Security Agent, Test-Coverage Agent, Reviewer Manager
        diff_status = shared_state.agent_statuses.get("Diff Agent")
        mgr_status = shared_state.agent_statuses.get("Reviewer Manager")

        diff_failed = (diff_status is None or diff_status.status == "FAILED")
        mgr_failed = (mgr_status is None or mgr_status.status == "FAILED")

        specialist_names = ["Style Agent", "Security Agent", "Test-Coverage Agent"]
        failed_specialists = [
            s for s in specialist_names
            if shared_state.agent_statuses.get(s) is None or shared_state.agent_statuses[s].status == "FAILED"
        ]

        # Determine review status: FAILED, PARTIAL, or COMPLETED
        if diff_failed or mgr_failed or len(failed_specialists) == len(specialist_names):
            shared_state.status = "FAILED"
            shared_state.recommendation = "REQUEST_CHANGES"
            reasons = []
            if diff_failed:
                reasons.append("Diff Agent failed")
            if mgr_failed:
                reasons.append("Reviewer Manager failed")
            if len(failed_specialists) == len(specialist_names):
                reasons.append("All specialist review agents failed")
            shared_state.recommendation_rationale = (
                f"Review FAILED: Pipeline halted due to critical agent failure ({', '.join(reasons)}). "
                f"Automated approval is strictly prohibited."
            )
        elif len(failed_specialists) > 0:
            shared_state.status = "PARTIAL"
            # Even if Reviewer Manager had tentatively evaluated APPROVE, enforce REQUEST_CHANGES
            if shared_state.recommendation == "APPROVE" or not shared_state.recommendation:
                shared_state.recommendation = "REQUEST_CHANGES"
                shared_state.recommendation_rationale = (
                    f"Review PARTIAL: Analysis incomplete due to failure in mandatory agent(s): "
                    f"{', '.join(failed_specialists)}. "
                    f"Approval cannot be granted on partial or incomplete review evidence."
                )
        else:
            shared_state.status = "COMPLETED"

        self.logger.log_event(
            shared_state.review_id,
            "REVIEW_FINISHED",
            metadata={
                "status": shared_state.status,
                "recommendation": shared_state.recommendation,
                "total_findings": len(shared_state.consolidated_findings)
            }
        )

        # Commit to SQLite
        try:
            self.db.save_review_state(shared_state)
        except Exception as e:
            shared_state.error_records.append({
                "agent": "Persistence",
                "error": f"DB save failed: {e}",
                "timestamp": time.time()
            })

        return shared_state
