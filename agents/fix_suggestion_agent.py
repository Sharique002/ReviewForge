"""
Fix-Suggestion Agent (Group-of-Three Extension)
CSE476 CA2 — Automated Code Review Board (Q14)

Responsibilities:
- Inspect consolidated findings post-review.
- Deterministically select exactly ONE highest-severity finding.
- Inspect the source code context around the target line.
- Formulate a concrete unified diff patch proposal.
- Validate patch syntax and dry-run applicability.
- Provide a clear, actionable explanation of the remediation.
- Never automatically modify the submitted project code.
- Update SharedChangeState.
"""

import time
from typing import Dict, Any, List, Optional

from semantic_kernel.kernel import Kernel
from semantic_kernel.functions import kernel_function
from semantic_kernel.agents import Agent, AgentResponseItem, ChatHistoryAgentThread
from semantic_kernel.contents import ChatMessageContent, AuthorRole

from memory.shared_change_state import SharedChangeState, Finding, PatchProposal, Severity
from memory.persistence import JsonlAuditLogger
from tools.fix_tools import FixTools
from ai.provider_factory import AIProviderFactory


class FixToolsPlugin:
    """Semantic Kernel Plugin exposing real patch inspection and validation tools."""

    @kernel_function(name="inspect_finding_context", description="Retrieves code lines surrounding a finding")
    def inspect_finding_context(self, source_root: str, file_path: str, line_number: int) -> Dict[str, Any]:
        dummy_f = Finding(
            finding_id="TEMP", agent="Fix-Suggestion Agent", category="Context",
            severity=Severity.INFO, title="", description="", file=file_path,
            line=line_number, evidence="", recommendation="", tool="fix-inspector"
        )
        return FixTools.inspect_finding_context(source_root, dummy_f)

    @kernel_function(name="validate_patch_proposal", description="Dry-run validates unified diff applicability")
    def validate_patch_proposal(self, patch: str, source_root: str, file_path: str) -> Dict[str, Any]:
        return FixTools.validate_patch_proposal(patch, source_root, file_path)


