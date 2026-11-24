"""
Fix Tools
CSE476 CA2 — Automated Code Review Board (Q14)

Tools for the Fix-Suggestion Agent (Group-of-Three Extension):
1. inspect_finding_context(source_root, finding)
2. validate_patch_proposal(patch_str, source_root, target_file)
"""

import os
import difflib
from typing import Dict, Any, Optional

from memory.shared_change_state import Finding


class FixTools:
    """Inspects finding context and safely validates generated patches."""

    @staticmethod
    def inspect_finding_context(source_root: str, finding: Finding, window: int = 10) -> Dict[str, Any]:
        """
        Reads source code surrounding the finding's file and line number.
        Returns the context lines, target line, and line numbers.
        """
        if not source_root or not finding.file:
            return {"status": "FAILED", "error": "Missing source root or file path", "lines": []}

        full_path = os.path.join(source_root, finding.file)
        if not os.path.exists(full_path):
            return {"status": "FAILED", "error": f"File does not exist: {finding.file}", "lines": []}

        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()

            target_line_idx = max(0, (finding.line or 1) - 1)
            start_idx = max(0, target_line_idx - window)
            end_idx = min(len(all_lines), target_line_idx + window + 1)

            context_lines = all_lines[start_idx:end_idx]
            
            return {
                "status": "SUCCESS",
                "file": finding.file,
                "target_line_number": finding.line or 1,
                "start_line": start_idx + 1,
                "end_line": end_idx,
                "target_line_content": all_lines[target_line_idx] if target_line_idx < len(all_lines) else "",
                "context_snippet": "".join(context_lines),
                "total_file_lines": len(all_lines)
            }
        except Exception as e:
            return {"status": "FAILED", "error": str(e), "lines": []}

    @staticmethod
    def validate_patch_proposal(patch_str: str, source_root: str, target_file: str) -> Dict[str, Any]:
        """
        Validates unified diff syntax and tests applicability against the target file
        WITHOUT modifying the original source file.
        """
        if not patch_str or not patch_str.strip():
            return {"status": "FAILED", "reason": "Empty patch proposal."}

        # Check basic unified diff headers
        lines = patch_str.strip().splitlines()
        has_header = any(l.startswith("---") for l in lines) and any(l.startswith("+++") for l in lines)
        has_hunk = any(l.startswith("@@") for l in lines)

        if not (has_header and has_hunk):
            return {
                "status": "FAILED",
                "reason": "Malformed unified diff: missing standard diff headers (---, +++, @@)."
            }

        if not source_root or not target_file:
            return {"status": "NOT_RUN", "reason": "Target file context not provided for dry-run validation."}

        full_path = os.path.join(source_root, target_file)
        if not os.path.exists(full_path):
            return {"status": "FAILED", "reason": f"Target file does not exist: {target_file}"}

        # In-memory applicability check
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                original_lines = f.readlines()

            # Verify that removed lines (-) actually exist in the original file
            removed_lines = [
                l[1:].strip() for l in lines
                if l.startswith("-") and not l.startswith("---")
            ]
            orig_text = "".join(original_lines)
            
            for rl in removed_lines:
                if rl and rl not in orig_text:
                    return {
                        "status": "FAILED",
                        "reason": f"Patch removed line not found in target file: '{rl}'"
                    }

            return {
                "status": "PASSED",
                "reason": "Unified diff syntax is valid and removed lines match target file."
            }
        except Exception as e:
            return {"status": "FAILED", "reason": f"Validation error: {e}"}
