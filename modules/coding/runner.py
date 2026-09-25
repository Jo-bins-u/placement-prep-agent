"""Contract-aware DSA execution and deterministic judging."""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Any

# Sandbox policy (see SECURITY notes in README):
#   PREPWISE_SANDBOX unset / "docker" -> run only inside the locked-down Docker container.
#                                        If Docker isn't running, code is NOT executed.
#   PREPWISE_SANDBOX=local            -> explicit opt-in to run code as a plain local process.
#                                        Unsafe: submitted code has the app's full access to
#                                        this machine. Only for a single-user dev laptop / tests.
SANDBOX_UNAVAILABLE_MESSAGE = (
    "The code runner is unavailable: start Docker Desktop so submissions run in an isolated "
    "sandbox (or, on a private dev machine only, set PREPWISE_SANDBOX=local)."
)


def _normalize(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    return value


def _equal(actual: Any, expected: Any) -> bool:
    actual, expected = _normalize(actual), _normalize(expected)
    if isinstance(actual, float) or isinstance(expected, float):
        try:
            return abs(float(actual) - float(expected)) <= 1e-6
        except (TypeError, ValueError):
            return False
    return actual == expected


def _run_case(problem: dict[str, Any], code: str, test_case: dict[str, Any], timeout: float = 3.0) -> dict[str, Any]:
    signature = problem.get("function_signature") or {}
    function_name = signature.get("name", "solution")
    args = test_case.get("args")
    if not isinstance(args, list):
        return {"status": "error", "message": "Invalid executable test contract: args must be a list."}
    expected = test_case.get("expected")
    payload = repr(args)
    harness = f'''import json
{code}

try:
    _value = {function_name}(*{payload})
    print(json.dumps(_value, ensure_ascii=False))
except Exception as _exc:
    print(json.dumps({{"error": str(_exc)}}))
'''
    mode = sandbox_mode()
    if mode is None:
        return {"status": "unavailable", "input": args, "expected": expected, "actual": None,
                "message": SANDBOX_UNAVAILABLE_MESSAGE, "execution_time_ms": 0}
    if timeout <= 0.2:  # the request's overall time budget is used up
        return {"status": "timeout", "input": args, "expected": expected, "actual": None,
                "message": "Skipped: the time budget for this run was used up by earlier tests.", "execution_time_ms": 0}
    with tempfile.TemporaryDirectory(prefix="placement_dsa_") as tmpdir:
        script = os.path.join(tmpdir, "solution.py")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write(harness)
        # The sandbox user (uid 65532) must be able to read the read-only mounted folder. It only
        # holds this one throwaway script, so world-readable is fine.
        os.chmod(tmpdir, 0o755)  # nosec B103
        os.chmod(script, 0o644)
        start = time.perf_counter()
        container = None
        extra = {}
        if mode == "docker":
            docker = _docker_command()
            container = f"prepwise-{uuid.uuid4().hex[:16]}"
            command = [
                docker, "run", "--rm", "--name", container,
                "--network", "none",                      # no internet or LAN access
                "--cpus", "0.5", "--memory", "256m", "--pids-limit", "64",
                "--read-only",
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",  # nosec B108
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--user", "65532:65532",                  # not root inside the container
                "-v", f"{tmpdir}:/sandbox:ro",
                SANDBOX_IMAGE, "python", "-I", "/sandbox/solution.py",
            ]
            timeout = timeout + DOCKER_STARTUP_ALLOWANCE
        else:
            # Explicitly allowed local run: isolated interpreter (-I ignores env vars and user
            # site-packages), empty environment, and OS resource limits where supported.
            command = [sys.executable, "-I", script]
            extra = {"start_new_session": True}  # own process group, so the whole tree can be killed
            if os.name == "posix":  # the harness caps itself before any submitted code runs
                with open(script, "w", encoding="utf-8") as handle:
                    handle.write(_LOCAL_PROLOGUE + harness)
        env = {"PATH": os.environ.get("PATH", "")}
        if os.name == "nt" and os.environ.get("SYSTEMROOT"):
            env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
        returncode, stdout, stderr, outcome = _run_bounded(command, timeout, container, cwd=tmpdir, env=env, **extra)
        elapsed = round((time.perf_counter() - start) * 1000, 1)
        if outcome == "timeout":
            return {"status": "timeout", "input": args, "expected": expected, "actual": None, "execution_time_ms": elapsed}
        if outcome == "too_much_output":
            return {"status": "error", "input": args, "expected": expected, "actual": None, "execution_time_ms": elapsed,
                    "message": f"Your program printed more than {MAX_OUTPUT_BYTES // 1024} KB of output and was stopped."}
        if returncode != 0:
            return {"status": "error", "input": args, "expected": expected, "actual": None, "message": _clip(stderr.strip()) or "Compilation or runtime error.", "execution_time_ms": elapsed}
        output = stdout.strip().splitlines()
        if not output:
            return {"status": "error", "input": args, "expected": expected, "actual": None, "message": "The function returned no serializable output.", "execution_time_ms": elapsed}
        try:
            actual = json.loads(output[-1])
        except json.JSONDecodeError:
            actual = output[-1]
        if isinstance(actual, dict) and "error" in actual:
            return {"status": "error", "input": args, "expected": expected, "actual": None, "message": _clip(str(actual["error"])), "execution_time_ms": elapsed}
        return {"status": "passed" if _equal(actual, expected) else "failed", "input": args, "expected": expected, "actual": actual, "execution_time_ms": elapsed}


MAX_OUTPUT_BYTES = 64 * 1024   # per stream; more than this and the program is stopped
MESSAGE_LIMIT = 2000           # characters of an error message kept (the end of a traceback)
RUN_BUDGET_SECONDS = 20        # all visible tests of one "Run"
SUBMIT_BUDGET_SECONDS = 40     # all hidden tests of one "Submit"


def _clip(text: str) -> str:
    return text if len(text) <= MESSAGE_LIMIT else "..." + text[-MESSAGE_LIMIT:]


def _kill(process, container) -> None:
    if container:  # killing the docker CLI does not stop the container itself
        try:
            subprocess.run([_docker_command(), "kill", container], capture_output=True, timeout=10)  # nosec B603
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        if os.name == "posix" and not container:
            import signal
            os.killpg(process.pid, signal.SIGKILL)  # the whole process group, including forked children
        else:
            process.kill()
    except (OSError, ProcessLookupError):
        pass


def _run_bounded(command, timeout: float, container, **kwargs):
    """Run with a wall-clock timeout and a cap on captured output, so a program that prints
    endlessly can't exhaust the server's memory. Returns (returncode, stdout, stderr, outcome)
    where outcome is "ok", "timeout" or "too_much_output"."""
    import threading

    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)  # nosec B603
    buffers = {"out": bytearray(), "err": bytearray()}
    overflow = threading.Event()

    def pump(stream, key):
        buffer = buffers[key]
        while True:
            try:
                chunk = stream.read1(65536) if hasattr(stream, "read1") else stream.read(65536)
            except (OSError, ValueError):  # pipe closed below after a stuck grandchild
                break
            if not chunk:
                break
            room = MAX_OUTPUT_BYTES - len(buffer)
            if room > 0:
                buffer.extend(chunk[:room])
            if len(chunk) > room and not overflow.is_set():
                overflow.set()
                _kill(process, container)
        try:
            stream.close()
        except (OSError, ValueError):
            pass

    readers = [threading.Thread(target=pump, args=(process.stdout, "out"), daemon=True),
               threading.Thread(target=pump, args=(process.stderr, "err"), daemon=True)]
    for reader in readers:
        reader.start()
    outcome = "ok"
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        outcome = "timeout"
        _kill(process, container)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
    for reader in readers:
        reader.join(timeout=2)
    for stream in (process.stdout, process.stderr):  # a detached grandchild may still hold the pipes
        try:
            stream.close()
        except (OSError, ValueError):
            pass
    if overflow.is_set():
        outcome = "too_much_output"
    decode = lambda data: bytes(data).decode("utf-8", "replace")  # noqa: E731
    return process.returncode, decode(buffers["out"]), decode(buffers["err"]), outcome


