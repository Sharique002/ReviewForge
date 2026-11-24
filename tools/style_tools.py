"""
Style Tools
CSE476 CA2 — Automated Code Review Board (Q14)

Tools for the Style Agent:
1. run_ruff_check(project_path, changed_files)
2. check_formatting(project_path, changed_files)
"""

import os
import sys
import json
import subprocess
from typing import Dict, Any, List

from memory.shared_change_state import Finding, Severity


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


class StyleTools:
    """Executes Ruff static analysis and formatting verification."""

    @staticmethod
    def run_ruff_check(project_path: str, changed_files: List[str]) -> Dict[str, Any]:
        """
        Executes Ruff linter on changed Python files.
        Returns structured findings with rule, severity, and recommendations.
        """
        if not os.path.exists(project_path):
            return {"status": "FAILED", "error": f"Path not found: {project_path}", "findings": []}

        # Filter only changed Python files
        py_files = [
            f for f in changed_files
            if f.endswith(".py") and os.path.exists(os.path.join(project_path, f))
        ]

        if not py_files:
            # If changed_files empty, scan all python files under project_path
            for root, _, files in os.walk(project_path):
                for file in files:
                    if file.endswith(".py"):
                        rel = _safe_relpath(os.path.join(root, file), project_path)
                        py_files.append(rel)

        if not py_files:
            return {"status": "SUCCESS", "findings": [], "message": "No Python files to lint."}

        full_paths = [os.path.join(project_path, f) for f in py_files]
        cmd = [sys.executable, "-m", "ruff", "check", "--output-format", "json"] + full_paths

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
            output = res.stdout.strip()
            ruff_records = []
            if output:
                try:
                    ruff_records = json.loads(output)
                except json.JSONDecodeError:
                    pass

            findings: List[Finding] = []
            for i, item in enumerate(ruff_records, start=1):
                raw_file = item.get("filename", "")
                rel_file = _safe_relpath(raw_file, project_path)
                code = item.get("code", "STYLE")
                msg = item.get("message", "Style or maintainability issue")
                line = item.get("location", {}).get("row", 1)
                end_line = item.get("end_location", {}).get("row", line)

                # Map Ruff rules to severity
                # E9xx, F821 (undefined names) -> HIGH/MEDIUM; standard style -> LOW/INFO
                severity = Severity.LOW
                if code.startswith("E9") or code in ("F821", "F822", "F823"):
                    severity = Severity.HIGH
                elif code.startswith("F") or code.startswith("B"):  # Pyflakes / Bugbear
                    severity = Severity.MEDIUM
                elif code.startswith("E") or code.startswith("W"):
                    severity = Severity.LOW

                finding = Finding(
                    finding_id=f"STYLE-{i:03d}",
                    agent="Style Agent",
                    category="Style & Maintainability",
                    severity=severity,
                    title=f"Ruff {code}: {msg}",
                    description=f"Rule {code} violated in {rel_file}: {msg}",
                    file=rel_file,
                    line=line,
                    end_line=end_line,
                    evidence=f"Ruff diagnostic rule {code} at line {line}",
                    recommendation=f"Update code to satisfy Ruff rule {code}. See: https://docs.astral.sh/ruff/rules/{code}/",
                    tool="ruff",
                    confidence="HIGH"
                )
                findings.append(finding)

            return {
                "status": "SUCCESS",
                "files_scanned": len(py_files),
                "violations_count": len(findings),
                "findings": findings
            }

        except subprocess.TimeoutExpired:
            return {"status": "TIMEOUT", "error": "Ruff check timed out after 60s", "findings": []}
        except Exception as e:
            return {"status": "FAILED", "error": str(e), "findings": []}

    @staticmethod
    def check_formatting(project_path: str, changed_files: List[str]) -> Dict[str, Any]:
        """
        Executes Ruff format check to detect unformatted or poorly indented code.
        """
        if not os.path.exists(project_path):
            return {"status": "FAILED", "error": f"Path not found: {project_path}", "findings": []}

        py_files = [
            f for f in changed_files
            if f.endswith(".py") and os.path.exists(os.path.join(project_path, f))
        ]

        if not py_files:
            return {"status": "SUCCESS", "findings": [], "message": "No Python files to format check."}

        full_paths = [os.path.join(project_path, f) for f in py_files]
        cmd = [sys.executable, "-m", "ruff", "format", "--check"] + full_paths

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
            unformatted_files = []
            findings = []

            # Non-zero returncode in ruff format --check indicates formatting diffs
            if res.returncode != 0:
                for line in (res.stdout + "\n" + res.stderr).splitlines():
                    if "would be reformatted" in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            raw_path = parts[1]
                            rel_p = _safe_relpath(raw_path, project_path)
                            unformatted_files.append(rel_p)

                for idx, uf in enumerate(set(unformatted_files), start=1):
                    findings.append(Finding(
                        finding_id=f"FMT-{idx:03d}",
                        agent="Style Agent",
                        category="Formatting",
                        severity=Severity.LOW,
                        title="Code formatting deviation",
                        description=f"File {uf} does not conform to standard PEP 8 formatting rules.",
                        file=uf,
                        line=1,
                        evidence="Ruff format check reported file would be reformatted.",
                        recommendation="Run 'ruff format' or format file with standard black/ruff rules.",
                        tool="ruff-format",
                        confidence="HIGH"
                    ))

            return {
                "status": "SUCCESS",
                "is_formatted": res.returncode == 0,
                "unformatted_files": unformatted_files,
                "findings": findings
            }

        except subprocess.TimeoutExpired:
            return {"status": "TIMEOUT", "error": "Ruff format check timed out", "findings": []}
        except Exception as e:
            return {"status": "FAILED", "error": str(e), "findings": []}
