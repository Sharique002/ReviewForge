# IMPLEMENTATION PLAN: AUTOMATED CODE REVIEW BOARD (Q14)

**Project:** CSE476 CA2 — Automated Code Review Board  
**Target Completion:** Fully Functional, Multi-Agent System with Group-of-Three Extension (6 Agents)  

---

## 1. Phased Architecture & Execution Order

### Phase 1: Semantic Kernel Compatibility Proof
- Inspect installed `semantic_kernel` (v1.47.0) architecture: `Kernel`, `KernelPlugin`, `kernel_function`, `KernelArguments`.
- Construct a 4-agent concurrent orchestration prototype using real Kernel instances and plugin functions.
- Verify Ollama / local connector patterns and graceful offline fallbacks.
- Implement `tests/test_semantic_kernel_compatibility.py` and `docs/SEMANTIC_KERNEL_COMPATIBILITY.md`.
- Ensure tests pass with 100% green status before proceeding.

### Phase 2: Input Contract & Archive Security
- Input: `.zip` archives containing `base/` and `proposed/` snapshot folders + optional `review-manifest.json`.
- Implement `services/archive_validator.py` with strict security guardrails:
  - Max archive size (e.g., 25MB), max extracted size (e.g., 100MB), max file count (1000).
  - Path traversal checks (prevent `../` or absolute paths).
  - Symlink and hard link rejection.
  - Safe extraction into isolated ephemeral temp directories.
- Implement `services/extraction_service.py` with full snapshot verification.
- Unit and security tests for archive validation and malicious ZIP fixtures.

