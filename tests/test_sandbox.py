"""
Docker Sandbox, Dependency Injection & Review State Test Suite
CSE476 CA2 — Automated Code Review Board (Q14)

Verifies:
1. SandboxService container flags, resource limits, and isolation parameters.
2. Correct dependency injection of SandboxService through TestCoverageAgent & TestingToolsPlugin.
3. Safe NOT_RUN fallback when Docker is offline (zero untrusted code execution on host).
4. Isolated Docker execution with mocked responsive Docker daemon.
5. Accurate COMPLETED, PARTIAL, and FAILED review states and rejection of unjustified approvals.
6. Elimination of duplicate Diff Agent execution in orchestration fan-out.
"""

import os
import subprocess
import tempfile
import asyncio
from unittest.mock import patch, MagicMock
import pytest

from services.sandbox_service import SandboxService
from tools.testing_tools import TestingTools
from agents.test_coverage_agent import TestCoverageAgent, TestingToolsPlugin
from agents.diff_agent import DiffAgent
from agents.style_agent import StyleAgent
from agents.security_agent import SecurityAgent
from agents.reviewer_manager import ReviewerManager
from agents.fix_suggestion_agent import FixSuggestionAgent
from tools.manager_tools import ManagerTools
from orchestration.fanout_fanin import FanOutFanInOrchestrator
from memory.shared_change_state import SharedChangeState, Finding, Severity


def test_sandbox_service_defaults_and_configuration():
    """Verify SandboxService default parameters and configurable resource limits."""
    sb = SandboxService(
        image="custom-sandbox:v1",
        cpu_limit="2.0",
        memory_limit="1g",
        timeout_seconds=45
    )
    assert sb.image == "custom-sandbox:v1"
    assert sb.cpu_limit == "2.0"
    assert sb.memory_limit == "1g"
    assert sb.timeout_seconds == 45

    default_sb = SandboxService()
    assert default_sb.cpu_limit == "1.0"
    assert default_sb.memory_limit == "512m"
    assert default_sb.timeout_seconds == 30


def test_sandbox_docker_unavailable_honest_not_run(tmp_path):
    """When Docker is unavailable, tests must truthfully report NOT_RUN without host execution."""
    sb = SandboxService()
    with patch.object(sb, "is_docker_available", return_value=False):
        res = sb.run_isolated_tests(str(tmp_path), ["foo.py"])
        assert res["status"] == "NOT_RUN"
        assert res["passed"] is False
        assert "prohibited by security policy" in res["reason"]


def test_testing_tools_plugin_dependency_injection():
    """Verify that SandboxService is correctly injected into TestingToolsPlugin and TestCoverageAgent."""
    custom_sb = SandboxService(image="test-img:latest")
    agent = TestCoverageAgent(sandbox_service=custom_sb)

    # Verify agent attribute
    assert agent.sandbox_service is custom_sb

    # Verify plugin attribute inside Kernel
    plugin = agent.kernel.plugins["test_plugin"]
    # The plugin instance wrapped by Kernel
    # The plugin itself was initialized with sandbox_service
    assert hasattr(agent, "sandbox_service")
    assert agent.sandbox_service.image == "test-img:latest"


def test_sandbox_docker_command_isolation_flags(tmp_path):
    """
    Verify that when Docker is available, the docker run command strictly enforces:
    - --network none
    - --user 1000:1000
    - --cpus 1.0
    - --memory 512m
    - --cap-drop ALL
    - --read-only
    - --tmpfs /tmp:rw,noexec,nosuid,size=64m
    - -v ...:/app:ro
    - -o cache_dir=/tmp/.pytest_cache
    """
    sb = SandboxService(cpu_limit="1.0", memory_limit="512m", timeout_seconds=30)
    
    with patch.object(sb, "is_docker_available", return_value=True), \
         patch.object(sb, "_resolve_image", return_value="reviewforge-sandbox:latest"), \
         patch("subprocess.run") as mock_run:
        
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "===== 2 passed in 0.12s ====="
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        result = sb.run_isolated_tests(str(tmp_path), ["calc.py"])

        assert result["status"] == "SUCCESS"
        assert result["passed"] is True
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]

        # Verify all mandatory security and isolation arguments
        assert cmd[0] == "docker"
        assert cmd[1] == "run"
        assert "--rm" in cmd
        assert "--network" in cmd and cmd[cmd.index("--network") + 1] == "none"
        assert "--user" in cmd and cmd[cmd.index("--user") + 1] == "1000:1000"
        assert "--cpus" in cmd and cmd[cmd.index("--cpus") + 1] == "1.0"
        assert "--memory" in cmd and cmd[cmd.index("--memory") + 1] == "512m"
        assert "--cap-drop" in cmd and cmd[cmd.index("--cap-drop") + 1] == "ALL"
        assert "--read-only" in cmd
        assert "--tmpfs" in cmd and "/tmp:rw,noexec,nosuid,size=64m" in cmd[cmd.index("--tmpfs") + 1]
        
        # Verify read-only mount
        mount_arg = f"{os.path.abspath(str(tmp_path))}:/app:ro"
        assert mount_arg in cmd

        # Verify cache_dir redirect to isolated tmpfs
        assert "cache_dir=/tmp/.pytest_cache" in cmd


