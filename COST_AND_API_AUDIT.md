# COST & API AUDIT: REVIEWFORGE (Q14)
**CSE476 CA2 — Automated Code Review Board**  
**Policy:** Local-First &bull; Zero Incurred Cost &bull; No Paid Subscriptions &bull; Academic Compliance  

---

## 1. Executive Cost Audit Summary

| Component / Service | Operational Tier | Incurred Cost | External Transmission | Fallback Behavior |
|---|---|---|---|---|
| **Python Static Tools** (`ruff`, `bandit`, `detect-secrets`) | Local (Host / WSL) | **$0.00** | None (100% on-device) | Standard execution |
| **Local Ollama** (`http://localhost:11434`) | Local Open-Source | **$0.00** | None (Loopback only) | Falls back to Deterministic Offline Engine |
| **Google Gemini API** (Optional) | Free Tier (Rate-limited) | **$0.00** | Cloud (If API key set) | Falls back to Deterministic Offline Engine |
| **SQLite Database** (`data/reviews.db`) | Local File | **$0.00** | None | Standard execution |
| **Append-Only JSONL** (`logs/run_log.jsonl`) | Local File | **$0.00** | None | Standard execution |
| **Docker Engine** (Sandbox) | Local Container | **$0.00** | None (`--network none`) | Flags `NOT_RUN` with security notice |
| **TOTAL INCURRED COST** | &mdash; | **$0.00** | &mdash; | &mdash; |

---

## 2. API & Network Transmission Audit

### 2.1 Default Operational Mode: 100% Local-First
- ReviewForge is engineered to run completely offline without an active internet connection.
- Ruff, Bandit, detect-secrets, and Python difflib run as local subprocesses.
- Semantic Kernel orchestrates agents in-process without outbound telemetry.
- If Ollama is running locally, prompt exchanges stay within `127.0.0.1:11434`.

### 2.2 Optional Provider: Google Gemini
- Configured strictly via the environment variable `GEMINI_API_KEY`.
- If `GEMINI_API_KEY` is not set, ReviewForge silently and gracefully defaults to the `Deterministic Offline Engine`.
- When active, Gemini requests are constrained:
  - Temperature: `0.2`
  - Max tokens: `1000`
  - Free-tier rate limits respected.
- The system will **never** automatically sign up for, switch to, or charge a paid cloud service.

---

## 3. Environment Variables Audit

| Variable Name | Required? | Default Value | Description |
|---|---|---|---|
| `OLLAMA_HOST` | No | `http://localhost:11434` | Local Ollama daemon endpoint. |
| `OLLAMA_MODEL` | No | `llama3.2` | Local model name for Ollama inference. |
| `GEMINI_API_KEY` | No | `None` | Optional Google Gemini API key (Free Tier). |
| `REVIEWS_DB_PATH` | No | `data/reviews.db` | Custom path for SQLite database. |
| `REVIEWS_LOG_DIR` | No | `logs` | Custom directory for `run_log.jsonl`. |

---

## 4. Academic Integrity & Zero-Cost Compliance
ReviewForge strictly adheres to Section 3 of the Authoritative Assignment Requirements:
- No paid API keys or subscriptions are committed or required.
- No external hosted databases (e.g. AWS RDS, Pinecone) are introduced.
- Deterministic static analysis, multi-agent fan-out/fan-in, deduplication, merge recommendations, and patch proposals remain 100% functional even when no LLM or network connection is available.
