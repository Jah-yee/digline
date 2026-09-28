"""The example-locks gate: what it reads, that it runs, and that it can fail.

`tools/example_locks.py` runs `uv sync --locked` in every example that carries a
`uv.lock`. Three ways it could stop meaning anything, each pinned here:

- the list is written down somewhere and a new lock is skipped — `mcp-tools`
  was skipped by the release ritual for exactly that reason;
- the glob finds nothing and the loop is green over an empty list;
- `ci.yml` stops running it, and the only record left is a checklist.

The failing control is built offline: an example with no dependencies locks
without the index, and moving its `requires-python` afterwards is a lock that
no longer matches its `pyproject.toml` — the refusal `--locked` exists for.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from tests.test_releasing import gate_commands

from example_locks import ROOT, locked_examples, main

COMMAND = "uv run python tools/example_locks.py"


def _example(root: Path, name: str, requires_python: str) -> Path:
    directory = root / "examples" / name
    directory.mkdir(parents=True)
    (directory / "pyproject.toml").write_text(
        "[project]\n"
        f'name = "{name}"\n'
        'version = "0"\n'
        f'requires-python = "{requires_python}"\n'
        "dependencies = []\n"
        "\n"
        "[tool.uv]\n"
        "package = false\n",
        encoding="utf-8",
    )
    return directory


def _lock(directory: Path) -> None:
    subprocess.run(
        ["uv", "lock", "--offline"],
        cwd=directory,
        check=True,
        capture_output=True,
    )


def test_the_list_is_every_lock_in_the_tree() -> None:
    found = {path.name for path in locked_examples(ROOT)}
    # Deliberately not the function's own glob: the directories are walked and
    # asked, so a narrowed pattern would disagree with this.
    expected = {
        directory.name
        for directory in (ROOT / "examples").iterdir()
        if (directory / "uv.lock").is_file()
    }
    assert expected, "no example carries a uv.lock: the gate would check nothing"
    assert found == expected
    assert "mcp-tools" in found


def test_an_example_without_a_lock_is_not_asked(tmp_path: Path) -> None:
    locked = _example(tmp_path, "locked", ">=3.12")
    _lock(locked)
    _example(tmp_path, "unlocked", ">=3.12")
    assert locked_examples(tmp_path) == (locked,)


def test_nothing_to_check_is_a_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "examples").mkdir()
    assert main(tmp_path) == 1
    assert "nothing was checked" in capsys.readouterr().out


def test_a_lock_that_matches_installs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _lock(_example(tmp_path, "current", ">=3.12"))
    assert main(tmp_path) == 0
    assert "1 of 1 example locks install as written" in capsys.readouterr().out


def test_a_lock_behind_its_pyproject_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    current = _example(tmp_path, "current", ">=3.12")
    _lock(current)
    stale = _example(tmp_path, "stale", ">=3.12")
    _lock(stale)
    pyproject = stale / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8").replace(">=3.12", ">=3.11"),
        encoding="utf-8",
    )

    assert main(tmp_path) == 1
    out = capsys.readouterr().out
    # Why, not only that: the refusal is `--locked`'s, and the example that
    # still matches is reported as such rather than stopped at.
    assert "FAILED  stale" in out
    assert "needs to be updated" in out
    assert "ok      current" in out
    assert "1 of 2 example locks install as written" in out


def test_the_gates_job_runs_it() -> None:
    assert COMMAND in gate_commands()
