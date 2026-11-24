"""
Diff Tools
CSE476 CA2 — Automated Code Review Board (Q14)

Tools for the Diff Agent:
1. identify_changed_files(base_path, proposed_path)
2. extract_file_diff(base_path, proposed_path, relative_file)
"""

import os
import difflib
from typing import Dict, Any, List, Tuple


class DiffTools:
    """Provides file comparison, change discovery, and unified diff generation."""

    @staticmethod
    def identify_changed_files(base_path: str, proposed_path: str) -> Dict[str, Any]:
        """
        Scans base and proposed directories, classifying files into:
        - added
        - modified
        - deleted
        - renamed
        """
        base_files = {}
        proposed_files = {}

        if base_path and os.path.exists(base_path):
            for root, _, files in os.walk(base_path):
                for f in files:
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, base_path).replace("\\", "/")
                    try:
                        with open(full_p, "rb") as fp:
                            base_files[rel_p] = fp.read()
                    except Exception:
                        pass

        if proposed_path and os.path.exists(proposed_path):
            for root, _, files in os.walk(proposed_path):
                for f in files:
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, proposed_path).replace("\\", "/")
                    try:
                        with open(full_p, "rb") as fp:
                            proposed_files[rel_p] = fp.read()
                    except Exception:
                        pass

        added = []
        modified = []
        deleted = []
        renamed = []

        base_set = set(base_files.keys())
        prop_set = set(proposed_files.keys())

        # Exact path matches
        common = base_set.intersection(prop_set)
        for rel_p in common:
            if base_files[rel_p] != proposed_files[rel_p]:
                modified.append(rel_p)

        # Potential adds & deletes
        potential_added = prop_set - base_set
        potential_deleted = base_set - prop_set

        # Detect renames by identical content or high similarity
        matched_added = set()
        matched_deleted = set()

        for del_file in potential_deleted:
            del_content = base_files[del_file]
            for add_file in potential_added:
                if add_file not in matched_added and del_content == proposed_files[add_file]:
                    renamed.append({"from": del_file, "to": add_file})
                    matched_added.add(add_file)
                    matched_deleted.add(del_file)
                    break

        added = sorted(list(potential_added - matched_added))
        deleted = sorted(list(potential_deleted - matched_deleted))
        modified = sorted(modified)

        # All touched files in proposed snapshot
        touched_files = sorted(list(set(modified + added + [r["to"] for r in renamed])))

        return {
            "touched_files": touched_files,
            "added": added,
            "modified": modified,
            "deleted": deleted,
            "renamed": renamed,
            "base_file_count": len(base_files),
            "proposed_file_count": len(proposed_files)
        }

    @staticmethod
    def extract_file_diff(base_path: str, proposed_path: str, relative_file: str) -> Dict[str, Any]:
        """Generates a unified diff for a single file between base and proposed snapshots."""
        base_file_path = os.path.join(base_path, relative_file) if base_path else ""
        prop_file_path = os.path.join(proposed_path, relative_file) if proposed_path else ""

        base_lines = []
        prop_lines = []

        if base_file_path and os.path.exists(base_file_path):
            try:
                with open(base_file_path, "r", encoding="utf-8", errors="replace") as f:
                    base_lines = f.readlines()
            except Exception:
                base_lines = []

        if prop_file_path and os.path.exists(prop_file_path):
            try:
                with open(prop_file_path, "r", encoding="utf-8", errors="replace") as f:
                    prop_lines = f.readlines()
            except Exception:
                prop_lines = []

        diff = list(difflib.unified_diff(
            base_lines,
            prop_lines,
            fromfile=f"a/{relative_file}",
            tofile=f"b/{relative_file}",
            lineterm=""
        ))

        diff_text = "\n".join(diff)
        lines_added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
        lines_deleted = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))

        return {
            "file": relative_file,
            "unified_diff": diff_text,
            "lines_added": lines_added,
            "lines_deleted": lines_deleted,
            "is_empty": len(diff) == 0
        }
