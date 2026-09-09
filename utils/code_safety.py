"""
utils/code_safety.py

Small shared helpers used right before any LLM-generated code is exec()'d.
This is a denylist, not a sandbox -- it catches the obvious escape hatches
(imports, os/sys access, nested eval/exec) but should not be treated as a
security boundary for untrusted users. See README for the caveat.
"""

import re
import ast

FORBIDDEN_PATTERNS = [
    "import ", "__", "open(", "exec(", "eval(", "os.", "sys.",
    "subprocess", "input(", "globals(", "locals(", "compile(",
    "getattr(", "setattr(", "delattr(", ".system(",
]


def strip_code_fences(text: str) -> str:
    """
    Robustly extract Python code from LLM responses.
    Handles markdown fences (```python ... ```), intro text, and trailing commentary.
    """
    if not text:
        return ""

    raw = text.strip()

    # 1. Search for fenced code block anywhere in the LLM response
    fenced = re.search(r"```(?:python|py)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if fenced:
        candidate = fenced.group(1).strip()
        if candidate:
            return candidate

    # 2. Strip leading/trailing fences if partially formatted
    cleaned = re.sub(r"^```(?:python|py)?\s*", "", raw)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    # 3. If there is introductory text before the Python code (e.g. "Sure! Here is the code:"),
    # find the first line that parses into valid Python
    lines = cleaned.split("\n")
    for start_idx in range(len(lines)):
        chunk = "\n".join(lines[start_idx:]).strip()
        try:
            ast.parse(chunk)
            return chunk
        except SyntaxError:
            continue

    return cleaned


def is_code_safe(code: str) -> bool:
    lowered = code.lower()
    return not any(pattern in lowered for pattern in FORBIDDEN_PATTERNS)


def validate_python_syntax(code: str) -> tuple[bool, str]:
    """
    Validate that the code is syntactically valid Python.
    Returns (is_valid, error_message).
    """
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}"
