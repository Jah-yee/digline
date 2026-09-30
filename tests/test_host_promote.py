"""`digline.host.promote`: the public route to a promotion (#256).

The store's `promote_baseline` checks a run against `expected_config_hash`, and
the value a caller outside digline could reach for that was the run's own hash —
a condition 2 that compares the run with itself. `promote` computes the hash
from the suite and the target measured. The first test here is the one that
turns red if it ever takes the hash from the run again.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests._helpers import baseline_in, run_key, write_suite

from digline.core import NO_BASELINE
from digline.host import REFUSALS, UsageError, load_suite, promote, utc_now_iso
from digline.store import ConfigMismatchError, FileResultStore

#: A second target with a declared price, so a run measured with it hashes
#: differently from one measured with the suite's own.
PRICED_TARGET = """
class Priced:
    price_digest = "feedbeefcafe0000"

    def __call__(self, case):
        return target(case)


other = Priced()
"""

WHEN = "2026-09-30T12:00:00+00:00"


def test_the_hash_is_the_suites_and_the_measured_targets_not_the_runs(
    repo: Path,
) -> None:
    """A run measured with `other` promoted as if measured with the suite's own
    target is refused: the hash `promote` computes is not the run's. Taking it
    from the run would promote here, with exit 0 and a wrong reference."""
    write_suite(repo, preamble=PRICED_TARGET)
    key = run_key(repo, "--target", "suite_qa.py:other")
    _suite, loaded = load_suite(str(repo / "suite_qa.py"), root=repo)
    store = FileResultStore(repo)

    with pytest.raises(ConfigMismatchError):
        promote(
            store,
            loaded,
            key,
            target=None,
            replacing=baseline_in(repo),
            promoted_at=WHEN,
        )

    promoted = promote(
        store,
        loaded,
        key,
        target=f"{repo / 'suite_qa.py'}:other",
        replacing=baseline_in(repo),
        promoted_at=WHEN,
    )
    assert promoted == store.read_baseline(promoted.tenant, promoted.suite)
    assert promoted.promoted_at == WHEN


def test_a_suite_with_no_target_promotes_with_none(repo: Path) -> None:
    """No `target` in the module and no spec: nothing is priced, as the command
    line has always promoted it."""
    key = run_key(repo)
    source = (repo / "suite_qa.py").read_text(encoding="utf-8")
    (repo / "suite_qa.py").write_text(
        source.replace("def target(case):", "def _target(case):"), encoding="utf-8"
    )
    _suite, loaded = load_suite(str(repo / "suite_qa.py"), root=repo)

    promoted = promote(
        FileResultStore(repo),
        loaded,
        key,
        target=None,
        replacing=baseline_in(repo),
        promoted_at=utc_now_iso(),
    )
    assert promoted.promoted_at


def test_latest_is_refused_and_the_refusal_is_classified(repo: Path) -> None:
    """`latest` is resolved by `resolve_key`, which returns what its scan
    stepped over; resolved inside `promote`, that note would have nowhere to
    go."""
    run_key(repo)
    _suite, loaded = load_suite(str(repo / "suite_qa.py"), root=repo)

    with pytest.raises(UsageError, match="resolve_key") as refused:
        promote(
            FileResultStore(repo),
            loaded,
            "latest",
            target=None,
            replacing=NO_BASELINE,
            promoted_at=WHEN,
        )
    assert isinstance(refused.value, REFUSALS)
