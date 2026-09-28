"""`refusals_for` and `refusal_for_a_moved_baseline`, called on their own.

The point of the extraction is that these are answerable without a store: every
test here holds a `Run` and nothing else, which is the property the conditions
did not have while they were a method body.

The promotion behaviour they back — which refusal a person actually sees — is
`tests/test_promote_replacing.py`'s, and it is unchanged by the move.
"""

from __future__ import annotations

import pytest

from digline.core import (
    UNRECONCILED,
    CalibrationBand,
    CaseResult,
    Run,
    Score,
    Verdict,
    key_of,
)
from digline.store import (
    BaselineMovedError,
    ConfigMismatchError,
    ErroredRunError,
    ReplayedRunError,
    UncalibratedRunError,
    refusal_for_a_moved_baseline,
    refusals_for,
)

CFG = "hash-a"
REMOVED_BY = "git log -- .digline/acme/baselines/qa.json says which"


def verdict(
    *,
    name: str = "contains",
    score: float | None = 1.0,
    status: str = "pass",
    metadata: dict[str, object] | None = None,
    assertion_id: str = "contains-1",
    threshold: float = 1.0,
) -> Verdict:
    return Verdict(
        score=Score(name=name, score=score, metadata=metadata or {}),
        threshold=threshold,
        tolerance=0.0,
        status=status,  # type: ignore[arg-type]
        reason="found",
        assertion_id=assertion_id,
    )


def run(
    *results: CaseResult,
    created_at: str = "2026-01-01T10:00:00+00:00",
    config_hash: str = CFG,
    rejudged_from: str | None = None,
) -> Run:
    return Run(
        tenant="acme",
        environment="test",
        suite="qa",
        config_hash=config_hash,
        created_at=created_at,
        results=results or (CaseResult("case-1", (verdict(),)),),
        rejudged_from=rejudged_from,
    )


def a_gap() -> CaseResult:
    """A recorded gap: an errored verdict carrying the marker `unreconciled`
    reads on. It is *also* an errored verdict, which is the whole reason
    condition 6 has to fire before condition 3."""
    return CaseResult(
        "case-1",
        (verdict(score=None, status="error", metadata={UNRECONCILED: True}),),
    )


def out_of_band() -> CaseResult:
    return CaseResult(
        "cal-1",
        # Passing its own threshold and outside its band: a lost scale is a
        # real score in the wrong place, not a failing check.
        (verdict(name="score", score=0.2, assertion_id="score-1", threshold=0.0),),
        calibration=CalibrationBand(
            assertion_id="score-1", check="score", low=0.8, high=0.95
        ),
    )


# --------------------------------------------------------------------------- #
# Nothing to refuse
# --------------------------------------------------------------------------- #


def test_a_promotable_run_refuses_nothing() -> None:
    """The empty tuple is the answer, not the absence of one: `()` is a value a
    caller can assert on, print and pass around — the idiom `unreconciled` and
    `scale_lost` already use for *nothing wrong*."""
    assert refusals_for(run(), CFG) == ()


# --------------------------------------------------------------------------- #
# One condition at a time
# --------------------------------------------------------------------------- #


def test_a_configuration_that_moved_is_refused() -> None:
    (refusal,) = refusals_for(run(config_hash="hash-b"), CFG)
    assert isinstance(refusal, ConfigMismatchError)
    assert "hash-b" in str(refusal) and CFG in str(refusal)


def test_a_replayed_run_is_refused() -> None:
    (refusal,) = refusals_for(run(rejudged_from="an-earlier-run"), CFG)
    assert isinstance(refusal, ReplayedRunError)
    assert "an-earlier-run" in str(refusal)


def test_an_errored_verdict_is_refused() -> None:
    broken = CaseResult("case-1", (verdict(score=None, status="error"),))
    (refusal,) = refusals_for(run(broken), CFG)
    assert isinstance(refusal, ErroredRunError)
    assert "could not judge" in str(refusal)


def test_a_calibration_case_outside_its_band_is_refused() -> None:
    (refusal,) = refusals_for(run(out_of_band()), CFG)
    assert isinstance(refusal, UncalibratedRunError)
    assert "cal-1" in str(refusal)


# --------------------------------------------------------------------------- #
# The order, which is the contract
# --------------------------------------------------------------------------- #


