"""Canonical DSA problem generation and validation service."""

from __future__ import annotations

import hashlib
import json
import random
import re
import uuid
from copy import deepcopy
from typing import Any, Optional

from services.llm_service import request_json

from modules.coding.dsa_bank import PROBLEMS

TOPICS = {
    "arrays", "strings", "hashing", "two_pointers", "sliding_window", "binary_search",
    "linked_lists", "stacks", "queues", "trees", "graphs", "greedy", "backtracking",
    "dynamic_programming", "recursion", "sorting", "searching", "heap", "bit_manipulation",
}
DIFFICULTIES = {"easy", "medium", "hard"}
LANGUAGES = {"python", "java", "c++", "javascript"}
ALIASES = {
    "array": "arrays", "string": "strings", "hash": "hashing", "two_pointer": "two_pointers",
    "window": "sliding_window", "binary search": "binary_search", "linked_list": "linked_lists",
    "stack": "stacks", "queue": "queues", "tree": "trees", "graph": "graphs", "dp": "dynamic_programming",
    "dynamic programming": "dynamic_programming", "bit manipulation": "bit_manipulation",
}


def normalize_topic(value: Optional[str]) -> str:
    key = (value or "arrays").strip().lower().replace("-", "_")
    key = ALIASES.get(key, key)
    return key if key in TOPICS else "arrays"


def normalize_language(value: Optional[str]) -> str:
    key = (value or "python").strip().lower()
    aliases = {"py": "python", "python3": "python", "cpp": "c++", "c++17": "c++", "js": "javascript", "node": "javascript"}
    return aliases.get(key, key if key in LANGUAGES else "python")


def _case(args: list[Any], expected: Any) -> dict[str, Any]:
    return {"args": args, "expected": expected, "input": repr(args), "output": str(expected)}


def _canonical_hash(topic: str, difficulty: str, title: str, description: str) -> str:
    canonical = "|".join([topic or "", difficulty or "", title or "", description or ""])
    return hashlib.sha256(re.sub(r"\W+", " ", canonical.lower()).encode()).hexdigest()


def _from_bank_entry(entry: dict[str, Any]) -> dict[str, Any]:
    visible = [_case(list(args), expected) for args, expected in entry["visible"]]
    hidden = [_case(list(args), expected) for args, expected in entry["hidden"]]
    return {
        "title": entry["title"], "description": entry["description"],
        "difficulty": entry["difficulty"], "topic": entry["topic"], "subtopic": entry["topic"],
        "skills": [entry["topic"], entry["difficulty"]],
        "constraints": ["Inputs satisfy the stated function contract.", "Return the exact requested type."],
        "examples": visible, "visible_test_cases": visible, "hidden_test_cases": hidden,
        "function_signature": {"name": entry["name"], "parameters": [{"name": n, "type": t} for n, t in entry["params"]],
                               "return_type": entry["returns"]},
        "reference_solution": {"python": entry["solution"]}, "source": "curated_bank",
    }


def _fallback(topic: str, difficulty: str, avoid_hashes: Optional[list[str]] = None) -> dict[str, Any]:
    """A curated problem for exactly this topic and difficulty, avoiding recently seen ones when possible."""
    matches = [e for e in PROBLEMS if e["topic"] == topic and e["difficulty"] == difficulty]
    if not matches:  # every combination is covered today; keep a safe default anyway
        matches = [e for e in PROBLEMS if e["topic"] == "arrays" and e["difficulty"] == difficulty] or PROBLEMS[:1]
    avoid = set(avoid_hashes or [])
    fresh = [e for e in matches if _canonical_hash(e["topic"], e["difficulty"], e["title"], e["description"]) not in avoid]
    return _from_bank_entry(random.choice(fresh or matches))


