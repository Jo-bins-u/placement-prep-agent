"""
Curated DSA problem bank — used whenever the LLM is unavailable or its problem fails
verification. Every topic x difficulty combination has at least one problem.

Each entry: topic, difficulty, title, description, name, params [(name, type)],
returns, visible [(args, expected)], hidden [(args, expected)], solution (Python).
`args` is always the list of positional arguments. Linked lists are given as Python
lists of node values; binary trees as nested [value, left, right] lists (None = empty).

tests/test_dsa_bank.py runs every reference solution against every test case.
"""

P = []


def add(topic, difficulty, title, description, name, params, returns, visible, hidden, solution):
    P.append({
        "topic": topic, "difficulty": difficulty, "title": title, "description": description,
        "name": name, "params": params, "returns": returns,
        "visible": visible, "hidden": hidden, "solution": solution.strip() + "\n",
    })


# ----------------------------------------------------------------- arrays
add("arrays", "easy", "Sum Array Values", "Return the sum of every integer in nums.",
    "sum_array", [("nums", "list[int]")], "int",
    [([[1, 2, 3]], 6), ([[-2, 5, 1]], 4)],
    [([[0]], 0), ([[10, -3, 2]], 9), ([[]], 0)],
    """
def sum_array(nums):
    return sum(nums)
""")
add("arrays", "medium", "Maximum Subarray Sum", "Return the largest sum of a non-empty contiguous subarray.",
    "max_subarray_sum", [("nums", "list[int]")], "int",
    [([[-2, 1, -3, 4, -1, 2, 1, -5, 4]], 6), ([[5, -4, 3]], 5)],
    [([[-5, -2]], -2), ([[8, -1, 2, -10, 4]], 9), ([[1]], 1)],
    """
def max_subarray_sum(nums):
    best = current = nums[0]
    for value in nums[1:]:
        current = max(value, current + value)
        best = max(best, current)
    return best
""")
add("arrays", "hard", "Count Inversion Pairs", "Count pairs i < j where nums[i] > nums[j].",
    "count_inversions", [("nums", "list[int]")], "int",
    [([[2, 4, 1, 3, 5]], 3), ([[5, 4, 3, 2, 1]], 10)],
    [([[1, 1, 1]], 0), ([[3, 1, 2]], 2), ([[]], 0)],
    """
def count_inversions(nums):
    def sort(a):
        if len(a) < 2:
            return a, 0
        mid = len(a) // 2
        left, x = sort(a[:mid])
        right, y = sort(a[mid:])
        merged, count, i, j = [], x + y, 0, 0
        while i < len(left) and j < len(right):
            if left[i] <= right[j]:
                merged.append(left[i]); i += 1
            else:
                merged.append(right[j]); j += 1
                count += len(left) - i
        return merged + left[i:] + right[j:], count
    return sort(list(nums))[1]
""")

# ----------------------------------------------------------------- strings
add("strings", "easy", "Reverse Words", "Return the words in s in reverse order with single spaces between them.",
    "reverse_words", [("s", "str")], "str",
    [(["hello world"], "world hello"), (["prep wise"], "wise prep")],
    [(["a"], "a"), (["one two three"], "three two one"), (["  lots   of space "], "space of lots")],
    """
def reverse_words(s):
    return " ".join(reversed(s.split()))
""")
add("strings", "medium", "Longest Unique Substring", "Return the length of the longest substring without repeated characters.",
    "longest_unique_substring", [("s", "str")], "int",
    [(["abcabcbb"], 3), (["bbbbb"], 1)],
    [(["pwwkew"], 3), ([""], 0), (["abcdef"], 6)],
    """
def longest_unique_substring(s):
    left = best = 0
    seen = {}
    for right, char in enumerate(s):
        if char in seen and seen[char] >= left:
            left = seen[char] + 1
        seen[char] = right
        best = max(best, right - left + 1)
    return best
""")
add("strings", "hard", "Minimum Edit Distance", "Return the minimum number of insertions, deletions or substitutions to turn a into b.",
    "edit_distance", [("a", "str"), ("b", "str")], "int",
    [(["horse", "ros"], 3), (["intention", "execution"], 5)],
    [(["", "abc"], 3), (["abc", "abc"], 0), (["kitten", "sitting"], 3)],
    """
def edit_distance(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        nxt = [i]
        for j, y in enumerate(b, 1):
            nxt.append(min(nxt[-1] + 1, row[j] + 1, row[j - 1] + (x != y)))
        row = nxt
    return row[-1]
""")

