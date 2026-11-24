"""
Security Agent
CSE476 CA2 — Automated Code Review Board (Q14)

Responsibilities:
- Run Bandit AST scanner for unsafe Python code patterns.
- Run detect-secrets for exposed credentials and API keys.
- Redact all sensitive values from evidence, logs, and findings.
- Report scanner errors or incomplete security coverage.
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
from tools.security_tools import SecurityTools


class SecurityToolsPlugin:
    """Semantic Kernel Plugin exposing real Bandit and detect-secrets security scanners."""

    @kernel_function(name="run_bandit_scan", description="Executes Bandit AST vulnerability scanner")
    def run_bandit_scan(self, project_path: str, changed_files: List[str]) -> Dict[str, Any]:
        return SecurityTools.run_bandit_scan(project_path, changed_files)

    @kernel_function(name="scan_secrets", description="Scans code for exposed credentials with redaction")
    def scan_secrets(self, project_path: str, changed_files: List[str]) -> Dict[str, Any]:
        return SecurityTools.scan_secrets(project_path, changed_files)


class SecurityAgent(Agent):
    """Application Security Specialist Agent powered by Microsoft Semantic Kernel."""

    def __init__(self, logger: Optional[JsonlAuditLogger] = None):
        super().__init__(name="security_agent")
        object.__setattr__(self, "agent_name", "Security Agent")
        object.__setattr__(self, "logger", logger or JsonlAuditLogger())
        
        # Initialize isolated Semantic Kernel and register real tools plugin
        k = Kernel()
        sec_plugin = SecurityToolsPlugin()
        k.add_plugin(sec_plugin, plugin_name="security_plugin")
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
            # Tool 1: run_bandit_scan
            t0 = time.time()
            bandit_func = self.kernel.plugins["security_plugin"]["run_bandit_scan"]
            bandit_res = await self.kernel.invoke(bandit_func, project_path=target_dir, changed_files=changed_files)
            dur1 = time.time() - t0
            b_val = bandit_res.value if hasattr(bandit_res, "value") else bandit_res

            findings1 = b_val.get("findings", [])
            all_findings.extend(findings1)
            shared_state.add_tool_record(
                self.agent_name, "run_bandit_scan", b_val.get("status", "SUCCESS"), dur1,
                f"Bandit scan completed; flagged {len(findings1)} vulnerability finding(s)."
            )
            self.logger.log_event(shared_state.review_id, "TOOL_EXECUTED", agent=self.agent_name,
                                  tool="run_bandit_scan", status=b_val.get("status", "SUCCESS"))

            # Tool 2: scan_secrets
            t1 = time.time()
            secret_func = self.kernel.plugins["security_plugin"]["scan_secrets"]
            secret_res = await self.kernel.invoke(secret_func, project_path=target_dir, changed_files=changed_files)
            dur2 = time.time() - t1
            s_val = secret_res.value if hasattr(secret_res, "value") else secret_res

            findings2 = s_val.get("findings", [])
            all_findings.extend(findings2)
            shared_state.add_tool_record(
                self.agent_name, "scan_secrets", s_val.get("status", "SUCCESS"), dur2,
                f"Secret scanner completed; detected {len(findings2)} potential credential leakage issue(s)."
            )
            self.logger.log_event(shared_state.review_id, "TOOL_EXECUTED", agent=self.agent_name,
                                  tool="scan_secrets", status=s_val.get("status", "SUCCESS"))

            # Update shared state with findings
            shared_state.add_findings(self.agent_name, all_findings)
            shared_state.update_agent_status(self.agent_name, "COMPLETED")
            self.logger.log_event(shared_state.review_id, "AGENT_COMPLETED", agent=self.agent_name,
                                  metadata={"findings_count": len(all_findings)})

            summary = f"Security scan completed. Identified {len(all_findings)} security/credential finding(s)."
            msg = ChatMessageContent(role=AuthorRole.ASSISTANT, name=self.agent_name, content=summary)
            return AgentResponseItem(message=msg, thread=ChatHistoryAgentThread())

        except Exception as e:
            err_msg = str(e)
            shared_state.update_agent_status(self.agent_name, "FAILED", error=err_msg)
            self.logger.log_event(shared_state.review_id, "AGENT_FAILED", agent=self.agent_name,
                                  status="FAILED", metadata={"error": err_msg})
            msg = ChatMessageContent(role=AuthorRole.ASSISTANT, name=self.agent_name, content=f"Security Agent failed: {err_msg}")
            return AgentResponseItem(message=msg, thread=ChatHistoryAgentThread())

    async def invoke(self, messages=None, **kwargs):
        item = await self.get_response(messages=messages, **kwargs)
        yield item

    async def invoke_stream(self, messages=None, **kwargs):
        item = await self.get_response(messages=messages, **kwargs)
        yield item
