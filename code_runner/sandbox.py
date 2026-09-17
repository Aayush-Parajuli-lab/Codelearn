"""
Code Runner — Isolated Execution Sandbox
===========================================
Executes untrusted student code and returns captured stdout/stderr so the
Automated Code Evaluation algorithm (Algorithm 1) can compare it against
expected test-case output.

Two execution modes, selected transparently by the CODE_RUNNER_URL
environment variable — the public `execute()` API and its return type
(`ExecutionResult`) are identical either way, so `code_runner/evaluator.py`
never needs to know which mode is active:

  - CODE_RUNNER_URL unset (local dev, `manage.py demo_pipeline`, tests):
    runs directly via `subprocess` + `resource` limits, in-process.
  - CODE_RUNNER_URL set (podman-compose.yml sets this to the code-runner
    service's internal address): forwards the request over HTTP to the
    isolated `code_runner_service` container instead — a locked-down,
    network-restricted, non-root, read-only-rootfs container whose only
    job is running untrusted code. See code_runner_service/app.py and
    Dockerfile, and the `code-runner` service in podman-compose.yml.

Design notes
-------------
* Never uses shell=True. Never trusts the source code string as
  anything other than data.
"""
from __future__ import annotations

import os
import resource
import subprocess
import tempfile
import time
from dataclasses import dataclass

DEFAULT_TIMEOUT_SECONDS = 5
DEFAULT_MEMORY_LIMIT_MB = 128
MAX_OUTPUT_CHARS = 10_000
CODE_RUNNER_URL = os.environ.get("CODE_RUNNER_URL", "").rstrip("/")


@dataclass
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    execution_time_ms: float


def _limit_resources(memory_mb: int):
    """Called in the child process (via preexec_fn) to cap memory and
    disable core dumps before the student's code ever runs."""
    mem_bytes = memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run_python(source_code: str, stdin_data: str = "", timeout: int = DEFAULT_TIMEOUT_SECONDS,
                memory_mb: int = DEFAULT_MEMORY_LIMIT_MB) -> ExecutionResult:
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = os.path.join(tmpdir, "submission.py")
        with open(script_path, "w") as f:
            f.write(source_code)
        return _execute(
            ["python3", "-I", script_path],  # -I: isolated mode, ignores env/user site
            stdin_data, timeout, memory_mb,
        )


def run_c(source_code: str, stdin_data: str = "", timeout: int = DEFAULT_TIMEOUT_SECONDS,
          memory_mb: int = DEFAULT_MEMORY_LIMIT_MB) -> ExecutionResult:
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = os.path.join(tmpdir, "submission.c")
        bin_path = os.path.join(tmpdir, "submission")
        with open(src_path, "w") as f:
            f.write(source_code)

        compile_proc = subprocess.run(
            ["gcc", src_path, "-O2", "-o", bin_path],
            capture_output=True, text=True, timeout=timeout,
        )
        if compile_proc.returncode != 0:
            return ExecutionResult(
                stdout="", stderr=compile_proc.stderr[:MAX_OUTPUT_CHARS],
                exit_code=compile_proc.returncode, timed_out=False, execution_time_ms=0.0,
            )
        return _execute([bin_path], stdin_data, timeout, memory_mb)


def run_java(source_code: str, stdin_data: str = "", timeout: int = DEFAULT_TIMEOUT_SECONDS,
             memory_mb: int = DEFAULT_MEMORY_LIMIT_MB) -> ExecutionResult:
    with tempfile.TemporaryDirectory() as tmpdir:
        # Java requires the public class name to match the filename
        src_path = os.path.join(tmpdir, "Main.java")
        with open(src_path, "w") as f:
            f.write(source_code)

        compile_proc = subprocess.run(
            ["javac", src_path], capture_output=True, text=True,
            timeout=timeout, cwd=tmpdir,
        )
        if compile_proc.returncode != 0:
            return ExecutionResult(
                stdout="", stderr=compile_proc.stderr[:MAX_OUTPUT_CHARS],
                exit_code=compile_proc.returncode, timed_out=False, execution_time_ms=0.0,
            )
        return _execute(
            ["java", "-Xmx%dm" % memory_mb, "-cp", tmpdir, "Main"],
            stdin_data, timeout, memory_mb,
        )


def _execute(cmd: list[str], stdin_data: str, timeout: int, memory_mb: int) -> ExecutionResult:
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=timeout,
            preexec_fn=lambda: _limit_resources(memory_mb) if os.name == "posix" else None,
        )
        elapsed_ms = (time.monotonic() - start) * 1000
        return ExecutionResult(
            stdout=proc.stdout[:MAX_OUTPUT_CHARS],
            stderr=proc.stderr[:MAX_OUTPUT_CHARS],
            exit_code=proc.returncode,
            timed_out=False,
            execution_time_ms=round(elapsed_ms, 2),
        )
    except subprocess.TimeoutExpired:
        elapsed_ms = (time.monotonic() - start) * 1000
        return ExecutionResult(
            stdout="", stderr="Execution timed out",
            exit_code=-1, timed_out=True, execution_time_ms=round(elapsed_ms, 2),
        )


RUNNERS = {
    "PYTHON": run_python,
    "C": run_c,
    "JAVA": run_java,
}


def _execute_remote(language: str, source_code: str, stdin_data: str, timeout: int, memory_mb: int) -> ExecutionResult:
    """Forwards execution to the isolated code-runner container over HTTP."""
    import requests  # imported lazily so local-mode deployments don't need it

    resp = requests.post(
        f"{CODE_RUNNER_URL}/execute",
        json={
            "language": language,
            "source_code": source_code,
            "stdin_data": stdin_data,
            "timeout": timeout,
            "memory_mb": memory_mb,
        },
        timeout=timeout + 5,  # allow a little headroom over the sandbox's own timeout
    )
    resp.raise_for_status()
    data = resp.json()
    return ExecutionResult(
        stdout=data["stdout"], stderr=data["stderr"], exit_code=data["exit_code"],
        timed_out=data["timed_out"], execution_time_ms=data["execution_time_ms"],
    )


def execute(language: str, source_code: str, stdin_data: str = "", timeout: int = DEFAULT_TIMEOUT_SECONDS,
            memory_mb: int = DEFAULT_MEMORY_LIMIT_MB) -> ExecutionResult:
    if language not in RUNNERS:
        raise ValueError(f"Unsupported language: {language}")

    if CODE_RUNNER_URL:
        return _execute_remote(language, source_code, stdin_data, timeout, memory_mb)

    return RUNNERS[language](source_code, stdin_data, timeout=timeout, memory_mb=memory_mb)