### Phase 3: Shared Change State & Real Python Tools
- Implement `memory/shared_change_state.py`:
  - Pydantic models for `Finding`, `AgentExecutionRecord`, `ToolExecutionRecord`, `SnapshotInfo`, `ChangeStatistics`, and `SharedChangeState`.
  - Severity enum: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`.
  - Concurrency-safe, thread-safe update methods.
- Implement real tools in `tools/`:
  - `diff_tools.py`: `extract_file_diff`, `identify_changed_files` (using `difflib` and filesystem tree analysis).
  - `style_tools.py`: `run_ruff_check`, `check_formatting`.
  - `security_tools.py`: `run_bandit_scan`, `scan_secrets` (detect-secrets integration + automatic redaction).
  - `testing_tools.py`: `discover_test_files`, `run_pytest_coverage` (with safe sandbox gating).
  - `manager_tools.py`: `collect_agent_findings`, `rank_and_decide`.
  - `fix_tools.py`: `inspect_finding_context`, `validate_patch_proposal`.
- Comprehensive test coverage for all tool modules.

### Phase 4: Specialist Agents
- Implement 4 specialist agent classes with Semantic Kernel plugin registration:
  - `agents/diff_agent.py`: Diff Agent (invokes at least 2 real diff tools).
  - `agents/style_agent.py`: Style Agent (invokes at least 2 real style tools).
  - `agents/security_agent.py`: Security Agent (invokes at least 2 real security tools).
  - `agents/test_coverage_agent.py`: Test-Coverage Agent (invokes at least 2 real testing tools).
- Verify each agent properly reads from and updates `SharedChangeState`.

### Phase 5: Fan-Out / Fan-In Orchestration
- Implement `orchestration/fanout_fanin.py` and `orchestration/workflow.py`:
  - Fan-out: Concurrently schedule and execute the 4 specialist agents via `asyncio.gather`.
  - Fault tolerance: Exception isolation ensures failure of one agent does not cancel or corrupt others.
  - Fan-in: Await specialist completion, record timestamps, transitions, and trace events.

### Phase 6: Reviewer Manager
- Implement `agents/reviewer_manager.py`:
  - Collects all findings across specialist slots in `SharedChangeState`.
  - Validates finding schemas.
  - Deduplicates overlapping findings (by normalized path, rule ID, line range, similarity).
  - Deterministic decision policy:
    - CRITICAL / HIGH / MEDIUM -> `REQUEST_CHANGES`
    - LOW / INFO only -> `APPROVE` (unless tests failed or security incomplete)
  - Explicit disclosure of missing test runs, scanner failures, or incomplete analyses.

### Phase 7: Fix-Suggestion Agent (Group-of-Three Extension)
- Implement `agents/fix_suggestion_agent.py`:
  - Triggered post-consolidation.
  - Selects the single highest-severity finding (deterministic tie-breaking).
  - Inspects source context around the target line.
  - Formulates a concrete unified diff patch proposal and rationale.
  - Validates patch syntax and applicability (via `git apply --check` or Python parsing).
  - Strictly non-mutating (never modifies submitted project).

### Phase 8: Safe Execution & Docker Sandbox
- Implement `services/sandbox_service.py`:
  - Checks Docker engine availability.
  - When Docker is active: runs tests in an isolated ephemeral container (non-root, network disabled, read-only code mount, memory/CPU limits).
  - When Docker is unavailable: marks tests as `NOT_RUN` with explicit security explanation. Prevents host compromise.

### Phase 9: Flask Backend, SQLite Persistence & JSONL Audit Log
- Implement `backend/app.py`, `backend/routes.py`, `backend/schemas.py`:
  - Endpoints: `POST /api/reviews`, `GET /api/reviews/<id>`, `GET /api/reviews/<id>/status`, `GET /api/reviews/<id>/report`, `GET /api/reviews/<id>/trace`, `GET /api/providers/status`, `GET /api/agents`.
- SQLite persistence in `data/reviews.db`:
  - Tables for reviews, findings, agent executions, and patch suggestions.
- Append-only JSONL log in `logs/run_log.jsonl`:
  - Structured event schema: `REVIEW_CREATED`, `AGENT_STARTED`, `TOOL_EXECUTED`, `FINDING_CREATED`, etc.
  - Redaction of sensitive values prior to emission.

### Phase 10: Professional Enterprise Web Dashboard
- Implement modern, clean dark-theme dashboard (`static/index.html`, `static/css/styles.css`, `static/js/app.js`):
  - Overview cards, ZIP drag-and-drop upload, Review history.
  - Agent Activity Cards (6 agents with status, tools invoked, findings count).
  - Severity-grouped findings accordion (CRITICAL, HIGH, MEDIUM, LOW, INFO) with search & filter.
  - Merge Recommendation banner (`APPROVE` / `REQUEST_CHANGES`) with transparent rationale.
  - Fix Suggestion card with interactive unified diff syntax highlighter.
  - Real-time Execution Trace log viewer.
  - AI Provider Status indicator.

### Phase 11: Testing, Scenarios & Runnable Demo Notebook
- Implement end-to-end tests covering:
  - Scenario 1: Clean Change (Approve).
  - Scenario 2: Security Issue (detect-secrets / bandit trigger -> Request Changes -> Patch Proposed).
  - Scenario 3: Style Issues / Missing Tests (Request Changes).
  - Edge cases: Malicious ZIP, path traversal, zip bomb, scanner timeouts, offline providers.
- Implement `notebooks/Q14_Code_Review_Demo.ipynb` executing the real pipeline with live outputs.

### Phase 12: Documentation, Architecture Diagrams & Final Audit
- Deliverables:
  - `README.md` (maximum 2 pages, clear run instructions).
  - `PROJECT_REPORT.md` (comprehensive academic project report).
  - `ARCHITECTURE.md` (system architecture, component interactions, threat model).
  - `CA2_REQUIREMENT_TRACEABILITY.md` (matrix mapping every requirement to code, tests, and evidence).
  - `TEST_REPORT.md` (pytest results, coverage numbers).
  - `COST_AND_API_AUDIT.md` (zero-cost, local-first audit).
  - `diagrams/architecture.png` (high-resolution architecture diagram).
  - `run.py` (entry-point for the application).
