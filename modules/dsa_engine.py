import ast
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Sequence


ALLOWED_DIFFICULTIES = {"easy", "medium", "hard"}
DEFAULT_SKILLS = ["Python", "Data Structures", "Algorithms"]
TOPIC_ALIASES = {
    "arrays": "arrays",
    "array": "arrays",
    "strings": "strings",
    "string": "strings",
    "hashing": "hashing",
    "hash": "hashing",
    "dynamic_programming": "dynamic_programming",
    "dp": "dynamic_programming",
    "graphs": "graphs",
    "graph": "graphs",
    "trees": "trees",
    "tree": "trees",
    "sorting": "sorting",
    "searching": "searching",
    "stack": "stack",
    "queue": "queue",
    "two_pointers": "two_pointers",
    "sliding_window": "sliding_window",
    "greedy": "greedy",
    "linked_lists": "linked_lists",
    "linked_list": "linked_lists",
}


def normalize_topic(topic: str) -> str:
    if not topic:
        return "arrays"
    return TOPIC_ALIASES.get(topic.strip().lower().replace(" ", "_"), "arrays")


def normalize_language(language: str) -> str:
    language = (language or "Python").strip()
    mapping = {
        "python": "Python",
        "py": "Python",
        "java": "Java",
        "cpp": "C++",
        "c++": "C++",
        "javascript": "JavaScript",
        "js": "JavaScript",
    }
    return mapping.get(language.lower(), language)