_DOCKER_STATE = {}
SANDBOX_IMAGE = os.getenv("PREPWISE_SANDBOX_IMAGE", "python:3.13-slim")
DOCKER_STARTUP_ALLOWANCE = 2.0  # container start-up time, on top of the per-test limit


def _docker_command():
    """Path to docker only if the daemon actually responds (checked once per process)."""
    if "path" not in _DOCKER_STATE:
        path = shutil.which("docker")
        usable = False
        if path:
            try:
                usable = subprocess.run([path, "info"], capture_output=True, timeout=5).returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                usable = False
        _DOCKER_STATE["path"] = path if usable else None
    return _DOCKER_STATE["path"]


def sandbox_mode():
    """'docker', 'local' (explicitly allowed), or None when code must not be executed."""
    choice = os.getenv("PREPWISE_SANDBOX", "docker").strip().lower()
    if choice == "local":
        return "local"
    return "docker" if _docker_command() else None


_LOCAL_PROLOGUE = """import resource as _r
for _name, _value in (("RLIMIT_CPU", 5), ("RLIMIT_AS", 512 * 1024 * 1024), ("RLIMIT_FSIZE", 1024 * 1024), ("RLIMIT_NPROC", 0)):
    if hasattr(_r, _name):
        try:
            _r.setrlimit(getattr(_r, _name), (_value, _value))
        except (ValueError, OSError):
            pass
del _r, _name, _value
"""


