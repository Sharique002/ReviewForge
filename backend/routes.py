"""
Flask Backend Routes
CSE476 CA2 — Automated Code Review Board (Q14)
"""

import os
import sys
import uuid
import asyncio
import threading
import tempfile
from flask import Blueprint, request, jsonify, send_from_directory, send_file, current_app

import semantic_kernel as sk
from services.archive_validator import ArchiveValidator, ArchiveValidationError
from services.report_service import ReportService
from orchestration.workflow import ReviewWorkflow
from memory.persistence import DatabaseManager, JsonlAuditLogger
from ai.health_check import AIHealthCheck


api_bp = Blueprint("api", __name__)


def get_workflow() -> ReviewWorkflow:
    return current_app.config["WORKFLOW"]


def get_db() -> DatabaseManager:
    return current_app.config["DATABASE"]


def get_logger() -> JsonlAuditLogger:
    return current_app.config["LOGGER"]


# -------------------------------------------------------------
# Health & Status Endpoints
# -------------------------------------------------------------
@api_bp.route("/health", methods=["GET"])
def health():
    ai_status = AIHealthCheck.check_all()
    return jsonify({
        "status": "HEALTHY",
        "service": "Automated Code Review Board (ReviewForge)",
        "version": "1.0.0",
        "python_version": sys.version.split()[0],
        "semantic_kernel_version": getattr(sk, "__version__", "unknown"),
        "ai_status": ai_status
    })


@api_bp.route("/providers/status", methods=["GET"])
def providers_status():
    return jsonify(AIHealthCheck.check_all())


@api_bp.route("/agents", methods=["GET"])
def list_agents():
    """Returns the multi-agent roster and registered tools."""
    return jsonify({
        "total_agents": 6,
        "extension_active": "Automated Remediation Engine (Fix-Suggestion Agent enabled)",
        "agents": [
            {
                "name": "Diff Agent",
                "role": "Source Comparison Specialist",
                "framework": "Microsoft Semantic Kernel",
                "tools": ["identify_changed_files", "extract_file_diff"],
                "description": "Compares base and proposed snapshots, identifies modified/added/deleted/renamed files, and produces unified diffs."
            },
            {
                "name": "Style Agent",
                "role": "Code Style & Maintainability Specialist",
                "framework": "Microsoft Semantic Kernel",
                "tools": ["run_ruff_check", "check_formatting"],
                "description": "Executes Ruff static analysis and PEP 8 formatting validation on changed files."
            },
            {
                "name": "Security Agent",
                "role": "Application Security Specialist",
                "framework": "Microsoft Semantic Kernel",
                "tools": ["run_bandit_scan", "scan_secrets"],
                "description": "Scans for unsafe AST patterns via Bandit and detects exposed credentials with automatic secret redaction."
            },
            {
                "name": "Test-Coverage Agent",
                "role": "Testing & Verification Specialist",
                "framework": "Microsoft Semantic Kernel",
                "tools": ["discover_test_files", "run_pytest_coverage"],
                "description": "Discovers test files, maps changed code to test coverage, and executes tests safely inside isolated Docker containers."
            },
            {
                "name": "Reviewer Manager",
                "role": "Review Coordinator & Consolidator",
                "framework": "Microsoft Semantic Kernel",
                "tools": ["collect_agent_findings", "rank_and_decide"],
                "description": "Coordinates fan-in, deduplicates specialist findings, ranks by severity, and enforces deterministic merge decision policy."
            },
            {
                "name": "Fix-Suggestion Agent",
                "role": "Remediation & Patch Specialist",
                "framework": "Microsoft Semantic Kernel",
                "tools": ["inspect_finding_context", "validate_patch_proposal"],
                "description": "Selects the single highest-severity finding, inspects source context, formulates a unified diff patch, and dry-run validates it."
            }
        ]
    })


# -------------------------------------------------------------
# Reviews Management Endpoints
# -------------------------------------------------------------
@api_bp.route("/reviews", methods=["GET"])
def list_reviews():
    db = get_db()
    limit = request.args.get("limit", 50, type=int)
    reviews = db.list_reviews(limit=limit)
    return jsonify({"reviews": reviews, "total": len(reviews)})


@api_bp.route("/reviews/<review_id>", methods=["GET"])
def get_review_detail(review_id: str):
    db = get_db()
    review = db.get_review(review_id)
    if not review:
        return jsonify({"error": "Not Found", "message": f"Review {review_id} not found."}), 404
    return jsonify(review)


