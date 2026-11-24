"""
Security Tools
CSE476 CA2 — Automated Code Review Board (Q14)

Tools for the Security Agent:
1. run_bandit_scan(project_path, changed_files)
2. scan_secrets(project_path, changed_files)
"""

import os
import sys
import json
import subprocess
from typing import Dict, Any, List

from memory.shared_change_state import Finding, Severity
from memory.persistence import redact_sensitive_text


def _safe_relpath(path: str, start: str) -> str:
    """Calculates relative path safely across different Windows drive mounts."""
    if not path:
        return "unknown"
    try:
        drive_path = os.path.splitdrive(os.path.abspath(path))[0].lower()
        drive_start = os.path.splitdrive(os.path.abspath(start))[0].lower()
        if drive_path == drive_start:
            return os.path.relpath(path, start).replace("\\", "/")
        return os.path.basename(path)
    except Exception:
        return os.path.basename(path)


class SecurityTools:
    """Executes Bandit AST scanning and detect-secrets credential analysis."""

    @staticmethod
    def run_bandit_scan(project_path: str, changed_files: List[str]) -> Dict[str, Any]:
        """
        Runs Bandit AST security scanner against Python files.
        Maps issues to CRITICAL, HIGH, MEDIUM, LOW severity.
        """
        if not os.path.exists(project_path):
            return {"status": "FAILED", "error": f"Path not found: {project_path}", "findings": []}

        py_files = [
            f for f in changed_files
            if f.endswith(".py") and os.path.exists(os.path.join(project_path, f))
        ]

        # Fallback to scanning project directory if changed_files empty
        scan_target = [os.path.join(project_path, f) for f in py_files] if py_files else [project_path]

        cmd = [sys.executable, "-m", "bandit", "-f", "json", "-q"] + scan_target

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=90, check=False)
            output = res.stdout.strip()
            bandit_data = {}
            if output:
                try:
                    bandit_data = json.loads(output)
                except json.JSONDecodeError:
                    pass

            results = bandit_data.get("results", [])
            findings: List[Finding] = []

            for i, item in enumerate(results, start=1):
                raw_file = item.get("filename", "")
                rel_file = _safe_relpath(raw_file, project_path)
                test_id = item.get("test_id", "B000")
                issue_text = item.get("issue_text", "Security issue detected")
                raw_severity = item.get("issue_severity", "MEDIUM").upper()
                line = item.get("line_number", 1)
                code_snippet = item.get("code", "")

                # Map Bandit severity
                severity = Severity.MEDIUM
                if raw_severity == "HIGH":
                    severity = Severity.HIGH
                elif raw_severity == "LOW":
                    severity = Severity.LOW

                # Detect especially dangerous patterns (eval, exec, sql injection) -> promote to CRITICAL
                if test_id in ("B307", "B102", "B608"):  # eval, exec, hardcoded sql
                    severity = Severity.CRITICAL

                # Sanitize evidence
                clean_snippet = redact_sensitive_text(code_snippet.strip())
                clean_text = redact_sensitive_text(issue_text)

                finding = Finding(
                    finding_id=f"SEC-BND-{i:03d}",
                    agent="Security Agent",
                    category="Application Security",
                    severity=severity,
                    title=f"Bandit {test_id}: {clean_text}",
                    description=f"Potential vulnerability in {rel_file}:{line}. {clean_text}",
                    file=rel_file,
                    line=line,
                    evidence=clean_snippet or f"Flagged by rule {test_id}",
                    recommendation=item.get("more_info", "Review and remediate according to secure coding standards."),
                    tool="bandit",
                    confidence=item.get("issue_confidence", "HIGH")
                )
                findings.append(finding)

            return {
                "status": "SUCCESS",
                "scanned_targets": len(scan_target),
                "issues_count": len(findings),
                "findings": findings
            }

        except subprocess.TimeoutExpired:
            return {"status": "TIMEOUT", "error": "Bandit scan timed out after 90s", "findings": []}
        except Exception as e:
            return {"status": "FAILED", "error": str(e), "findings": []}

    @staticmethod
    def scan_secrets(project_path: str, changed_files: List[str]) -> Dict[str, Any]:
        """
        Runs detect-secrets scanner to locate exposed credentials, tokens, and private keys.
        Redacts all sensitive values before returning findings.
        """
        if not os.path.exists(project_path):
            return {"status": "FAILED", "error": f"Path not found: {project_path}", "findings": []}

        try:
            cmd = [sys.executable, "-m", "detect_secrets", "scan", "--all-files", project_path]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
            
            output = res.stdout.strip()
            secret_data = {}
            if output:
                try:
                    secret_data = json.loads(output)
                except json.JSONDecodeError:
                    pass

            findings: List[Finding] = []
            files_dict = secret_data.get("results", {})

            counter = 1
            for raw_filepath, secrets_list in files_dict.items():
                rel_file = _safe_relpath(raw_filepath, project_path)
                # If changed_files provided, only report secrets touching changed files
                if changed_files and rel_file not in changed_files:
                    continue

                for secret_item in secrets_list:
                    secret_type = secret_item.get("type", "Secret Keyword")
                    line_no = secret_item.get("line_number", 1)

                    finding = Finding(
                        finding_id=f"SEC-KEY-{counter:03d}",
                        agent="Security Agent",
                        category="Secret Detection",
                        severity=Severity.HIGH,  # Secrets are high or critical
                        title=f"Potential Hardcoded Secret: {secret_type}",
                        description=f"A potential {secret_type} was identified in {rel_file} at line {line_no}.",
                        file=rel_file,
                        line=line_no,
                        evidence=f"Detected pattern: {secret_type} (value redacted for security)",
                        recommendation="Remove hardcoded secret from repository. Load from environment variable or secure vault.",
                        tool="detect-secrets",
                        confidence="HIGH"
                    )
                    findings.append(finding)
                    counter += 1

            return {
                "status": "SUCCESS",
                "secrets_detected": len(findings),
                "findings": findings
            }

        except subprocess.TimeoutExpired:
            return {"status": "TIMEOUT", "error": "Secret detection scan timed out", "findings": []}
        except Exception as e:
            return {"status": "FAILED", "error": str(e), "findings": []}
