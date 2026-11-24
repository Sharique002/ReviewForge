"""
Shared Change State Model & Concurrency Management
CSE476 CA2 — Automated Code Review Board (Q14)
"""

import threading
import time
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class FindingStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class Finding(BaseModel):
    finding_id: str
    agent: str
    category: str
    severity: Severity
    title: str
    description: str
    file: Optional[str] = None
    line: Optional[int] = None
    end_line: Optional[int] = None
    evidence: str
    recommendation: str
    tool: str
    confidence: str = "HIGH"
    status: FindingStatus = FindingStatus.OPEN
    timestamp: float = Field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "agent": self.agent,
            "category": self.category,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "file": self.file,
            "line": self.line,
            "end_line": self.end_line,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
            "tool": self.tool,
            "confidence": self.confidence,
            "status": self.status.value,
            "timestamp": self.timestamp,
        }


class ToolExecutionRecord(BaseModel):
    tool_name: str
    agent: str
    status: str  # SUCCESS, FAILED, TIMEOUT, NOT_RUN
    execution_time_seconds: float
    output_summary: str
    timestamp: float = Field(default_factory=time.time)


class AgentExecutionRecord(BaseModel):
    agent_name: str
    status: str  # PENDING, RUNNING, COMPLETED, FAILED, TIMEOUT
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    tools_called: List[str] = Field(default_factory=list)
    findings_count: int = 0
    error_message: Optional[str] = None


class PatchProposal(BaseModel):
    agent: str = "Fix-Suggestion Agent"
    target_finding: str
    file: str
    severity: str
    patch_status: str  # PROPOSED, VALIDATED, NOT_RUN, REJECTED
    explanation: str
    patch: str
    validation: str  # PASSED, FAILED, NOT_RUN
    timestamp: float = Field(default_factory=time.time)


class ChangeStatistics(BaseModel):
    files_added: List[str] = Field(default_factory=list)
    files_modified: List[str] = Field(default_factory=list)
    files_deleted: List[str] = Field(default_factory=list)
    files_renamed: List[Dict[str, str]] = Field(default_factory=list)
    total_lines_added: int = 0
    total_lines_deleted: int = 0


