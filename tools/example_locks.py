"""Every example that carries a `uv.lock` installs exactly as that lock says.

    uv run python tools/example_locks.py

For each `examples/*/uv.lock` — found by looking, the same glob
`.github/release_followup.py` reads, never a list written down — this runs
`uv sync --locked` in that example's directory, with the interpreter's own
minor version, into a throwaway environment. `--locked` refuses a lock that no
longer matches its `pyproject.toml` instead of quietly rewriting it, which is
what a bare `uv sync` does and exits 0 over.

It exists because nothing else looked at those locks before a merge: the
`gates` tests import the examples against the source tree, with the root lock's
versions, and the only job that installs an example from its own lock,
`examples-from-pypi`, does not run on a pull request. A dependabot bump of an
example lock was therefore first installed by the post-release check of the
release it rode in.

**What it does not prove is written beside the step in `ci.yml`, and it is most
of what matters about an example.** Read that paragraph before reading a green
here as "the examples work".

Nothing here touches the examples' own `.venv`: each sync goes into a
temporary directory through `UV_PROJECT_ENVIRONMENT`, so running this locally
leaves a working example exactly as it was.

A tool, not part of the package: it lives outside `src/` and is never shipped.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def locked_examples(root: Path) -> tuple[Path, ...]:
    """Every example directory that carries a `uv.lock`, in a fixed order."""
    return tuple(sorted(lock.parent for lock in root.glob("examples/*/uv.lock")))


def sync_locked(example: Path, python: str) -> subprocess.CompletedProcess[str]:
    """`uv sync --locked` in `example`, into an environment that is thrown away."""
    env = dict(os.environ)
    # `uv run` exports the workspace's environment; left in place, uv warns that
    # it does not match the example's and ignores it. Removed so the output
    # says only what the sync found.
    env.pop("VIRTUAL_ENV", None)
    with tempfile.TemporaryDirectory() as scratch:
        env["UV_PROJECT_ENVIRONMENT"] = str(Path(scratch) / "venv")
        return subprocess.run(
            ["uv", "sync", "--locked", "--python", python],
            cwd=example,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )


def main(root: Path = ROOT) -> int:
    examples = locked_examples(root)
    if not examples:
        # A loop over nothing is green and proves nothing.
        print(f"no examples/*/uv.lock under {root}: nothing was checked")
        return 1
    python = f"{sys.version_info.major}.{sys.version_info.minor}"
    failed: list[str] = []
    for example in examples:
        result = sync_locked(example, python)
        name = example.name
        if result.returncode == 0:
            print(f"ok      {name}")
        else:
            failed.append(name)
            print(f"FAILED  {name} (exit {result.returncode})")
            print(result.stderr.rstrip())
    print(
        f"{len(examples) - len(failed)} of {len(examples)} example locks "
        f"install as written on Python {python}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
