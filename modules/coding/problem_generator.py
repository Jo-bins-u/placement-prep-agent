"""Canonical DSA problem generation and validation service."""

from __future__ import annotations

import hashlib
import re
import uuid
from copy import deepcopy
from typing import Any, Optional

from services.llm_service import request_json

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


def _fallback(topic: str, difficulty: str) -> dict[str, Any]:
    bank = {
        ("arrays", "easy"): ("Sum Array Values", "Return the sum of every integer in nums.", "sum_array", [("nums", "list[int]")], "int", [[1, 2, 3], [-2, 5, 1]], [6, 4], [[0], [10, -3, 2]], [0, 9]),
        ("arrays", "medium"): ("Maximum Subarray Sum", "Return the largest sum of a non-empty contiguous subarray.", "max_subarray_sum", [("nums", "list[int]")], "int", [[-2, 1, -3, 4, -1, 2, 1, -5, 4], [5, -4, 3]], [6, 5], [[-5, -2], [8, -1, 2, -10, 4]], [-2, 9]),
        ("arrays", "hard"): ("Count Inversion Pairs", "Count pairs i < j where nums[i] > nums[j].", "count_inversions", [("nums", "list[int]")], "int", [[2, 4, 1, 3, 5], [5, 4, 3, 2, 1]], [3, 10], [[1, 1, 1], [3, 1, 2]], [0, 2]),
        ("strings", "easy"): ("Reverse Words", "Return the words in s in reverse order with one space between them.", "reverse_words", [("s", "str")], "str", ["hello world", "prep wise"], ["world hello", "wise prep"], ["a", "one two three"], ["a", "three two one"]),
        ("strings", "medium"): ("Longest Unique Substring", "Return the length of the longest substring without repeated characters.", "longest_unique_substring", [("s", "str")], "int", ["abcabcbb", "bbbbb"], [3, 1], ["pwwkew", ""], [3, 0]),
        ("strings", "hard"): ("Minimum Edit Distance", "Return the minimum edits needed to transform a into b.", "edit_distance", [("a", "str"), ("b", "str")], "int", [["horse", "ros"], ["intention", "execution"]], [3, 5], [["", "abc"], ["abc", "abc"]], [3, 0]),
        ("hashing", "easy"): ("Contains Duplicate", "Return True when nums contains a repeated value.", "contains_duplicate", [("nums", "list[int]")], "bool", [[1, 2, 3, 1], [1, 2, 3]], [True, False], [[1], [2, 2]], [False, True]),
        ("sliding_window", "medium"): ("Maximum Fixed Window", "Return the maximum sum of a contiguous window of length k.", "max_window_sum", [("nums", "list[int]"), ("k", "int")], "int", [[[1, 2, 3, 4, 5], 3], [[-1, 2, 4, -3, 5, 6], 2]], [12, 11], [[[1], 1], [[4, -2, 7], 2]], [1, 5]),
        ("binary_search", "medium"): ("First Occurrence", "Return the first index of target in sorted nums, or -1.", "first_occurrence", [("nums", "list[int]"), ("target", "int")], "int", [[[1, 2, 2, 2, 4], 2], [[1, 3, 5], 4]], [1, -1], [[[1], 1], [[2, 2], 2]], [0, 0]),
        ("dynamic_programming", "medium"): ("Climbing Stairs", "Return the number of distinct ways to climb n stairs taking one or two steps.", "climb_stairs", [("n", "int")], "int", [5, 6], [8, 13], [1, 2], [1, 2]),
        ("dynamic_programming", "hard"): ("House Robber", "Return the maximum amount that can be robbed from non-adjacent houses.", "rob_houses", [("nums", "list[int]")], "int", [[2, 7, 9, 3, 1], [2, 1, 1, 2]], [12, 4], [[1, 2, 3, 1], [5, 1, 1, 5]], [4, 10]),
        ("graphs", "medium"): ("Reachable Nodes", "Given an adjacency list and start node, return the number of reachable nodes.", "reachable_count", [("graph", "list[list[int]]"), ("start", "int")], "int", [[[[1, 2], [2], [0], []], 0], [[[1], [], []], 0]], [3, 2], [[[[ ]], 0], [[[1], [], []], 2]], [1, 1]),
        ("trees", "medium"): ("Count Tree Nodes", "Return the node count for a nested [value,left,right] tree or None.", "count_tree_nodes", [("root", "Any")], "int", [[1, [2, None, None], [3, None, None]], None], [3, 0], [[4, None, None]], [1]),
    }
    item = bank.get((topic, difficulty)) or bank.get(("arrays", difficulty)) or bank[("arrays", "easy")]
    title, description, name, params, return_type, visible_raw, visible_expected, hidden_raw, hidden_expected = item
    def make(raw_values, expected_values):
        return [_case(raw if len(params) > 1 else [raw], expected) for raw, expected in zip(raw_values, expected_values)]
    visible = make(visible_raw, visible_expected)
    hidden = make(hidden_raw, hidden_expected)
    return {
        "title": title, "description": description, "difficulty": difficulty, "topic": topic,
        "subtopic": topic, "skills": [topic, difficulty],
        "constraints": ["Inputs satisfy the stated function contract.", "Return the exact requested type."],
        "examples": visible, "visible_test_cases": visible, "hidden_test_cases": hidden,
        "function_signature": {"name": name, "parameters": [{"name": n, "type": t} for n, t in params], "return_type": return_type},
        "input_format": ", ".join(f"{n}: {t}" for n, t in params), "output_format": return_type,
        "reference_solution": {}, "source": "validated_fallback_bank",
    }


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
    solutions = {
        "sum_array": "def sum_array(nums):\n    return sum(nums)\n",
        "max_subarray_sum": "def max_subarray_sum(nums):\n    best = current = nums[0]\n    for value in nums[1:]:\n        current = max(value, current + value)\n        best = max(best, current)\n    return best\n",
        "count_inversions": "def count_inversions(nums):\n    return sum(nums[i] > nums[j] for i in range(len(nums)) for j in range(i + 1, len(nums)))\n",
        "reverse_words": "def reverse_words(s):\n    return ' '.join(reversed(s.split()))\n",
        "longest_unique_substring": "def longest_unique_substring(s):\n    left = best = 0\n    seen = {}\n    for right, char in enumerate(s):\n        if char in seen and seen[char] >= left:\n            left = seen[char] + 1\n        seen[char] = right\n        best = max(best, right - left + 1)\n    return best\n",
        "edit_distance": "def edit_distance(a, b):\n    row = list(range(len(b) + 1))\n    for i, x in enumerate(a, 1):\n        next_row = [i]\n        for j, y in enumerate(b, 1):\n            next_row.append(min(next_row[-1] + 1, row[j] + 1, row[j - 1] + (x != y)))\n        row = next_row\n    return row[-1]\n",
        "contains_duplicate": "def contains_duplicate(nums):\n    return len(nums) != len(set(nums))\n",
        "max_window_sum": "def max_window_sum(nums, k):\n    current = sum(nums[:k])\n    best = current\n    for i in range(k, len(nums)):\n        current += nums[i] - nums[i-k]\n        best = max(best, current)\n    return best\n",
        "first_occurrence": "def first_occurrence(nums, target):\n    lo, hi = 0, len(nums) - 1\n    answer = -1\n    while lo <= hi:\n        mid = (lo + hi) // 2\n        if nums[mid] == target:\n            answer = mid\n            hi = mid - 1\n        elif nums[mid] < target:\n            lo = mid + 1\n        else:\n            hi = mid - 1\n    return answer\n",
        "climb_stairs": "def climb_stairs(n):\n    a, b = 1, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\n",
        "rob_houses": "def rob_houses(nums):\n    previous, current = 0, 0\n    for value in nums:\n        previous, current = current, max(current, previous + value)\n    return current\n",
        "reachable_count": "def reachable_count(graph, start):\n    seen = {start}\n    stack = [start]\n    while stack:\n        node = stack.pop()\n        for neighbor in graph[node]:\n            if neighbor not in seen:\n                seen.add(neighbor)\n                stack.append(neighbor)\n    return len(seen)\n",
        "count_tree_nodes": "def count_tree_nodes(root):\n    if root is None:\n        return 0\n    return 1 + count_tree_nodes(root[1]) + count_tree_nodes(root[2])\n",
    }
    return solutions.get(name, "")


