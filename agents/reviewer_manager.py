"""
Reviewer Manager
CSE476 CA2 — Automated Code Review Board (Q14)

Responsibilities:
- Coordinate the review fan-in.
- Collect findings from all specialist agents.
- Deduplicate equivalent findings across agents.
- Rank findings deterministically by severity.
- Evaluate deterministic merge policy (APPROVE vs REQUEST_CHANGES).
- Disclose unexecuted tests and incomplete analyses.
- Update SharedChangeState with final consolidated findings and decision.
"""

import time
from typing import Dict, Any, List, Optional, Tuple

from semantic_kernel.kernel import Kernel
from semantic_kernel.functions import kernel_function
from semantic_kernel.agents import Agent, AgentResponseItem, ChatHistoryAgentThread
from semantic_kernel.contents import ChatMessageContent, AuthorRole

from memory.shared_change_state import SharedChangeState, Finding, Severity
from memory.persistence import JsonlAuditLogger
from tools.manager_tools import ManagerTools
from ai.provider_factory import AIProviderFactory


class ManagerToolsPlugin:
    """Semantic Kernel Plugin exposing real Reviewer Manager consolidation tools."""

    @kernel_function(name="collect_agent_findings", description="Collects findings from specialist agent slots")
    def collect_agent_findings(self, shared_state: SharedChangeState) -> List[Finding]:
        return ManagerTools.collect_agent_findings(shared_state)

    @kernel_function(name="rank_and_decide", description="Deduplicates, ranks by severity, and decides merge recommendation")
    def rank_and_decide(self, findings: List[Finding], metadata: Dict[str, Any] = None) -> Tuple[List[Finding], str, str]:
        return ManagerTools.rank_and_decide(findings, metadata)


class ReviewerManager(Agent):
    """Reviewer Manager Coordinator Agent powered by Microsoft Semantic Kernel."""

    def __init__(self, logger: Optional[JsonlAuditLogger] = None):
        super().__init__(name="reviewer_manager")
        object.__setattr__(self, "agent_name", "Reviewer Manager")
        object.__setattr__(self, "logger", logger or JsonlAuditLogger())
        object.__setattr__(self, "ai_provider", AIProviderFactory.get_provider())
        
        # Initialize isolated Semantic Kernel and register real tools plugin
        k = Kernel()
        mgr_plugin = ManagerToolsPlugin()
        k.add_plugin(mgr_plugin, plugin_name="manager_plugin")
        object.__setattr__(self, "kernel", k)

    async def get_response(self, messages=None, shared_state: Optional[SharedChangeState] = None, **kwargs) -> AgentResponseItem:
        if not shared_state:
            msg = ChatMessageContent(role=AuthorRole.ASSISTANT, name=self.agent_name, content="Error: No SharedChangeState provided.")
            return AgentResponseItem(message=msg, thread=ChatHistoryAgentThread())

        shared_state.update_agent_status(self.agent_name, "RUNNING")
        self.logger.log_event(shared_state.review_id, "FAN_IN_STARTED", agent=self.agent_name)

        try:
            # Tool 1: collect_agent_findings
            t0 = time.time()
            collect_func = self.kernel.plugins["manager_plugin"]["collect_agent_findings"]
            coll_res = await self.kernel.invoke(collect_func, shared_state=shared_state)
            dur1 = time.time() - t0
            raw_findings = coll_res.value if hasattr(coll_res, "value") else coll_res

            shared_state.add_tool_record(
                self.agent_name, "collect_agent_findings", "SUCCESS", dur1,
                f"Collected {len(raw_findings)} raw findings across specialist agents."
            )
            self.logger.log_event(shared_state.review_id, "TOOL_EXECUTED", agent=self.agent_name,
                                  tool="collect_agent_findings", status="SUCCESS")

            # Check execution disclosures (e.g. tests unexecuted, failed agents, security status)
            failed_agents = [
                name for name, rec in shared_state.agent_statuses.items()
                if rec.status == "FAILED" and name in ("Diff Agent", "Style Agent", "Security Agent", "Test-Coverage Agent")
            ]
            sec_record = shared_state.agent_statuses.get("Security Agent")
            security_incomplete = (sec_record is None or sec_record.status != "COMPLETED")

            tests_unexecuted = True  # Default cautious
            for tr in shared_state.tool_records:
                if tr.tool_name == "run_pytest_coverage" and tr.status == "SUCCESS":
                    tests_unexecuted = False

            meta = {
                "failed_agents": failed_agents,
                "has_agent_failures": len(failed_agents) > 0,
                "security_incomplete": security_incomplete,
                "tests_unexecuted": tests_unexecuted,
                "scanner_errors": [e["error"] for e in shared_state.error_records]
            }

            # Tool 2: rank_and_decide
            t1 = time.time()
            decide_func = self.kernel.plugins["manager_plugin"]["rank_and_decide"]
            dec_res = await self.kernel.invoke(decide_func, findings=raw_findings, metadata=meta)
            dur2 = time.time() - t1
            ranked_findings, decision, rationale = dec_res.value if hasattr(dec_res, "value") else dec_res

            shared_state.add_tool_record(
                self.agent_name, "rank_and_decide", "SUCCESS", dur2,
                f"Deduplicated to {len(ranked_findings)} findings. Recommendation: {decision}."
            )
            self.logger.log_event(shared_state.review_id, "TOOL_EXECUTED", agent=self.agent_name,
                                  tool="rank_and_decide", status="SUCCESS")
            self.logger.log_event(shared_state.review_id, "FINDINGS_DEDUPLICATED", agent=self.agent_name,
                                  metadata={"before": len(raw_findings), "after": len(ranked_findings)})

            # Update shared state with final consolidated findings and decision
            shared_state.set_consolidated_findings(ranked_findings, decision, rationale)
            shared_state.update_agent_status(self.agent_name, "COMPLETED")
            self.logger.log_event(shared_state.review_id, "DECISION_CREATED", agent=self.agent_name,
                                  metadata={"recommendation": decision, "rationale": rationale})

            summary = (
                f"Consolidated Review Complete. Decision: {decision}.\n"
                f"Rationale: {rationale}\n"
                f"Total Deduplicated Findings: {len(ranked_findings)} "
                f"({shared_state.severity_distribution.get('CRITICAL', 0)} CRITICAL, "
                f"{shared_state.severity_distribution.get('HIGH', 0)} HIGH, "
                f"{shared_state.severity_distribution.get('MEDIUM', 0)} MEDIUM, "
                f"{shared_state.severity_distribution.get('LOW', 0)} LOW, "
                f"{shared_state.severity_distribution.get('INFO', 0)} INFO)."
            )

            msg = ChatMessageContent(role=AuthorRole.ASSISTANT, name=self.agent_name, content=summary)
            return AgentResponseItem(message=msg, thread=ChatHistoryAgentThread())

        except Exception as e:
            err_msg = str(e)
            shared_state.update_agent_status(self.agent_name, "FAILED", error=err_msg)
            self.logger.log_event(shared_state.review_id, "AGENT_FAILED", agent=self.agent_name,
                                  status="FAILED", metadata={"error": err_msg})
            msg = ChatMessageContent(role=AuthorRole.ASSISTANT, name=self.agent_name, content=f"Reviewer Manager failed: {err_msg}")
            return AgentResponseItem(message=msg, thread=ChatHistoryAgentThread())

    async def invoke(self, messages=None, **kwargs):
        item = await self.get_response(messages=messages, **kwargs)
        yield item

    async def invoke_stream(self, messages=None, **kwargs):
        item = await self.get_response(messages=messages, **kwargs)
        yield item
