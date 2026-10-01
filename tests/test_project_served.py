"""The second way in: a run nobody promoted, projected for a page served at
the data owner's side.

Written from the mistake each test prevents: a served page that could show
only the reference (ADR 0038 §1), a served projection that carried more than a
projected reference (§2), a refusal of `project` that leaked into the new way
or one of `project_served`'s that fell out of it, and a document that a
renderer could not read. (ADR 0038 §1, §2, §3)
"""

from __future__ import annotations

import json
import secrets
from dataclasses import replace

import pytest
from tests.test_projection import CASE, CHECK, LEAKS, NAMES, Table, promoted, verdict

from digline.core import (
    REDACTED,
    CaseResult,
    ProjectionRefusedError,
    RecordedResponse,
    Run,
    Score,
    SystemConfig,
    Verdict,
    compare,
    project,
    project_served,
    run_from_json,
    run_to_json,
)
from digline.report import Locale, headline, render_html, render_run_html
from digline.store.promotion import refusals_for

ANSWER = "Dear Mario Rossi, your IBAN IT60X0542811101 is overdrawn"
TIMED_OUT = "the judge timed out reading the Rossi file"
NEW_CASE = "bianchi-anna-mortgage"
LEAKED = (*NAMES, ANSWER, TIMED_OUT, NEW_CASE)


def unpromoted() -> Run:
    """A run as the store holds it after a round: never promoted, its answers
    recorded, one check that got worse, and one that could not be judged."""
    base = promoted()
    errored = Verdict(
        score=Score(name=CHECK, score=None),
        threshold=0.5,
        status="error",
        reason=TIMED_OUT,
        assertion_id=LEAKS,
    )
    return replace(
        base,
        promoted_at="",
        created_at="2026-10-01T09:00:00+00:00",
        results=(
            CaseResult(
                CASE,
                (verdict(CHECK, LEAKS, 0.3),),
                responses=(RecordedResponse(output=ANSWER, kind="text"),),
            ),
            *base.results[1:],
            CaseResult(NEW_CASE, (errored,)),
        ),
    )


# --------------------------------------------------------------------------- #
# What it accepts that `project` refuses
# --------------------------------------------------------------------------- #


def test_a_run_nobody_promoted_is_projected() -> None:
    served = project_served(unpromoted(), Table())
    assert served.projected
    assert served.redacted
    assert served.promoted_at == ""


def test_project_still_refuses_the_same_run() -> None:
    """The committed file keeps both refusals. The new way did not remove
    them from `project`; it is a second name, not a switch on the first."""
    with pytest.raises(ProjectionRefusedError, match="not promoted"):
        project(unpromoted(), Table())
    answered = replace(unpromoted(), promoted_at="2026-10-01T10:00:00+00:00")
    with pytest.raises(ProjectionRefusedError, match="recorded answers"):
        project(answered, Table())


def test_project_names_the_way_for_a_page() -> None:
    with pytest.raises(ProjectionRefusedError, match="project_served"):
        project(unpromoted(), Table())


def test_promotions_refusals_are_not_applied() -> None:
    """The states promotion refuses are the ones a reviewer most needs to
    see: here an errored verdict, a replayed run and an old configuration."""
    run = replace(
        unpromoted(), rejudged_from="2026-09-30T10-00-00-00-00-c0ffee00c0ffee00"
    )
    assert len(refusals_for(run, "0123456789abcdef")) == 3
    served = project_served(run, Table())
    assert served.rejudged_from == run.rejudged_from
    assert [v.status for v in served.results[3].verdicts] == ["error"]


# --------------------------------------------------------------------------- #
# What it carries: a projected reference's, plus what a run has (ADR 0038 §2)
# --------------------------------------------------------------------------- #


def test_a_served_projection_names_nothing() -> None:
    document = run_to_json(project_served(unpromoted(), Table()))
    for name in LEAKED:
        assert name not in document, name


