"""One case, read down the runs instead of across a comparison.

`compare()` answers "what changed between these two". Calibration asks a
different question — "how does this case behave over five runs of the same
configuration" — and no pair of runs can answer it. That table was built by
hand, with a script, to choose which run to promote; this is the same table as
a pure fold.

Pure like the rest of `report`: it takes runs that someone else read.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from digline.core import DifferentRegimesError, Run, Verdict, is_token

__all__ = ["CaseEntry", "CaseHistory", "case_history"]


@dataclass(frozen=True, slots=True)
class CaseEntry:
    """How one run judged one case."""

    run_key: str
    created_at: str
    environment: str
    config_hash: str
    git_commit: str | None
    #: Empty when the run had the case but judged nothing, which happens when it
    #: was suspended. `suspended` says which of the two it was.
    verdicts: tuple[Verdict, ...]
    suspended: str | None
    #: False when the run does not contain the case at all — it was added or
    #: removed. A gap in a history is a fact about the suite, and blank rows
    #: that could mean either would hide it.
    present: bool = True


@dataclass(frozen=True, slots=True)
class CaseHistory:
    """One case across every run given, oldest first.

    Oldest first because the question is "how did it move", and a sequence read
    downward is read forward in time. The run list elsewhere is newest first
    because there the question is "what happened last".
    """

    case_id: str
    entries: tuple[CaseEntry, ...] = ()

    @property
    def assertion_names(self) -> tuple[str, ...]:
        """Every assertion name seen, in the order it first appears.

        Taken from the whole history rather than from the newest run: an
        assertion removed last week still has scores in the runs before it, and
        a column that disappeared would take that evidence with it.
        """
        seen: list[str] = []
        for entry in self.entries:
            for verdict in entry.verdicts:
                if verdict.score.name not in seen:
                    seen.append(verdict.score.name)
        return tuple(seen)

    def scores(self, entry: CaseEntry) -> Mapping[str, Verdict]:
        """The entry's verdicts keyed by assertion name, for tabulating.

        Two assertions can share a name — that is why `identity` exists — and
        here the later one wins. The column header is a name because a table
        the reader scans has to be readable; when two share one, the run list
        and the comparison are where the identities are told apart.
        """
        return {verdict.score.name: verdict for verdict in entry.verdicts}


def case_history(runs: Sequence[tuple[str, Run]], case_id: str) -> CaseHistory:
    """Fold `(key, run)` pairs into one case's history, oldest first.

    Sorted on `created_at`, the recorded fact, with the key as tie-breaker so
    two runs recorded in the same microsecond still order deterministically —
    a table whose row order changed between two renderings would be unusable
    for exactly the comparison it exists to support.

    **The history covers the runs it was given, and only those.** A run that
    was never read is not an absent entry, it is no entry: the rows on each
    side of it close up, and the gap reads as continuity. That is the shape of
    #287, where `log` folded a missing run away. What the read left out exists
    on the read, in `SuiteRuns.note()`, and nowhere here. **So whoever shows
    this history shows that note beside it.** It is the step that gets
    forgotten, which is why it is written on the fold and not only beside the
    read.

    **Refused**, as `DifferentRegimesError`, two ways:

    - runs of which some are projected and some are not. One names its cases
      by token and the other by text, so the case would be found in half of
      them and read as absent from the rest;
    - projected runs and a `case_id` that is not a token. A name in clear
      matches no token, so every entry would read `present=False`: *this case
      is in no run*, which is a wrong answer given in silence. The sentence
      does not quote the id, because the page a refusal reaches may be one
      that names nothing.

    **The other direction is not refused**: runs in clear and an id with a
    token's form. A case id is free text, and 22 characters of url-safe base64
    is a legal one.
    """
    regimes = {run.projected for _, run in runs}
    if len(regimes) > 1:
        raise DifferentRegimesError(
            "cannot fold one case across runs of which some are projected and "
            "some are not: one names its cases by token and the other by text, "
            "so the case would read as absent from half of them"
        )
    if regimes == {True} and not is_token(case_id):
        raise DifferentRegimesError(
            "the runs are projected and the case id is not a token: a name in "
            "clear matches no token, so the case would read as absent from "
            "every run. Ask for the case by the token its links carry"
        )
    entries: list[CaseEntry] = []
    for key, run in sorted(runs, key=lambda pair: (pair[1].created_at, pair[0])):
        found = next((c for c in run.results if c.case_id == case_id), None)
        entries.append(
            CaseEntry(
                run_key=key,
                created_at=run.created_at,
                environment=run.environment,
                config_hash=run.config_hash,
                git_commit=run.git_commit,
                verdicts=() if found is None else tuple(found.verdicts),
                suspended=None if found is None else found.suspended,
                present=found is not None,
            )
        )
    return CaseHistory(case_id=case_id, entries=tuple(entries))