def _tests(problem: dict[str, Any], hidden: bool) -> list[dict[str, Any]]:
    key = "hidden_test_cases" if hidden else "visible_test_cases"
    cases = problem[key] if key in problem else ([] if hidden else problem.get("examples", []))
    return [case for case in cases if isinstance(case, dict) and isinstance(case.get("args"), list)]


def _result(results: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    total = len(results)
    passed = sum(item["status"] == "passed" for item in results)
    first_error = next((item for item in results if item["status"] in {"error", "timeout"}), None)
    if any(item["status"] == "unavailable" for item in results):
        status, message = "unavailable", SANDBOX_UNAVAILABLE_MESSAGE
    elif total == 0:
        status = "configuration_error"
        message = "No executable test cases were generated for this problem."
    elif first_error and first_error["status"] == "timeout":
        status, message = "timeout", "Execution exceeded the time limit."
    elif first_error:
        status, message = "runtime_error", first_error.get("message", "The program could not be executed.")
    elif passed == total:
        status, message = "passed", "All executed tests passed."
    else:
        status, message = "failed", "One or more executed tests failed."
    return {"status": status, "mode": mode, "passed_tests": passed, "total_tests": total, "tests": results, "execution_time_ms": round(sum(item.get("execution_time_ms", 0) for item in results), 1), "message": message, "output": message}


def _run_all(problem: dict[str, Any], code: str, cases: list, budget: float) -> list:
    """Run test cases one after another within an overall wall-clock budget."""
    deadline = time.monotonic() + budget
    return [_run_case(problem, code or "", case, timeout=min(3.0, deadline - time.monotonic())) for case in cases]


def run_candidate_code(problem: dict[str, Any], code: str) -> dict[str, Any]:
    return _result(_run_all(problem, code, _tests(problem, hidden=False), RUN_BUDGET_SECONDS), "run")


def evaluate_submission(problem: dict[str, Any], code: str) -> dict[str, Any]:
    results = _run_all(problem, code, _tests(problem, hidden=True), SUBMIT_BUDGET_SECONDS)
    summary = _result(results, "submit")
    total = summary["total_tests"]
    passed = summary["passed_tests"]
    score = round((passed / total) * 100, 1) if total else 0.0
    summary.update({"coding_score": score, "score": score, "execution_time": summary["execution_time_ms"], "memory_usage": 0, "feedback": summary["message"], "status": "correct" if score == 100 and total else ("partially_correct" if passed else summary["status"])})
    return summary