def _base_problem(topic: str, difficulty: str, language: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    topic_name = normalize_topic(topic)
    difficulty_name = difficulty.lower() if difficulty else "medium"
    if difficulty_name not in ALLOWED_DIFFICULTIES:
        difficulty_name = "medium"

    profile_skills = profile.get("skills", []) or []
    resume_context = profile.get("experience_raw", []) or []
    context_skills = [str(skill) for skill in profile_skills[:5]]
    skills = list(dict.fromkeys(DEFAULT_SKILLS + context_skills))

    title = {
        "arrays": "Sum of Array Elements",
        "strings": "Count Character Frequencies",
        "hashing": "Check for Duplicate Values",
        "dynamic_programming": "Maximum Subarray Sum",
        "graphs": "Graph Reachability Check",
        "trees": "Tree Node Count",
        "sorting": "Sort Array in Ascending Order",
        "searching": "Find Target in Array",
        "stack": "Balanced Parentheses Check",
        "queue": "Queue Replay Check",
        "two_pointers": "Two Pointer Pair Sum",
        "sliding_window": "Largest Window Sum",
        "greedy": "Choose Maximum Profit",
        "linked_lists": "Linked List Length",
    }.get(topic_name, "Sum of Array Elements")

    examples = []
    hidden_tests = []

    if topic_name == "arrays":
        examples = [
            {"input": "[1, 2, 3, 4]", "output": "10"},
            {"input": "[5, -2, 9, 0]", "output": "12"},
        ]
        hidden_tests = [
            {"input": "[0, 0, 0]", "output": "0"},
            {"input": "[-3, 4, 2, -1]", "output": "2"},
            {"input": "[7, 8, 9, 10, 11]", "output": "45"},
        ]
        description = "Given an array of integers, return the sum of all elements in the array."
        input_format = "nums: a list of integers"
        output_format = "Return the total sum as an integer."
        constraints = ["1 <= len(nums) <= 10^5", "-10^9 <= nums[i] <= 10^9"]
        starter_code = "def solution(nums):\n    # Write your code here\n    pass\n"

    elif topic_name == "strings":
        examples = [
            {"input": '"hello"', "output": "{'h': 1, 'e': 1, 'l': 2, 'o': 1}"},
            {"input": '"programming"', "output": "{'p': 1, 'r': 2, 'o': 1, 'g': 2, 'a': 1, 'm': 2, 'i': 1, 'n': 1}"},
        ]
        hidden_tests = [
            {"input": '"a"', "output": "{'a': 1}"},
            {"input": '"mississippi"', "output": "{'m': 1, 'i': 4, 's': 4, 'p': 2}"},
            {"input": '"abcabc"', "output": "{'a': 2, 'b': 2, 'c': 2}"},
        ]
        description = "Given a string, count the frequency of each character and return it as a dictionary."
        input_format = "s: a string"
        output_format = "Return a dictionary mapping each character to its count."
        constraints = ["1 <= len(s) <= 10^5", "Characters are lowercase English letters"]
        starter_code = "def solution(s):\n    # Write your code here\n    pass\n"

    elif topic_name == "hashing":
        examples = [
            {"input": "[1, 2, 3, 2, 1]", "output": "True"},
            {"input": "[4, 5, 6]", "output": "False"},
        ]
        hidden_tests = [
            {"input": "[9, 9, 9]", "output": "True"},
            {"input": "[1, 2, 3, 4, 5]", "output": "False"},
        ]
        description = "Determine whether the array contains any duplicate values."
        input_format = "nums: a list of integers"
        output_format = "Return True if a duplicate exists, otherwise False."
        constraints = ["1 <= len(nums) <= 10^5", "-10^9 <= nums[i] <= 10^9"]
        starter_code = "def solution(nums):\n    # Write your code here\n    pass\n"

    else:
        examples = [
            {"input": "[1, 2, 3, 4]", "output": "10"},
            {"input": "[5, 6, 7]", "output": "18"},
        ]
        hidden_tests = [
            {"input": "[0, 0, 0]", "output": "0"},
            {"input": "[-3, 2, 5]", "output": "4"},
        ]
        description = "Given a list of numbers, compute the required result for the selected topic."
        input_format = "data: a list of integers"
        output_format = "Return the computed value."
        constraints = ["1 <= len(data) <= 10^5", "Values may be positive or negative"]
        starter_code = "def solution(data):\n    # Write your code here\n    pass\n"

    if language == "Java":
        starter_code = "class Solution {\n    public static int solution(int[] nums) {\n        return 0;\n    }\n}\n"
    elif language == "C++":
        starter_code = "#include <vector>\nusing namespace std;\n\nint solution(vector<int> nums) {\n    return 0;\n}\n"
    elif language == "JavaScript":
        starter_code = "function solution(nums) {\n    return 0;\n}\n"

    problem = {
        "id": f"dsa-{uuid.uuid4().hex[:12]}",
        "title": title,
        "description": description,
        "difficulty": difficulty_name,
        "topic": topic_name,
        "skills": skills,
        "input_format": input_format,
        "output_format": output_format,
        "constraints": constraints,
        "examples": examples,
        "starter_code": starter_code,
        "time_limit_ms": {"easy": 1000, "medium": 2000, "hard": 3000}[difficulty_name],
        "memory_limit_mb": 256,
        "language": language,
        "hidden_tests": hidden_tests,
        "context": " ".join(resume_context[:2]) if resume_context else "General algorithm practice",
    }
    return problem


def generate_dsa_problem(profile: Dict[str, Any], difficulty: str = "medium", topic: str = "arrays", language: str = "Python") -> Dict[str, Any]:
    normalized_lang = normalize_language(language)
    normalized_topic = normalize_topic(topic)
    return _base_problem(normalized_topic, difficulty, normalized_lang, profile)


def validate_problem_schema(problem: Dict[str, Any]) -> bool:
    if not isinstance(problem, dict):
        return False
    required = [
        "id",
        "title",
        "description",
        "difficulty",
        "topic",
        "skills",
        "input_format",
        "output_format",
        "constraints",
        "examples",
        "starter_code",
        "time_limit_ms",
        "memory_limit_mb",
    ]
    if not all(key in problem for key in required):
        return False
    if problem["difficulty"] not in ALLOWED_DIFFICULTIES:
        return False
    if not isinstance(problem["examples"], list) or len(problem["examples"]) == 0:
        return False
    if not isinstance(problem["constraints"], list) or len(problem["constraints"]) == 0:
        return False
    for example in problem["examples"]:
        if not isinstance(example, dict) or "input" not in example or "output" not in example:
            return False
    return True


def _canonicalize_result(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _to_python_literal(raw: str) -> Any:
    try:
        return ast.literal_eval(raw)
    except Exception:
        return raw


def _execute_user_solution(code: str, case_input: Any, timeout_seconds: float = 3.0):
    normalized_input = case_input
    if isinstance(case_input, str):
        normalized_input = _to_python_literal(case_input)

    with tempfile.TemporaryDirectory(prefix="placement_dsa_") as tmpdir:
        script_path = Path(tmpdir) / "solution.py"
        script_body = (
            "import json\n"
            "import ast\n"
            "\n"
            f"{code}\n\n"
            "def _normalize(value):\n"
            "    if isinstance(value, (list, tuple)):\n"
            "        return json.dumps(value, sort_keys=True)\n"
            "    if isinstance(value, dict):\n"
            "        return json.dumps(value, sort_keys=True)\n"
            "    return str(value)\n\n"
            "payload = " + repr(normalized_input) + "\n"
            "try:\n"
            "    if isinstance(payload, tuple):\n"
            "        result = solution(*payload)\n"
            "    else:\n"
            "        result = solution(payload)\n"
            "    print(_normalize(result))\n"
            "except Exception as exc:\n"
            "    raise\n"
        )
        script_path.write_text(script_body, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=tmpdir,
                env={**os.environ, "PYTHONPATH": tmpdir},
            )
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "error": "Execution timed out."}

        if proc.returncode != 0:
            return {"status": "error", "error": proc.stderr.strip() or proc.stdout.strip() or "Execution failed."}

        stdout = proc.stdout.strip()
        if not stdout:
            return {"status": "error", "error": "No output captured."}
        return {"status": "success", "result": stdout}


def run_sample_tests(problem: Dict[str, Any], code: str) -> Dict[str, Any]:
    examples = problem.get("examples", [])
    results = []
    for example in examples:
        parsed_input = _to_python_literal(example.get("input", ""))
        run = _execute_user_solution(code, parsed_input)
        if run["status"] == "success":
            actual = _canonicalize_result(run["result"])
            expected = str(example.get("output", ""))
            status = "success" if actual == expected else "failed"
            results.append({"status": status, "actual": actual, "expected": expected})
        else:
            results.append({"status": "error", "actual": run.get("error", "Execution failed."), "expected": example.get("output", "")})

    failed = [r for r in results if r["status"] != "success"]
    if not failed:
        return {"status": "success", "output": "All sample tests passed.", "execution_time_ms": 20, "details": results}
    return {"status": "failed", "output": "At least one sample test failed.", "execution_time_ms": 20, "details": results}


def _score_submission(passed: int, total: int, execution_time_ms: int, memory_usage_mb: float) -> float:
    if total == 0:
        return 0.0
    correctness = (passed / total) * 100
    time_penalty = max(0.0, 15.0 - min(execution_time_ms / 200.0, 15.0))
    memory_penalty = max(0.0, 10.0 - min(memory_usage_mb / 40.0, 10.0))
    score = max(0.0, min(100.0, correctness * 0.8 + time_penalty + memory_penalty))
    return round(score, 1)


def submit_solution(problem: Dict[str, Any], code: str) -> Dict[str, Any]:
    tests = problem.get("hidden_tests", []) or problem.get("examples", [])
    total = len(tests)
    passed = 0
    execution_time_ms = 0
    memory_usage_mb = 0.0
    evaluation = []

    for index, case in enumerate(tests):
        start = time.perf_counter()
        parsed_input = _to_python_literal(case.get("input", ""))
        run = _execute_user_solution(code, parsed_input)
        elapsed = int((time.perf_counter() - start) * 1000)
        execution_time_ms += elapsed
        if run["status"] == "success":
            actual = _canonicalize_result(run["result"])
            expected = str(case.get("output", ""))
            ok = actual == expected
            if ok:
                passed += 1
            evaluation.append({"index": index + 1, "passed": ok, "actual": actual, "expected": expected})
        else:
            evaluation.append({"index": index + 1, "passed": False, "actual": run.get("error", "Execution failed."), "expected": case.get("output", "")})

    status = "success" if passed == total and total > 0 else ("partial" if passed > 0 else "incorrect")
    score = _score_submission(passed, total, execution_time_ms, memory_usage_mb)
    feedback = (
        "All hidden tests passed." if status == "success"
        else f"Passed {passed}/{total} hidden tests. Review input handling and edge cases."
    )
    return {
        "status": status,
        "passed_tests": passed,
        "total_tests": total,
        "execution_time_ms": execution_time_ms,
        "memory_usage_mb": memory_usage_mb,
        "score": score,
        "feedback": feedback,
        "tests": evaluation,
    }


def compute_skill_gap(profile: Dict[str, Any], history: Sequence[Dict[str, Any]]) -> List[str]:
    history_map = {}
    for record in history:
        if not isinstance(record, dict):
            continue
        topic = normalize_topic(str(record.get("topic", "arrays")))
        score = float(record.get("score", 0) or 0)
        history_map.setdefault(topic, []).append(score)

    avg_scores = {topic: sum(values) / len(values) for topic, values in history_map.items()}
    if not avg_scores:
        return ["arrays", "graphs", "dynamic_programming"]

    profile_skills = {str(skill).strip().lower() for skill in (profile.get("skills") or [])}
    weak = [topic for topic, score in sorted(avg_scores.items(), key=lambda item: item[1]) if score < 70]
    weak = [topic for topic in weak if topic not in {"python", "sql"}]
    if not weak:
        weak = ["graphs", "dynamic_programming", "trees"]
    if profile_skills:
        weak = [topic for topic in weak if topic not in {"python", "sql"}]
    return weak[:5]
