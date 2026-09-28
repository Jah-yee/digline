"""Whether a verdict carries the name of the assertion that produced it.

`Assertion.name` is the "human-facing label in the verdict", and `Score.name`
is copied verbatim into every document, redacted ones included. A verdict named
otherwise than its assertion is therefore a string nobody declared, crossing
where the declaration was supposed to be, and a name built from the answer
carries the answer out of the perimeter past the redaction of its reason.
(ADR 0034 §7, route 4)

So the driver refuses it: one errored verdict, marked, in place of the one it
refused. This module is the comparison and the marker, pure, so the online
driver calls the same function the offline one does (decisions 1 and 7).
(ADR 0027 §6, amended 2026-09-28)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from digline.core.assertions import error_verdict
from digline.core.protocols import Assertion
from digline.core.run import Run
from digline.core.types import Score, Verdict

__all__ = ["MISNAMED", "misnamed", "misnamed_verdict", "misnamings"]

#: The `Score.metadata` key the driver sets on the errored verdict it records in
#: place of one named otherwise than its assertion. A boolean, so it survives
#: `redact()` without a schema bump — which is the whole reason it exists: in a
#: redacted document the reason is gone, and without the marker the refusal
#: reads as an assertion that raised. (ADR 0027 §6, amended 2026-09-28)
#:
#: Like `UNRECONCILED`, it does not cross through the run projection on the
#: wire unless a suite discloses it; the readings on `compare --json` and
#: `explain --json` carry the count.
MISNAMED = "misnamed"


def misnamings(declared: str, verdicts: Iterable[Verdict]) -> tuple[str, ...]:
    """Every name among `verdicts` that is not `declared`, once each, in order.

    Empty when every verdict is named after its assertion. `declared` is the
    name captured before the first case, not `assertion.name` read now: an
    assertion that is not frozen could rename itself from the answer inside
    `__call__`, and a live read would then always agree with it.
    """
    # A dict as an ordered set: `set` would lose the order the names came in.
    wrong: dict[str, None] = {}
    for verdict in verdicts:
        if verdict.score.name != declared:
            wrong[verdict.score.name] = None
    return tuple(wrong)


def misnamed_verdict(
    assertion: Assertion, declared: str, names: Iterable[str]
) -> Verdict:
    """The errored, marked verdict that stands in for the refused one.

    Built from the assertion and never from the refused verdict, so none of the
    refused verdict's metadata survives: its score, its keys and its name all
    stay out of the document. The reason names what was refused, because a
    reason is payload and is withheld wherever the name would have mattered.
    """
    refused = ", ".join(repr(name) for name in names)
    verdict = error_verdict(
        assertion,
        f"the assertion {declared!r} returned a verdict named {refused}; a verdict "
        "carries the name of the assertion that produced it",
    )
    return replace(
        verdict, score=Score(name=declared, score=None, metadata={MISNAMED: True})
    )


def misnamed(run: Run) -> tuple[tuple[str, str], ...]:
    """The `(case_id, check)` pairs this run refused for their name, in run order.

    Read off the run alone, like `unreconciled`, so the headline, the reading
    and the single-run document say it without a reference. The marker counts
    only on an errored verdict and only when it is `True` by identity: anywhere
    else it would be a key an assertion happened to write.
    """
    return tuple(
        (case.case_id, verdict.score.name)
        for case in run.results
        for verdict in case.verdicts
        if verdict.status == "error" and verdict.score.metadata.get(MISNAMED) is True
    )