# ----------------------------------------------------------------- hashing
add("hashing", "easy", "Contains Duplicate", "Return True if any value appears at least twice in nums.",
    "contains_duplicate", [("nums", "list[int]")], "bool",
    [([[1, 2, 3, 1]], True), ([[1, 2, 3]], False)],
    [([[1]], False), ([[2, 2]], True), ([[]], False)],
    """
def contains_duplicate(nums):
    return len(nums) != len(set(nums))
""")
add("hashing", "medium", "Count Anagram Groups", "Return how many groups of anagrams the list of words forms (each word belongs to exactly one group).",
    "count_anagram_groups", [("words", "list[str]")], "int",
    [([["eat", "tea", "tan", "ate", "nat", "bat"]], 3), ([["a"]], 1)],
    [([[]], 0), ([["abc", "cba", "bca"]], 1), ([["ab", "ba", "abc", "cab", "x"]], 3)],
    """
def count_anagram_groups(words):
    return len({"".join(sorted(w)) for w in words})
""")
add("hashing", "hard", "Longest Consecutive Sequence", "Return the length of the longest run of consecutive integers that can be formed from nums (order in nums does not matter). Aim for O(n).",
    "longest_consecutive", [("nums", "list[int]")], "int",
    [([[100, 4, 200, 1, 3, 2]], 4), ([[0, 3, 7, 2, 5, 8, 4, 6, 0, 1]], 9)],
    [([[]], 0), ([[5]], 1), ([[1, 2, 2, 3, 10, 11]], 3)],
    """
def longest_consecutive(nums):
    values = set(nums)
    best = 0
    for v in values:
        if v - 1 not in values:
            length = 1
            while v + length in values:
                length += 1
            best = max(best, length)
    return best
""")

# ----------------------------------------------------------------- two pointers
add("two_pointers", "easy", "Valid Palindrome", "Return True if s reads the same forwards and backwards, ignoring case and any character that is not a letter or digit.",
    "is_palindrome", [("s", "str")], "bool",
    [(["A man, a plan, a canal: Panama"], True), (["race a car"], False)],
    [([""], True), (["No 'x' in Nixon"], True), (["ab"], False)],
    """
def is_palindrome(s):
    cleaned = [c.lower() for c in s if c.isalnum()]
    return cleaned == cleaned[::-1]
""")
add("two_pointers", "medium", "Pair With Target Sum", "nums is sorted ascending. Return [i, j] (0-based, i < j) of the first pair found by moving two pointers inward whose values add to target, or [-1, -1] if none exists.",
    "pair_sum_sorted", [("nums", "list[int]"), ("target", "int")], "list[int]",
    [([[1, 2, 4, 7, 11], 9], [1, 3]), ([[1, 3, 5], 10], [-1, -1])],
    [([[2, 7], 9], [0, 1]), ([[-3, 0, 3, 6], 3], [0, 3]), ([[], 1], [-1, -1])],
    """
def pair_sum_sorted(nums, target):
    i, j = 0, len(nums) - 1
    while i < j:
        total = nums[i] + nums[j]
        if total == target:
            return [i, j]
        if total < target:
            i += 1
        else:
            j -= 1
    return [-1, -1]
""")
add("two_pointers", "hard", "Trapping Rain Water", "heights are bar heights of width 1. Return how many units of rain water are trapped between the bars.",
    "trap_rain_water", [("heights", "list[int]")], "int",
    [([[0, 1, 0, 2, 1, 0, 1, 3, 2, 1, 2, 1]], 6), ([[4, 2, 0, 3, 2, 5]], 9)],
    [([[]], 0), ([[3, 3, 3]], 0), ([[5, 0, 5]], 5)],
    """
def trap_rain_water(heights):
    i, j = 0, len(heights) - 1
    left_max = right_max = water = 0
    while i < j:
        if heights[i] < heights[j]:
            left_max = max(left_max, heights[i])
            water += left_max - heights[i]
            i += 1
        else:
            right_max = max(right_max, heights[j])
            water += right_max - heights[j]
            j -= 1
    return water
""")

# ----------------------------------------------------------------- sliding window
add("sliding_window", "easy", "Most Vowels In A Window", "Return the maximum number of vowels (a, e, i, o, u) in any substring of s of length k.",
    "max_vowels", [("s", "str"), ("k", "int")], "int",
    [(["abciiidef", 3], 3), (["leetcode", 3], 2)],
    [(["aeiou", 2], 2), (["rhythm", 2], 0), (["a", 1], 1)],
    """
def max_vowels(s, k):
    vowels = set("aeiou")
    count = sum(1 for c in s[:k] if c in vowels)
    best = count
    for i in range(k, len(s)):
        count += (s[i] in vowels) - (s[i - k] in vowels)
        best = max(best, count)
    return best
""")
add("sliding_window", "medium", "Maximum Fixed Window", "Return the maximum sum of any contiguous window of length k.",
    "max_window_sum", [("nums", "list[int]"), ("k", "int")], "int",
    [([[1, 2, 3, 4, 5], 3], 12), ([[-1, 2, 4, -3, 5, 6], 2], 11)],
    [([[1], 1], 1), ([[4, -2, 7], 2], 5), ([[-5, -1, -3], 2], -4)],
    """
def max_window_sum(nums, k):
    current = best = sum(nums[:k])
    for i in range(k, len(nums)):
        current += nums[i] - nums[i - k]
        best = max(best, current)
    return best
""")
add("sliding_window", "hard", "Longest Substring With K Distinct", "Return the length of the longest substring of s that contains at most k distinct characters.",
    "longest_k_distinct", [("s", "str"), ("k", "int")], "int",
    [(["eceba", 2], 3), (["aa", 1], 2)],
    [(["", 2], 0), (["abc", 0], 0), (["abaccc", 2], 4), (["abcadcacacaca", 3], 11)],
    """
def longest_k_distinct(s, k):
    counts, left, best = {}, 0, 0
    for right, c in enumerate(s):
        counts[c] = counts.get(c, 0) + 1
        while len(counts) > k:
            counts[s[left]] -= 1
            if counts[s[left]] == 0:
                del counts[s[left]]
            left += 1
        best = max(best, right - left + 1)
    return best
""")

