"""
Flask Backend API Test Suite
CSE476 CA2 — Automated Code Review Board (Q14)
"""

import os
import io
import zipfile
import tempfile
import pytest

from backend.app import create_app


@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "test_api.db")
        log_dir = os.path.join(td, "test_logs")
        os.makedirs(log_dir)

        app = create_app({
            "TESTING": True,
            "DATABASE_PATH": db_path,
            "LOG_DIR": log_dir,
        })
        with app.test_client() as client:
            yield client


def create_in_memory_zip(file_map: dict) -> io.BytesIO:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, 'w', zipfile.ZIP_DEFLATED) as zf:
        for arcname, content in file_map.items():
            zf.writestr(arcname, content)
    bio.seek(0)
    return bio


def test_api_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "HEALTHY"
    assert "semantic_kernel_version" in data


def test_api_providers_status(client):
    res = client.get("/api/providers/status")
    assert res.status_code == 200
    data = res.get_json()
    assert "ollama" in data
    assert "deterministic_fallback_ready" in data


def test_api_agents_roster(client):
    res = client.get("/api/agents")
    assert res.status_code == 200
    data = res.get_json()
    assert data["total_agents"] == 6
    names = [a["name"] for a in data["agents"]]
    assert "Diff Agent" in names
    assert "Security Agent" in names
    assert "Fix-Suggestion Agent" in names


def test_api_upload_invalid_zip(client):
    # Upload corrupt file
    data = {
        "file": (io.BytesIO(b"not a real zip"), "bad.zip"),
        "project_name": "BadProject"
    }
    res = client.post("/api/reviews", data=data, content_type="multipart/form-data")
    assert res.status_code == 400
    resp_json = res.get_json()
    assert "Archive Validation Failed" in resp_json["error"]


def test_api_upload_valid_zip_and_track(client):
    bio = create_in_memory_zip({
        "base/main.py": "x = 1\n",
        "proposed/main.py": "x = 2\n",
        "review-manifest.json": '{"project_name": "UploadTest"}'
    })
    data = {
        "file": (bio, "test_upload.zip"),
        "project_name": "UploadTest"
    }
    res = client.post("/api/reviews", data=data, content_type="multipart/form-data")
    assert res.status_code == 202
    resp_json = res.get_json()
    assert resp_json["status"] == "ACCEPTED"
    review_id = resp_json["review_id"]
    assert review_id.startswith("REV-")

    # Check reviews list
    list_res = client.get("/api/reviews")
    assert list_res.status_code == 200
    reviews = list_res.get_json()["reviews"]
    assert any(r["review_id"] == review_id for r in reviews)

    # Check review trace endpoint
    trace_res = client.get(f"/api/reviews/{review_id}/trace")
    assert trace_res.status_code == 200


def test_dashboard_index(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"REVIEWFORGE" in res.data
