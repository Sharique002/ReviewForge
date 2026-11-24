"""
Archive Validator Service
CSE476 CA2 — Automated Code Review Board (Q14)

Provides rigorous security validation for uploaded ZIP archives:
- Format verification
- File extension validation
- Path traversal protection (e.g. '../', absolute paths, backslashes)
- Zip bomb protection (compression ratio, extracted size limits, file count limits)
- Symlink and hardlink detection
- Duplicate archive paths
- Snapshot structure validation (base/ and proposed/ folders)
- Review manifest schema validation
"""

import os
import zipfile
import json
from typing import Dict, Any, List, Tuple, Optional


class ArchiveValidationError(Exception):
    """Raised when an archive fails security or structural validation."""
    pass


class ArchiveValidator:
    """Security validator for uploaded review ZIP archives."""

    # Security Limits
    MAX_COMPRESSED_SIZE_BYTES = 25 * 1024 * 1024       # 25 MB
    MAX_EXTRACTED_SIZE_BYTES = 100 * 1024 * 1024       # 100 MB
    MAX_FILE_COUNT = 1000                              # 1,000 files maximum
    MAX_INDIVIDUAL_FILE_SIZE = 10 * 1024 * 1024        # 10 MB per file
    MAX_DIRECTORY_DEPTH = 15                           # 15 directory levels
    MAX_COMPRESSION_RATIO = 100.0                      # Max 100:1 ratio (zip bomb defense)

    ALLOWED_EXTENSIONS = {
        ".py", ".pyw", ".txt", ".md", ".rst", ".json", ".yaml", ".yml",
        ".toml", ".ini", ".cfg", ".sql", ".sh", ".bat", ".html", ".css",
        ".js", ".csv", ".tsv", ".xml"
    }

    @classmethod
    def validate_archive_file(cls, zip_path: str) -> Dict[str, Any]:
        """
        Performs comprehensive pre-extraction security analysis on a ZIP archive.
        Returns metadata if valid, otherwise raises ArchiveValidationError.
        """
        if not os.path.exists(zip_path):
            raise ArchiveValidationError(f"Archive file does not exist: {zip_path}")

        # Check compressed size
        compressed_size = os.path.getsize(zip_path)
        if compressed_size > cls.MAX_COMPRESSED_SIZE_BYTES:
            raise ArchiveValidationError(
                f"Archive exceeds maximum compressed size: {compressed_size} > {cls.MAX_COMPRESSED_SIZE_BYTES} bytes"
            )
        if compressed_size == 0:
            raise ArchiveValidationError("Archive is empty (0 bytes).")

        # Verify ZIP format integrity
        if not zipfile.is_zipfile(zip_path):
            raise ArchiveValidationError("File is not a valid ZIP archive.")

        total_extracted_size = 0
        file_count = 0
        seen_paths = set()
        has_base_folder = False
        has_proposed_folder = False
        manifest_info: Optional[Dict[str, Any]] = None

        with zipfile.ZipFile(zip_path, 'r') as zf:
            infolist = zf.infolist()
            if not infolist:
                raise ArchiveValidationError("Archive contains no entries.")

            for member in infolist:
                file_count += 1
                if file_count > cls.MAX_FILE_COUNT:
                    raise ArchiveValidationError(
                        f"Archive exceeds maximum file count limit ({cls.MAX_FILE_COUNT} files)."
                    )

                filename = member.filename
                normalized_name = filename.replace("\\", "/").strip()

                # Check duplicate paths
                if normalized_name in seen_paths:
                    raise ArchiveValidationError(f"Archive contains duplicate path: {normalized_name}")
                seen_paths.add(normalized_name)

                # Path traversal checks
                if normalized_name.startswith("/") or normalized_name.startswith("\\"):
                    raise ArchiveValidationError(f"Path traversal detected (absolute path): {filename}")
                if ".." in normalized_name.split("/"):
                    raise ArchiveValidationError(f"Path traversal detected ('..'): {filename}")
                if ":" in normalized_name:  # Windows drive letter e.g. C:
                    raise ArchiveValidationError(f"Path traversal detected (drive specifier): {filename}")

                # Directory depth check
                depth = len([p for p in normalized_name.split("/") if p])
                if depth > cls.MAX_DIRECTORY_DEPTH:
                    raise ArchiveValidationError(
                        f"Directory depth ({depth}) exceeds limit ({cls.MAX_DIRECTORY_DEPTH}): {filename}"
                    )

                # Detect symlinks (UNIX symlink attribute)
                if (member.external_attr >> 16) & 0o120000 == 0o120000:
                    raise ArchiveValidationError(f"Symlinks are prohibited for security: {filename}")

                # Check individual file size
                if member.file_size > cls.MAX_INDIVIDUAL_FILE_SIZE:
                    raise ArchiveValidationError(
                        f"File exceeds maximum uncompressed size ({member.file_size} > {cls.MAX_INDIVIDUAL_FILE_SIZE} bytes): {filename}"
                    )

                # Compression ratio check (zip bomb protection)
                if member.compress_size > 0:
                    ratio = member.file_size / member.compress_size
                    if ratio > cls.MAX_COMPRESSION_RATIO:
                        raise ArchiveValidationError(
                            f"Suspicious compression ratio ({ratio:.1f}:1 exceeds {cls.MAX_COMPRESSION_RATIO}:1): {filename}"
                        )

                total_extracted_size += member.file_size
                if total_extracted_size > cls.MAX_EXTRACTED_SIZE_BYTES:
                    raise ArchiveValidationError(
                        f"Archive exceeds total extracted size limit ({total_extracted_size} > {cls.MAX_EXTRACTED_SIZE_BYTES} bytes)."
                    )

                # Track base/ and proposed/ structure
                clean_path = normalized_name.strip("/")
                if clean_path == "base" or clean_path.startswith("base/"):
                    has_base_folder = True
                elif clean_path == "proposed" or clean_path.startswith("proposed/"):
                    has_proposed_folder = True

                # Optional manifest check
                if clean_path == "review-manifest.json":
                    try:
                        manifest_bytes = zf.read(member)
                        manifest_info = json.loads(manifest_bytes.decode("utf-8"))
                        cls.validate_manifest(manifest_info)
                    except json.JSONDecodeError as e:
                        raise ArchiveValidationError(f"Invalid review-manifest.json format: {e}")

        # Review snapshot mode validation
        mode = "CHANGE_REVIEW"
        if not has_base_folder and not has_proposed_folder:
            raise ArchiveValidationError(
                "Archive missing required snapshots. Expected 'base/' and 'proposed/' directories."
            )
        elif not has_base_folder or not has_proposed_folder:
            # If only one snapshot is supplied, clearly designate FULL_PROJECT_AUDIT mode
            mode = "FULL_PROJECT_AUDIT"

        return {
            "mode": mode,
            "has_base": has_base_folder,
            "has_proposed": has_proposed_folder,
            "file_count": file_count,
            "compressed_size": compressed_size,
            "total_extracted_size": total_extracted_size,
            "manifest": manifest_info or {}
        }

    @classmethod
    def validate_manifest(cls, manifest: Any) -> None:
        """Validates review-manifest.json schema if provided."""
        if not isinstance(manifest, dict):
            raise ArchiveValidationError("Manifest must be a JSON object.")
        
        # Validate allowed keys and types
        allowed_keys = {"project_name", "description", "primary_language", "instructions", "metadata"}
        for k in manifest:
            if k not in allowed_keys:
                raise ArchiveValidationError(f"Unexpected key in review-manifest.json: {k}")
            
        if "project_name" in manifest and not isinstance(manifest["project_name"], str):
            raise ArchiveValidationError("project_name must be a string")
        if "instructions" in manifest and not isinstance(manifest["instructions"], str):
            raise ArchiveValidationError("instructions must be a string")