# ----------------------------------------------------------------- binary search
add("binary_search", "easy", "Binary Search", "nums is sorted ascending with distinct values. Return the index of target, or -1 if it is not present.",
    "binary_search", [("nums", "list[int]"), ("target", "int")], "int",
    [([[-1, 0, 3, 5, 9, 12], 9], 4), ([[-1, 0, 3, 5, 9, 12], 2], -1)],
    [([[], 1], -1), ([[5], 5], 0), ([[1, 3, 5, 7], 1], 0)],
    """
def binary_search(nums, target):
    lo, hi = 0, len(nums) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if nums[mid] == target:
            return mid
        if nums[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1
""")
add("binary_search", "medium", "First Occurrence", "Return the first index of target in sorted nums, or -1.",
    "first_occurrence", [("nums", "list[int]"), ("target", "int")], "int",
    [([[1, 2, 2, 2, 4], 2], 1), ([[1, 3, 5], 4], -1)],
    [([[1], 1], 0), ([[2, 2], 2], 0), ([[], 3], -1)],
    """
def first_occurrence(nums, target):
    lo, hi, answer = 0, len(nums) - 1, -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if nums[mid] == target:
            answer, hi = mid, mid - 1
        elif nums[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return answer
""")
add("binary_search", "hard", "Search Rotated Sorted Array", "A sorted array of distinct values was rotated at an unknown pivot. Return the index of target or -1, in O(log n).",
    "search_rotated", [("nums", "list[int]"), ("target", "int")], "int",
    [([[4, 5, 6, 7, 0, 1, 2], 0], 4), ([[4, 5, 6, 7, 0, 1, 2], 3], -1)],
    [([[1], 0], -1), ([[1], 1], 0), ([[3, 1], 1], 1), ([[5, 1, 3], 5], 0)],
    """
def search_rotated(nums, target):
    lo, hi = 0, len(nums) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if nums[mid] == target:
            return mid
        if nums[lo] <= nums[mid]:
            if nums[lo] <= target < nums[mid]:
                hi = mid - 1
            else:
                lo = mid + 1
        else:
            if nums[mid] < target <= nums[hi]:
                lo = mid + 1
            else:
                hi = mid - 1
    return -1
""")

# ----------------------------------------------------------------- linked lists (given as lists of node values)
add("linked_lists", "easy", "Reverse A Linked List", "The linked list is given as a list of node values from head to tail. Return the values of the reversed list.",
    "reverse_list", [("values", "list[int]")], "list[int]",
    [([[1, 2, 3, 4, 5]], [5, 4, 3, 2, 1]), ([[1, 2]], [2, 1])],
    [([[]], []), ([[7]], [7]), ([[3, 3, 1]], [1, 3, 3])],
    """
def reverse_list(values):
    prev = None
    for v in values:          # build then reverse pointers, like a real linked list
        prev = (v, prev)
    out = []
    while prev:
        out.append(prev[0]); prev = prev[1]
    return out
""")
add("linked_lists", "medium", "Remove Nth Node From End", "Remove the n-th node from the end of the list (1 = last node) and return the remaining values. n is always valid.",
    "remove_nth_from_end", [("values", "list[int]"), ("n", "int")], "list[int]",
    [([[1, 2, 3, 4, 5], 2], [1, 2, 3, 5]), ([[1], 1], [])],
    [([[1, 2], 1], [1]), ([[1, 2], 2], [2]), ([[9, 8, 7, 6], 4], [8, 7, 6])],
    """
def remove_nth_from_end(values, n):
    index = len(values) - n
    return values[:index] + values[index + 1:]
""")
add("linked_lists", "hard", "Merge K Sorted Lists", "Each inner list is a sorted linked list. Merge all of them into one sorted list.",
    "merge_k_sorted", [("lists", "list[list[int]]")], "list[int]",
    [([[[1, 4, 5], [1, 3, 4], [2, 6]]], [1, 1, 2, 3, 4, 4, 5, 6]), ([[]], [])],
    [([[[]]], []), ([[[2], [], [1]]], [1, 2]), ([[[-3, 0], [-5, 10], [0]]], [-5, -3, 0, 0, 10])],
    """
import heapq

def merge_k_sorted(lists):
    heap = [(lst[0], i, 0) for i, lst in enumerate(lists) if lst]
    heapq.heapify(heap)
    out = []
    while heap:
        value, i, j = heapq.heappop(heap)
        out.append(value)
        if j + 1 < len(lists[i]):
            heapq.heappush(heap, (lists[i][j + 1], i, j + 1))
    return out
""")

