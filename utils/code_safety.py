"""
utils/code_safety.py

Small shared helpers used right before any LLM-generated code is exec()'d.
This is a denylist, not a sandbox -- it catches the obvious escape hatches
(imports, os/sys access, nested eval/exec) but should not be treated as a
security boundary for untrusted users. See README for the caveat.
"""

import re

FORBIDDEN_PATTERNS = [
    "import ", "__", "open(", "exec(", "eval(", "os.", "sys.",
    "subprocess", "input(", "globals(", "locals(", "compile(",
    "getattr(", "setattr(", "delattr(", ".system(",
]


def strip_code_fences(text: str) -> str:
    """
    Models sometimes wrap code in ```python ... ``` even when told not to.
    Strip that off so we're left with bare executable code.
    """
    text = text.strip()
    text = re.sub(r"^```(?:python)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def is_code_safe(code: str) -> bool:
    lowered = code.lower()
    return not any(pattern in lowered for pattern in FORBIDDEN_PATTERNS)
