"""
Generates reusable demo test fixtures for the three assignment scenarios.
"""

import os
import zipfile


def build_fixtures():
    os.makedirs("fixtures", exist_ok=True)

    # Fixture 1: Clean Change (Approve)
    f1_path = os.path.join("fixtures", "scenario_1_clean.zip")
    with zipfile.ZipFile(f1_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("base/math_ops.py", "def add(a: int, b: int) -> int:\n    return a + b\n")
        zf.writestr("proposed/math_ops.py", (
            "def add(a: int, b: int) -> int:\n"
            "    return a + b\n\n\n"
            "def multiply(a: int, b: int) -> int:\n"
            "    return a * b\n"
        ))
        zf.writestr("proposed/tests/test_math_ops.py", (
            "from math_ops import add, multiply\n\n\n"
            "def test_add():\n"
            "    assert add(2, 3) == 5\n\n\n"
            "def test_multiply():\n"
            "    assert multiply(2, 3) == 6\n"
        ))
        zf.writestr("review-manifest.json", '{"project_name": "MathService", "description": "Clean arithmetic changes"}')

    # Fixture 2: Security Issue (Request Changes + Patch Proposal)
    f2_path = os.path.join("fixtures", "scenario_2_security.zip")
    with zipfile.ZipFile(f2_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("base/auth.py", "def check_user(username: str) -> bool:\n    return True\n")
        zf.writestr("proposed/auth.py", (
            "# Unsafe credential and dynamic evaluation\n"
            "API_KEY = 'sk-live-abcdef1234567890abcdef12345678'\n\n"
            "def check_user(username: str) -> bool:\n"
            "    # Evaluates user input unsafely\n"
            "    return eval(username)\n"
        ))
        zf.writestr("proposed/tests/test_auth.py", "def test_dummy():\n    pass\n")
        zf.writestr("review-manifest.json", '{"project_name": "AuthService", "description": "Authentication module modification"}')

    # Fixture 2-Resolved: Auto-Remediated Safe Auth (Approve - All Green)
    f2_res_path = os.path.join("fixtures", "scenario_2_resolved.zip")
    with zipfile.ZipFile(f2_res_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("base/auth.py", "def check_user(username: str) -> bool:\n    return True\n")
        zf.writestr("proposed/auth.py", (
            "import ast\n"
            "import os\n\n"
            "API_KEY = os.environ.get('AUTH_API_KEY', '')\n\n\n"
            "def check_user(username: str) -> bool:\n"
            "    try:\n"
            "        return bool(ast.literal_eval(username))\n"
            "    except (ValueError, SyntaxError):\n"
            "        return bool(username)\n"
        ))
        zf.writestr("proposed/tests/test_auth.py", (
            "from auth import check_user\n\n\n"
            "def test_check_user():\n"
            "    assert check_user('\"admin\"') is True\n"
        ))
        zf.writestr("review-manifest.json", '{"project_name": "AuthService [Auto-Remediated & Verified]", "description": "Remediated safe authentication service"}')

    # Fixture 3: Missing Tests & Style Defect (Request Changes)
    f3_path = os.path.join("fixtures", "scenario_3_style_tests.zip")
    with zipfile.ZipFile(f3_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("base/pipeline.py", "def process():\n    return 100\n")
        zf.writestr("proposed/pipeline.py", (
            "import os\n"
            "import sys\n"
            "def process():\n"
            "    unused_var = 50\n"
            "    return 100\n"
        ))
        zf.writestr("review-manifest.json", '{"project_name": "DataPipeline", "description": "Data processing without tests"}')

    # Fixture 3-Resolved: Clean Pipeline with Tests (Approve - All Green)
    f3_res_path = os.path.join("fixtures", "scenario_3_resolved.zip")
    with zipfile.ZipFile(f3_res_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("base/pipeline.py", "def process() -> int:\n    return 100\n")
        zf.writestr("proposed/pipeline.py", (
            "def process() -> int:\n"
            "    return 100\n"
        ))
        zf.writestr("proposed/tests/test_pipeline.py", (
            "from pipeline import process\n\n\n"
            "def test_process():\n"
            "    assert process() == 100\n"
        ))
        zf.writestr("review-manifest.json", '{"project_name": "DataPipeline [Auto-Remediated & Verified]", "description": "Clean data processing with tests"}')

    print("Fixtures created successfully in fixtures/:")
    print(" - fixtures/scenario_1_clean.zip")
    print(" - fixtures/scenario_2_security.zip")
    print(" - fixtures/scenario_3_style_tests.zip")


if __name__ == "__main__":
    build_fixtures()
