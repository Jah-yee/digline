"""The clock a library caller is sent to keeps two quick runs apart (#285).

A run's key is `created_at` slugged, then `config_hash`. Two runs of one suite
stamped in the same second share a key, and `write_run` then replaces the first
with the second, in silence. `execute()` takes `created_at` as a value and its
docstring names the clock to read it from. For as long as that name was
`store.utc_now_iso()`, which truncated to the second, following the
documentation lost a run: measured at `f2b9c5b`, two runs 2 ms apart, one file.

So the test does what a reader of that docstring does. It reads the name, stamps
two runs with that clock and writes both, then counts what is on disk.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Callable
from pathlib import Path
from typing import cast

from tests._helpers import write_suite

from digline.host import load_suite, load_target, read_artifacts
from digline.run import execute
from digline.store import FileResultStore


def documented_clock() -> Callable[[], str]:
    """The `utc_now_iso` `execute()`'s docstring names, imported as named."""
    doc = execute.__doc__ or ""
    named = re.findall(r"`([\w.]+)\.utc_now_iso\(\)`", doc)
    assert len(named) == 1, f"execute() should name one clock, it names {named}"
    module = named[0] if named[0].startswith("digline") else f"digline.{named[0]}"
    return cast(Callable[[], str], importlib.import_module(module).utc_now_iso)


def test_two_quick_runs_stamped_by_the_documented_clock_keep_two_keys(
    tmp_path: Path,
) -> None:
    clock = documented_clock()
    path = write_suite(tmp_path)
    suite, loaded = load_suite(str(path), root=tmp_path)
    target = load_target(None, loaded, str(path))
    store = FileResultStore(tmp_path)

    keys = [
        store.write_run(
            execute(
                suite,
                target,
                created_at=clock(),
                git_commit=None,
                artifacts=read_artifacts(suite, target, path.parent, root=tmp_path),
            )
        ).key
        for _ in range(2)
    ]

    assert len(set(keys)) == 2, f"two runs, one key: {keys}"
    assert len(store.scan_runs(suite.tenant, suite.name).runs) == 2
