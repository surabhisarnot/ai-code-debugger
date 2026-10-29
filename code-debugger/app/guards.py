"""Small safety helpers. Phase 5 will grow this file."""
import re

MAX_CHARS = 20_000  # crude size limit


def add_line_numbers(code: str) -> str:
    lines = code.splitlines()
    width = len(str(len(lines)))
    return "\n".join(f"{i:>{width}} | {line}" for i, line in enumerate(lines, 1))


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def evidence_exists(evidence: str, code: str) -> bool:
    """True if the quoted evidence really appears in the submitted code."""
    return _normalize(evidence) in _normalize(code)
