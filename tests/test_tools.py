"""
Tool Implementation & Shared State Test Suite
CSE476 CA2 — Automated Code Review Board (Q14)
"""

import os
import tempfile
import pytest

from memory.shared_change_state import SharedChangeState, Finding, Severity, FindingStatus
from memory.persistence import DatabaseManager, JsonlAuditLogger, redact_sensitive_text
from tools.diff_tools import DiffTools
from tools.style_tools import StyleTools
from tools.security_tools import SecurityTools
from tools.testing_tools import TestingTools
from tools.manager_tools import ManagerTools
from tools.fix_tools import FixTools


@pytest.fixture
def temp_project():
    with tempfile.TemporaryDirectory() as td:
        base = os.path.join(td, "base")
        prop = os.path.join(td, "proposed")
        os.makedirs(base)
        os.makedirs(prop)

        # Base snapshot
        with open(os.path.join(base, "calc.py"), "w") as f:
            f.write("def add(a, b):\n    return a + b\n")

        # Proposed snapshot
        with open(os.path.join(prop, "calc.py"), "w") as f:
            f.write("def add(a, b):\n    # Modified\n    return a + b\n\ndef sub(a, b):\n    return a - b\n")

        yield td, base, prop


def test_diff_tools(temp_project):
    _, base, prop = temp_project
    changes = DiffTools.identify_changed_files(base, prop)
    assert "calc.py" in changes["modified"]
    assert "calc.py" in changes["touched_files"]

    diff_res = DiffTools.extract_file_diff(base, prop, "calc.py")
    assert diff_res["lines_added"] > 0
    assert "+def sub(a, b):" in diff_res["unified_diff"]


def test_style_tools(temp_project):
    _, _, prop = temp_project
    # Create file with bad formatting and unused import
    bad_py = os.path.join(prop, "bad_style.py")
    with open(bad_py, "w") as f:
        f.write("import sys\nimport os\ndef test():pass\n")

    check_res = StyleTools.run_ruff_check(prop, ["bad_style.py"])
    assert check_res["status"] == "SUCCESS"
    assert len(check_res["findings"]) > 0

    fmt_res = StyleTools.check_formatting(prop, ["bad_style.py"])
    assert fmt_res["status"] == "SUCCESS"


def test_security_tools_and_redaction(temp_project):
    _, _, prop = temp_project
    # File with potential security issue (eval) and simulated credential
    sec_py = os.path.join(prop, "security_test.py")
    with open(sec_py, "w") as f:
        f.write("API_KEY = 'sk-abcdef1234567890abcdef'\ndef run(x):\n    return eval(x)\n")

    bandit_res = SecurityTools.run_bandit_scan(prop, ["security_test.py"])
    assert bandit_res["status"] == "SUCCESS"
    # eval (B307) should be detected
    eval_findings = [f for f in bandit_res["findings"] if "eval" in f.title.lower()]
    assert len(eval_findings) > 0
    assert eval_findings[0].severity in (Severity.CRITICAL, Severity.HIGH)

    # Redaction test
    raw_text = "Encountered secret: api_key = 'sk-1234567890abcdef1234567890'"
    redacted = redact_sensitive_text(raw_text)
    assert "sk-1234567890abcdef1234567890" not in redacted
    assert "[REDACTED_CREDENTIAL]" in redacted


def test_testing_tools(temp_project):
    _, _, prop = temp_project
    # calc.py is present, but no test_calc.py exists
    disc_res = TestingTools.discover_test_files(prop, ["calc.py"])
    assert disc_res["status"] == "SUCCESS"
    assert "calc.py" in disc_res["untested_sources"]
    assert len(disc_res["findings"]) > 0

    # Test run without sandbox returns NOT_RUN with explicit security explanation
    cov_res = TestingTools.run_pytest_coverage(prop, ["calc.py"], sandbox_service=None)
    assert cov_res["status"] == "NOT_RUN"
    assert "prohibited by security policy" in cov_res["reason"]


def test_manager_tools_deduplication_and_ranking():
    f1 = Finding(
        finding_id="F-1", agent="Style Agent", category="Style",
        severity=Severity.LOW, title="Line too long", description="Exceeds 88",
        file="app.py", line=10, evidence="evidence 1", recommendation="wrap", tool="ruff"
    )
    f2 = Finding(
        finding_id="F-2", agent="Style Agent", category="Style",
        severity=Severity.LOW, title="Line too long", description="Exceeds 88",
        file="app.py", line=11, evidence="evidence 2", recommendation="wrap", tool="ruff"
    )
    f3 = Finding(
        finding_id="F-3", agent="Security Agent", category="Security",
        severity=Severity.CRITICAL, title="Remote code execution", description="eval detected",
        file="app.py", line=25, evidence="eval(cmd)", recommendation="remove eval", tool="bandit"
    )

    ranked, decision, rationale = ManagerTools.rank_and_decide([f1, f2, f3])
    # Duplicate style findings should be deduplicated
    assert len(ranked) == 2
    # Critical must be first
    assert ranked[0].severity == Severity.CRITICAL
    assert decision == "REQUEST_CHANGES"


def test_fix_tools(temp_project):
    _, _, prop = temp_project
    target_f = Finding(
        finding_id="SEC-001", agent="Security Agent", category="Security",
        severity=Severity.CRITICAL, title="Eval call", description="Bad",
        file="calc.py", line=1, evidence="evidence", recommendation="fix", tool="bandit"
    )
    ctx = FixTools.inspect_finding_context(prop, target_f, window=3)
    assert ctx["status"] == "SUCCESS"
    assert "def add(a, b):" in ctx["context_snippet"]

    # Test patch validation
    patch = """--- a/calc.py
+++ b/calc.py
@@ -1,3 +1,3 @@
-def add(a, b):
+def add_numbers(a, b):
"""
    val = FixTools.validate_patch_proposal(patch, prop, "calc.py")
    assert val["status"] == "PASSED"


def test_shared_state_and_persistence(temp_project):
    td, _, _ = temp_project
    db_path = os.path.join(td, "test.db")
    db = DatabaseManager(db_path=db_path)
    logger = JsonlAuditLogger(log_dir=os.path.join(td, "logs"))

    state = SharedChangeState(review_id="REV-100", project_name="UnitTest")
    state.update_agent_status("Security Agent", "RUNNING")
    
    finding = Finding(
        finding_id="F-001", agent="Security Agent", category="Security",
        severity=Severity.HIGH, title="Hardcoded credential", description="Token found",
        file="auth.py", line=5, evidence="token = 'xyz'", recommendation="vault", tool="bandit"
    )
    state.add_findings("Security Agent", [finding])
    state.set_consolidated_findings([finding], "REQUEST_CHANGES", "Blocked by security finding")

    # Persist
    db.save_review_state(state)
    logger.log_event("REV-100", "REVIEW_SAVED", "Reviewer Manager", status="SUCCESS")

    # Retrieve
    retrieved = db.get_review("REV-100")
    assert retrieved is not None
    assert retrieved["recommendation"] == "REQUEST_CHANGES"
    assert len(retrieved["findings"]) == 1
    assert retrieved["findings"][0]["severity"] == "HIGH"