class SharedChangeState:
    """
    Thread-safe Shared Change State shared among all specialist agents,
    the Reviewer Manager, and the Fix-Suggestion Agent.
    """

    def __init__(self, review_id: str, project_name: str = "Submitted Project"):
        self._lock = threading.Lock()
        self.review_id = review_id
        self.project_name = project_name
        self.created_at = time.time()
        self.updated_at = time.time()

        # Paths and mode
        self.base_path: Optional[str] = None
        self.proposed_path: Optional[str] = None
        self.review_mode: str = "CHANGE_REVIEW"  # or FULL_PROJECT_AUDIT
        self.manifest_data: Dict[str, Any] = {}

        # Change metadata
        self.changed_files: List[str] = []
        self.change_stats: ChangeStatistics = ChangeStatistics()
        self.diff_summary: str = ""
        self.unified_diffs: Dict[str, str] = {}

        # Specialist execution slots
        self.agent_statuses: Dict[str, AgentExecutionRecord] = {
            "Diff Agent": AgentExecutionRecord(agent_name="Diff Agent", status="PENDING"),
            "Style Agent": AgentExecutionRecord(agent_name="Style Agent", status="PENDING"),
            "Security Agent": AgentExecutionRecord(agent_name="Security Agent", status="PENDING"),
            "Test-Coverage Agent": AgentExecutionRecord(agent_name="Test-Coverage Agent", status="PENDING"),
            "Reviewer Manager": AgentExecutionRecord(agent_name="Reviewer Manager", status="PENDING"),
            "Fix-Suggestion Agent": AgentExecutionRecord(agent_name="Fix-Suggestion Agent", status="PENDING"),
        }

        # Isolated finding slots per agent (prevents concurrent overwrite)
        self.agent_findings: Dict[str, List[Finding]] = {
            "Diff Agent": [],
            "Style Agent": [],
            "Security Agent": [],
            "Test-Coverage Agent": [],
            "Reviewer Manager": [],
            "Fix-Suggestion Agent": [],
        }

        # Consolidated deduplicated findings
        self.consolidated_findings: List[Finding] = []
        self.severity_distribution: Dict[str, int] = {
            "CRITICAL": 0,
            "HIGH": 0,
            "MEDIUM": 0,
            "LOW": 0,
            "INFO": 0,
        }

        # Tool execution records and errors
        self.tool_records: List[ToolExecutionRecord] = []
        self.error_records: List[Dict[str, Any]] = []

        # Decision & Patch
        self.recommendation: Optional[str] = None  # APPROVE or REQUEST_CHANGES
        self.recommendation_rationale: str = ""
        self.patch_proposal: Optional[PatchProposal] = None

        # Progress percentage
        self.progress: int = 0
        self.status: str = "INITIALIZED"  # INITIALIZED, RUNNING, COMPLETED, PARTIAL, FAILED

    def update_agent_status(self, agent_name: str, status: str, error: Optional[str] = None):
        with self._lock:
            record = self.agent_statuses.get(agent_name)
            if not record:
                record = AgentExecutionRecord(agent_name=agent_name, status=status)
                self.agent_statuses[agent_name] = record
            
            record.status = status
            if status == "RUNNING" and record.start_time is None:
                record.start_time = time.time()
            elif status in ("COMPLETED", "FAILED", "TIMEOUT"):
                record.end_time = time.time()
            
            if error:
                record.error_message = error
                self.error_records.append({
                    "agent": agent_name,
                    "error": error,
                    "timestamp": time.time()
                })
            self.updated_at = time.time()

    def add_tool_record(self, agent_name: str, tool_name: str, status: str,
                        duration: float, summary: str):
        with self._lock:
            record = ToolExecutionRecord(
                tool_name=tool_name,
                agent=agent_name,
                status=status,
                execution_time_seconds=duration,
                output_summary=summary
            )
            self.tool_records.append(record)
            if agent_name in self.agent_statuses:
                if tool_name not in self.agent_statuses[agent_name].tools_called:
                    self.agent_statuses[agent_name].tools_called.append(tool_name)
            self.updated_at = time.time()

    def add_findings(self, agent_name: str, findings: List[Finding]):
        with self._lock:
            if agent_name not in self.agent_findings:
                self.agent_findings[agent_name] = []
            self.agent_findings[agent_name].extend(findings)
            if agent_name in self.agent_statuses:
                self.agent_statuses[agent_name].findings_count = len(self.agent_findings[agent_name])
            self.updated_at = time.time()

    def set_consolidated_findings(self, findings: List[Finding], recommendation: str, rationale: str):
        with self._lock:
            self.consolidated_findings = findings
            dist = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
            for f in findings:
                sev = f.severity.value
                if sev in dist:
                    dist[sev] += 1
            self.severity_distribution = dist
            self.recommendation = recommendation
            self.recommendation_rationale = rationale
            self.updated_at = time.time()

    def set_patch_proposal(self, patch: PatchProposal):
        with self._lock:
            self.patch_proposal = patch
            self.updated_at = time.time()

    def set_diff_data(self, changed_files: List[str], stats: ChangeStatistics,
                      diff_summary: str, unified_diffs: Dict[str, str]):
        with self._lock:
            self.changed_files = changed_files
            self.change_stats = stats
            self.diff_summary = diff_summary
            self.unified_diffs = unified_diffs
            self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "review_id": self.review_id,
                "project_name": self.project_name,
                "review_mode": self.review_mode,
                "status": self.status,
                "progress": self.progress,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "changed_files": list(self.changed_files),
                "change_stats": self.change_stats.model_dump(),
                "diff_summary": self.diff_summary,
                "agent_statuses": {k: v.model_dump() for k, v in self.agent_statuses.items()},
                "findings": [f.to_dict() for f in self.consolidated_findings],
                "severity_distribution": dict(self.severity_distribution),
                "tool_records": [t.model_dump() for t in self.tool_records],
                "error_records": list(self.error_records),
                "recommendation": self.recommendation,
                "recommendation_rationale": self.recommendation_rationale,
                "patch_proposal": self.patch_proposal.model_dump() if self.patch_proposal else None,
            }
