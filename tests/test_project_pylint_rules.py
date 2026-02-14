"""Tests for custom project pylint rules."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run_pylint_for_source(
    *,
    tmp_path: Path,
    source: str,
    enable: str,
) -> subprocess.CompletedProcess[str]:
    file_path = tmp_path / "lint_target.py"
    file_path.write_text(source, encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pylint",
            str(file_path),
            "-rn",
            "-sn",
            "--disable=all",
            f"--enable={enable}",
            "--load-plugins=project_pylint_rules",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_prefer_union_rule_triggers_for_type_alias_pipe_union(tmp_path: Path) -> None:
    """The custom rule should reject ``|`` unions in ``type`` aliases."""
    result = _run_pylint_for_source(
        tmp_path=tmp_path,
        source=(
            "from __future__ import annotations\n"
            "from collections.abc import Mapping\n"
            "type JSONValue = str | list[str] | Mapping[str, str]\n"
        ),
        enable="prefer-union",
    )
    combined_output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0, combined_output
    assert "prefer-union" in combined_output, combined_output


def test_prefer_optional_rule_triggers_for_pipe_none(tmp_path: Path) -> None:
    """The existing custom rule should reject ``T | None`` syntax."""
    result = _run_pylint_for_source(
        tmp_path=tmp_path,
        source=("from __future__ import annotations\nvalue: str | None = None\n"),
        enable="prefer-optional",
    )
    combined_output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0, combined_output
    assert "prefer-optional" in combined_output, combined_output