# ----------------------------------------------------------------- stacks
add("stacks", "easy", "Valid Parentheses", "Return True if every bracket in s ('()', '[]', '{}') is closed by the same type in the correct order.",
    "valid_parentheses", [("s", "str")], "bool",
    [(["()[]{}"], True), (["(]"], False)],
    [([""], True), (["([{}])"], True), (["(("], False), (["){"], False)],
    """
def valid_parentheses(s):
    pairs = {")": "(", "]": "[", "}": "{"}
    stack = []
    for c in s:
        if c in pairs:
            if not stack or stack.pop() != pairs[c]:
                return False
        else:
            stack.append(c)
    return not stack
""")
add("stacks", "medium", "Evaluate Reverse Polish Notation", "Evaluate an expression given as tokens in Reverse Polish Notation. Operators are + - * /, and division truncates toward zero.",
    "eval_rpn", [("tokens", "list[str]")], "int",
    [([["2", "1", "+", "3", "*"]], 9), ([["4", "13", "5", "/", "+"]], 6)],
    [([["7"]], 7), ([["10", "6", "9", "3", "+", "-11", "*", "/", "*", "17", "+", "5", "+"]], 22), ([["-7", "2", "/"]], -3)],
    """
def eval_rpn(tokens):
    stack = []
    for t in tokens:
        if t in {"+", "-", "*", "/"}:
            b, a = stack.pop(), stack.pop()
            if t == "+": stack.append(a + b)
            elif t == "-": stack.append(a - b)
            elif t == "*": stack.append(a * b)
            else: stack.append(int(a / b))
        else:
            stack.append(int(t))
    return stack[0]
""")
add("stacks", "hard", "Largest Rectangle In Histogram", "Return the area of the largest rectangle that fits inside the histogram of bar heights (each bar has width 1).",
    "largest_rectangle", [("heights", "list[int]")], "int",
    [([[2, 1, 5, 6, 2, 3]], 10), ([[2, 4]], 4)],
    [([[]], 0), ([[1, 1, 1, 1]], 4), ([[6, 2, 5, 4, 5, 1, 6]], 12)],
    """
def largest_rectangle(heights):
    stack, best = [], 0
    for i, h in enumerate(heights + [0]):
        start = i
        while stack and stack[-1][1] >= h:
            start, height = stack.pop()
            best = max(best, height * (i - start))
        stack.append((start, h))
    return best
""")

# ----------------------------------------------------------------- queues
add("queues", "easy", "First Unique Character", "Return the index of the first character in s that appears exactly once, or -1.",
    "first_unique_char", [("s", "str")], "int",
    [(["leetcode"], 0), (["loveleetcode"], 2)],
    [(["aabb"], -1), ([""], -1), (["z"], 0)],
    """
from collections import Counter, deque

def first_unique_char(s):
    counts = Counter(s)
    queue = deque(range(len(s)))
    while queue:
        i = queue.popleft()
        if counts[s[i]] == 1:
            return i
    return -1
""")
add("queues", "medium", "Josephus Survivor", "n people stand in a circle numbered 1..n. Counting from person 1, every k-th person is removed. Return the number of the last person remaining.",
    "josephus", [("n", "int"), ("k", "int")], "int",
    [([5, 2], 3), ([7, 3], 4)],
    [([1, 1], 1), ([6, 1], 6), ([10, 3], 4)],
    """
from collections import deque

def josephus(n, k):
    circle = deque(range(1, n + 1))
    while len(circle) > 1:
        circle.rotate(-(k - 1))
        circle.popleft()
    return circle[0]
""")
add("queues", "hard", "Sliding Window Maximum", "Return a list with the maximum of every contiguous window of length k, in O(n).",
    "sliding_window_max", [("nums", "list[int]"), ("k", "int")], "list[int]",
    [([[1, 3, -1, -3, 5, 3, 6, 7], 3], [3, 3, 5, 5, 6, 7]), ([[1], 1], [1])],
    [([[9, 8, 7, 6], 2], [9, 8, 7]), ([[1, 2, 3], 3], [3]), ([[4, 4, 4], 1], [4, 4, 4])],
    """
from collections import deque

def sliding_window_max(nums, k):
    window, out = deque(), []
    for i, v in enumerate(nums):
        while window and nums[window[-1]] <= v:
            window.pop()
        window.append(i)
        if window[0] <= i - k:
            window.popleft()
        if i >= k - 1:
            out.append(nums[window[0]])
    return out
""")

