# SYSTEM ARCHITECTURE: REVIEWFORGE (Q14)
**CSE476 CA2 Multi-Agent Architecture | Microsoft Semantic Kernel & Python**  

---

## 1. High-Level Architectural Model
ReviewForge implements an asynchronous **Blackboard-coordinated Fan-Out / Fan-In Multi-Agent Architecture**.

```text
                               +-----------------------------+
                               |     USER / WEB DASHBOARD    |
                               +-----------------------------+
                                              |
                                              v (HTTP POST /api/reviews)
                               +-----------------------------+
                               |      FLASK BACKEND &        |
                               |      ARCHIVE VALIDATOR      |
                               +-----------------------------+
                                              |
                                              v (Validated Extraction)
+-------------------------------------------------------------------------------------------------+
|                                 MICROSOFT SEMANTIC KERNEL ENGINE                                |
|                                                                                                 |
|   +--------------------------------- FAN-OUT (asyncio.gather) -------------------------------+  |
|   |                                                                                          |  |
|   |   +-------------------+  +-------------------+  +-------------------+  +-------------+   |  |
|   |   |    DIFF AGENT     |  |    STYLE AGENT    |  |  SECURITY AGENT   |  | TEST-COV AG |   |  |
|   |   |  (DiffToolsPlugin)|  | (StyleToolsPlugin)|  | (SecToolsPlugin)  |  | (TestPlugin)|   |  |
|   |   +-------------------+  +-------------------+  +-------------------+  +-------------+   |  |
|   |             |                      |                      |                   |          |  |
|   +-------------|----------------------|----------------------|-------------------|----------+  |
|                 |                      |                      |                   |             |
|                 +----------------------+----------------------+-------------------+             |
|                                                |                                                |
|                                                v                                                |
|                                   SHARED CHANGE STATE (Memory)                                  |
|                                                |                                                |
|                                                v (FAN-IN CONSOLIDATION)                         |
|                                      +--------------------+                                     |
|                                      |  REVIEWER MANAGER  |                                     |
|                                      | (ManagerToolsPlugin|                                     |
|                                      +--------------------+                                     |
|                                                |                                                |
|                                                v (POST-REVIEW EXTENSION)                        |
|                                      +--------------------+                                     |
|                                      | FIX-SUGGESTION AG  |                                     |
|                                      |  (FixToolsPlugin)  |                                     |
|                                      +--------------------+                                     |
+-------------------------------------------------------------------------------------------------+
                                       |              |
                                       v              v
                              [SQLite Database]  [JSONL Audit Trail]
                              (data/reviews.db)  (logs/run_log.jsonl)
```

---

## 2. Component Boundaries & Interfaces

### 2.1 Web Presentation & API Layer (`backend/`)
- `app.py`: Application factory initializing Flask, CORS, maximum content length (25MB), database connections, and logger instances.
- `routes.py`: REST controllers:
  - `GET /`: Serves static dashboard (`static/index.html`).
  - `GET /api/health`: Provides system health and dependency versions.
  - `GET /api/providers/status`: Exposes status of Ollama, Gemini, and offline engine.
  - `GET /api/agents`: Describes the 6-agent roster and registered tool sets.
  - `POST /api/reviews`: Validates uploaded ZIP, writes initial DB record, and dispatches review workflow.
  - `GET /api/reviews/<id>`: Retrieves full review record, findings, diffs, and proposed patches.
  - `GET /api/reviews/<id>/trace`: Streams JSONL execution audit events.

### 2.2 Ingestion & Quarantine Subsystem (`services/`)
- `archive_validator.py`: Analyzes ZIP archive before disk extraction. Verifies file count, size quotas, directory depth, compression ratios, prohibits symlinks and path traversals (`../`), and validates snapshot structures (`base/` and `proposed/`).
- `extraction_service.py`: Extracts verified archives into isolated ephemeral workspaces under `tempfile.gettempdir()/reviewforge_workspaces/<review_id>`.

### 2.3 Shared Change State (Blackboard Memory) (`memory/`)
- Centralized `SharedChangeState` object with reentrant thread locks (`threading.Lock`).
- Segregated agent finding slots prevent race conditions during concurrent specialist execution.
- Contains change statistics, unified diffs, execution records, severity distributions, and decision rationale.

### 2.4 Semantic Kernel Specialist Agent Layer (`agents/` & `tools/`)
Each agent is an autonomous module subclassing `semantic_kernel.agents.Agent`:
- `DiffAgent`: Invocations of `identify_changed_files` and `extract_file_diff`.
- `StyleAgent`: Invocations of `run_ruff_check` and `check_formatting`.
- `SecurityAgent`: Invocations of `run_bandit_scan` and `scan_secrets` with automatic secret redaction.
- `TestCoverageAgent`: Invocations of `discover_test_files` and `run_pytest_coverage` (safe sandbox gating).
- `ReviewerManager`: Invocations of `collect_agent_findings` and `rank_and_decide`.
- `FixSuggestionAgent`: Invocations of `inspect_finding_context` and `validate_patch_proposal`.

---

## 3. Concurrency, Execution Flow & Fault Isolation
1. **Fan-Out Synchronization:**
   - Specialist agents run concurrently via `asyncio.gather(*tasks, return_exceptions=True)`.
   - Each agent operates with its own isolated `Kernel` instance and dedicated plugin.
2. **Fault Isolation:**
   - If an individual agent encounters an unhandled exception or scanner timeout, the exception is trapped and recorded in `shared_state.error_records`.
   - Completed findings from other specialist agents remain intact.
3. **Fan-In Deduplication & Ranking:**
   - The coordinator waits for all 4 specialist agents to complete or timeout.
   - It performs deterministic deduplication (combining normalized paths, line numbers within a 3-line window, and category similarity).
   - Findings are deterministically sorted by severity: `CRITICAL` > `HIGH` > `MEDIUM` > `LOW` > `INFO`.
4. **Deterministic Policy Engine:**
   - `CRITICAL` / `HIGH` / `MEDIUM` findings -> `REQUEST_CHANGES`.
   - `LOW` / `INFO` findings alone -> `APPROVE`.
   - Incomplete analyses (e.g. unexecuted tests) are disclosed in the rationale.

---

## 4. Threat Model & Security Posture
- **Threat: Malicious Archive Injection (Zip Slip / Zip Bomb):**
  - Mitigated by `ArchiveValidator`: Verifies every entry path, rejects absolute paths, rejects `..` segments, enforces extracted size <= 100MB, file count <= 1000, compression ratio <= 100:1.
- **Threat: Untrusted Host Code Execution:**
  - Mitigated by `SandboxService`: Host execution of untrusted code is prohibited. When Docker is active, tests run in a locked container (`--network none`, `--cap-drop ALL`, non-root, read-only mount). When Docker is offline, tests are safely marked `NOT_RUN`.
- **Threat: Credential Leakage in Audit Trails:**
  - Mitigated by `redact_sensitive_text`: Regex filters mask detected tokens, API keys (`sk-...`, `ghp_...`), and passwords across all databases, logs, and frontend payloads.