def test_the_unreconciled_refusal_comes_before_the_errored_one() -> None:
    """6 before 3, asserted on the sequence rather than inferred from which
    exception escaped.

    The two share an exception type — the protocol's docstring records that it
    once said "five conditions" while there were six, "because the sixth shares
    an exception type with the third and is invisible to anyone counting types".
    A tuple makes it visible: one gap produces **both** refusals, the stronger
    one first, and a reader can see the pair.
    """
    first, second = refusals_for(run(a_gap()), CFG)
    assert isinstance(first, ErroredRunError) and isinstance(second, ErroredRunError)
    assert "does not reconcile" in str(first)
    assert "could not judge" in str(second)


def test_every_refusal_a_document_carries_comes_back_in_order() -> None:
    """2, 4, 6, 3, 5 — a run that breaks all of them answers once for each,
    which is what a single body raising the first could never show."""
    document = run(
        a_gap(),
        out_of_band(),
        config_hash="hash-b",
        rejudged_from="an-earlier-run",
    )
    assert [type(refusal) for refusal in refusals_for(document, CFG)] == [
        ConfigMismatchError,
        ReplayedRunError,
        ErroredRunError,
        ErroredRunError,
        UncalibratedRunError,
    ]


def test_the_run_is_named_by_the_key_its_own_document_claims() -> None:
    """A function holding only the run has one key available, and it is the one
    `write_run` files it under (the invariant on the protocol)."""
    document = run(config_hash="hash-b")
    (refusal,) = refusals_for(document, CFG)
    assert key_of(document.created_at, document.config_hash) in str(refusal)


# --------------------------------------------------------------------------- #
# Condition 8's sentence — one question, one answer
# --------------------------------------------------------------------------- #


def baseline(created_at: str, *, promoted_at: str = "") -> Run:
    return Run(
        tenant="acme",
        environment="test",
        suite="qa",
        config_hash=CFG,
        created_at=created_at,
        results=(CaseResult("case-1", (verdict(),)),),
        promoted_at=promoted_at,
    )


def test_the_reference_that_is_still_there_is_not_a_refusal() -> None:
    current = baseline("2026-01-01T09:00:00+00:00")
    expected = key_of(current.created_at, current.config_hash)
    assert (
        refusal_for_a_moved_baseline(run(), current, expected, removed_by=REMOVED_BY)
        is None
    )


def test_a_reference_that_moved_is_refused_and_both_keys_are_named() -> None:
    current = baseline("2026-01-01T09:00:00+00:00", promoted_at="2026-01-02T09:00:00Z")
    moved = refusal_for_a_moved_baseline(
        run(), current, "some-older-key", removed_by=REMOVED_BY
    )
    assert isinstance(moved, BaselineMovedError)
    assert "some-older-key" in str(moved)
    assert key_of(current.created_at, current.config_hash) in str(moved)
    assert "promoted 2026-01-02T09:00:00Z" in str(moved)


def test_a_reference_that_is_gone_sends_the_reader_where_the_backend_says() -> None:
    """`removed_by` is the one clause a backend writes for itself: the file
    store names a path for `git log`, and another backend names its own thing.
    """
    moved = refusal_for_a_moved_baseline(
        run(), None, "some-older-key", removed_by=REMOVED_BY
    )
    assert isinstance(moved, BaselineMovedError)
    assert REMOVED_BY in str(moved)


def test_none_is_not_a_wildcard() -> None:
    """`--replacing none` states that nothing is there, so a baseline being
    there refuses it."""
    current = baseline("2026-01-01T09:00:00+00:00")
    moved = refusal_for_a_moved_baseline(run(), current, None, removed_by=REMOVED_BY)
    assert isinstance(moved, BaselineMovedError)
    assert "has no baseline yet, and it has one" in str(moved)


def test_no_baseline_and_none_expected_is_the_first_promotion() -> None:
    assert (
        refusal_for_a_moved_baseline(run(), None, None, removed_by=REMOVED_BY) is None
    )


@pytest.mark.parametrize("expected", ["", "not-a-key"])
def test_a_first_promotion_that_expected_a_reference_is_refused(expected: str) -> None:
    moved = refusal_for_a_moved_baseline(run(), None, expected, removed_by=REMOVED_BY)
    assert isinstance(moved, BaselineMovedError)
    assert "no longer there" in str(moved)