def test_the_answers_cross_as_a_count_and_nothing_else() -> None:
    served = project_served(unpromoted(), Table())
    assert served.results[0].responses == (RecordedResponse(withheld=True),)
    raw = json.loads(run_to_json(served))
    assert raw["results"][0]["responses"] == [{"withheld": True}]


def test_an_errored_verdict_keeps_its_status_and_loses_its_reason() -> None:
    errored = project_served(unpromoted(), Table()).results[3].verdicts[0]
    assert (errored.status, errored.reason) == ("error", REDACTED)


def test_for_a_reference_both_ways_give_the_same_document() -> None:
    """`project` is `project_served` with two refusals in front. Through one
    table they produce one document, so a page and a commit never disagree
    about what a reference says."""
    table = Table()
    assert run_to_json(project(promoted(), table)) == run_to_json(
        project_served(promoted(), table)
    )


def test_a_served_projection_reads_back() -> None:
    served = project_served(unpromoted(), Table())
    assert run_from_json(run_to_json(served)) == served


# --------------------------------------------------------------------------- #
# What it still refuses
# --------------------------------------------------------------------------- #


def test_a_served_projection_is_not_projected_again() -> None:
    table = Table()
    with pytest.raises(ProjectionRefusedError, match="already projected"):
        project_served(project_served(unpromoted(), table), table)


def test_an_identity_on_the_target_side_is_refused() -> None:
    target = SystemConfig(values={"provider": "p", "model": "m"}, identities=("p/m",))
    with pytest.raises(ProjectionRefusedError, match="no token kind"):
        project_served(replace(unpromoted(), target_config=target), Table())


def test_a_readable_identity_is_refused() -> None:
    run = unpromoted()
    readable = replace(
        run.results[0], verdicts=(verdict(CHECK, "rossi-mario-account-check"),)
    )
    with pytest.raises(ProjectionRefusedError, match="dataclass_identity"):
        project_served(replace(run, results=(readable, *run.results[1:])), Table())


def test_an_answer_without_a_tokens_form_is_refused() -> None:
    with pytest.raises(ProjectionRefusedError, match="token's form"):
        project_served(unpromoted(), lambda kind, text: text)


def test_a_minter_answering_one_name_twice_differently_is_refused() -> None:
    with pytest.raises(ProjectionRefusedError, match="two tokens"):
        project_served(unpromoted(), lambda kind, text: secrets.token_urlsafe(16))


def test_a_minter_giving_two_names_one_token_is_refused() -> None:
    constant = secrets.token_urlsafe(16)
    with pytest.raises(ProjectionRefusedError, match="already given"):
        project_served(unpromoted(), lambda kind, text: constant)


# --------------------------------------------------------------------------- #
# Shape B: two projections through one table, compared (ADR 0038 §3)
# --------------------------------------------------------------------------- #


def test_through_one_table_the_comparison_finds_the_regression() -> None:
    table = Table()
    reference = project(promoted(), table)
    served = project_served(unpromoted(), table)
    comparison = compare(served, reference)
    assert headline(comparison, served, reference, locale="en").worse
    regressed = [d.case_id for d in comparison.deltas if d.outcome == "regressed"]
    assert regressed == [table.token("case_id", CASE)]


# --------------------------------------------------------------------------- #
# The renderers read it (ADR 0038 §1: without them the new way buys nothing)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("locale", ["en", "it"])
def test_a_served_run_renders_on_its_own_and_names_nothing(locale: Locale) -> None:
    table = Table()
    html = render_run_html(project_served(unpromoted(), table), locale=locale)
    for name in LEAKED:
        assert name not in html, name
    assert table.token("case_id", NEW_CASE) in html


@pytest.mark.parametrize("locale", ["en", "it"])
def test_a_served_run_renders_against_the_reference_and_names_nothing(
    locale: Locale,
) -> None:
    table = Table()
    reference = project(promoted(), table)
    served = project_served(unpromoted(), table)
    html = render_html(compare(served, reference), served, reference, locale=locale)
    for name in LEAKED:
        assert name not in html, name
    assert table.token("case_id", CASE) in html