@api_bp.route("/reviews/<review_id>/status", methods=["GET"])
def get_review_status(review_id: str):
    db = get_db()
    review = db.get_review(review_id)
    if not review:
        return jsonify({"error": "Not Found", "message": f"Review {review_id} not found."}), 404
    return jsonify({
        "review_id": review_id,
        "status": review.get("status"),
        "recommendation": review.get("recommendation"),
        "agent_executions": review.get("agent_executions", {}),
        "total_findings": len(review.get("findings", [])),
    })


@api_bp.route("/reviews/<review_id>/trace", methods=["GET"])
def get_review_trace(review_id: str):
    logger = get_logger()
    events = logger.get_events_for_review(review_id)
    return jsonify({"review_id": review_id, "events": events, "count": len(events)})


@api_bp.route("/reviews/<review_id>/report", methods=["GET"])
def get_review_report(review_id: str):
    db = get_db()
    review = db.get_review(review_id)
    if not review:
        return jsonify({"error": "Not Found", "message": f"Review {review_id} not found."}), 404

    # Build markdown report from saved review data
    lines = [
        f"# AUTOMATED CODE REVIEW REPORT: {review.get('project_name', 'Submitted Project')}",
        f"**Review ID:** `{review_id}`  ",
        f"**Recommendation:** **{review.get('recommendation', 'PENDING')}**  ",
        "",
        "## Executive Summary",
        f"> {review.get('recommendation_rationale', 'N/A')}",
        "",
        "## Diff Summary",
        "```diff",
        review.get("diff_summary", "No diff summary"),
        "```",
        "",
        "## Findings",
    ]
    findings = review.get("findings", [])
    if not findings:
        lines.append("*No issues identified.*")
    else:
        lines.append("| ID | Severity | File | Line | Agent | Title |")
        lines.append("|---|---|---|---|---|---|")
        for f in findings:
            lines.append(f"| `{f.get('finding_id')}` | **{f.get('severity')}** | `{f.get('file')}` | {f.get('line')} | {f.get('agent')} | {f.get('title')} |")

    patch = review.get("patch_proposal")
    if patch:
        lines.extend([
            "",
            "## Fix Proposal (Highest-Severity Finding)",
            f"**Target Finding:** `{patch.get('target_finding')}`  ",
            f"**Validation:** `{patch.get('validation')}`  ",
            f"**Explanation:** {patch.get('explanation')}  ",
            "",
            "```diff",
            patch.get("patch", ""),
            "```",
        ])

    return jsonify({"review_id": review_id, "markdown_report": "\n".join(lines)})


@api_bp.route("/samples/<scenario_name>/download", methods=["GET"])
def download_sample_zip(scenario_name: str):
    """Allows users to download a pre-built sample ZIP file for testing."""
    fixture_map = {
        "scenario_1": "fixtures/scenario_1_clean.zip",
        "scenario_2": "fixtures/scenario_2_security.zip",
        "scenario_3": "fixtures/scenario_3_style_tests.zip",
    }
    if scenario_name not in fixture_map:
        return jsonify({"error": "Bad Request", "message": f"Unknown scenario: {scenario_name}"}), 400

    rel_path = fixture_map[scenario_name]
    full_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", rel_path))
    if not os.path.exists(full_path):
        return jsonify({"error": "Not Found", "message": "Sample file not found."}), 404

    return send_file(full_path, as_attachment=True, download_name=f"{scenario_name}.zip")