# ----------------------------------------------------------------- trees ([value, left, right] or None)
add("trees", "easy", "Maximum Depth Of A Tree", "The tree is a nested list [value, left, right] (None = empty). Return the number of nodes on the longest root-to-leaf path.",
    "tree_max_depth", [("root", "Any")], "int",
    [([[3, [9, None, None], [20, [15, None, None], [7, None, None]]]], 3), ([None], 0)],
    [([[1, None, None]], 1), ([[1, [2, [3, [4, None, None], None], None], None]], 4), ([[1, None, [2, None, None]]], 2)],
    """
def tree_max_depth(root):
    if root is None:
        return 0
    return 1 + max(tree_max_depth(root[1]), tree_max_depth(root[2]))
""")
add("trees", "medium", "Count Tree Nodes", "Return the number of nodes in a tree given as nested [value, left, right] lists (None = empty).",
    "count_tree_nodes", [("root", "Any")], "int",
    [([[1, [2, None, None], [3, None, None]]], 3), ([None], 0)],
    [([[4, None, None]], 1), ([[1, [2, [4, None, None], None], [3, None, [5, None, None]]]], 5)],
    """
def count_tree_nodes(root):
    if root is None:
        return 0
    return 1 + count_tree_nodes(root[1]) + count_tree_nodes(root[2])
""")
add("trees", "hard", "Diameter Of A Binary Tree", "Return the number of edges on the longest path between any two nodes of the tree (nested [value, left, right] lists).",
    "tree_diameter", [("root", "Any")], "int",
    [([[1, [2, [4, None, None], [5, None, None]], [3, None, None]]], 3), ([[1, [2, None, None], None]], 1)],
    [([None], 0), ([[1, None, None]], 0), ([[1, [2, [3, [4, None, None], None], None], [5, None, [6, None, None]]]], 5)],
    """
def tree_diameter(root):
    best = 0
    def depth(node):
        nonlocal best
        if node is None:
            return 0
        left, right = depth(node[1]), depth(node[2])
        best = max(best, left + right)
        return 1 + max(left, right)
    depth(root)
    return best
""")

# ----------------------------------------------------------------- graphs (adjacency lists; graph[i] = neighbours of node i)
add("graphs", "easy", "Highest Out-Degree", "graph[i] lists the nodes that node i points to. Return the largest number of outgoing edges any node has (0 for an empty graph).",
    "max_out_degree", [("graph", "list[list[int]]")], "int",
    [([[[1, 2], [2], []]], 2), ([[[], [], []]], 0)],
    [([[]], 0), ([[[1], [0, 2, 3], [], []]], 3)],
    """
def max_out_degree(graph):
    return max((len(edges) for edges in graph), default=0)
""")
add("graphs", "medium", "Reachable Nodes", "Given an adjacency list and a start node, return how many nodes are reachable from start (including start).",
    "reachable_count", [("graph", "list[list[int]]"), ("start", "int")], "int",
    [([[[1, 2], [2], [0], []], 0], 3), ([[[1], [], []], 0], 2)],
    [([[[]], 0], 1), ([[[1], [], []], 2], 1), ([[[1], [2], [0, 3], []], 1], 4)],
    """
def reachable_count(graph, start):
    seen, stack = {start}, [start]
    while stack:
        for nxt in graph[stack.pop()]:
            if nxt not in seen:
                seen.add(nxt); stack.append(nxt)
    return len(seen)
""")
add("graphs", "hard", "Detect Cycle In A Directed Graph", "graph[i] lists the nodes that node i points to. Return True if the directed graph contains a cycle.",
    "has_cycle", [("graph", "list[list[int]]")], "bool",
    [([[[1], [2], [0]]], True), ([[[1, 2], [2], []]], False)],
    [([[]], False), ([[[0]]], True), ([[[1], [], [3], [1, 2]]], True), ([[[1], [2], [3], []]], False)],
    """
def has_cycle(graph):
    state = [0] * len(graph)   # 0 new, 1 visiting, 2 done
    def visit(node):
        if state[node] == 1:
            return True
        if state[node] == 2:
            return False
        state[node] = 1
        if any(visit(n) for n in graph[node]):
            return True
        state[node] = 2
        return False
    return any(visit(n) for n in range(len(graph)))
""")

