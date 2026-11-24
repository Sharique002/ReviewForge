"""
Database & Audit Persistence Layer
CSE476 CA2 — Automated Code Review Board (Q14)

Provides:
- SQLite persistent storage for reviews, findings, agent executions, and patches.
- Append-only JSONL execution logging (logs/run_log.jsonl) with automatic credential redaction.
"""

import os
import sqlite3
import json
import time
import uuid
import threading
import re
from contextlib import contextmanager
from typing import Dict, Any, List, Optional

from memory.shared_change_state import SharedChangeState, Finding, PatchProposal


# Regex patterns for detecting and redacting sensitive credentials in logs & DB
REDACTION_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|secret|password|token|auth|bearer)\s*[:=]\s*["\']?([a-zA-Z0-9_\-\.]{8,})["\']?'),
    re.compile(r'(?i)(sk-[a-zA-Z0-9]{20,})'),
    re.compile(r'(?i)(ghp_[a-zA-Z0-9]{20,})'),
]


def redact_sensitive_text(text: str) -> str:
    """Sanitizes text by masking sensitive values."""
    if not isinstance(text, str):
        return text
    sanitized = text
    for pattern in REDACTION_PATTERNS:
        def mask_match(m):
            full = m.group(0)
            if len(m.groups()) >= 2:
                # Mask group 2 (the secret value)
                return full.replace(m.group(2), "[REDACTED_CREDENTIAL]")
            return "[REDACTED_CREDENTIAL]"
        sanitized = pattern.sub(mask_match, sanitized)
    return sanitized