def _starter(language: str, signature: dict[str, Any]) -> str:
    name = signature["name"]
    params = ", ".join(item["name"] for item in signature["parameters"])
    if language == "python":
        return f"def {name}({params}):\n    # Write your solution here\n    pass\n"
    if language == "javascript":
        return f"function {name}({params}) {{\n    // Write your solution here\n}}\n"
    if language == "java":
        return f"class Solution {{\n    public static Object {name}(Object... args) {{\n        // Write your solution here\n        return null;\n    }}\n}}\n"
    return f"class Solution {{\npublic:\n    auto {name}(/* parameters */) {{\n        // Write your solution here\n    }}\n}};\n"


def _reference_solution(name: str) -> str:
    return next((e["solution"] for e in PROBLEMS if e["name"] == name), "")


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def verify_llm_problem(raw: Any, topic: str, difficulty: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Accept an LLM-generated problem only if it is well-formed AND its own reference solution
    passes every one of its test cases when actually executed. Returns (problem, None) or (None, reason)."""
    if not isinstance(raw, dict):
        return None, "not_json_object"
    title, description = raw.get("title"), raw.get("description")
    if not isinstance(title, str) or not title.strip() or len(title) > 120:
        return None, "bad_title"
    if not isinstance(description, str) or len(description.strip()) < 30:
        return None, "bad_description"
    signature = raw.get("function_signature")
    if not isinstance(signature, dict) or not _IDENTIFIER.match(str(signature.get("name", ""))):
        return None, "bad_signature"
    params = signature.get("parameters")
    if not isinstance(params, list) or not all(isinstance(p, dict) and _IDENTIFIER.match(str(p.get("name", ""))) for p in params):
        return None, "bad_parameters"

    def cases(value):
        if not isinstance(value, list):
            return None
        out = []
        for case in value:
            if not isinstance(case, dict) or not isinstance(case.get("args"), list) or "expected" not in case:
                return None
            if len(case["args"]) != len(params):
                return None
            try:
                json.dumps(case["args"]), json.dumps(case["expected"])
            except (TypeError, ValueError):
                return None
            out.append(_case(case["args"], case["expected"]))
        return out

    visible = cases(raw.get("visible_test_cases") or raw.get("examples"))
    hidden = cases(raw.get("hidden_test_cases"))
    if not visible or len(visible) < 2:
        return None, "too_few_visible_tests"
    if not hidden or len(hidden) < 2:
        return None, "too_few_hidden_tests"
    if len(visible) + len(hidden) > 30:
        return None, "too_many_tests"

    reference = raw.get("reference_solution")
    if isinstance(reference, dict):
        reference = reference.get("python")
    if not isinstance(reference, str) or f"def {signature['name']}(" not in reference:
        return None, "missing_python_reference"

    problem = {
        "title": title.strip(), "description": description.strip(), "difficulty": difficulty, "topic": topic,
        "subtopic": topic, "skills": [topic, difficulty],
        "constraints": [str(c) for c in raw.get("constraints", [])][:8] if isinstance(raw.get("constraints"), list) and raw.get("constraints") else
                       ["Inputs satisfy the stated function contract.", "Return the exact requested type."],
        "examples": visible, "visible_test_cases": visible, "hidden_test_cases": hidden,
        "function_signature": {"name": signature["name"], "parameters": [{"name": p["name"], "type": str(p.get("type", "Any"))} for p in params],
                               "return_type": str(signature.get("return_type", "Any"))},
        "reference_solution": {"python": reference}, "source": "llm_verified",
    }
    # Execute the model's own solution against all of its tests: a wrong answer key is rejected here,
    # instead of later marking a correct candidate solution as wrong.
    import time as _time
    from modules.coding.runner import _run_case
    deadline = _time.monotonic() + 20  # whole-verification budget, so generation can't hog a worker
    for case in visible + hidden:
        outcome = _run_case(problem, reference, case, timeout=min(3.0, deadline - _time.monotonic()))
        if outcome.get("status") != "passed":
            return None, f"reference_{outcome.get('status', 'failed')}"
    return problem, None


def _from_llm(profile: dict[str, Any], topic: str, difficulty: str, language: str, previous_hashes: list[str]) -> Optional[dict[str, Any]]:
    system = ("Generate one original algorithm problem. Return only JSON. Do not generate Two Sum. "
              "Every test must contain structured args (one entry per function parameter) and the exact expected value. "
              "The reference_solution must be Python and must pass every test.")
    context = {"difficulty": difficulty, "topic": topic.replace("_", " "), "skills": [str(skill)[:40] for skill in (profile.get("skills") or [])[:10]],
               "avoid_hashes": previous_hashes[-20:]}
    shape = ('{"title": str, "description": str, "constraints": [str], '
             '"function_signature": {"name": str, "parameters": [{"name": str, "type": str}], "return_type": str}, '
             '"visible_test_cases": [{"args": [...], "expected": ...}] (2-3), "hidden_test_cases": [{"args": [...], "expected": ...}] (3-6, include edge cases), '
             '"reference_solution": {"python": "def <name>(...): ..."}}')
    raw = request_json(system, f"Generate a DSA problem for {json.dumps(context)}. Return JSON with this shape: {shape}", max_tokens=1800)
    if raw is None:
        return None
    problem, reason = verify_llm_problem(raw, topic, difficulty)
    try:
        from services.metrics_log import log_event
        log_event("dsa_llm_problem", accepted=problem is not None, reason=reason, topic=topic, difficulty=difficulty)
    except Exception:
        pass
    return problem


def generate_dsa_problem(profile: Optional[dict[str, Any]] = None, difficulty: Optional[str] = None, topic: Optional[str] = None, language: Optional[str] = None, previous_hashes: Optional[list[str]] = None) -> dict[str, Any]:
    profile = profile if isinstance(profile, dict) else {}
    difficulty = (difficulty or "medium").lower()
    difficulty = difficulty if difficulty in DIFFICULTIES else "medium"
    topic = normalize_topic(topic)
    language = normalize_language(language)
    problem = _from_llm(profile, topic, difficulty, language, previous_hashes or []) or _fallback(topic, difficulty, previous_hashes)
    problem = deepcopy(problem)
    problem["difficulty"], problem["topic"], problem["language"] = difficulty, topic, language
    signature = problem["function_signature"]
    problem["starter_code"] = _starter(language, signature)
    problem["time_limit_ms"] = problem.get("time_limit_ms", 2000)
    problem["memory_limit_mb"] = problem.get("memory_limit_mb", 256)
    problem["canonical_hash"] = _canonical_hash(problem["topic"], problem["difficulty"], problem.get("title", ""), problem.get("description", ""))
    problem["id"] = f"dsa-{uuid.uuid4().hex[:12]}"
    return problem


def validate_problem_schema(problem: dict[str, Any]) -> bool:
    required = {"id", "title", "description", "difficulty", "topic", "constraints", "examples", "visible_test_cases", "hidden_test_cases", "function_signature", "starter_code", "time_limit_ms", "memory_limit_mb"}
    if not isinstance(problem, dict) or not required.issubset(problem) or problem["difficulty"] not in DIFFICULTIES or problem["topic"] not in TOPICS:
        return False
    signature = problem["function_signature"]
    if not isinstance(signature, dict) or not signature.get("name") or not isinstance(signature.get("parameters"), list):
        return False
    tests = problem["visible_test_cases"] + problem["hidden_test_cases"]
    if not tests or any(not isinstance(case, dict) or not isinstance(case.get("args"), list) or "expected" not in case for case in tests):
        return False
    return bool(problem["examples"] and problem["constraints"] and problem.get("reference_solution"))


def public_problem(problem: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(problem)
    for key in ("hidden_tests", "hidden_test_cases", "reference_solution"):
        result.pop(key, None)
    return result


def generate_problem(**kwargs):
    return generate_dsa_problem(**kwargs)
