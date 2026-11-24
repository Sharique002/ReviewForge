"""
Style Agent
CSE476 CA2 — Automated Code Review Board (Q14)

Responsibilities:
- Run Ruff linter on changed Python files.
- Check formatting and style conformity.
- Identify readability and maintainability defects.
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
from tools.style_tools import StyleTools


class StyleToolsPlugin:
    """Semantic Kernel Plugin exposing real Ruff lint and formatting tools."""

    @kernel_function(name="run_ruff_check", description="Executes Ruff linter on changed files")
    def run_ruff_check(self, project_path: str, changed_files: List[str]) -> Dict[str, Any]:
        return StyleTools.run_ruff_check(project_path, changed_files)

    @kernel_function(name="check_formatting", description="Verifies formatting against PEP 8 rules")
    def check_formatting(self, project_path: str, changed_files: List[str]) -> Dict[str, Any]:
        return StyleTools.check_formatting(project_path, changed_files)


class StyleAgent(Agent):
    """Style & Maintainability Specialist Agent powered by Microsoft Semantic Kernel."""

    def __init__(self, logger: Optional[JsonlAuditLogger] = None):
        super().__init__(name="style_agent")
        object.__setattr__(self, "agent_name", "Style Agent")
        object.__setattr__(self, "logger", logger or JsonlAuditLogger())
        
        # Initialize isolated Semantic Kernel and register real tools plugin
        k = Kernel()
        style_plugin = StyleToolsPlugin()
        k.add_plugin(style_plugin, plugin_name="style_plugin")
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
            # Tool 1: run_ruff_check
            t0 = time.time()
            lint_func = self.kernel.plugins["style_plugin"]["run_ruff_check"]
            lint_res = await self.kernel.invoke(lint_func, project_path=target_dir, changed_files=changed_files)
            dur1 = time.time() - t0
            lint_val = lint_res.value if hasattr(lint_res, "value") else lint_res

            findings1 = lint_val.get("findings", [])
            all_findings.extend(findings1)
            shared_state.add_tool_record(
                self.agent_name, "run_ruff_check", lint_val.get("status", "SUCCESS"), dur1,
                f"Scanned files; identified {len(findings1)} style violation(s)."
            )
            self.logger.log_event(shared_state.review_id, "TOOL_EXECUTED", agent=self.agent_name,
                                  tool="run_ruff_check", status=lint_val.get("status", "SUCCESS"))

            # Tool 2: check_formatting
            t1 = time.time()
            fmt_func = self.kernel.plugins["style_plugin"]["check_formatting"]
            fmt_res = await self.kernel.invoke(fmt_func, project_path=target_dir, changed_files=changed_files)
            dur2 = time.time() - t1
            fmt_val = fmt_res.value if hasattr(fmt_res, "value") else fmt_res

            findings2 = fmt_val.get("findings", [])
            all_findings.extend(findings2)
            shared_state.add_tool_record(
                self.agent_name, "check_formatting", fmt_val.get("status", "SUCCESS"), dur2,
                f"Format checked; {len(findings2)} unformatted file issue(s) flagged."
            )
            self.logger.log_event(shared_state.review_id, "TOOL_EXECUTED", agent=self.agent_name,
                                  tool="check_formatting", status=fmt_val.get("status", "SUCCESS"))

            # Update shared state with findings
            shared_state.add_findings(self.agent_name, all_findings)
            shared_state.update_agent_status(self.agent_name, "COMPLETED")
            self.logger.log_event(shared_state.review_id, "AGENT_COMPLETED", agent=self.agent_name,
                                  metadata={"findings_count": len(all_findings)})

            summary = f"Style analysis completed. Identified {len(all_findings)} style/formatting finding(s)."
            msg = ChatMessageContent(role=AuthorRole.ASSISTANT, name=self.agent_name, content=summary)
            return AgentResponseItem(message=msg, thread=ChatHistoryAgentThread())

        except Exception as e:
            err_msg = str(e)
            shared_state.update_agent_status(self.agent_name, "FAILED", error=err_msg)
            self.logger.log_event(shared_state.review_id, "AGENT_FAILED", agent=self.agent_name,
                                  status="FAILED", metadata={"error": err_msg})
            msg = ChatMessageContent(role=AuthorRole.ASSISTANT, name=self.agent_name, content=f"Style Agent failed: {err_msg}")
            return AgentResponseItem(message=msg, thread=ChatHistoryAgentThread())

    async def invoke(self, messages=None, **kwargs):
        item = await self.get_response(messages=messages, **kwargs)
        yield item

    async def invoke_stream(self, messages=None, **kwargs):
        item = await self.get_response(messages=messages, **kwargs)
        yield item
