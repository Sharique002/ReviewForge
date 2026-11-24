"""
Diff Agent
CSE476 CA2 — Automated Code Review Board (Q14)

Responsibilities:
- Compare source snapshots.
- Identify changed, added, modified, deleted, and renamed files.
- Generate unified diffs.
- Calculate change statistics.
- Update SharedChangeState.
"""

import time
from typing import Dict, Any, List, Optional

from semantic_kernel.kernel import Kernel
from semantic_kernel.functions import kernel_function
from semantic_kernel.agents import Agent, AgentResponseItem, ChatHistoryAgentThread
from semantic_kernel.contents import ChatMessageContent, AuthorRole

from memory.shared_change_state import SharedChangeState, ChangeStatistics
from memory.persistence import JsonlAuditLogger
from tools.diff_tools import DiffTools


class DiffToolsPlugin:
    """Semantic Kernel Plugin exposing real diff calculation tools."""

    @kernel_function(name="identify_changed_files", description="Discovers modified, added, deleted, renamed files")
    def identify_changed_files(self, base_path: str, proposed_path: str) -> Dict[str, Any]:
        return DiffTools.identify_changed_files(base_path, proposed_path)

    @kernel_function(name="extract_file_diff", description="Generates unified diff for a modified file")
    def extract_file_diff(self, base_path: str, proposed_path: str, file_path: str) -> Dict[str, Any]:
        return DiffTools.extract_file_diff(base_path, proposed_path, file_path)


class DiffAgent(Agent):
    """Diff Specialist Agent powered by Microsoft Semantic Kernel."""

    def __init__(self, logger: Optional[JsonlAuditLogger] = None):
        super().__init__(name="diff_agent")
        object.__setattr__(self, "agent_name", "Diff Agent")
        object.__setattr__(self, "logger", logger or JsonlAuditLogger())
        
        # Initialize isolated Semantic Kernel and register real tools plugin
        k = Kernel()
        diff_plugin = DiffToolsPlugin()
        k.add_plugin(diff_plugin, plugin_name="diff_plugin")
        object.__setattr__(self, "kernel", k)

    async def get_response(self, messages=None, shared_state: Optional[SharedChangeState] = None, **kwargs) -> AgentResponseItem:
        if not shared_state:
            msg = ChatMessageContent(role=AuthorRole.ASSISTANT, name=self.agent_name, content="Error: No SharedChangeState provided.")
            return AgentResponseItem(message=msg, thread=ChatHistoryAgentThread())

        shared_state.update_agent_status(self.agent_name, "RUNNING")
        self.logger.log_event(shared_state.review_id, "AGENT_STARTED", agent=self.agent_name)

        try:
            base_p = shared_state.base_path or ""
            prop_p = shared_state.proposed_path or ""

            # Tool 1: identify_changed_files
            t0 = time.time()
            id_func = self.kernel.plugins["diff_plugin"]["identify_changed_files"]
            change_data = await self.kernel.invoke(id_func, base_path=base_p, proposed_path=prop_p)
            dur1 = time.time() - t0
            changes = change_data.value if hasattr(change_data, "value") else change_data

            shared_state.add_tool_record(
                self.agent_name, "identify_changed_files", "SUCCESS", dur1,
                f"Discovered {len(changes['touched_files'])} touched file(s)."
            )
            self.logger.log_event(shared_state.review_id, "TOOL_EXECUTED", agent=self.agent_name,
                                  tool="identify_changed_files", status="SUCCESS")

            # Tool 2: extract_file_diff for each touched file
            diff_func = self.kernel.plugins["diff_plugin"]["extract_file_diff"]
            t1 = time.time()
            unified_diffs = {}
            total_added = 0
            total_deleted = 0

            for f in changes["touched_files"]:
                diff_res = await self.kernel.invoke(diff_func, base_path=base_p, proposed_path=prop_p, file_path=f)
                d_val = diff_res.value if hasattr(diff_res, "value") else diff_res
                unified_diffs[f] = d_val.get("unified_diff", "")
                total_added += d_val.get("lines_added", 0)
                total_deleted += d_val.get("lines_deleted", 0)

            dur2 = time.time() - t1
            shared_state.add_tool_record(
                self.agent_name, "extract_file_diff", "SUCCESS", dur2,
                f"Calculated diffs: +{total_added} / -{total_deleted} lines across {len(unified_diffs)} file(s)."
            )
            self.logger.log_event(shared_state.review_id, "TOOL_EXECUTED", agent=self.agent_name,
                                  tool="extract_file_diff", status="SUCCESS")

            stats = ChangeStatistics(
                files_added=changes["added"],
                files_modified=changes["modified"],
                files_deleted=changes["deleted"],
                files_renamed=changes["renamed"],
                total_lines_added=total_added,
                total_lines_deleted=total_deleted
            )

            summary = (
                f"Change Summary: {len(changes['touched_files'])} file(s) touched "
                f"({len(changes['added'])} added, {len(changes['modified'])} modified, "
                f"{len(changes['deleted'])} deleted, {len(changes['renamed'])} renamed). "
                f"+{total_added} / -{total_deleted} lines."
            )

            # Update shared state
            shared_state.set_diff_data(changes["touched_files"], stats, summary, unified_diffs)
            shared_state.update_agent_status(self.agent_name, "COMPLETED")
            self.logger.log_event(shared_state.review_id, "AGENT_COMPLETED", agent=self.agent_name)

            msg = ChatMessageContent(role=AuthorRole.ASSISTANT, name=self.agent_name, content=summary)
            return AgentResponseItem(message=msg, thread=ChatHistoryAgentThread())

        except Exception as e:
            err_msg = str(e)
            shared_state.update_agent_status(self.agent_name, "FAILED", error=err_msg)
            self.logger.log_event(shared_state.review_id, "AGENT_FAILED", agent=self.agent_name,
                                  status="FAILED", metadata={"error": err_msg})
            msg = ChatMessageContent(role=AuthorRole.ASSISTANT, name=self.agent_name, content=f"Diff Agent failed: {err_msg}")
            return AgentResponseItem(message=msg, thread=ChatHistoryAgentThread())

    async def invoke(self, messages=None, **kwargs):
        item = await self.get_response(messages=messages, **kwargs)
        yield item

    async def invoke_stream(self, messages=None, **kwargs):
        item = await self.get_response(messages=messages, **kwargs)
        yield item
