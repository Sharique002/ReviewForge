"""
Reviewer Manager Tools
CSE476 CA2 — Automated Code Review Board (Q14)

Tools for the Reviewer Manager:
1. collect_agent_findings(shared_state)
2. rank_and_decide(findings, execution_metadata)
"""

from typing import Dict, Any, List, Tuple
from memory.shared_change_state import SharedChangeState, Finding, Severity


SEVERITY_ORDER = {
    Severity.CRITICAL: 1,
    Severity.HIGH: 2,
    Severity.MEDIUM: 3,
    Severity.LOW: 4,
    Severity.INFO: 5,
}


class ManagerTools:
    """Consolidation, deduplication, ranking, and deterministic policy evaluation."""

    @staticmethod
    def collect_agent_findings(shared_state: SharedChangeState) -> List[Finding]:
        """Collects all specialist findings from the shared state slots."""
        raw_findings: List[Finding] = []
        for agent_name, findings_list in shared_state.agent_findings.items():
            if agent_name in ("Diff Agent", "Style Agent", "Security Agent", "Test-Coverage Agent"):
                raw_findings.extend(findings_list)
        return raw_findings

    @staticmethod
    def deduplicate_findings(findings: List[Finding]) -> List[Finding]:
        """
        Deduplicates equivalent findings based on:
        - normalized file path
        - tool / rule ID / title
        - proximity of line numbers (+/- 3 lines)
        Preserves original agent attribution, evidence, and recommendations.
        """
        deduped: List[Finding] = []

        for f in findings:
            is_duplicate = False
            for existing in deduped:
                # Compare file
                same_file = (f.file == existing.file)
                # Compare category / tool
                same_category = (f.category == existing.category or f.tool == existing.tool)
                
                # Check line range similarity
                line_match = False
                if f.line is None and existing.line is None:
                    line_match = True
                elif f.line is not None and existing.line is not None:
                    line_match = abs(f.line - existing.line) <= 3
                
                # Title similarity
                title_match = (f.title.strip().lower() == existing.title.strip().lower())

                if same_file and (title_match or (same_category and line_match)):
                    # Merge / deduplicate: retain highest severity
                    if SEVERITY_ORDER[f.severity] < SEVERITY_ORDER[existing.severity]:
                        existing.severity = f.severity
                        existing.title = f.title
                        existing.description = f.description
                        existing.evidence = f"{existing.evidence}\n[Additional evidence from {f.agent}]: {f.evidence}"
                    is_duplicate = True
                    break

            if not is_duplicate:
                deduped.append(f)

        return deduped

    @staticmethod
    def rank_and_decide(findings: List[Finding], metadata: Dict[str, Any] = None) -> Tuple[List[Finding], str, str]:
        """
        Ranks findings by severity and evaluates deterministic merge policy:
        - CRITICAL -> REQUEST_CHANGES
        - HIGH -> REQUEST_CHANGES
        - MEDIUM -> REQUEST_CHANGES
        - LOW / INFO only -> APPROVE (with caveats if analysis incomplete)

        Returns: (ranked_findings, recommendation, rationale)
        """
        meta = metadata or {}
        deduped = ManagerTools.deduplicate_findings(findings)

        # Sort by severity rank, then file, then line
        ranked = sorted(
            deduped,
            key=lambda x: (SEVERITY_ORDER.get(x.severity, 99), str(x.file), x.line or 0)
        )

        counts = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 0,
            Severity.MEDIUM: 0,
            Severity.LOW: 0,
            Severity.INFO: 0
        }
        for f in ranked:
            counts[f.severity] = counts.get(f.severity, 0) + 1

        # Check disclosures & caveats
        failed_agents = meta.get("failed_agents", [])
        security_incomplete = meta.get("security_incomplete", False)
        tests_unexecuted = meta.get("tests_unexecuted", False)
        scanner_errors = meta.get("scanner_errors", [])

        disclosures = []
        if tests_unexecuted:
            disclosures.append("Dynamic tests were not executed (Docker sandbox offline).")
        if security_incomplete:
            disclosures.append("Security analysis was incomplete or encountered errors.")
        if failed_agents:
            disclosures.append(f"Mandatory review agent(s) failed: {', '.join(failed_agents)}.")
        if scanner_errors:
            disclosures.append(f"Scanner warnings/incomplete: {len(scanner_errors)} error(s) logged.")

        # Deterministic Policy Evaluation
        # Guard 1: Never approve if any mandatory agent failed or security analysis is incomplete
        if failed_agents or security_incomplete:
            rec = "REQUEST_CHANGES"
            failed_agents_label = ", ".join(failed_agents) if failed_agents else "Security Agent"
            rationale = (
                f"Merge blocked: Analysis incomplete due to failure in mandatory agent(s): {failed_agents_label}. "
                f"Automated approval is strictly prohibited when mandatory review analyses fail."
            )
        elif counts[Severity.CRITICAL] > 0:
            rec = "REQUEST_CHANGES"
            rationale = (
                f"Merge blocked: {counts[Severity.CRITICAL]} CRITICAL finding(s) detected. "
                f"Immediate security or critical defect remediation required."
            )
        elif counts[Severity.HIGH] > 0:
            rec = "REQUEST_CHANGES"
            rationale = (
                f"Merge blocked: {counts[Severity.HIGH]} HIGH severity finding(s) detected. "
                f"Security vulnerabilities or syntax errors must be resolved."
            )
        elif counts[Severity.MEDIUM] > 0:
            rec = "REQUEST_CHANGES"
            rationale = (
                f"Merge blocked: {counts[Severity.MEDIUM]} MEDIUM severity finding(s) detected "
                f"(missing unit tests or maintainability defects)."
            )
        else:
            rec = "APPROVE"
            rationale = (
                f"Code review approved. No blocking CRITICAL, HIGH, or MEDIUM defects found. "
                f"({counts[Severity.LOW]} low, {counts[Severity.INFO]} info)."
            )

        if disclosures:
            rationale += " Disclosures: " + " ".join(disclosures)

        return ranked, rec, rationale
