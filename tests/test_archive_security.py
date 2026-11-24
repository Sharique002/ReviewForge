"""
Archive Security & Validation Test Suite
CSE476 CA2 — Automated Code Review Board (Q14)
"""

import os
import zipfile
import tempfile
import pytest

from services.archive_validator import ArchiveValidator, ArchiveValidationError
from services.extraction_service import ExtractionService


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        yield td


def create_zip(zip_path: str, file_map: dict):
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for arcname, content in file_map.items():
            zf.writestr(arcname, content)


def test_valid_archive(temp_dir):
    zip_path = os.path.join(temp_dir, "valid.zip")
    files = {
        "base/main.py": "def hello():\n    return 'hello'\n",
        "proposed/main.py": "def hello():\n    return 'hello world'\n",
        "review-manifest.json": '{"project_name": "Test Project", "description": "Test"}'
    }
    create_zip(zip_path, files)
    
    meta = ArchiveValidator.validate_archive_file(zip_path)
    assert meta["mode"] == "CHANGE_REVIEW"
    assert meta["has_base"] is True
    assert meta["has_proposed"] is True
    assert meta["manifest"]["project_name"] == "Test Project"

    # Test extraction
    extractor = ExtractionService(base_workspace_dir=os.path.join(temp_dir, "workspaces"))
    extracted = extractor.extract_archive(zip_path, "rev-001")
    assert extracted["base_dir"] is not None
    assert extracted["proposed_dir"] is not None
    assert os.path.exists(os.path.join(extracted["base_dir"], "main.py"))
    assert os.path.exists(os.path.join(extracted["proposed_dir"], "main.py"))
    
    # Clean up
    assert extractor.cleanup_workspace(extracted["workspace_path"]) is True


def test_path_traversal_relative_rejected(temp_dir):
    zip_path = os.path.join(temp_dir, "traversal.zip")
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("../evil.txt", "exploit")
        zf.writestr("base/main.py", "safe")
        zf.writestr("proposed/main.py", "safe")
        
    with pytest.raises(ArchiveValidationError, match="Path traversal detected"):
        ArchiveValidator.validate_archive_file(zip_path)


def test_path_traversal_absolute_rejected(temp_dir):
    zip_path = os.path.join(temp_dir, "abs.zip")
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("/etc/passwd", "exploit")
        zf.writestr("base/main.py", "safe")
        zf.writestr("proposed/main.py", "safe")
        
    with pytest.raises(ArchiveValidationError, match="Path traversal detected"):
        ArchiveValidator.validate_archive_file(zip_path)


def test_duplicate_path_rejected(temp_dir):
    zip_path = os.path.join(temp_dir, "dupe.zip")
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("base/main.py", "first")
        # Direct low-level write of duplicate member
        zf.writestr("base/main.py", "second")
        zf.writestr("proposed/main.py", "safe")
        
    with pytest.raises(ArchiveValidationError, match="duplicate path"):
        ArchiveValidator.validate_archive_file(zip_path)


def test_missing_snapshots_rejected(temp_dir):
    zip_path = os.path.join(temp_dir, "empty_snapshots.zip")
    create_zip(zip_path, {"random.py": "x = 1"})
    
    with pytest.raises(ArchiveValidationError, match="missing required snapshots"):
        ArchiveValidator.validate_archive_file(zip_path)


def test_single_snapshot_full_project_audit_mode(temp_dir):
    zip_path = os.path.join(temp_dir, "proposed_only.zip")
    create_zip(zip_path, {"proposed/app.py": "print('hello')"})
    
    meta = ArchiveValidator.validate_archive_file(zip_path)
    assert meta["mode"] == "FULL_PROJECT_AUDIT"
    assert meta["has_proposed"] is True
    assert meta["has_base"] is False


def test_invalid_manifest_rejected(temp_dir):
    zip_path = os.path.join(temp_dir, "bad_manifest.zip")
    files = {
        "base/main.py": "x = 1",
        "proposed/main.py": "x = 2",
        "review-manifest.json": '{"invalid_key": 123}'
    }
    create_zip(zip_path, files)
    with pytest.raises(ArchiveValidationError, match="Unexpected key in review-manifest.json"):
        ArchiveValidator.validate_archive_file(zip_path)