# ----------------------------------------------------------------- greedy
add("greedy", "easy", "Fewest Coins", "Using unlimited coins of 1, 2, 5 and 10, return the fewest coins that add up to amount (greedy works for this coin set).",
    "fewest_coins", [("amount", "int")], "int",
    [([18], 4), ([0], 0)],
    [([1], 1), ([7], 2), ([99], 12)],
    """
def fewest_coins(amount):
    count = 0
    for coin in (10, 5, 2, 1):
        count += amount // coin
        amount %= coin
    return count
""")
add("greedy", "medium", "Jump Game", "nums[i] is the maximum jump length from index i. Return True if you can reach the last index starting from index 0.",
    "can_jump", [("nums", "list[int]")], "bool",
    [([[2, 3, 1, 1, 4]], True), ([[3, 2, 1, 0, 4]], False)],
    [([[0]], True), ([[1, 0, 1]], False), ([[2, 0, 0]], True)],
    """
def can_jump(nums):
    reach = 0
    for i, jump in enumerate(nums):
        if i > reach:
            return False
        reach = max(reach, i + jump)
    return True
""")
add("greedy", "hard", "Non-Overlapping Intervals", "Return the minimum number of intervals [start, end] to remove so the rest do not overlap (touching at an end point is allowed).",
    "erase_overlap", [("intervals", "list[list[int]]")], "int",
    [([[[1, 2], [2, 3], [3, 4], [1, 3]]], 1), ([[[1, 2], [1, 2], [1, 2]]], 2)],
    [([[]], 0), ([[[1, 2], [2, 3]]], 0), ([[[1, 100], [11, 22], [1, 11], [2, 12]]], 2)],
    """
def erase_overlap(intervals):
    removed, end = 0, float("-inf")
    for start, finish in sorted(intervals, key=lambda iv: iv[1]):
        if start >= end:
            end = finish
        else:
            removed += 1
    return removed
""")

# ----------------------------------------------------------------- backtracking
add("backtracking", "easy", "Binary Strings Of Length N", "Return every binary string of length n in ascending order.",
    "binary_strings", [("n", "int")], "list[str]",
    [([2], ["00", "01", "10", "11"]), ([1], ["0", "1"])],
    [([0], [""]), ([3], ["000", "001", "010", "011", "100", "101", "110", "111"])],
    """
def binary_strings(n):
    out = []
    def build(prefix):
        if len(prefix) == n:
            out.append(prefix); return
        build(prefix + "0"); build(prefix + "1")
    build("")
    return out
""")
add("backtracking", "medium", "Count Subsets With Target Sum", "Return how many subsets of nums (chosen by position, so equal values count separately) add up to target.",
    "count_subset_sums", [("nums", "list[int]"), ("target", "int")], "int",
    [([[1, 2, 3], 3], 2), ([[2, 4, 6], 5], 0)],
    [([[], 0], 1), ([[1, 1, 1], 2], 3), ([[5], 5], 1)],
    """
def count_subset_sums(nums, target):
    def go(i, remaining):
        if i == len(nums):
            return 1 if remaining == 0 else 0
        return go(i + 1, remaining) + go(i + 1, remaining - nums[i])
    return go(0, target)
""")
add("backtracking", "hard", "N-Queens Count", "Return how many ways n queens can be placed on an n x n board so that no two attack each other.",
    "n_queens", [("n", "int")], "int",
    [([4], 2), ([1], 1)],
    [([2], 0), ([3], 0), ([6], 4), ([8], 92)],
    """
def n_queens(n):
    def place(row, cols, d1, d2):
        if row == n:
            return 1
        total = 0
        for c in range(n):
            if c not in cols and row - c not in d1 and row + c not in d2:
                total += place(row + 1, cols | {c}, d1 | {row - c}, d2 | {row + c})
        return total
    return place(0, frozenset(), frozenset(), frozenset())
""")

# ----------------------------------------------------------------- dynamic programming
add("dynamic_programming", "easy", "Fibonacci Number", "Return the n-th Fibonacci number, where fib(0) = 0 and fib(1) = 1.",
    "fib", [("n", "int")], "int",
    [([2], 1), ([10], 55)],
    [([0], 0), ([1], 1), ([30], 832040)],
    """
def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
""")
add("dynamic_programming", "medium", "Climbing Stairs", "Return the number of distinct ways to climb n stairs taking one or two steps at a time.",
    "climb_stairs", [("n", "int")], "int",
    [([5], 8), ([6], 13)],
    [([1], 1), ([2], 2), ([20], 10946)],
    """
def climb_stairs(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a
""")
add("dynamic_programming", "hard", "House Robber", "Return the maximum amount that can be taken from houses in a row without taking from two adjacent houses.",
    "rob_houses", [("nums", "list[int]")], "int",
    [([[2, 7, 9, 3, 1]], 12), ([[2, 1, 1, 2]], 4)],
    [([[1, 2, 3, 1]], 4), ([[5, 1, 1, 5]], 10), ([[]], 0)],
    """
def rob_houses(nums):
    previous = current = 0
    for value in nums:
        previous, current = current, max(current, previous + value)
    return current
""")

