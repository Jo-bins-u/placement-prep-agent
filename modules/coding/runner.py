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
from typing import Any


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
    with tempfile.TemporaryDirectory(prefix="placement_dsa_") as tmpdir:
        script = os.path.join(tmpdir, "solution.py")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write(harness)
        start = time.perf_counter()
        docker = shutil.which("docker")
        command = [sys.executable, script]
        if docker:
            command = [docker, "run", "--rm", "--network", "none", "--cpus", "0.5", "--memory", "256m", "--pids-limit", "64", "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", "65532:65532", "-v", f"{tmpdir}:/sandbox:ro", "python:3.13-slim", "python", "/sandbox/solution.py"]
        try:
            process = subprocess.run(command, capture_output=True, text=True, timeout=timeout, cwd=tmpdir, env={"PATH": os.environ.get("PATH", "")})
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "input": args, "expected": expected, "actual": None, "execution_time_ms": round((time.perf_counter() - start) * 1000, 1)}
        elapsed = round((time.perf_counter() - start) * 1000, 1)
        if process.returncode != 0:
            return {"status": "error", "input": args, "expected": expected, "actual": None, "message": process.stderr.strip() or "Compilation or runtime error.", "execution_time_ms": elapsed}
        output = process.stdout.strip().splitlines()
        if not output:
            return {"status": "error", "input": args, "expected": expected, "actual": None, "message": "The function returned no serializable output.", "execution_time_ms": elapsed}
        try:
            actual = json.loads(output[-1])
        except json.JSONDecodeError:
            actual = output[-1]
        if isinstance(actual, dict) and "error" in actual:
            return {"status": "error", "input": args, "expected": expected, "actual": None, "message": actual["error"], "execution_time_ms": elapsed}
        return {"status": "passed" if _equal(actual, expected) else "failed", "input": args, "expected": expected, "actual": actual, "execution_time_ms": elapsed}


def _tests(problem: dict[str, Any], hidden: bool) -> list[dict[str, Any]]:
    key = "hidden_test_cases" if hidden else "visible_test_cases"
    cases = problem[key] if key in problem else ([] if hidden else problem.get("examples", []))
    return [case for case in cases if isinstance(case, dict) and isinstance(case.get("args"), list)]


def _result(results: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    total = len(results)
    passed = sum(item["status"] == "passed" for item in results)
    first_error = next((item for item in results if item["status"] in {"error", "timeout"}), None)
    if total == 0:
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


def run_candidate_code(problem: dict[str, Any], code: str) -> dict[str, Any]:
    return _result([_run_case(problem, code or "", case) for case in _tests(problem, hidden=False)], "run")


def evaluate_submission(problem: dict[str, Any], code: str) -> dict[str, Any]:
    results = [_run_case(problem, code or "", case) for case in _tests(problem, hidden=True)]
    summary = _result(results, "submit")
    total = summary["total_tests"]
    passed = summary["passed_tests"]
    score = round((passed / total) * 100, 1) if total else 0.0
    summary.update({"coding_score": score, "score": score, "execution_time": summary["execution_time_ms"], "memory_usage": 0, "feedback": summary["message"], "status": "correct" if score == 100 and total else ("partially_correct" if passed else summary["status"])})
    return summary
