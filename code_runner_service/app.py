"""
CodeLearn Code Runner Service
================================
A minimal, dependency-light HTTP service that executes untrusted student
code and returns the result. Runs in its own container
(`code_runner_service/Dockerfile`) — separate from the main Django app —
so that:

  - a crash, resource exhaustion, or escape attempt in student code can't
    touch the web app's process or filesystem
  - the container can be locked down independently: read-only rootfs,
    no outbound network, non-root user, tight CPU/memory caps
    (see podman-compose.yml)

This mirrors code_runner/sandbox.py's logic (same timeout/memory-limit
approach) but is intentionally self-contained — no Django import — so
this image only needs Flask + the language runtimes, not the whole app.

POST /execute
    {
      "language": "PYTHON" | "C" | "JAVA",
      "source_code": "...",
      "stdin_data": "...",
      "timeout": 5,        # optional, seconds
      "memory_mb": 128     # optional
    }
  -> 200
    {
      "stdout": "...", "stderr": "...", "exit_code": 0,
      "timed_out": false, "execution_time_ms": 12.3
    }

GET /health -> 200 {"status": "ok"}
"""
import os
import resource
import subprocess
import tempfile
import time

from flask import Flask, jsonify, request

app = Flask(__name__)

MAX_OUTPUT_CHARS = 10_000
DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("RUNNER_DEFAULT_TIMEOUT", "5"))
DEFAULT_MEMORY_MB = int(os.environ.get("RUNNER_DEFAULT_MEMORY_MB", "128"))


def _limit_resources(memory_mb):
    mem_bytes = memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _execute(cmd, stdin_data, timeout, memory_mb):
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, input=stdin_data, capture_output=True, text=True, timeout=timeout,
            preexec_fn=lambda: _limit_resources(memory_mb),
        )
        elapsed_ms = (time.monotonic() - start) * 1000
        return {
            "stdout": proc.stdout[:MAX_OUTPUT_CHARS],
            "stderr": proc.stderr[:MAX_OUTPUT_CHARS],
            "exit_code": proc.returncode,
            "timed_out": False,
            "execution_time_ms": round(elapsed_ms, 2),
        }
    except subprocess.TimeoutExpired:
        elapsed_ms = (time.monotonic() - start) * 1000
        return {
            "stdout": "", "stderr": "Execution timed out",
            "exit_code": -1, "timed_out": True,
            "execution_time_ms": round(elapsed_ms, 2),
        }


def run_python(source_code, stdin_data, timeout, memory_mb):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "submission.py")
        with open(path, "w") as f:
            f.write(source_code)
        return _execute(["python3", "-I", path], stdin_data, timeout, memory_mb)


def run_c(source_code, stdin_data, timeout, memory_mb):
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "submission.c")
        binp = os.path.join(tmp, "submission")
        with open(src, "w") as f:
            f.write(source_code)
        compile_proc = subprocess.run(
            ["gcc", src, "-O2", "-o", binp], capture_output=True, text=True, timeout=timeout,
        )
        if compile_proc.returncode != 0:
            return {
                "stdout": "", "stderr": compile_proc.stderr[:MAX_OUTPUT_CHARS],
                "exit_code": compile_proc.returncode, "timed_out": False, "execution_time_ms": 0.0,
            }
        return _execute([binp], stdin_data, timeout, memory_mb)


def run_java(source_code, stdin_data, timeout, memory_mb):
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "Main.java")
        with open(src, "w") as f:
            f.write(source_code)
        compile_proc = subprocess.run(
            ["javac", src], capture_output=True, text=True, timeout=timeout, cwd=tmp,
        )
        if compile_proc.returncode != 0:
            return {
                "stdout": "", "stderr": compile_proc.stderr[:MAX_OUTPUT_CHARS],
                "exit_code": compile_proc.returncode, "timed_out": False, "execution_time_ms": 0.0,
            }
        return _execute(
            ["java", f"-Xmx{memory_mb}m", "-cp", tmp, "Main"], stdin_data, timeout, memory_mb,
        )


RUNNERS = {"PYTHON": run_python, "C": run_c, "JAVA": run_java}


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/execute", methods=["POST"])
def execute():
    payload = request.get_json(force=True, silent=True) or {}
    language = payload.get("language")
    source_code = payload.get("source_code", "")
    stdin_data = payload.get("stdin_data", "")
    timeout = int(payload.get("timeout", DEFAULT_TIMEOUT_SECONDS))
    memory_mb = int(payload.get("memory_mb", DEFAULT_MEMORY_MB))

    if language not in RUNNERS:
        return jsonify({"error": f"Unsupported language: {language}"}), 400

    result = RUNNERS[language](source_code, stdin_data, timeout, memory_mb)
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6000)
