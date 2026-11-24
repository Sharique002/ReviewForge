# REVIEWFORGE: AUTOMATED CODE REVIEW BOARD (Q14)
**CSE476 CA2 Multi-Agent Architecture | Python & Microsoft Semantic Kernel**  
**Submission Category:** Group-of-Three Extension (6 Autonomous Agents Implemented)  

---

## 1. Project Overview & Objective
**ReviewForge** is an enterprise-grade automated multi-agent code review system built for CSE476 CA2 Question 14. Given an uploaded code change archive (`.zip`) containing baseline (`base/`) and modified (`proposed/`) snapshots, ReviewForge orchestrates six autonomous agents to perform concurrent static, security, style, and test coverage analyses, consolidate findings, compute a deterministic merge recommendation (`APPROVE` vs `REQUEST_CHANGES`), and propose an automated dry-run remediation patch.

---

## 2. Multi-Agent Roster & Real Python Tools
Every agent is a dedicated module inheriting from Microsoft Semantic Kernel's `Agent` abstraction with its own `Kernel`, registering a plugin with at least two real Python tools:

| Agent Name | Architectural Role | Minimum Real Python Tools Invoked | Primary Responsibility |
|---|---|---|---|
| **Diff Agent** | Specialist (Fan-Out) | `identify_changed_files`, `extract_file_diff` | Discovers touched, added, modified, deleted, and renamed files; generates unified diffs. |
| **Style Agent** | Specialist (Fan-Out) | `run_ruff_check`, `check_formatting` | Executes Ruff static analysis and PEP 8 formatting validation on changed files. |
| **Security Agent** | Specialist (Fan-Out) | `run_bandit_scan`, `scan_secrets` | Executes Bandit AST vulnerability scanning and detect-secrets credential scanning with auto-redaction. |
| **Test-Coverage Agent** | Specialist (Fan-Out) | `discover_test_files`, `run_pytest_coverage` | Discovers unit tests, identifies untested changes, safely executes tests in isolated Docker containers (or flags `NOT_RUN`). |
| **Reviewer Manager** | Coordinator (Fan-In) | `collect_agent_findings`, `rank_and_decide` | Collects specialist outputs, deduplicates findings, ranks by severity, enforces deterministic merge policy. |
| **Fix-Suggestion Agent** | Extension (Post-Review) | `inspect_finding_context`, `validate_patch_proposal` | Targets single highest-severity finding, inspects context, formulates unified diff patch, verifies dry-run applicability. |

---

## 3. Architecture: Fan-Out / Fan-In Coordination
ReviewForge implements an asynchronous fan-out / fan-in architecture:
```text
Upload ZIP -> ArchiveValidator -> ExtractionService -> Semantic Kernel Fan-Out
                                                          |
     +-------------------+--------------------+-----------+-------------------+
     |                   |                    |                               |
     v                   v                    v                               v
[Diff Agent]       [Style Agent]      [Security Agent]             [Test-Coverage Agent]
     |                   |                    |                               |
     +-------------------+--------------------+-------------------------------+
                                 |
                                 v
                       SHARED CHANGE STATE (Thread-Safe Blackboard)
                                 |
                                 v
                      [Reviewer Manager] (Fan-In Consolidation & Deduplication)
                                 |
                                 v
                     [Fix-Suggestion Agent] (Single Highest-Severity Patch)
                                 |
                       PERSISTENCE & DASHBOARD (SQLite + run_log.jsonl)
```
- **Concurrency & Isolation:** Specialist agents run concurrently via `asyncio.gather` with exception isolation; an individual agent failure does not corrupt other agents.
- **Shared Memory:** A centralized `SharedChangeState` object with thread-safe locks maintains dedicated agent slots, diff statistics, consolidated findings, and audit traces.
- **Deterministic Policy:** `CRITICAL`, `HIGH`, or `MEDIUM` findings deterministically trigger `REQUEST_CHANGES`. `LOW` and `INFO` permit `APPROVE`.

---

## 4. Setup & Quickstart Instructions

### Prerequisites
- Python 3.11+
- Windows 11 / WSL2 / Linux

### Installation
```bash
# 1. Clone repository and install pinned dependencies
pip install -r requirements.txt

# 2. Verify Semantic Kernel Compatibility (10/10 Proof)
python -m pytest tests/test_semantic_kernel_compatibility.py -v

# 3. Execute Complete Automated Test Suite (27/27 Tests)
python -m pytest -v

# 4. Launch Web Application & Dashboard
python run.py --port 5000
```
Access the dashboard at `http://127.0.0.1:5000`.

---

## 5. Failure Scenario & Resiliency Handling
**Scenario: Path Traversal & Malicious Archive Injection**
- **Threat:** An adversary uploads a malicious ZIP containing relative directory traversal paths (`../../etc/passwd` or `../evil.py`) designed to overwrite system files.
- **Handling:** `ArchiveValidator` inspects all member entries before extraction. It detects directory traversal, absolute paths, duplicate archive names, symlinks, or suspicious compression ratios (>100:1). Extraction is instantly aborted, an `ArchiveValidationError` is raised, a `400 Bad Request` is returned to the client, and a structured tamper-evident event is committed to `logs/run_log.jsonl`. No untrusted files touch the host filesystem.
