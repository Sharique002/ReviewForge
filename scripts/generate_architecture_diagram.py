"""
Generates high-resolution diagrams/architecture.png
CSE476 CA2 — Automated Code Review Board (Q14)
"""

import os
from PIL import Image, ImageDraw, ImageFont


def create_diagram():
    os.makedirs("diagrams", exist_ok=True)
    width = 1600
    height = 1000
    img = Image.new("RGB", (width, height), color="#0b0f19")
    draw = ImageDraw.Draw(img)

    # Load system font or default
    try:
        font_title = ImageFont.truetype("arial.ttf", 28)
        font_sub = ImageFont.truetype("arial.ttf", 16)
        font_box_title = ImageFont.truetype("arialbd.ttf", 18)
        font_box_body = ImageFont.truetype("arial.ttf", 13)
        font_mono = ImageFont.truetype("consola.ttf", 12)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_box_title = ImageFont.load_default()
        font_box_body = ImageFont.load_default()
        font_mono = ImageFont.load_default()

    # Header
    draw.text((50, 40), "REVIEWFORGE: AUTOMATED CODE REVIEW BOARD (Q14)", fill="#38bdf8", font=font_title)
    draw.text((50, 80), "CSE476 CA2 Multi-Agent Architecture | Microsoft Semantic Kernel | 6 Autonomous Agents (Group-of-3 Extension)", fill="#94a3b8", font=font_sub)

    # Helper function to draw rounded boxes
    def draw_card(x1, y1, x2, y2, bg, border, title, lines, title_color="#38bdf8"):
        draw.rounded_rectangle([x1, y1, x2, y2], radius=10, fill=bg, outline=border, width=2)
        draw.text((x1 + 16, y1 + 14), title, fill=title_color, font=font_box_title)
        cy = y1 + 45
        for line in lines:
            draw.text((x1 + 16, cy), line, fill="#cbd5e1", font=font_box_body)
            cy += 20

    # Top Row: Client & Ingestion Layer
    draw_card(50, 130, 450, 240, "#111827", "#3b82f6", "1. CLIENT & DASHBOARD", [
        "Interactive Dark Developer Dashboard (HTML/JS/CSS)",
        "REST API (/api/reviews, /api/status, /api/trace)",
        "Input: Uploaded code-review.zip (base/ + proposed/)"
    ])

    draw_card(500, 130, 950, 240, "#111827", "#06b6d4", "2. SECURITY & EXTRACTION", [
        "ArchiveValidator: Zip bomb & traversal defense",
        "ExtractionService: Ephemeral workspace sandbox",
        "Deterministic integrity validation"
    ])

    draw_card(1000, 130, 1550, 240, "#111827", "#8b5cf6", "3. AI PROVIDER SUBSYSTEM", [
        "Local Ollama (http://localhost:11434 / llama3.2)",
        "Optional Google Gemini (Free-tier bound)",
        "Deterministic Offline Fallback (Active)"
    ])

    # Middle Layer: Microsoft Semantic Kernel Concurrent Fan-Out (4 Specialist Agents)
    draw.rounded_rectangle([50, 280, 1550, 520], radius=12, fill="#070a14", outline="#1e293b", width=2)
    draw.text((70, 295), "MICROSOFT SEMANTIC KERNEL: CONCURRENT FAN-OUT STAGE (asyncio.gather)", fill="#38bdf8", font=font_box_title)

    # 4 Specialist Agent Cards
    draw_card(70, 335, 410, 495, "#151d30", "#38bdf8", "DIFF AGENT", [
        "Role: Change Analysis & Diffing",
        "Tool 1: identify_changed_files()",
        "Tool 2: extract_file_diff()",
        "Output: Added, Modified, Deleted, Diffs"
    ])

    draw_card(430, 335, 770, 495, "#151d30", "#34d399", "STYLE AGENT", [
        "Role: Code Style & Maintainability",
        "Tool 1: run_ruff_check()",
        "Tool 2: check_formatting()",
        "Output: Ruff lint & format findings"
    ])

    draw_card(790, 335, 1150, 495, "#151d30", "#f43f5e", "SECURITY AGENT", [
        "Role: Vulnerability & Secret Scanning",
        "Tool 1: run_bandit_scan()",
        "Tool 2: scan_secrets() (detect-secrets)",
        "Output: Sanitized findings (Auto-Redaction)"
    ])

    draw_card(1170, 335, 1530, 495, "#151d30", "#fbbf24", "TEST-COVERAGE AGENT", [
        "Role: Test Discovery & Verification",
        "Tool 1: discover_test_files()",
        "Tool 2: run_pytest_coverage()",
        "Security Gated: Docker sandbox / NOT_RUN"
    ])

    # Shared Change State Central Bus
    draw_card(50, 560, 1550, 680, "#111827", "#06b6d4", "SHARED CHANGE STATE (Thread-Safe Central Blackboard Memory)", [
        "Slots: Review ID | Project Metadata | Snapshots Info | Diff Statistics | Unified Diffs",
        "Specialist Slots: Isolated agent finding arrays (Diff, Style, Security, Test-Coverage)",
        "Execution Tracking: ToolExecutionRecords | Timestamps | Progress % | Error Records",
        "Consolidated Slot: Deduplicated Findings | Severity Distribution | Final Recommendation | Proposed Patch"
    ], title_color="#06b6d4")

    # Bottom Layer: Reviewer Manager Fan-In & Fix-Suggestion Agent
    draw_card(50, 720, 780, 890, "#151d30", "#38bdf8", "REVIEWER MANAGER (Fan-In Consolidation)", [
        "Tool 1: collect_agent_findings() across specialist slots",
        "Tool 2: rank_and_decide() [Deduplication & Ranking]",
        "Deterministic Policy: CRITICAL/HIGH/MEDIUM -> REQUEST_CHANGES",
        "Merge Recommendation: APPROVE or REQUEST_CHANGES + Rationale"
    ])

    draw_card(820, 720, 1550, 890, "#151d30", "#10b981", "FIX-SUGGESTION AGENT (Group-of-3 Extension)", [
        "Receives Consolidated Review -> Targets Single Highest-Severity Finding",
        "Tool 1: inspect_finding_context() (Line window inspection)",
        "Tool 2: validate_patch_proposal() (Unified diff dry-run check)",
        "Safety Rule: Generates proposed patch preview only; NEVER mutates files"
    ], title_color="#34d399")

    # Footer Persistence Notes
    draw.text((50, 930), "Persistence: SQLite Database (data/reviews.db) | Append-Only Audit Log: logs/run_log.jsonl (Tamper-evident, Redacted)", fill="#64748b", font=font_mono)

    img.save("diagrams/architecture.png")
    print("Saved high-resolution architecture diagram to diagrams/architecture.png")


if __name__ == "__main__":
    create_diagram()