def _from_llm(profile: dict[str, Any], topic: str, difficulty: str, language: str, previous_hashes: list[str]) -> Optional[dict[str, Any]]:
    system = "Generate one original algorithm problem. Return only JSON. Do not generate Two Sum. Every test must contain structured args and expected values."
    context = {"difficulty": difficulty, "topic": topic, "language": language, "skills": (profile.get("skills") or [])[:10], "avoid_hashes": previous_hashes[-20:]}
    result = request_json(system, f"Generate a valid DSA problem for {context}. Include title, description, constraints, examples, visible_test_cases, hidden_test_cases, function_signature with name/parameters/return_type, and reference_solution. Return JSON only.", max_tokens=1800)
    return result if isinstance(result, dict) else None


def generate_dsa_problem(profile: Optional[dict[str, Any]] = None, difficulty: Optional[str] = None, topic: Optional[str] = None, language: Optional[str] = None, previous_hashes: Optional[list[str]] = None) -> dict[str, Any]:
    profile = profile if isinstance(profile, dict) else {}
    difficulty = (difficulty or "medium").lower()
    difficulty = difficulty if difficulty in DIFFICULTIES else "medium"
    topic = normalize_topic(topic)
    language = normalize_language(language)
    problem = _from_llm(profile, topic, difficulty, language, previous_hashes or []) or _fallback(topic, difficulty)
    problem = deepcopy(problem)
    problem["difficulty"], problem["topic"], problem["language"] = difficulty, topic, language
    signature = problem.get("function_signature") or {}
    if not signature.get("name"):
        problem = _fallback(topic, difficulty)
        signature = problem["function_signature"]
    problem["starter_code"] = _starter(language, signature)
    problem["reference_solution"] = problem.get("reference_solution") or {"python": _reference_solution(signature["name"])}
    problem["function_signature"] = signature
    problem["visible_test_cases"] = problem.get("visible_test_cases") or problem.get("examples") or []
    problem["hidden_test_cases"] = problem.get("hidden_test_cases") or []
    problem["examples"] = problem["visible_test_cases"]
    problem["time_limit_ms"] = problem.get("time_limit_ms", 2000)
    problem["memory_limit_mb"] = problem.get("memory_limit_mb", 256)
    canonical = "|".join([problem.get("topic", ""), problem.get("difficulty", ""), problem.get("title", ""), problem.get("description", "")])
    problem["canonical_hash"] = hashlib.sha256(re.sub(r"\W+", " ", canonical.lower()).encode()).hexdigest()
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
