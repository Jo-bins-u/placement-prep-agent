"""Child-process entry point: parse one resume file and print the result as JSON.

Run only by services/safe_parse.py. Before touching the file it caps its own memory and CPU
(so no `preexec_fn` is needed in the multi-threaded web server): RLIMIT_AS/RLIMIT_CPU on
Linux/macOS, and a watchdog on Windows that exits if memory use passes the limit.
"""

import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEMORY_LIMIT = int(os.environ.get("PREPWISE_PARSE_MEMORY", str(1024 * 1024 * 1024)))
CPU_SECONDS = int(os.environ.get("PREPWISE_PARSE_CPU", "20"))


def _limit_self() -> None:
    if os.name == "posix":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
        return
    try:  # Windows: poll this process's memory and bail out past the limit
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        get_info = ctypes.WinDLL("psapi").GetProcessMemoryInfo
        handle = ctypes.WinDLL("kernel32").GetCurrentProcess()

        def watch():
            counters = Counters()
            counters.cb = ctypes.sizeof(Counters)
            while True:
                if get_info(handle, ctypes.byref(counters), counters.cb) and counters.PagefileUsage > MEMORY_LIMIT:
                    os._exit(3)
                time.sleep(0.1)

        threading.Thread(target=watch, daemon=True).start()
    except Exception:  # pragma: no cover - the parent's wall-clock timeout still applies
        pass


def main() -> int:
    _limit_self()
    sys.path.insert(0, str(ROOT / "modules" / "profile_parsing"))
    sys.path.insert(0, str(ROOT))
    path, display_name = sys.argv[1], sys.argv[2]
    from extract_text import extract_text
    from parser import parse_resume

    raw_text = extract_text(path)
    profile = parse_resume(raw_text, source_file=display_name)
    sys.stdout.write(json.dumps({"profile": profile.to_dict(), "chars": len(raw_text)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