class FixSuggestionAgent(Agent):
    """Fix-Suggestion Agent implementing the Group-of-Three Extension."""

    def __init__(self, logger: Optional[JsonlAuditLogger] = None):
        super().__init__(name="fix_suggestion_agent")
        object.__setattr__(self, "agent_name", "Fix-Suggestion Agent")
        object.__setattr__(self, "logger", logger or JsonlAuditLogger())
        object.__setattr__(self, "ai_provider", AIProviderFactory.get_provider())
        
        # Initialize isolated Semantic Kernel and register real tools plugin
        k = Kernel()
        fix_plugin = FixToolsPlugin()
        k.add_plugin(fix_plugin, plugin_name="fix_plugin")
        object.__setattr__(self, "kernel", k)

    async def get_response(self, messages=None, shared_state: Optional[SharedChangeState] = None, **kwargs) -> AgentResponseItem:
        if not shared_state:
            msg = ChatMessageContent(role=AuthorRole.ASSISTANT, name=self.agent_name, content="Error: No SharedChangeState provided.")
            return AgentResponseItem(message=msg, thread=ChatHistoryAgentThread())

        shared_state.update_agent_status(self.agent_name, "RUNNING")
        self.logger.log_event(shared_state.review_id, "AGENT_STARTED", agent=self.agent_name)

        # Check if there are findings to fix
        if not shared_state.consolidated_findings:
            shared_state.update_agent_status(self.agent_name, "COMPLETED")
            msg = ChatMessageContent(role=AuthorRole.ASSISTANT, name=self.agent_name, content="No findings present; fix generation not needed.")
            return AgentResponseItem(message=msg, thread=ChatHistoryAgentThread())

        # Select exactly ONE highest-severity finding with deterministic tie-breaking
        target_finding = shared_state.consolidated_findings[0]
        source_root = shared_state.proposed_path or shared_state.base_path or ""
        target_file = target_finding.file or ""
        target_line = target_finding.line or 1

        try:
            # Tool 1: inspect_finding_context
            t0 = time.time()
            inspect_func = self.kernel.plugins["fix_plugin"]["inspect_finding_context"]
            ctx_res = await self.kernel.invoke(inspect_func, source_root=source_root, file_path=target_file, line_number=target_line)
            dur1 = time.time() - t0
            ctx_val = ctx_res.value if hasattr(ctx_res, "value") else ctx_res

            shared_state.add_tool_record(
                self.agent_name, "inspect_finding_context", "SUCCESS", dur1,
                f"Inspected source context for {target_finding.finding_id} in {target_file}:{target_line}."
            )
            self.logger.log_event(shared_state.review_id, "TOOL_EXECUTED", agent=self.agent_name,
                                  tool="inspect_finding_context", status="SUCCESS")

            target_line_content = ctx_val.get("target_line_content", "").strip()

            # Generate concrete unified diff proposal
            # Formulate specific remediation based on category
            explanation = ""
            patch_diff = ""

            if "eval" in target_finding.title.lower() or "eval" in target_line_content:
                explanation = "Replace dangerous dynamic 'eval()' execution with safe 'ast.literal_eval()' or explicit parsing."
                orig_line = target_line_content or "eval(user_input)"
                new_line = "ast.literal_eval(user_input)  # Remediated: safe literal evaluation"
                patch_diff = (
                    f"--- a/{target_file}\n"
                    f"+++ b/{target_file}\n"
                    f"@@ -{target_line},1 +{target_line},1 @@\n"
                    f"-{orig_line}\n"
                    f"+{new_line}\n"
                )
            elif "secret" in target_finding.title.lower() or "credential" in target_finding.title.lower():
                explanation = "Remove hardcoded secret; retrieve value dynamically from environment configuration."
                orig_line = target_line_content or "API_KEY = 'secret'"
                var_name = orig_line.split("=")[0].strip() if "=" in orig_line else "SECRET_KEY"
                new_line = f"{var_name} = os.environ.get('{var_name}', '')  # Remediated: loaded from environment"
                patch_diff = (
                    f"--- a/{target_file}\n"
                    f"+++ b/{target_file}\n"
                    f"@@ -{target_line},1 +{target_line},1 @@\n"
                    f"-{orig_line}\n"
                    f"+{new_line}\n"
                )
            else:
                # General remediation
                explanation = f"Remediate {target_finding.title}: {target_finding.recommendation}"
                orig_line = target_line_content or "# Original line"
                new_line = f"# Fix for {target_finding.finding_id}: {target_finding.title}\n{orig_line}"
                patch_diff = (
                    f"--- a/{target_file}\n"
                    f"+++ b/{target_file}\n"
                    f"@@ -{target_line},1 +{target_line},2 @@\n"
                    f"-{orig_line}\n"
                    f"+{new_line}\n"
                )

            # Tool 2: validate_patch_proposal
            t1 = time.time()
            val_func = self.kernel.plugins["fix_plugin"]["validate_patch_proposal"]
            val_res = await self.kernel.invoke(val_func, patch=patch_diff, source_root=source_root, file_path=target_file)
            dur2 = time.time() - t1
            val_data = val_res.value if hasattr(val_res, "value") else val_res

            val_status = val_data.get("status", "NOT_RUN")
            shared_state.add_tool_record(
                self.agent_name, "validate_patch_proposal", val_status, dur2,
                f"Patch dry-run validation result: {val_status}. Reason: {val_data.get('reason', '')}"
            )
            self.logger.log_event(shared_state.review_id, "TOOL_EXECUTED", agent=self.agent_name,
                                  tool="validate_patch_proposal", status=val_status)

            # Construct structured proposal
            proposal = PatchProposal(
                agent=self.agent_name,
                target_finding=target_finding.finding_id,
                file=target_file,
                severity=target_finding.severity.value,
                patch_status="PROPOSED",
                explanation=explanation,
                patch=patch_diff,
                validation=val_status
            )

            shared_state.set_patch_proposal(proposal)
            shared_state.update_agent_status(self.agent_name, "COMPLETED")
            self.logger.log_event(shared_state.review_id, "PATCH_PROPOSED", agent=self.agent_name,
                                  metadata={"target_finding": target_finding.finding_id, "validation": val_status})

            summary = (
                f"Fix Proposal Generated for {target_finding.finding_id} ({target_finding.severity.value}):\n"
                f"Target: {target_file}:{target_line}\n"
                f"Explanation: {explanation}\n"
                f"Validation: {val_status}\n"
                f"Note: Proposed patch preview only. Project files have not been modified."
            )
            msg = ChatMessageContent(role=AuthorRole.ASSISTANT, name=self.agent_name, content=summary)
            return AgentResponseItem(message=msg, thread=ChatHistoryAgentThread())

        except Exception as e:
            err_msg = str(e)
            shared_state.update_agent_status(self.agent_name, "FAILED", error=err_msg)
            self.logger.log_event(shared_state.review_id, "AGENT_FAILED", agent=self.agent_name,
                                  status="FAILED", metadata={"error": err_msg})
            msg = ChatMessageContent(role=AuthorRole.ASSISTANT, name=self.agent_name, content=f"Fix-Suggestion Agent failed: {err_msg}")
            return AgentResponseItem(message=msg, thread=ChatHistoryAgentThread())

    async def invoke(self, messages=None, **kwargs):
        item = await self.get_response(messages=messages, **kwargs)
        yield item

    async def invoke_stream(self, messages=None, **kwargs):
        item = await self.get_response(messages=messages, **kwargs)
        yield item