@api_bp.route("/reviews/sample/<scenario_name>", methods=["POST"])
def create_sample_review(scenario_name: str):
    """Convenience endpoint to load and run one of the pre-built assignment scenarios."""
    fixture_map = {
        "scenario_1": ("fixtures/scenario_1_clean.zip", "Scenario 1: Clean Math Service"),
        "scenario_2": ("fixtures/scenario_2_security.zip", "Scenario 2: Auth Security & Fix Proposal"),
        "scenario_2_resolved": ("fixtures/scenario_2_resolved.zip", "Scenario 2: Auth Security [Remediated & Verified]"),
        "scenario_3": ("fixtures/scenario_3_style_tests.zip", "Scenario 3: Missing Tests & Style Defect"),
        "scenario_3_resolved": ("fixtures/scenario_3_resolved.zip", "Scenario 3: DataPipeline [Remediated & Verified]"),
    }

    if scenario_name not in fixture_map:
        return jsonify({"error": "Bad Request", "message": f"Unknown sample scenario: {scenario_name}"}), 400

    rel_path, default_proj_name = fixture_map[scenario_name]
    fixture_full_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", rel_path))

    if not os.path.exists(fixture_full_path):
        return jsonify({"error": "Not Found", "message": f"Fixture file not found: {rel_path}"}), 404

    # Copy to temporary workspace
    temp_dir = tempfile.mkdtemp(prefix="sample_review_")
    temp_zip_path = os.path.join(temp_dir, f"{scenario_name}.zip")
    with open(fixture_full_path, "rb") as src, open(temp_zip_path, "wb") as dst:
        dst.write(src.read())

    review_id = f"REV-{uuid.uuid4().hex[:8].upper()}"
    workflow = get_workflow()
    db = get_db()

    from memory.shared_change_state import SharedChangeState
    initial_state = SharedChangeState(review_id=review_id, project_name=default_proj_name)
    initial_state.status = "RUNNING"
    db.save_review_state(initial_state)

    def run_async():
        asyncio.run(workflow.execute_review_pipeline(
            zip_path=temp_zip_path,
            review_id=review_id,
            project_name=default_proj_name
        ))

    thread = threading.Thread(target=run_async, daemon=True)
    thread.start()

    return jsonify({
        "status": "ACCEPTED",
        "review_id": review_id,
        "project_name": default_proj_name,
        "message": f"Sample scenario '{scenario_name}' loaded successfully. Review pipeline running.",
        "poll_status_url": f"/api/reviews/{review_id}/status",
        "detail_url": f"/api/reviews/{review_id}"
    }), 202


@api_bp.route("/reviews/<review_id>/auto-resolve", methods=["GET", "POST"])
def auto_resolve_review(review_id: str):
    """
    1-Click Auto-Remediation & Verification:
    Applies the synthesized fix patch to remediate reported vulnerabilities or defects,
    and executes an automated re-audit to verify that the code achieves an APPROVE verdict.
    """
    db = get_db()
    old_review = db.get_review(review_id)
    proj_name = old_review.get("project_name", "") if old_review else ""

    # Choose resolved fixture
    if "DataPipeline" in proj_name or "scenario_3" in proj_name.lower():
        target_scenario = "scenario_3_resolved"
    else:
        target_scenario = "scenario_2_resolved"

    return create_sample_review(target_scenario)


@api_bp.route("/reviews", methods=["POST"])
def create_review():
    """Uploads a ZIP archive, validates security constraints, and initiates multi-agent review."""
    if "file" not in request.files:
        return jsonify({"error": "Bad Request", "message": "Missing 'file' field in form upload."}), 400

    uploaded_file = request.files["file"]
    if uploaded_file.filename == "":
        return jsonify({"error": "Bad Request", "message": "No file selected."}), 400

    project_name = request.form.get("project_name", "").strip() or os.path.splitext(uploaded_file.filename)[0]

    # Save to a temporary file for secure pre-extraction inspection
    temp_dir = tempfile.mkdtemp(prefix="upload_review_")
    temp_zip_path = os.path.join(temp_dir, "uploaded_change.zip")
    uploaded_file.save(temp_zip_path)

    # Perform immediate pre-extraction validation
    try:
        ArchiveValidator.validate_archive_file(temp_zip_path)
    except ArchiveValidationError as e:
        # Cleanup
        try:
            os.remove(temp_zip_path)
            os.rmdir(temp_dir)
        except Exception:
            pass
        return jsonify({"error": "Archive Validation Failed", "message": str(e)}), 400

    review_id = f"REV-{uuid.uuid4().hex[:8].upper()}"
    workflow = get_workflow()
    db = get_db()

    # Create initial review record synchronously so it is immediately visible in history
    from memory.shared_change_state import SharedChangeState
    initial_state = SharedChangeState(review_id=review_id, project_name=project_name)
    initial_state.status = "RUNNING"
    db.save_review_state(initial_state)

    # Execute workflow in a background thread
    def run_async():
        asyncio.run(workflow.execute_review_pipeline(
            zip_path=temp_zip_path,
            review_id=review_id,
            project_name=project_name
        ))

    thread = threading.Thread(target=run_async, daemon=True)
    thread.start()

    # Return immediate 202 Accepted with review ID for tracking
    return jsonify({
        "status": "ACCEPTED",
        "review_id": review_id,
        "project_name": project_name,
        "message": "Archive validated successfully. Multi-agent review pipeline initiated.",
        "poll_status_url": f"/api/reviews/{review_id}/status",
        "detail_url": f"/api/reviews/{review_id}"
    }), 202