class JsonlAuditLogger:
    """Thread-safe, append-only JSONL execution audit logger."""
    _file_lock = threading.Lock()

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = os.path.abspath(log_dir)
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_path = os.path.join(self.log_dir, "run_log.jsonl")

    def log_event(self, review_id: str, event_type: str, agent: Optional[str] = None,
                  tool: Optional[str] = None, status: str = "SUCCESS",
                  metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Appends a structured event to run_log.jsonl with redaction applied."""
        safe_meta = {}
        if metadata:
            for k, v in metadata.items():
                if isinstance(v, str):
                    safe_meta[k] = redact_sensitive_text(v)
                else:
                    safe_meta[k] = v

        event = {
            "event_id": str(uuid.uuid4()),
            "review_id": review_id,
            "timestamp": time.time(),
            "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event_type": event_type,
            "agent": agent,
            "tool": tool,
            "status": status,
            "metadata": safe_meta
        }

        with self._file_lock:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")

        return event

    def get_events_for_review(self, review_id: str) -> List[Dict[str, Any]]:
        """Reads back events belonging to a specific review."""
        if not os.path.exists(self.log_path):
            return []
        events = []
        with self._file_lock:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            ev = json.loads(line)
                            if ev.get("review_id") == review_id:
                                events.append(ev)
                        except json.JSONDecodeError:
                            continue
        return events


class DatabaseManager:
    """Manages SQLite storage for code reviews."""

    def __init__(self, db_path: str = "data/reviews.db"):
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_schema()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_schema(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                review_id TEXT PRIMARY KEY,
                project_name TEXT,
                review_mode TEXT,
                status TEXT,
                recommendation TEXT,
                recommendation_rationale TEXT,
                diff_summary TEXT,
                created_at REAL,
                updated_at REAL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS findings (
                finding_id TEXT,
                review_id TEXT,
                agent TEXT,
                category TEXT,
                severity TEXT,
                title TEXT,
                description TEXT,
                file TEXT,
                line INTEGER,
                evidence TEXT,
                recommendation TEXT,
                tool TEXT,
                confidence TEXT,
                status TEXT,
                timestamp REAL,
                PRIMARY KEY (review_id, finding_id)
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_executions (
                review_id TEXT,
                agent_name TEXT,
                status TEXT,
                start_time REAL,
                end_time REAL,
                tools_called TEXT,
                findings_count INTEGER,
                error_message TEXT,
                PRIMARY KEY (review_id, agent_name)
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS patches (
                review_id TEXT PRIMARY KEY,
                target_finding TEXT,
                file TEXT,
                severity TEXT,
                patch_status TEXT,
                explanation TEXT,
                patch TEXT,
                validation TEXT,
                created_at REAL
            );
            """)
            conn.commit()

    def save_review_state(self, state: SharedChangeState):
        """Persists complete review state transactionally."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Upsert review
            cursor.execute("""
            INSERT INTO reviews (review_id, project_name, review_mode, status,
                                 recommendation, recommendation_rationale, diff_summary,
                                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(review_id) DO UPDATE SET
                status=excluded.status,
                recommendation=excluded.recommendation,
                recommendation_rationale=excluded.recommendation_rationale,
                diff_summary=excluded.diff_summary,
                updated_at=excluded.updated_at
            """, (
                state.review_id,
                state.project_name,
                state.review_mode,
                state.status,
                state.recommendation,
                state.recommendation_rationale,
                state.diff_summary,
                state.created_at,
                state.updated_at
            ))

            # Upsert agent executions
            for agent_name, record in state.agent_statuses.items():
                cursor.execute("""
                INSERT INTO agent_executions (review_id, agent_name, status, start_time,
                                              end_time, tools_called, findings_count, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(review_id, agent_name) DO UPDATE SET
                    status=excluded.status,
                    start_time=excluded.start_time,
                    end_time=excluded.end_time,
                    tools_called=excluded.tools_called,
                    findings_count=excluded.findings_count,
                    error_message=excluded.error_message
                """, (
                    state.review_id,
                    agent_name,
                    record.status,
                    record.start_time,
                    record.end_time,
                    json.dumps(record.tools_called),
                    record.findings_count,
                    record.error_message
                ))

            # Insert/replace findings
            for f in state.consolidated_findings:
                cursor.execute("""
                INSERT OR REPLACE INTO findings (
                    finding_id, review_id, agent, category, severity, title,
                    description, file, line, evidence, recommendation,
                    tool, confidence, status, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f.finding_id,
                    state.review_id,
                    f.agent,
                    f.category,
                    f.severity.value,
                    f.title,
                    f.description,
                    f.file,
                    f.line,
                    redact_sensitive_text(f.evidence),
                    f.recommendation,
                    f.tool,
                    f.confidence,
                    f.status.value,
                    f.timestamp
                ))

            # Save patch proposal if present
            if state.patch_proposal:
                p = state.patch_proposal
                cursor.execute("""
                INSERT OR REPLACE INTO patches (
                    review_id, target_finding, file, severity, patch_status,
                    explanation, patch, validation, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    state.review_id,
                    p.target_finding,
                    p.file,
                    p.severity,
                    p.patch_status,
                    p.explanation,
                    p.patch,
                    p.validation,
                    p.timestamp
                ))

            conn.commit()

    def get_review(self, review_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves complete review state from database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM reviews WHERE review_id = ?", (review_id,))
            row = cursor.fetchone()
            if not row:
                return None
            review_data = dict(row)

            # Get findings
            cursor.execute("SELECT * FROM findings WHERE review_id = ? ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 WHEN 'LOW' THEN 4 ELSE 5 END", (review_id,))
            review_data["findings"] = [dict(r) for r in cursor.fetchall()]

            # Get agent executions
            cursor.execute("SELECT * FROM agent_executions WHERE review_id = ?", (review_id,))
            review_data["agent_executions"] = {
                r["agent_name"]: {
                    "agent_name": r["agent_name"],
                    "status": r["status"],
                    "start_time": r["start_time"],
                    "end_time": r["end_time"],
                    "tools_called": json.loads(r["tools_called"] or "[]"),
                    "findings_count": r["findings_count"],
                    "error_message": r["error_message"]
                }
                for r in cursor.fetchall()
            }

            # Get patch
            cursor.execute("SELECT * FROM patches WHERE review_id = ?", (review_id,))
            p_row = cursor.fetchone()
            review_data["patch_proposal"] = dict(p_row) if p_row else None

            return review_data

    def list_reviews(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Lists recent reviews."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT review_id, project_name, review_mode, status, recommendation,
                   diff_summary, created_at, updated_at
            FROM reviews
            ORDER BY created_at DESC
            LIMIT ?
            """, (limit,))
            return [dict(r) for r in cursor.fetchall()]
