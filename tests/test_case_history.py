"""`case_history` on projected runs: the two ways it reads a case as absent
from every run when it is not, refused. (#278)

The second refusal is the one that matters: a case id in clear against
projected runs returned a history of `present=False` rows, which reads as
*this case is in no run*.
"""

from __future__ import annotations

import secrets

import pytest
from tests.test_projection import CASE, Table, promoted

from digline.core import DifferentRegimesError, Run, key_of, project_served
from digline.host import REFUSALS
from digline.report import case_history

T1, T2 = "2026-09-29T10:00:00+00:00", "2026-09-30T10:00:00+00:00"


def current(created_at: str) -> Run:
    return promoted(created_at=created_at, promoted_at="")


def pairs(*runs: Run) -> list[tuple[str, Run]]:
    return [(key_of(run.created_at, run.config_hash), run) for run in runs]


def test_projected_runs_fold_by_the_token_of_the_case() -> None:
    table = Table()
    runs = pairs(*(project_served(current(t), table) for t in (T1, T2)))

    history = case_history(runs, table.token("case_id", CASE))

    assert [entry.present for entry in history.entries] == [True, True]


def test_a_case_id_in_clear_against_projected_runs_is_refused() -> None:
    table = Table()
    runs = pairs(*(project_served(current(t), table) for t in (T1, T2)))

    with pytest.raises(DifferentRegimesError, match="not a token") as refused:
        case_history(runs, CASE)
    assert CASE not in str(refused.value)


def test_runs_of_two_regimes_are_refused() -> None:
    runs = pairs(current(T1), project_served(current(T2), Table()))

    with pytest.raises(DifferentRegimesError, match="some are projected"):
        case_history(runs, CASE)


def test_an_id_with_a_tokens_form_against_runs_in_clear_is_not_refused() -> None:
    """A case id is free text, and a token's form is a legal one."""
    history = case_history(pairs(current(T1)), secrets.token_urlsafe(16))
    assert [entry.present for entry in history.entries] == [False]


def test_runs_in_clear_fold_as_before() -> None:
    history = case_history(pairs(current(T2), current(T1)), CASE)
    assert [entry.created_at for entry in history.entries] == [T1, T2]
    assert all(entry.present for entry in history.entries)


def test_no_runs_is_an_empty_history_not_a_refusal() -> None:
    assert case_history([], CASE).entries == ()


def test_the_refusal_is_classified() -> None:
    assert DifferentRegimesError in REFUSALS
