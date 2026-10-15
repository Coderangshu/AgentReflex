"""Traceback Frame Regex Extractor for Speculative Prefetching.

Parses stack frames and compiler error diagnostics from test runners and command
outputs (Python, Rust, TypeScript, JavaScript, Go, C/C++, Ruby, PHP) to identify
culprit source files and proactively prefetch them into resident daemon RAM before
the LLM generates its next tool call.
"""

from __future__ import annotations
import os
import re
from pathlib import Path
from typing import List, Optional, Dict, Any


EXTERNAL_PATH_INDICATORS = (
    "/.venv/",
    "/venv/",
    "/site-packages/",
    "/dist-packages/",
    "/node_modules/",
    "/.cargo/registry/",
    "/.cargo/git/",
    "/.rustup/",
    "/usr/include/",
    "/usr/lib/",
    "/library/developer/",
    "/system/library/",
    "<string>",
    "<frozen",
    "<built-in>",
    "<stdin>",
    "<anonymous>",
)

# Ordered regex patterns matching compiler and runtime traceback frames
# Format: (language_tag, regex_pattern, file_group_idx, line_group_idx)
FRAME_PATTERNS = [
    # Python: File "/path/to/file.py", line 42, in fn_name
    (
        "python",
        re.compile(r'File\s+"([^"]+)",\s+line\s+(\d+)(?:,\s+in\s+([A-Za-z0-9_<>]+))?'),
        1,
        2,
    ),
    # Python alternative (unquoted File path.py, line 42)
    (
        "python",
        re.compile(r'File\s+([^\s,]+\.py),\s+line\s+(\d+)'),
        1,
        2,
    ),
    # Rust: --> src/main.rs:15:9
    (
        "rust",
        re.compile(r'-->\s+([^\s:]+\.rs):(\d+):(\d+)'),
        1,
        2,
    ),
    # Rust panic backtrace: at src/lib.rs:88:13
    (
        "rust",
        re.compile(r'at\s+([^\s:]+\.rs):(\d+):(\d+)'),
        1,
        2,
    ),
    # TypeScript / JavaScript (Node, Jest, Vitest, Bun): at /path/test.ts:42:15 or at func (/path/test.ts:42:15)
    (
        "javascript",
        re.compile(r'at\s+(?:[^\n(]+\s+\()?([^\s():]+\.(?:ts|tsx|js|jsx|mjs|cjs)):(\d+):(\d+)\)?'),
        1,
        2,
    ),
    # Go panic / test error: /path/to/main.go:42 or \t/path/to/main.go:42 +0x123
    (
        "go",
        re.compile(r'(?:^|\s|\t)([^\s:]+\.go):(\d+)(?::\d+|\s+\+0x)?', re.MULTILINE),
        1,
        2,
    ),
    # C / C++ compiler error: src/main.cpp:24:5: error: ...
    (
        "cpp",
        re.compile(r'([^\s:]+\.(?:c|cpp|cc|cxx|h|hpp)):(\d+):(\d+):\s+(?:fatal\s+)?error:'),
        1,
        2,
    ),
    # Ruby: from /path/to/app.rb:42:in `method'
    (
        "ruby",
        re.compile(r'(?:from\s+)?([^\s:]+\.rb):(\d+):in'),
        1,
        2,
    ),
    # PHP: in /path/to/file.php on line 42 or #0 /path/to/file.php(42): ...
    (
        "php",
        re.compile(r'(?:in\s+([^\s:]+\.php)\s+on\s+line\s+(\d+)|#\d+\s+([^\s:]+\.php)\((\d+)\))'),
        1,
        2,
    ),
]


def is_external_frame(path_str: str) -> bool:
    """Check if the path belongs to standard libraries, virtualenvs, or external packages."""
    if not path_str:
        return True
    norm = path_str.replace("\\", "/").lower()
    return any(indicator in norm for indicator in EXTERNAL_PATH_INDICATORS)


def extract_traceback_frames(text: str, cwd: Optional[str] = None) -> List[Dict[str, Any]]:
    """Extract all stack frames and error diagnostics from output text."""
    if not text or len(text.strip()) < 5:
        return []

    base_dir = Path(cwd).resolve() if cwd else Path.cwd().resolve()
    frames = []

    for lang, pattern, file_idx, line_idx in FRAME_PATTERNS:
        for match in pattern.finditer(text):
            # Special case for PHP multi-group pattern
            if lang == "php" and match.group(1) is None:
                file_str = match.group(3)
                line_str = match.group(4)
            else:
                file_str = match.group(file_idx)
                line_str = match.group(line_group_idx := line_idx)

            if not file_str:
                continue

            try:
                line_num = int(line_str)
            except (ValueError, TypeError):
                line_num = 1

            if is_external_frame(file_str):
                continue

            # Resolve file path
            p = Path(file_str)
            if not p.is_absolute():
                p = (base_dir / p).resolve()
            else:
                p = p.resolve()

            if p.is_file():
                frames.append({
                    "file": str(p),
                    "line": line_num,
                    "language": lang,
                    "raw_match": match.group(0),
                })

    return frames


def extract_culprit_frame(text: str, cwd: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Extract the primary culprit source file from a failure output.

    Iterates through detected stack frames in reverse (innermost crash frame nearest
    the bottom of the traceback) and returns the first existing local repository file.
    """
    frames = extract_traceback_frames(text, cwd=cwd)
    if not frames:
        return None

    # Innermost user code is typically the last frame in Python/Rust/JS backtraces
    return frames[-1]
