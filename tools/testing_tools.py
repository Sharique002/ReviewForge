"""
Testing & Coverage Tools
CSE476 CA2 — Automated Code Review Board (Q14)

Tools for the Test-Coverage Agent:
1. discover_test_files(project_path, changed_files)
2. run_pytest_coverage(project_path, changed_files, sandbox_service=None)
"""

import os
from typing import Dict, Any, List, Optional

from memory.shared_change_state import Finding, Severity


class TestingTools:
    """Discovers test suites, maps test coverage, and safely coordinates execution."""

    @staticmethod
    def discover_test_files(project_path: str, changed_files: List[str]) -> Dict[str, Any]:
        """
        Discovers test files in the project and identifies changed source files
        lacking corresponding unit or integration test coverage.
        """
        if not os.path.exists(project_path):
            return {"status": "FAILED", "error": f"Path not found: {project_path}", "test_files": []}

        all_test_files = []
        for root, _, files in os.walk(project_path):
            for f in files:
                if (f.startswith("test_") or f.endswith("_test.py")) and f.endswith(".py"):
                    rel = os.path.relpath(os.path.join(root, f), project_path).replace("\\", "/")
                    all_test_files.append(rel)

        # Map changed source files to candidate test files
        untested_files = []
        tested_files = []
        findings: List[Finding] = []

        # Filter changed python non-test files
        changed_py_sources = [
            cf for cf in changed_files
            if cf.endswith(".py") and not os.path.basename(cf).startswith("test_") and not cf.endswith("_test.py")
        ]

        counter = 1
        for src in changed_py_sources:
            base_stem = os.path.splitext(os.path.basename(src))[0]
            # Potential test names: test_foo.py, foo_test.py
            matched = [
                tf for tf in all_test_files
                if os.path.splitext(os.path.basename(tf))[0] in (f"test_{base_stem}", f"{base_stem}_test")
            ]

            if matched:
                tested_files.append({"source": src, "tests": matched})
            else:
                untested_files.append(src)
                finding = Finding(
                    finding_id=f"TEST-COV-{counter:03d}",
                    agent="Test-Coverage Agent",
                    category="Test Coverage",
                    severity=Severity.MEDIUM,
                    title=f"Untested source code change: {src}",
                    description=f"Source file '{src}' was modified or added, but no matching unit test (e.g. test_{base_stem}.py) was discovered.",
                    file=src,
                    line=1,
                    evidence=f"No associated test discovered among {len(all_test_files)} project test file(s).",
                    recommendation=f"Add unit tests for '{src}' under tests/test_{base_stem}.py to prevent regressions.",
                    tool="test-discovery",
                    confidence="HIGH"
                )
                findings.append(finding)
                counter += 1

        return {
            "status": "SUCCESS",
            "total_test_files_found": len(all_test_files),
            "test_files": all_test_files,
            "tested_sources": tested_files,
            "untested_sources": untested_files,
            "findings": findings
        }

    @staticmethod
    def run_pytest_coverage(project_path: str, changed_files: List[str],
                            sandbox_service: Optional[Any] = None) -> Dict[str, Any]:
        """
        Executes pytest and coverage analysis ONLY within a verified Docker sandbox.
        If Docker sandbox is unavailable or disabled, returns status 'NOT_RUN' with an
        explicit security explanation. Never executes untrusted project code on the host.
        """
        if sandbox_service and hasattr(sandbox_service, "is_docker_available") and sandbox_service.is_docker_available():
            res = sandbox_service.run_isolated_tests(project_path, changed_files)
            if "findings" not in res:
                res["findings"] = []
                if res.get("status") == "FAILED":
                    res["findings"].append(Finding(
                        finding_id="TEST-FAIL-001",
                        agent="Test-Coverage Agent",
                        category="Test Execution",
                        severity=Severity.HIGH,
                        title="Sandbox test execution failed",
                        description="One or more unit tests failed when executed inside the isolated Docker sandbox.",
                        file=None,
                        line=None,
                        evidence=(res.get("output") or "Test suite exited with non-zero status.")[:500],
                        recommendation="Fix failing test assertions before requesting code review approval.",
                        tool="docker-sandbox",
                        confidence="HIGH"
                    ))
                elif res.get("status") == "TIMEOUT":
                    res["findings"].append(Finding(
                        finding_id="TEST-TIME-001",
                        agent="Test-Coverage Agent",
                        category="Test Execution",
                        severity=Severity.HIGH,
                        title="Sandbox test execution timed out",
                        description=res.get("reason", "Test suite execution exceeded maximum sandbox timeout quota."),
                        file=None,
                        line=None,
                        evidence="Subprocess execution exceeded timeout limits.",
                        recommendation="Optimize test runtimes and eliminate infinite loops or blocked I/O.",
                        tool="docker-sandbox",
                        confidence="HIGH"
                    ))
            return res

        # Honest, security-first fallback: Host execution is strictly forbidden for untrusted code
        return {
            "status": "NOT_RUN",
            "passed": False,
            "tests_executed": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "coverage_percent": None,
            "reason": "Docker sandbox is unavailable; direct host execution of untrusted project code is prohibited by security policy.",
            "findings": [
                Finding(
                    finding_id="TEST-EXEC-001",
                    agent="Test-Coverage Agent",
                    category="Test Execution",
                    severity=Severity.INFO,
                    title="Test execution marked NOT_RUN (Sandbox unavailable)",
                    description="Automated dynamic test execution was skipped because Docker sandbox is offline. Untrusted code cannot be executed directly on the host.",
                    file=None,
                    line=None,
                    evidence="Host execution prohibited by Security Isolation Policy.",
                    recommendation="Enable Docker Desktop or run tests inside an isolated CI/CD container.",
                    tool="docker-sandbox",
                    confidence="HIGH"
                )
            ]
        }
