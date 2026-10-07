"""Deterministic pre-checks for file edits, shared by the agy and Claude Code hooks.

The Laya classifier over-scores short snippets (benign 3-line edits hit 90%+), so hooks check
edits with a high-precision credential regex first and only trust the model on longer edits.
"""

import re

MIN_EDIT_CHARS_FOR_MODEL = 200

SECRET_RE = re.compile(
    r"AKIA[0-9A-Z]{16}"
    r"|gh[pousr]_[A-Za-z0-9]{30,}"
    r"|sk_live_[A-Za-z0-9]{10,}"
    r"|sk-[A-Za-z0-9_-]{20,}"
    r"|-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    r"|(?i:(?:password|passwd|secret|api[_-]?key|access[_-]?key|auth[_-]?token|token)\w*)\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']"
    r"|(?i:(?:secret|api[_-]?key|access[_-]?key)\w*)\s*=\s*[A-Za-z0-9/+_-]{16,}"
)

SECRET_REASON = "AgentReflex: edit appears to contain a hardcoded secret or credential."


def has_hardcoded_secret(content: str) -> bool:
    return bool(SECRET_RE.search(content))