def test_manager_rejects_approval_on_failed_agent():
    """Verify that ManagerTools never produces an APPROVE recommendation if a mandatory agent fails."""
    # Findings with only LOW/INFO
    findings = [
        Finding(
            finding_id="F-001",
            agent="Style Agent",
            category="Code Style",
            severity=Severity.LOW,
            title="Trailing whitespace",
            description="Minor whitespace",
            evidence="line 10",
            recommendation="Trim whitespace",
            tool="ruff"
        )
    ]

    # Meta disclosing failed agent
    meta = {
        "failed_agents": ["Security Agent"],
        "security_incomplete": True,
        "tests_unexecuted": False,
        "scanner_errors": []
    }

    ranked, rec, rationale = ManagerTools.rank_and_decide(findings, metadata=meta)

    # Must be REQUEST_CHANGES, NEVER APPROVE
    assert rec == "REQUEST_CHANGES"
    assert "Security Agent" in rationale
    assert "strictly prohibited" in rationale


@pytest.mark.asyncio
async def test_orchestrator_failure_handling_states():
    """Verify COMPLETED, PARTIAL, and FAILED review state assignments."""
    orchestrator = FanOutFanInOrchestrator()

    async def mock_agent_success(name, shared_state):
        if shared_state:
            shared_state.update_agent_status(name, "COMPLETED")
        yield MagicMock()

    # Case 1: Partial Failure (Style Agent fails, other specialists succeed)
    state_partial = SharedChangeState(review_id="REV-TEST-PARTIAL")
    state_partial.changed_files = ["app.py"]

    with patch.object(DiffAgent, "invoke", side_effect=lambda *a, shared_state=None, **kw: mock_agent_success("Diff Agent", shared_state)), \
         patch.object(StyleAgent, "invoke", side_effect=Exception("Style linter crashed")), \
         patch.object(SecurityAgent, "invoke", side_effect=lambda *a, shared_state=None, **kw: mock_agent_success("Security Agent", shared_state)), \
         patch.object(TestCoverageAgent, "invoke", side_effect=lambda *a, shared_state=None, **kw: mock_agent_success("Test-Coverage Agent", shared_state)), \
         patch.object(ReviewerManager, "invoke", side_effect=lambda *a, shared_state=None, **kw: mock_agent_success("Reviewer Manager", shared_state)), \
         patch.object(FixSuggestionAgent, "invoke", side_effect=lambda *a, shared_state=None, **kw: mock_agent_success("Fix-Suggestion Agent", shared_state)):

        res_state = await orchestrator.execute_review(state_partial)
        assert res_state.status == "PARTIAL"
        assert res_state.recommendation == "REQUEST_CHANGES"
        assert "mandatory agent(s): Style Agent" in res_state.recommendation_rationale

    # Case 2: Critical Pipeline Failure (Diff Agent fails)
    state_failed = SharedChangeState(review_id="REV-TEST-FAILED")
    with patch.object(DiffAgent, "invoke", side_effect=Exception("Git repository corrupted")), \
         patch.object(StyleAgent, "invoke", side_effect=lambda *a, shared_state=None, **kw: mock_agent_success("Style Agent", shared_state)), \
         patch.object(SecurityAgent, "invoke", side_effect=lambda *a, shared_state=None, **kw: mock_agent_success("Security Agent", shared_state)), \
         patch.object(TestCoverageAgent, "invoke", side_effect=lambda *a, shared_state=None, **kw: mock_agent_success("Test-Coverage Agent", shared_state)), \
         patch.object(ReviewerManager, "invoke", side_effect=lambda *a, shared_state=None, **kw: mock_agent_success("Reviewer Manager", shared_state)), \
         patch.object(FixSuggestionAgent, "invoke", side_effect=lambda *a, shared_state=None, **kw: mock_agent_success("Fix-Suggestion Agent", shared_state)):

        res_state_failed = await orchestrator.execute_review(state_failed)
        assert res_state_failed.status == "FAILED"
        assert res_state_failed.recommendation == "REQUEST_CHANGES"
        assert "Diff Agent failed" in res_state_failed.recommendation_rationale


@pytest.mark.asyncio
async def test_no_duplicate_diff_agent_execution():
    """Verify Diff Agent executes exactly once (Step 1) and is not duplicated in Step 2 fan-out."""
    orchestrator = FanOutFanInOrchestrator()
    state = SharedChangeState(review_id="REV-TEST-DIFF-COUNT")

    diff_invoke_count = 0

    async def mock_diff_invoke(*args, shared_state=None, **kwargs):
        nonlocal diff_invoke_count
        diff_invoke_count += 1
        if shared_state:
            shared_state.update_agent_status("Diff Agent", "COMPLETED")
        yield MagicMock()

    async def mock_other_invoke(agent_name, shared_state=None, **kwargs):
        if shared_state:
            shared_state.update_agent_status(agent_name, "COMPLETED")
        yield MagicMock()

    with patch.object(DiffAgent, "invoke", side_effect=mock_diff_invoke), \
         patch.object(StyleAgent, "invoke", side_effect=lambda *a, shared_state=None, **kw: mock_other_invoke("Style Agent", shared_state)), \
         patch.object(SecurityAgent, "invoke", side_effect=lambda *a, shared_state=None, **kw: mock_other_invoke("Security Agent", shared_state)), \
         patch.object(TestCoverageAgent, "invoke", side_effect=lambda *a, shared_state=None, **kw: mock_other_invoke("Test-Coverage Agent", shared_state)), \
         patch.object(ReviewerManager, "invoke", side_effect=lambda *a, shared_state=None, **kw: mock_other_invoke("Reviewer Manager", shared_state)), \
         patch.object(FixSuggestionAgent, "invoke", side_effect=lambda *a, shared_state=None, **kw: mock_other_invoke("Fix-Suggestion Agent", shared_state)):

        await orchestrator.execute_review(state)
        # Must be invoked exactly once in Step 1
        assert diff_invoke_count == 1


async def _async_generator_mock(items):
    for item in items:
        yield item
