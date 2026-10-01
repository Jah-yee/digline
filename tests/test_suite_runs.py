"""`suite_runs`: the list a program shows, in clear or projected. (#276)

Written from the mistake each test prevents: one unreadable run taking the
whole list down, a run shown in clear on a projected page, a minter that pairs
rows that are not the same, and a baseline that could not be read reported as
no baseline at all.
"""

from __future__ import annotations

import inspect
import json
import secrets
from dataclasses import replace
from pathlib import Path

import pytest
from tests.test_projection import CHECK, FAMILY, NAMES, Table, promoted

from digline.core import (
    ProjectionRefusedError,
    Run,
    TokenKind,
    key_of,
    run_to_json,
)
from digline.core.run import SCHEMA_VERSION
from digline.host import REFUSALS, suite_runs
from digline.store import FileResultStore, PathRefusedError, RunRef

TENANT, SUITE = "acme", "support"
T1, T2, T3 = (
    "2026-09-28T10:00:00+00:00",
    "2026-09-29T10:00:00+00:00",
    "2026-09-30T10:00:00+00:00",
)


def current(created_at: str) -> Run:
    """A run as `execute` leaves it: nobody promoted it."""
    return promoted(created_at=created_at, promoted_at="")


def key(run: Run) -> str:
    return key_of(run.created_at, run.config_hash)


def stored(root: Path, *runs: Run) -> FileResultStore:
    store = FileResultStore(root)
    for run in runs:
        store.write_run(run)
    return store


def broken(store: FileResultStore, name: str) -> None:
    """A file the scan keeps, because its schema is current, and `read_run`
    refuses, because nothing else about it is a run."""
    path = store.runs_dir(TENANT) / SUITE / f"{name}.json"
    path.write_text(json.dumps({"schema_version": SCHEMA_VERSION}), encoding="utf-8")


def promote(store: FileResultStore, run: Run) -> None:
    store.promote_baseline(
        RunRef(tenant=TENANT, suite=SUITE, key=key(run)),
        run.config_hash,
        expected_baseline=None,
        promoted_at="2026-09-30T12:00:00+00:00",
    )


# --------------------------------------------------------------------------- #
# In clear
# --------------------------------------------------------------------------- #


def test_every_run_is_listed_by_key_with_the_baseline_marked(tmp_path: Path) -> None:
    older, newer = current(T1), current(T2)
    store = stored(tmp_path, older, newer)
    promote(store, older)

    listed = suite_runs(store, TENANT, SUITE, mint=None)

    assert [k for k, _ in listed.runs] == [key(older), key(newer)]
    assert [r for _, r in listed.runs] == [older, newer]
    assert listed.baseline_key == key(older)
    assert listed.note() == ""


def test_a_suite_with_no_runs_is_an_empty_list_not_a_refusal(tmp_path: Path) -> None:
    listed = suite_runs(FileResultStore(tmp_path), TENANT, SUITE, mint=None)
    assert listed.runs == ()
    assert listed.baseline_key is None
    assert listed.baseline_refused == ""


def test_one_run_the_store_refuses_does_not_take_the_others_down(
    tmp_path: Path,
) -> None:
    """The scan keeps a file at the current schema, and `read_run` can still
    refuse it. Every caller that read the scan by hand failed the whole list on
    it."""
    store = stored(tmp_path, current(T1), current(T2))
    broken(store, "2026-09-29T11-00-00-00-00-deadbeef")

    listed = suite_runs(store, TENANT, SUITE, mint=None)

    assert len(listed.runs) == 2
    [(refused_key, why)] = listed.refused
    assert refused_key == "2026-09-29T11-00-00-00-00-deadbeef"
    assert "redacted" in why  # the store's own sentence, in clear
    assert refused_key in listed.note()


def test_a_baseline_that_cannot_be_read_is_not_reported_as_none(
    tmp_path: Path,
) -> None:
    store = stored(tmp_path, current(T1))
    store.baseline_path(TENANT, SUITE).write_text(
        json.dumps({"schema_version": SCHEMA_VERSION}), encoding="utf-8"
    )

    listed = suite_runs(store, TENANT, SUITE, mint=None)

    assert listed.baseline_key is None
    assert listed.baseline_refused
    assert "the baseline could not be read" in listed.note()
    assert len(listed.runs) == 1


def test_a_baseline_whose_run_is_not_listed_is_said(tmp_path: Path) -> None:
    gone, kept = current(T1), current(T2)
    store = stored(tmp_path, gone, kept)
    promote(store, gone)
    store.run_path(RunRef(tenant=TENANT, suite=SUITE, key=key(gone))).unlink()

    listed = suite_runs(store, TENANT, SUITE, mint=None)

    assert listed.baseline_key == key(gone)
    assert f"promoted from run {key(gone)}, which is not in this list" in (
        listed.note()
    )


def test_a_name_that_is_not_one_segment_refuses_the_whole_call(
    tmp_path: Path,
) -> None:
    with pytest.raises(PathRefusedError):
        suite_runs(FileResultStore(tmp_path), TENANT, "../other", mint=None)


