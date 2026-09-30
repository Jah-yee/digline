"""`projected` verifies the form of every string it does not tokenise.
(Delta-pass over 0.25.0, F-4)

`_check_projected` refused a name in a case id or a verdict name, and let one
through in seven fields that are digline's own vocabulary (ADR 0034 §4, class
(a)): a verdict's and a band's `assertion_id`, `config_hash`,
`digline_version`, `rejudged_from`, `created_at`, `promoted_at` and
`resumed_at`. Their values are digests, versions, run keys and times, so each
is checked for that form, and a string without it is refused.

**It was reachable through `project` itself**, not only through a document
`project` did not write. The `Assertion` protocol lets `identity` be any
string, so a third-party assertion whose identity is readable text carried it
across the projection in clear. `project` now refuses that run by name, and
says what to use instead: `dataclass_identity`, which is what `AssertionBase`
derives.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace

import pytest

from digline.core import (
    AssertionBase,
    EvaluatorInputs,
    ProjectionRefusedError,
    Verdict,
    project,
    run_from_json,
    run_to_json,
)
from digline.core.run import DocumentRefusedError
from digline.run import Case, Response, Suite, execute
from test_projection import Table, promoted

NAME = "Mario Rossi IT60X0542811101"


def _edited(path: tuple[str | int, ...], value: object) -> str:
    """The projected document, with one field set to `value`."""
    document = json.loads(run_to_json(project(promoted(), Table())))
    target = document
    for step in path[:-1]:
        target = target[step]
    target[path[-1]] = value
    return json.dumps(document)


@pytest.mark.parametrize(
    "path",
    [
        pytest.param(("results", 0, "verdicts", 0, "assertion_id"), id="assertion_id"),
        pytest.param(("aggregate", 0, "assertion_id"), id="aggregate-assertion_id"),
        pytest.param(("config_hash",), id="config_hash"),
        pytest.param(("digline_version",), id="digline_version"),
        pytest.param(("rejudged_from",), id="rejudged_from"),
        pytest.param(("created_at",), id="created_at"),
        pytest.param(("promoted_at",), id="promoted_at"),
    ],
)
def test_a_name_in_a_field_of_digline_s_vocabulary_is_refused(
    path: tuple[str | int, ...],
) -> None:
    """Was: accepted, read back, and written out again."""
    with pytest.raises(DocumentRefusedError, match="Run.projected is set"):
        run_from_json(_edited(path, NAME))


def test_a_name_among_the_resume_times_is_refused() -> None:
    with pytest.raises(DocumentRefusedError, match="Run.projected is set"):
        run_from_json(_edited(("resumed_at",), [NAME]))


def test_the_forms_digline_writes_are_accepted() -> None:
    """The control: every value `project` produces has its form, so the
    projection round-trips, with a rejudged key and a resume time on it."""
    reference = replace(
        promoted(),
        digline_version="0.25.0",
        rejudged_from="2026-09-30T09-39-51-731311-00-00-282b0c02d6511fb4",
        resumed_at=("2026-09-30T10:05:00.123456+00:00",),
    )
    document = run_to_json(project(reference, Table()))
    assert run_to_json(run_from_json(document)) == document


@dataclass(frozen=True, slots=True)
class ReadableIdentity(AssertionBase):
    """What the protocol permits: an identity written by hand, as readable
    text."""

    name: str = "mentions_the_account"
    threshold: float = 0.5
    tolerance: float = 0.0

    @property
    def identity(self) -> str:
        return "rossi-mario-account-check"

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        return self._binary(True, "ok")


def test_project_refuses_a_readable_identity_and_names_the_way() -> None:
    """Was: `rossi-mario-account-check` in the projected document, in clear."""
    suite = Suite(
        tenant="acme",
        environment="test",
        name="triage",
        assertions=[ReadableIdentity()],
        cases=[Case(id="c1")],
    )
    run = execute(
        suite,
        lambda case: Response(output="ok"),
        created_at="2026-09-30T10:00:00+00:00",
    )
    reference = replace(
        run,
        promoted_at="2026-09-30T11:00:00+00:00",
        results=tuple(replace(case, responses=()) for case in run.results),
    )
    with pytest.raises(ProjectionRefusedError, match="dataclass_identity"):
        project(reference, Table())