# ----------------------------------------------------------------- recursion
add("recursion", "easy", "Factorial", "Return n! (the product 1 x 2 x ... x n), with 0! = 1.",
    "factorial", [("n", "int")], "int",
    [([5], 120), ([0], 1)],
    [([1], 1), ([10], 3628800), ([3], 6)],
    """
def factorial(n):
    return 1 if n <= 1 else n * factorial(n - 1)
""")
add("recursion", "medium", "Flatten Nested List", "Return all integers of an arbitrarily nested list in left-to-right order.",
    "flatten", [("nested", "list")], "list[int]",
    [([[1, [2, [3, 4]], 5]], [1, 2, 3, 4, 5]), ([[[[]]]], [])],
    [([[]], []), ([[[1], [2, [3]], [[4]]]], [1, 2, 3, 4]), ([[7]], [7])],
    """
def flatten(nested):
    out = []
    for item in nested:
        if isinstance(item, list):
            out.extend(flatten(item))
        else:
            out.append(item)
    return out
""")
add("recursion", "hard", "Integer Partitions", "Return the number of ways to write n as a sum of positive integers, ignoring order (e.g. 4 = 4, 3+1, 2+2, 2+1+1, 1+1+1+1).",
    "count_partitions", [("n", "int")], "int",
    [([4], 5), ([1], 1)],
    [([0], 1), ([5], 7), ([10], 42), ([30], 5604)],
    """
from functools import lru_cache

def count_partitions(n):
    @lru_cache(maxsize=None)
    def ways(remaining, largest):
        if remaining == 0:
            return 1
        return sum(ways(remaining - k, k) for k in range(1, min(largest, remaining) + 1))
    return ways(n, n)
""")

# ----------------------------------------------------------------- sorting
add("sorting", "easy", "Sort Ascending", "Return the values of nums sorted in ascending order (implement any sorting algorithm).",
    "sort_ascending", [("nums", "list[int]")], "list[int]",
    [([[5, 2, 3, 1]], [1, 2, 3, 5]), ([[5, 1, 1, 2, 0, 0]], [0, 0, 1, 1, 2, 5])],
    [([[]], []), ([[1]], [1]), ([[-1, -3, 2]], [-3, -1, 2])],
    """
def sort_ascending(nums):
    if len(nums) <= 1:
        return list(nums)
    mid = len(nums) // 2
    left, right = sort_ascending(nums[:mid]), sort_ascending(nums[mid:])
    out, i, j = [], 0, 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            out.append(left[i]); i += 1
        else:
            out.append(right[j]); j += 1
    return out + left[i:] + right[j:]
""")
add("sorting", "medium", "Kth Largest Element", "Return the k-th largest value in nums (k = 1 is the maximum; duplicates count separately).",
    "kth_largest", [("nums", "list[int]"), ("k", "int")], "int",
    [([[3, 2, 1, 5, 6, 4], 2], 5), ([[3, 2, 3, 1, 2, 4, 5, 5, 6], 4], 4)],
    [([[1], 1], 1), ([[2, 2, 2], 3], 2), ([[-1, -5, 0], 1], 0)],
    """
def kth_largest(nums, k):
    return sorted(nums, reverse=True)[k - 1]
""")
add("sorting", "hard", "Merge Intervals", "Merge all overlapping intervals [start, end] (touching intervals merge too) and return them sorted by start.",
    "merge_intervals", [("intervals", "list[list[int]]")], "list[list[int]]",
    [([[[1, 3], [2, 6], [8, 10], [15, 18]]], [[1, 6], [8, 10], [15, 18]]), ([[[1, 4], [4, 5]]], [[1, 5]])],
    [([[]], []), ([[[5, 7], [1, 2]]], [[1, 2], [5, 7]]), ([[[1, 10], [2, 3], [4, 11]]], [[1, 11]])],
    """
def merge_intervals(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged
""")

# ----------------------------------------------------------------- searching
add("searching", "easy", "Linear Search", "Return the index of the first occurrence of target in nums (unsorted), or -1.",
    "linear_search", [("nums", "list[int]"), ("target", "int")], "int",
    [([[4, 2, 7, 2], 2], 1), ([[1, 2, 3], 9], -1)],
    [([[], 1], -1), ([[5], 5], 0), ([[3, 3, 3], 3], 0)],
    """
def linear_search(nums, target):
    for i, v in enumerate(nums):
        if v == target:
            return i
    return -1
""")
add("searching", "medium", "Find A Peak", "A peak is an element strictly greater than its neighbours (outside the array counts as minus infinity). Return the index of the first peak from the left.",
    "first_peak", [("nums", "list[int]")], "int",
    [([[1, 2, 3, 1]], 2), ([[1, 2, 1, 3, 5, 6, 4]], 1)],
    [([[7]], 0), ([[5, 4, 3]], 0), ([[1, 2, 3]], 2)],
    """
def first_peak(nums):
    for i, v in enumerate(nums):
        left = nums[i - 1] if i > 0 else float("-inf")
        right = nums[i + 1] if i + 1 < len(nums) else float("-inf")
        if v > left and v > right:
            return i
    return -1
""")
add("searching", "hard", "Median Of Two Sorted Arrays", "Return the median of the combined values of two sorted arrays (at least one is non-empty).",
    "median_two_sorted", [("a", "list[int]"), ("b", "list[int]")], "float",
    [([[1, 3], [2]], 2.0), ([[1, 2], [3, 4]], 2.5)],
    [([[], [1]], 1.0), ([[0, 0], [0, 0]], 0.0), ([[1, 5, 9], [2, 3, 4, 10]], 4.0)],
    """
def median_two_sorted(a, b):
    merged, i, j = [], 0, 0
    while i < len(a) and j < len(b):
        if a[i] <= b[j]:
            merged.append(a[i]); i += 1
        else:
            merged.append(b[j]); j += 1
    merged += a[i:] + b[j:]
    n = len(merged)
    return float(merged[n // 2]) if n % 2 else (merged[n // 2 - 1] + merged[n // 2]) / 2
""")