def test_the_minter_has_no_default() -> None:
    """A default would decide for a caller whether its page shows names."""
    parameter = inspect.signature(suite_runs).parameters["mint"]
    assert parameter.default is inspect.Parameter.empty


# --------------------------------------------------------------------------- #
# Projected
# --------------------------------------------------------------------------- #


def test_every_listed_run_is_projected_and_names_nothing(tmp_path: Path) -> None:
    store = stored(tmp_path, current(T1), current(T2), current(T3))

    listed = suite_runs(store, TENANT, SUITE, mint=Table())

    assert len(listed.runs) == 3
    for _, run in listed.runs:
        assert run.projected
        document = run_to_json(run)
        assert not [name for name in NAMES if name in document]


def test_rows_pair_by_name_across_the_list(tmp_path: Path) -> None:
    """What `runs_page` does with the list: hold each row's aggregates against
    the baseline's, by name. One token per name across the whole list."""
    store = stored(tmp_path, current(T1), current(T2))
    table = Table()

    listed = suite_runs(store, TENANT, SUITE, mint=table)

    names = [{v.score.name for v in run.aggregate} for _, run in listed.runs]
    assert names[0] == names[1]
    assert table.token("verdict_name", FAMILY) in names[0]


def test_a_key_is_the_same_projected_and_in_clear(tmp_path: Path) -> None:
    older, newer = current(T1), current(T2)
    store = stored(tmp_path, older, newer)
    promote(store, older)

    clear = suite_runs(store, TENANT, SUITE, mint=None)
    shown = suite_runs(store, TENANT, SUITE, mint=Table())

    assert [k for k, _ in shown.runs] == [k for k, _ in clear.runs]
    assert [key(r) for _, r in shown.runs] == [k for k, _ in shown.runs]
    assert shown.baseline_key == clear.baseline_key


def test_a_run_that_cannot_be_projected_is_left_out_not_shown_in_clear(
    tmp_path: Path,
) -> None:
    """A readable `assertion_id` is refused by the projection; its sentence
    quotes the id, so a projected page carries the refusal's type only."""
    readable = "leaks-account-data-for-rossi"
    bad = current(T2)
    bad = replace(
        bad,
        results=(
            replace(
                bad.results[0],
                verdicts=tuple(
                    replace(v, assertion_id=readable) for v in bad.results[0].verdicts
                ),
            ),
            *bad.results[1:],
        ),
    )
    store = stored(tmp_path, current(T1), bad)

    listed = suite_runs(store, TENANT, SUITE, mint=Table())

    assert [k for k, _ in listed.runs] == [key(current(T1))]
    assert listed.refused == ((key(bad), "ProjectionRefusedError"),)
    assert readable not in listed.note()
    assert CHECK not in listed.note()


def test_a_refusal_on_a_projected_list_carries_no_sentence(tmp_path: Path) -> None:
    store = stored(tmp_path, current(T1))
    broken(store, "2026-09-29T11-00-00-00-00-deadbeef")

    listed = suite_runs(store, TENANT, SUITE, mint=Table())

    assert listed.refused == (
        ("2026-09-29T11-00-00-00-00-deadbeef", "DocumentRefusedError"),
    )


class Forgetful(FileResultStore):
    """A store that wipes the minter's table before every read: each run is
    projected consistently on its own, and differently from the one before.
    `project_served` alone passes every run of it."""

    table: Table

    def read_run(self, ref: RunRef) -> Run:
        self.table.rows.clear()
        return super().read_run(ref)


def test_a_minter_that_answers_a_name_two_ways_across_the_list_is_refused(
    tmp_path: Path,
) -> None:
    store = Forgetful(tmp_path)
    store.table = Table()
    store.write_run(current(T1))
    store.write_run(current(T2))

    with pytest.raises(ProjectionRefusedError, match="two tokens in one list"):
        suite_runs(store, TENANT, SUITE, mint=store.table)


def test_a_minter_answering_without_a_tokens_form_refuses_the_whole_call(
    tmp_path: Path,
) -> None:
    """Not one run left out: every run would meet the same minter."""
    store = stored(tmp_path, current(T1), current(T2))

    def echo(kind: TokenKind, text: str) -> str:
        return text

    with pytest.raises(ProjectionRefusedError, match="token's form") as refused:
        suite_runs(store, TENANT, SUITE, mint=echo)
    assert not [name for name in NAMES if name in str(refused.value)]


def test_a_minter_giving_two_names_one_token_refuses_the_whole_call(
    tmp_path: Path,
) -> None:
    store = stored(tmp_path, current(T1))
    one = secrets.token_urlsafe(16)

    with pytest.raises(ProjectionRefusedError, match="two names would read as one"):
        suite_runs(store, TENANT, SUITE, mint=lambda kind, text: one)


def test_what_it_raises_is_a_refusal() -> None:
    assert ProjectionRefusedError in REFUSALS
    assert PathRefusedError in REFUSALS
