"""The QA agent must survive a character its console cannot encode (TICK-253, #227).

`drain()` streams the model's own prose to stdout, and that prose routinely contains arrows and
box-drawing characters. Where stdout is cp1252 -- a Windows console, or any redirect to a file or
pipe on a Windows box -- a single `\u2192` raised UnicodeEncodeError, escaped `asyncio.run` and
killed the process partway through a run, before any report was written. It is not intermittent:
the tool had never once completed on such a console.

These are source-level checks, like `test_ios_no_arkit.py`, because importing `agent.py` needs the
`agents` extra that CI does not install. The behavioural test extracts the guard's own source and
runs it in a cp1252 subprocess, so it exercises the shipped code rather than a restatement of it.
"""

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

AGENT = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "qa-agent" / "agent.py"
GUARD = "allow_unencodable_output"
UNENCODABLE = "\u2192"


@pytest.fixture(scope="module")
def tree():
    if not AGENT.exists():
        pytest.skip(f"{AGENT} is not vendored in this checkout")
    return ast.parse(AGENT.read_text(encoding="utf-8"))


def _function(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def test_the_guard_exists(tree):
    assert _function(tree, GUARD) is not None, f"{GUARD}() is gone from agent.py"


def test_main_calls_the_guard_before_anything_can_print(tree):
    """Ordering is the whole point: a later call cannot save output already attempted."""
    main = _function(tree, "main")
    assert main is not None, "agent.py has no main()"

    first = main.body[0]
    called = (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Call)
        and getattr(first.value.func, "id", None) == GUARD
    )
    assert called, f"main() must call {GUARD}() as its first statement"


def test_the_guard_makes_an_unencodable_character_printable(tmp_path, tree):
    """Run the guard's own source on a cp1252 stream and print the character that killed a run."""
    guard = _function(tree, GUARD)
    script = tmp_path / "guard_check.py"
    script.write_text(
        "import sys\n"
        + ast.unparse(guard)
        + f"\n{GUARD}()\nprint({UNENCODABLE!r})\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )

    assert "UnicodeEncodeError" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
    assert UNENCODABLE in result.stdout
