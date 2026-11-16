"""Guardrails applied around the model: untrusted-content fencing, secret redaction, input limits."""

from __future__ import annotations

import re

MAX_QUESTION_CHARS = 4000

_SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"(?i)aws_secret_access_key\s*[=:]\s*\S+"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),  # GitHub tokens
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),  # Anthropic keys
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(password|passwd|secret|token)\s*[=:]\s*['\"]?[^\s'\"]{8,}"),
]


def redact(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def fence_untrusted(source: str, content: str) -> str:
    """Wrap tool output / retrieved text so the model treats it as data, never as instructions."""
    safe = redact(content).replace("</untrusted_data>", "</ untrusted_data>")
    return f'<untrusted_data source="{source}">\n{safe}\n</untrusted_data>'


class InputRejected(ValueError):
    pass


def check_question(question: str) -> str:
    q = question.strip()
    if not q:
        raise InputRejected("empty question")
    if len(q) > MAX_QUESTION_CHARS:
        raise InputRejected(f"question longer than {MAX_QUESTION_CHARS} characters")
    return q
