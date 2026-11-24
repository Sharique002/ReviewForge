"""
Extraction Service
CSE476 CA2 — Automated Code Review Board (Q14)

Safely extracts validated archives into unique, isolated workspace directories.
Guarantees separation of reviews and handles cleanup.
"""

import os
import shutil
import tempfile
import zipfile
from typing import Dict, Any, Optional

from services.archive_validator import ArchiveValidator, ArchiveValidationError


class ExtractionService:
    """Safely extracts validated review archives into isolated workspaces."""

    def __init__(self, base_workspace_dir: Optional[str] = None):
        if base_workspace_dir:
            self.base_workspace_dir = os.path.abspath(base_workspace_dir)
            os.makedirs(self.base_workspace_dir, exist_ok=True)
        else:
            self.base_workspace_dir = os.path.join(tempfile.gettempdir(), "reviewforge_workspaces")
            os.makedirs(self.base_workspace_dir, exist_ok=True)

    def prepare_review_workspace(self, review_id: str) -> str:
        """Creates a unique isolated directory for the given review ID."""
        clean_id = "".join(c for c in review_id if c.isalnum() or c in ("-", "_"))
        workspace_path = os.path.join(self.base_workspace_dir, clean_id)
        os.makedirs(workspace_path, exist_ok=True)
        return workspace_path

    def extract_archive(self, zip_path: str, review_id: str) -> Dict[str, Any]:
        """
        Validates and extracts an archive into an isolated review workspace.
        Returns paths to the extracted snapshots.
        """
        # Step 1: Pre-extraction validation
        validation_meta = ArchiveValidator.validate_archive_file(zip_path)

        # Step 2: Create isolated workspace
        workspace_path = self.prepare_review_workspace(review_id)
        extracted_root = os.path.join(workspace_path, "extracted")
        os.makedirs(extracted_root, exist_ok=True)

        # Step 3: Extract with safe canonical path verification
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for member in zf.infolist():
                # Canonical target path calculation
                normalized = member.filename.replace("\\", "/").lstrip("/")
                target_path = os.path.abspath(os.path.join(extracted_root, normalized))
                
                # Critical security guard: verify target is within extracted_root
                if not target_path.startswith(os.path.abspath(extracted_root)):
                    raise ArchiveValidationError(
                        f"Security violation: path traversal attempt during extraction: {member.filename}"
                    )

                if member.is_dir():
                    os.makedirs(target_path, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    with zf.open(member) as source, open(target_path, "wb") as dest:
                        shutil.copyfileobj(source, dest)

        # Step 4: Locate snapshot directories
        base_dir = os.path.join(extracted_root, "base")
        proposed_dir = os.path.join(extracted_root, "proposed")

        # Handle cases where archive contained an outer wrapper folder
        if not os.path.exists(base_dir) and not os.path.exists(proposed_dir):
            # Check if there is a single top-level directory containing base/proposed
            entries = [os.path.join(extracted_root, e) for e in os.listdir(extracted_root)]
            subdirs = [e for e in entries if os.path.isdir(e)]
            if len(subdirs) == 1:
                candidate_base = os.path.join(subdirs[0], "base")
                candidate_proposed = os.path.join(subdirs[0], "proposed")
                if os.path.exists(candidate_base) or os.path.exists(candidate_proposed):
                    base_dir = candidate_base
                    proposed_dir = candidate_proposed

        return {
            "workspace_path": workspace_path,
            "extracted_root": extracted_root,
            "base_dir": base_dir if os.path.exists(base_dir) else None,
            "proposed_dir": proposed_dir if os.path.exists(proposed_dir) else None,
            "mode": validation_meta["mode"],
            "manifest": validation_meta.get("manifest", {}),
            "file_count": validation_meta["file_count"],
        }

    def cleanup_workspace(self, workspace_path: str) -> bool:
        """Removes the temporary workspace directory safely."""
        try:
            if os.path.exists(workspace_path) and workspace_path.startswith(self.base_workspace_dir):
                shutil.rmtree(workspace_path, ignore_errors=True)
                return True
        except Exception:
            pass
        return False
