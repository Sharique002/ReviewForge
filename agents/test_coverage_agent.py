"""
Test-Coverage Agent
CSE476 CA2 — Automated Code Review Board (Q14)

Responsibilities:
- Discover test suites and test files.
- Map modified/added source files to tests.
- Identify untested changes.
- Safely execute tests in isolated Docker sandbox if available.
- Truthfully report NOT_RUN if sandbox is offline (never execute untrusted code on host).
- Update SharedChangeState.
"""

import time
from typing import Dict, Any, List, Optional

from semantic_kernel.kernel import Kernel
from semantic_kernel.functions import kernel_function
from semantic_kernel.agents import Agent, AgentResponseItem, ChatHistoryAgentThread
from semantic_kernel.contents import ChatMessageContent, AuthorRole

from memory.shared_change_state import SharedChangeState, Finding
from memory.persistence import JsonlAuditLogger
from tools.testing_tools import TestingTools
from services.sandbox_service import SandboxService


class TestingToolsPlugin:
    """Semantic Kernel Plugin exposing real test discovery and safe coverage execution tools."""
    __test__ = False

    def __init__(self, sandbox_service: Optional[Any] = None):
        self.sandbox_service = sandbox_service

    @kernel_function(name="discover_test_files", description="Discovers test files and maps changed sources to tests")
    def discover_test_files(self, project_path: str, changed_files: List[str]) -> Dict[str, Any]:
        return TestingTools.discover_test_files(project_path, changed_files)

    @kernel_function(name="run_pytest_coverage", description="Executes tests safely inside Docker sandbox")
    def run_pytest_coverage(self, project_path: str, changed_files: List[str]) -> Dict[str, Any]:
        return TestingTools.run_pytest_coverage(project_path, changed_files, sandbox_service=self.sandbox_service)


class TestCoverageAgent(Agent):
    """Test & Coverage Specialist Agent powered by Microsoft Semantic Kernel."""
    __test__ = False  # Prevent pytest from treating as a Test class

    def __init__(self, sandbox_service: Optional[Any] = None, logger: Optional[JsonlAuditLogger] = None):
        super().__init__(name="test_coverage_agent")
        sb = sandbox_service if sandbox_service is not None else SandboxService()
        object.__setattr__(self, "agent_name", "Test-Coverage Agent")
        object.__setattr__(self, "sandbox_service", sb)
        object.__setattr__(self, "logger", logger or JsonlAuditLogger())
        
        # Initialize isolated Semantic Kernel and register real tools plugin
        k = Kernel()
        test_plugin = TestingToolsPlugin(sandbox_service=sb)
        k.add_plugin(test_plugin, plugin_name="test_plugin")
        object.__setattr__(self, "kernel", k)

    async def get_response(self, messages=None, shared_state: Optional[SharedChangeState] = None, **kwargs) -> AgentResponseItem:
        if not shared_state:
            msg = ChatMessageContent(role=AuthorRole.ASSISTANT, name=self.agent_name, content="Error: No SharedChangeState provided.")
            return AgentResponseItem(message=msg, thread=ChatHistoryAgentThread())

        shared_state.update_agent_status(self.agent_name, "RUNNING")
        self.logger.log_event(shared_state.review_id, "AGENT_STARTED", agent=self.agent_name)

        target_dir = shared_state.proposed_path or shared_state.base_path or ""
        changed_files = list(shared_state.changed_files)
        all_findings: List[Finding] = []

        try:
            # Tool 1: discover_test_files
            t0 = time.time()
            disc_func = self.kernel.plugins["test_plugin"]["discover_test_files"]
            disc_res = await self.kernel.invoke(disc_func, project_path=target_dir, changed_files=changed_files)
            dur1 = time.time() - t0
            d_val = disc_res.value if hasattr(disc_res, "value") else disc_res

            findings1 = d_val.get("findings", [])
            all_findings.extend(findings1)
            shared_state.add_tool_record(
                self.agent_name, "discover_test_files", d_val.get("status", "SUCCESS"), dur1,
                f"Discovered {d_val.get('total_test_files_found', 0)} test file(s); {len(d_val.get('untested_sources', []))} untested source(s)."
            )
            self.logger.log_event(shared_state.review_id, "TOOL_EXECUTED", agent=self.agent_name,
                                  tool="discover_test_files", status=d_val.get("status", "SUCCESS"))

            # Tool 2: run_pytest_coverage (safely gated)
            t1 = time.time()
            exec_func = self.kernel.plugins["test_plugin"]["run_pytest_coverage"]
            exec_res = await self.kernel.invoke(exec_func, project_path=target_dir, changed_files=changed_files)
            dur2 = time.time() - t1
            e_val = exec_res.value if hasattr(exec_res, "value") else exec_res

            findings2 = e_val.get("findings", [])
            all_findings.extend(findings2)
            shared_state.add_tool_record(
                self.agent_name, "run_pytest_coverage", e_val.get("status", "NOT_RUN"), dur2,
                f"Execution result: {e_val.get('status', 'NOT_RUN')}. Reason: {e_val.get('reason', 'N/A')}"
            )
            self.logger.log_event(shared_state.review_id, "TOOL_EXECUTED", agent=self.agent_name,
                                  tool="run_pytest_coverage", status=e_val.get("status", "NOT_RUN"))

            # Update shared state with findings
            shared_state.add_findings(self.agent_name, all_findings)
            shared_state.update_agent_status(self.agent_name, "COMPLETED")
            self.logger.log_event(shared_state.review_id, "AGENT_COMPLETED", agent=self.agent_name,
                                  metadata={"findings_count": len(all_findings)})

            summary = (
                f"Test analysis completed. {d_val.get('total_test_files_found', 0)} test file(s) found; "
                f"{len(d_val.get('untested_sources', []))} untested changes flagged. "
                f"Execution status: {e_val.get('status', 'NOT_RUN')}."
            )
            msg = ChatMessageContent(role=AuthorRole.ASSISTANT, name=self.agent_name, content=summary)
            return AgentResponseItem(message=msg, thread=ChatHistoryAgentThread())

        except Exception as e:
            err_msg = str(e)
            shared_state.update_agent_status(self.agent_name, "FAILED", error=err_msg)
            self.logger.log_event(shared_state.review_id, "AGENT_FAILED", agent=self.agent_name,
                                  status="FAILED", metadata={"error": err_msg})
            msg = ChatMessageContent(role=AuthorRole.ASSISTANT, name=self.agent_name, content=f"Test-Coverage Agent failed: {err_msg}")
            return AgentResponseItem(message=msg, thread=ChatHistoryAgentThread())

    async def invoke(self, messages=None, **kwargs):
        item = await self.get_response(messages=messages, **kwargs)
        yield item

    async def invoke_stream(self, messages=None, **kwargs):
        item = await self.get_response(messages=messages, **kwargs)
        yield item
