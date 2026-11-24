# PROJECT AUDIT: AUTOMATED CODE REVIEW BOARD (Q14)

**Date:** 2026-11-18  
**Project:** CSE476 CA2 — Automated Code Review Board (Multi-Agent System)  
**Author:** Multi-Agent Systems & Security Architecture Team  

---

## 1. Executive Summary

This document establishes the baseline audit for the Automated Code Review Board (Q14), a production-grade multi-agent code review platform leveraging Microsoft Semantic Kernel, Flask, SQLite, and deterministic static analysis tooling.

---

## 2. Environment & System Specifications

| Attribute | Detected Value | Status / Notes |
|---|---|---|
| **Operating System** | Windows 11 (64-bit) | Host OS verified |
| **Shell** | PowerShell 7 (pwsh) | Operational |
| **Python Version** | 3.11.9 | Fully compatible with Semantic Kernel v1.x |
| **Semantic Kernel** | 1.47.0 | Verified installed via pip |
| **Static Style Analyzer** | Ruff 0.17.5 | Verified operational |
| **Security Scanner** | Bandit 1.9.4 | Verified operational |
| **Secret Detection** | detect-secrets 1.5.0 | Verified operational |
| **Test Runner & Coverage**| pytest 9.1.1 / coverage 7.17.2 / pytest-cov 7.1.0 | Verified operational |
| **Web Framework** | Flask 3.1.3 | Verified operational |
| **Container Engine** | Docker 29.8.1 installed (Daemon currently stopped) | Safe `NOT_RUN` fallback enforced for host security |
| **Local LLM (Ollama)** | Port 11434 connection refused (daemon stopped) | Deterministic fallback operational without degradation |
| **Cloud LLM (Gemini)** | `GEMINI_API_KEY` unset | Graceful unavailable provider handling enabled |

---

## 3. Dependency Inventory & Audit

### Verified Core Dependencies
- `semantic-kernel==1.47.0`: Multi-agent orchestration, kernel plugins, kernel functions, native invocation.
- `ruff==0.17.5`: Ultra-fast deterministic linting and formatting analysis.
- `bandit==1.9.4`: AST-based Python security vulnerability detection.
- `detect-secrets==1.5.0`: Heuristic & entropy secret scanning.
- `pytest==9.1.1` & `coverage==7.17.2`: Test suite execution and coverage calculation.
- `flask==3.1.3` & `werkzeug==3.1.1`: Backend REST API and static dashboard serving.
- `pydantic==2.13.5`: Shared state schemas, finding models, and strict type validation.
- `sqlite3`: Built-in transactional persistence for review records and audit history.

---

## 4. Architectural Risk Analysis

1. **Semantic Kernel 1.47.0 API Dynamics**:
   - Modern Semantic Kernel 1.x uses `Kernel`, `KernelPlugin`, `kernel_function`, and async invocation rather than legacy pre-1.0 planner classes.
   - Orchestration must execute concurrent specialist tasks safely via `asyncio.gather` with Kernel invocation, feeding into a consolidated Reviewer Manager.
   - Compatibility must be proven with a dedicated test suite before building higher-level orchestration.

2. **Host Execution Security**:
   - Running untrusted user-submitted Python code directly on the host machine is dangerous.
   - When Docker is stopped/unavailable, test execution MUST NOT blindly fall back to the host. It must report `NOT_RUN` with an explicit security notice while static analysis and test discovery proceed normally.

3. **AI Provider Availability**:
   - Since neither Ollama nor a Gemini key is guaranteed on all review environments, the system must be completely resilient in deterministic offline mode:
     - Scanners (Ruff, Bandit, detect-secrets, difflib) run deterministically.
     - Policy decisions (CRITICAL/HIGH/MEDIUM -> REQUEST_CHANGES) are deterministic.
     - Findings are fully structured, populated, and ranked.
     - When an LLM is active, it generates contextual narrative summaries and natural language patch commentary. When inactive, structured deterministic summaries are generated.

4. **Secret Leakage Risk**:
   - detect-secrets or bandit findings might discover real or synthetic secrets in user changes.
   - All reports, JSONL logs, database rows, and UI displays MUST sanitize and redact sensitive values.

---

## 5. Repository State

The workspace is clean and ready for phased implementation following the authoritative development plan.