# ----------------------------------------------------------------- heap
add("heap", "easy", "K Smallest Values", "Return the k smallest values of nums in ascending order.",
    "k_smallest", [("nums", "list[int]"), ("k", "int")], "list[int]",
    [([[7, 10, 4, 3, 20, 15], 3], [3, 4, 7]), ([[5, 1], 1], [1])],
    [([[1, 1, 1], 2], [1, 1]), ([[3], 0], []), ([[-2, 9, 0], 3], [-2, 0, 9])],
    """
import heapq

def k_smallest(nums, k):
    return heapq.nsmallest(k, nums)
""")
add("heap", "medium", "Top K Frequent", "Return the k most frequent values, most frequent first; ties are broken by the smaller value first.",
    "top_k_frequent", [("nums", "list[int]"), ("k", "int")], "list[int]",
    [([[1, 1, 1, 2, 2, 3], 2], [1, 2]), ([[1], 1], [1])],
    [([[4, 4, 5, 5, 6], 2], [4, 5]), ([[3, 3, 2, 2, 1, 1, 1], 1], [1]), ([[9, 8, 7], 3], [7, 8, 9])],
    """
import heapq
from collections import Counter

def top_k_frequent(nums, k):
    counts = Counter(nums)
    return [v for _, v in heapq.nsmallest(k, ((-c, v) for v, c in counts.items()))]
""")
add("heap", "hard", "Meeting Rooms Needed", "Given meetings [start, end), return the minimum number of rooms needed so no two overlapping meetings share a room.",
    "min_meeting_rooms", [("intervals", "list[list[int]]")], "int",
    [([[[0, 30], [5, 10], [15, 20]]], 2), ([[[7, 10], [2, 4]]], 1)],
    [([[]], 0), ([[[1, 5], [5, 10]]], 1), ([[[1, 10], [2, 7], [3, 19], [8, 12], [10, 20], [11, 30]]], 4)],
    """
import heapq

def min_meeting_rooms(intervals):
    ends, rooms = [], 0
    for start, end in sorted(intervals):
        while ends and ends[0] <= start:
            heapq.heappop(ends)
        heapq.heappush(ends, end)
        rooms = max(rooms, len(ends))
    return rooms
""")

# ----------------------------------------------------------------- bit manipulation
add("bit_manipulation", "easy", "Count Set Bits", "Return how many 1 bits are in the binary representation of the non-negative integer n.",
    "count_set_bits", [("n", "int")], "int",
    [([11], 3), ([128], 1)],
    [([0], 0), ([255], 8), ([1023], 10)],
    """
def count_set_bits(n):
    count = 0
    while n:
        n &= n - 1
        count += 1
    return count
""")
add("bit_manipulation", "medium", "Single Number", "Every value in nums appears twice except one. Return that value using O(1) extra space.",
    "single_number", [("nums", "list[int]")], "int",
    [([[2, 2, 1]], 1), ([[4, 1, 2, 1, 2]], 4)],
    [([[7]], 7), ([[-3, 5, 5]], -3), ([[0, 9, 9]], 0)],
    """
def single_number(nums):
    result = 0
    for v in nums:
        result ^= v
    return result
""")
add("bit_manipulation", "hard", "Maximum XOR Of Two Numbers", "Return the largest value of nums[i] XOR nums[j] over all pairs (i may equal j).",
    "max_xor_pair", [("nums", "list[int]")], "int",
    [([[3, 10, 5, 25, 2, 8]], 28), ([[0]], 0)],
    [([[14, 70, 53, 83, 49, 91, 36, 80, 92, 51, 66, 70]], 127), ([[8, 1, 2, 12]], 14), ([[5, 5]], 0)],
    """
def max_xor_pair(nums):
    best, mask = 0, 0
    for bit in range(31, -1, -1):
        mask |= 1 << bit
        prefixes = {v & mask for v in nums}
        candidate = best | (1 << bit)
        if any(candidate ^ p in prefixes for p in prefixes):
            best = candidate
    return best
""")

PROBLEMS = P
