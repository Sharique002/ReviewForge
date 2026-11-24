"""
Multi-Agent Orchestration & Assignment Scenarios Test Suite
CSE476 CA2 — Automated Code Review Board (Q14)

Covers the three authoritative assignment scenarios:
SCENARIO 1 — CLEAN CHANGE (APPROVE)
SCENARIO 2 — SECURITY ISSUE (REQUEST_CHANGES + PATCH PROPOSAL)
SCENARIO 3 — MISSING TESTS / STYLE ISSUES (REQUEST_CHANGES)
"""

import os
import zipfile
import tempfile
import asyncio
import pytest

from orchestration.workflow import ReviewWorkflow
from memory.shared_change_state import Severity


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as td:
        ws_dir = os.path.join(td, "ws")
        db_path = os.path.join(td, "test.db")
        log_dir = os.path.join(td, "logs")
        os.makedirs(ws_dir)
        os.makedirs(log_dir)
        workflow = ReviewWorkflow(workspace_base_dir=ws_dir, db_path=db_path, log_dir=log_dir)
        yield td, workflow


def create_zip(zip_path: str, file_map: dict):
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for arcname, content in file_map.items():
            zf.writestr(arcname, content)


# ----------------------------------------------------------------------
# SCENARIO 1 — CLEAN CHANGE
# - Valid base & proposed snapshots
# - Clean, formatted Python code
# - Matching unit test included
# - Specialist agents run concurrently
# - Reviewer Manager consolidates and APPROVES
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_1_clean_change(temp_workspace):
    td, workflow = temp_workspace
    zip_p = os.path.join(td, "clean_change.zip")

    files = {
        "base/math_ops.py": "def add(a: int, b: int) -> int:\n    return a + b\n",
        "proposed/math_ops.py": "def add(a: int, b: int) -> int:\n    return a + b\n\n\ndef multiply(a: int, b: int) -> int:\n    return a * b\n",
        "proposed/tests/test_math_ops.py": "from math_ops import add, multiply\n\n\ndef test_add():\n    assert add(2, 3) == 5\n\n\ndef test_multiply():\n    assert multiply(2, 3) == 6\n",
        "review-manifest.json": '{"project_name": "MathService", "description": "Add multiply function"}'
    }
    create_zip(zip_p, files)

    state = await workflow.execute_review_pipeline(zip_p, review_id="REV-SCENARIO-1")

    assert state.status == "COMPLETED"
    assert "math_ops.py" in state.changed_files
    # Verify all agents participated
    for agent_name in ["Diff Agent", "Style Agent", "Security Agent", "Test-Coverage Agent", "Reviewer Manager"]:
        assert state.agent_statuses[agent_name].status == "COMPLETED"

    # Merge recommendation should be APPROVE (no blocking security/style/test findings)
    assert state.recommendation == "APPROVE"
    assert state.severity_distribution.get("CRITICAL", 0) == 0
    assert state.severity_distribution.get("HIGH", 0) == 0


# ----------------------------------------------------------------------
# SCENARIO 2 — SECURITY ISSUE
# - Controlled fixture with dummy credential / dangerous eval pattern
# - Security Agent detects the issue and redacts sensitive data
# - Reviewer Manager REQUESTS_CHANGES
# - Fix-Suggestion Agent proposes a concrete patch
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_2_security_issue(temp_workspace):
    td, workflow = temp_workspace
    zip_p = os.path.join(td, "security_issue.zip")

    files = {
        "base/auth.py": "def verify(user: str) -> bool:\n    return True\n",
        "proposed/auth.py": "def verify(user: str) -> bool:\n    # Unsafe evaluation\n    return eval(user)\n",
        "proposed/tests/test_auth.py": "def test_dummy():\n    pass\n",
        "review-manifest.json": '{"project_name": "AuthService", "description": "Authentication fix"}'
    }
    create_zip(zip_p, files)

    state = await workflow.execute_review_pipeline(zip_p, review_id="REV-SCENARIO-2")

    assert state.status == "COMPLETED"
    # Merge recommendation must be REQUEST_CHANGES due to critical/high security finding
    assert state.recommendation == "REQUEST_CHANGES"

    # Verify security findings exist
    sec_findings = [f for f in state.consolidated_findings if f.category == "Application Security"]
    assert len(sec_findings) > 0
    assert any(f.severity in (Severity.CRITICAL, Severity.HIGH) for f in sec_findings)

    # Verify Fix-Suggestion Agent generated a patch for the highest-severity finding
    assert state.patch_proposal is not None
    assert state.patch_proposal.patch_status == "PROPOSED"
    assert "--- a/auth.py" in state.patch_proposal.patch
    assert state.patch_proposal.validation in ("PASSED", "NOT_RUN")


# ----------------------------------------------------------------------
# SCENARIO 3 — MISSING TESTS / STYLE ISSUES
# - Submit change with style violation and no corresponding tests
# - Style Agent reports style defect
# - Test-Coverage Agent reports missing test coverage
# - Reviewer Manager ranks findings and REQUESTS_CHANGES
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_3_missing_tests_and_style(temp_workspace):
    td, workflow = temp_workspace
    zip_p = os.path.join(td, "style_test_issue.zip")

    # Syntax with unused imports and no test file created
    files = {
        "base/service.py": "def run():\n    return 1\n",
        "proposed/service.py": "import os\nimport sys\ndef run():\n    x = 10\n    return x\n",
        "review-manifest.json": '{"project_name": "DataPipeline", "description": "Data processing"}'
    }
    create_zip(zip_p, files)

    state = await workflow.execute_review_pipeline(zip_p, review_id="REV-SCENARIO-3")

    assert state.status == "COMPLETED"
    # Untested change + style defects trigger REQUEST_CHANGES under strict policy
    assert state.recommendation == "REQUEST_CHANGES"

    # Verify Test-Coverage Agent flagged untested change
    test_findings = [f for f in state.consolidated_findings if f.category == "Test Coverage"]
    assert len(test_findings) > 0
    assert "service.py" in test_findings[0].file
