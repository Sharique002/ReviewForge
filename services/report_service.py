"""
Review Report Generator Service
CSE476 CA2 — Automated Code Review Board (Q14)
"""

from typing import Dict, Any, List
from memory.shared_change_state import SharedChangeState


class ReportService:
    """Generates structured Markdown and JSON reports from completed reviews."""

    @staticmethod
    def generate_markdown_report(state: SharedChangeState) -> str:
        """Produces an enterprise-grade Markdown review summary."""
        data = state.to_dict()
        stats = data.get("change_stats", {})
        findings = data.get("findings", [])
        decision = data.get("recommendation", "PENDING")
        rationale = data.get("recommendation_rationale", "")

        lines = [
            f"# AUTOMATED CODE REVIEW REPORT: {data['project_name']}",
            f"**Review ID:** `{data['review_id']}`  ",
            f"**Mode:** `{data['review_mode']}`  ",
            f"**Merge Recommendation:** **{decision}**  ",
            "",
            "## 1. Executive Summary & Merge Decision",
            f"> **Decision Rationale:** {rationale}",
            "",
            "### Severity Distribution",
            f"- **CRITICAL:** {data['severity_distribution'].get('CRITICAL', 0)}",
            f"- **HIGH:** {data['severity_distribution'].get('HIGH', 0)}",
            f"- **MEDIUM:** {data['severity_distribution'].get('MEDIUM', 0)}",
            f"- **LOW:** {data['severity_distribution'].get('LOW', 0)}",
            f"- **INFO:** {data['severity_distribution'].get('INFO', 0)}",
            "",
            "## 2. Code Change Statistics",
            f"- **Files Touched:** {len(data.get('changed_files', []))}",
            f"- **Files Added:** {len(stats.get('files_added', []))}",
            f"- **Files Modified:** {len(stats.get('files_modified', []))}",
            f"- **Files Deleted:** {len(stats.get('files_deleted', []))}",
            f"- **Lines Added:** +{stats.get('total_lines_added', 0)}",
            f"- **Lines Deleted:** -{stats.get('total_lines_deleted', 0)}",
            "",
            "```diff",
            f"{data.get('diff_summary', 'No diff summary')}",
            "```",
            "",
            "## 3. Consolidated Findings",
        ]

        if not findings:
            lines.append("*No issues or security vulnerabilities identified.*")
        else:
            lines.append("| ID | Severity | Category | File | Line | Agent | Tool | Description |")
            lines.append("|---|---|---|---|---|---|---|---|")
            for f in findings:
                f_id = f.get("finding_id", "")
                sev = f.get("severity", "")
                cat = f.get("category", "")
                file_p = f.get("file") or "-"
                line_p = str(f.get("line") or "-")
                agent = f.get("agent", "")
                tool = f.get("tool", "")
                desc = f.get("title", "").replace("|", "-")
                lines.append(f"| `{f_id}` | **{sev}** | {cat} | `{file_p}` | {line_p} | {agent} | `{tool}` | {desc} |")

        # Fix Suggestion section
        lines.append("")
        lines.append("## 4. Fix Suggestion (Group-of-Three Extension)")
        patch_info = data.get("patch_proposal")
        if patch_info:
            lines.extend([
                f"**Target Finding:** `{patch_info.get('target_finding')}`  ",
                f"**File:** `{patch_info.get('file')}`  ",
                f"**Severity:** `{patch_info.get('severity')}`  ",
                f"**Validation Status:** `{patch_info.get('validation')}`  ",
                f"**Explanation:** {patch_info.get('explanation')}  ",
                "",
                "```diff",
                patch_info.get("patch", "No patch available"),
                "```",
                "> *Note: Patch proposal only. Original project files were not modified.*",
            ])
        else:
            lines.append("*No fix proposal generated.*")

        return "\n".join(lines)
