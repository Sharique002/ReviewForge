"""
Isolated Execution & Docker Sandbox Service
CSE476 CA2 — Automated Code Review Board (Q14)

Guarantees safe test execution in an isolated Docker container when available,
and strictly enforces a NOT_RUN fallback when container isolation is offline.
Untrusted user code is NEVER executed directly on the host machine.
"""

import os
import shutil
import subprocess
from typing import Dict, Any, List, Optional


class SandboxService:
    """
    Provides isolated ephemeral execution containers for running test suites.
    Strictly enforces:
    - Network isolation (--network none)
    - Read-only source mounting (:ro)
    - Non-root unprivileged execution (--user 1000:1000)
    - Ephemeral writable temporary directory (--tmpfs /tmp:rw,noexec,nosuid,size=64m)
    - Resource quotas (--cpus, --memory, --cap-drop ALL)
    - Execution timeout enforcement
    - Safe NOT_RUN fallback when Docker is unavailable
    """

    DEFAULT_IMAGE = "reviewforge-sandbox:latest"
    FALLBACK_IMAGE = "python:3.11-slim"
    DEFAULT_CPU_LIMIT = "1.0"
    DEFAULT_MEMORY_LIMIT = "512m"
    DEFAULT_TIMEOUT_SECONDS = 30

    def __init__(
        self,
        image: Optional[str] = None,
        cpu_limit: Optional[str] = None,
        memory_limit: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ):
        self.image = image or self.DEFAULT_IMAGE
        self.cpu_limit = cpu_limit or self.DEFAULT_CPU_LIMIT
        self.memory_limit = memory_limit or self.DEFAULT_MEMORY_LIMIT
        self.timeout_seconds = timeout_seconds or self.DEFAULT_TIMEOUT_SECONDS

    def is_docker_available(self) -> bool:
        """Checks if Docker CLI exists and Docker daemon is responsive."""
        if not shutil.which("docker"):
            return False
        try:
            res = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=3,
                check=False
            )
            return res.returncode == 0
        except Exception:
            return False

    def _resolve_image(self) -> str:
        """Verifies if the custom sandbox image exists, otherwise uses fallback image."""
        try:
            res = subprocess.run(
                ["docker", "image", "inspect", self.image],
                capture_output=True,
                timeout=3,
                check=False
            )
            if res.returncode == 0:
                return self.image
        except Exception:
            pass
        return self.FALLBACK_IMAGE

    def run_isolated_tests(self, project_path: str, changed_files: List[str]) -> Dict[str, Any]:
        """
        Executes pytest inside an isolated ephemeral Docker container.
        Enforces:
        - Network disabled (--network none)
        - Read-only root filesystem (--read-only)
        - Read-only source code volume mount (-v {abs_path}:/app:ro)
        - Non-root user (--user 1000:1000)
        - Isolated in-memory writable temporary directory (--tmpfs /tmp)
        - CPU, memory, and capability drop quotas
        - Strict timeout enforcement
        """
        if not self.is_docker_available():
            return {
                "status": "NOT_RUN",
                "passed": False,
                "tests_executed": 0,
                "tests_passed": 0,
                "tests_failed": 0,
                "coverage_percent": None,
                "reason": "Docker sandbox unavailable; direct host execution of untrusted code is prohibited by security policy."
            }

        abs_path = os.path.abspath(project_path)
        if not os.path.isdir(abs_path):
            return {
                "status": "FAILED",
                "passed": False,
                "tests_executed": 0,
                "tests_passed": 0,
                "tests_failed": 0,
                "coverage_percent": None,
                "reason": f"Project path does not exist: {project_path}"
            }

        image_to_use = self._resolve_image()

        cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "--user", "1000:1000",
            "--cpus", str(self.cpu_limit),
            "--memory", str(self.memory_limit),
            "--cap-drop", "ALL",
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "-v", f"{abs_path}:/app:ro",
            "-w", "/app",
            "-e", "TMPDIR=/tmp",
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            image_to_use,
            "pytest", "-v", "-o", "cache_dir=/tmp/.pytest_cache"
        ]

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False
            )
            output = (res.stdout or "") + "\n" + (res.stderr or "")
            passed = (res.returncode == 0)

            return {
                "status": "SUCCESS" if passed else "FAILED",
                "passed": passed,
                "exit_code": res.returncode,
                "output": output,
                "tests_executed": 1 if passed else 0,
                "tests_passed": 1 if passed else 0,
                "tests_failed": 0 if passed else 1,
                "coverage_percent": None,
                "reason": "Tests executed successfully inside isolated container." if passed else "Tests failed inside sandbox."
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "TIMEOUT",
                "passed": False,
                "tests_executed": 0,
                "tests_passed": 0,
                "tests_failed": 0,
                "coverage_percent": None,
                "reason": f"Execution timed out after {self.timeout_seconds} seconds inside sandbox container."
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "passed": False,
                "tests_executed": 0,
                "tests_passed": 0,
                "tests_failed": 0,
                "coverage_percent": None,
                "reason": f"Sandbox container execution error: {e}"
            }

    # Backward compatibility classmethods
    @classmethod
    def get_default_service(cls) -> "SandboxService":
        return cls()
