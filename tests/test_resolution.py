"""The resolver: a projected document read back through the owning process's
lookup. Written from the mistakes it prevents — a document read against the
wrong table and reported green, one kind's text put where another's belongs,
and half a configuration read as a system. (ADR 0036 §2, §3, §8)
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

import pytest
from tests.test_projection import CASE, GROUP, Table, promoted

from digline.core import (
    NOTHING_EXTRA,
    NameRow,
    NothingResolvedError,
    NotProjectedError,
    Run,
    SystemConfig,
    TokenKind,
    UnresolvedConfigError,
    WrongKindError,
    WrongRowError,
    project,
    redact,
    resolve_tokens,
    run_to_json,
)
from digline.host import REFUSALS


@dataclass(frozen=True)
class Row:
    """A row the way the owning process keeps one. digline builds none: this
    satisfies `NameRow` by having the three fields, and imports nothing for it."""

    token: str
    kind: str
    text: str


class Owner:
    """The owning process: its table, its minter and its lookup, and a way to
    erase a row."""

    def __init__(self) -> None:
        self.table = Table()
        self.erased: set[str] = set()

    def mint(self, kind: TokenKind, text: str) -> str:
        return self.table(kind, text)

    def lookup(self, token: str) -> NameRow | None:
        if token in self.erased:
            return None
        for (kind, text), minted in self.table.rows.items():
            if minted == token:
                return Row(token, kind, text)
        return None

    def erase(self, kind: TokenKind, text: str) -> None:
        self.erased.add(self.table.token(kind, text))


def projected(owner: Owner, run: Run | None = None) -> Run:
    return project(promoted() if run is None else run, owner.mint)


# --------------------------------------------------------------------------- #
# The round trip
# --------------------------------------------------------------------------- #


def test_resolving_a_projection_gives_back_the_redacted_reference() -> None:
    """With every row present, the text comes back to every place it left,
    and the result is the reference as redaction alone would have written it:
    the reasons do not come back, and nothing else stays behind."""
    owner = Owner()
    reference = promoted()
    resolved = resolve_tokens(project(reference, owner.mint), owner.lookup)
    assert run_to_json(resolved) == run_to_json(redact(reference, NOTHING_EXTRA))


def test_the_resolved_run_is_redacted_and_no_longer_projected() -> None:
    owner = Owner()
    resolved = resolve_tokens(projected(owner), owner.lookup)
    assert (resolved.projected, resolved.redacted) == (False, True)


def test_the_named_endpoint_is_seen_again_once_resolved() -> None:
    """On the projected document the widening could not see `base_url`; with
    the text back it can, and `resolved_model` is withheld as it was."""
    owner = Owner()
    config = resolve_tokens(projected(owner), owner.lookup).target_config
    assert "resolved_model" in config.perimeter()
    assert {"base_url", "fingerprint", "resolved_model"} <= config.withheld


# --------------------------------------------------------------------------- #
# §8: the wrong table, and the empty document
# --------------------------------------------------------------------------- #


def test_a_document_read_against_another_table_is_refused() -> None:
    owner, other = Owner(), Owner()
    with pytest.raises(NothingResolvedError, match="another tenant's"):
        resolve_tokens(projected(owner), other.lookup)


def test_a_document_with_no_token_is_read() -> None:
    """Zero tokens is an empty document, not the wrong table."""
    owner = Owner()
    empty = promoted(
        results=(),
        aggregate=(),
        artifacts={},
        pinned=(),
        target_config=SystemConfig(),
        judge_config=SystemConfig(),
    )
    resolved = resolve_tokens(project(empty, owner.mint), Owner().lookup)
    assert resolved.projected is False
    assert resolved.results == ()


def test_an_erased_row_leaves_its_token_in_place() -> None:
    owner = Owner()
    run = projected(owner)
    owner.erase("case_id", CASE)
    resolved = resolve_tokens(run, owner.lookup)
    assert resolved.results[0].case_id == owner.table.token("case_id", CASE)
    assert resolved.results[1].case_id == "calibration-1"


def test_an_erased_group_leaves_the_name_parseable() -> None:
    owner = Owner()
    run = projected(owner)
    owner.erase("group", GROUP)
    name = resolve_tokens(run, owner.lookup).aggregate[1].score.name
    assert name == f"precision[group={owner.table.token('group', GROUP)}]"


# --------------------------------------------------------------------------- #
# §3: the kind is checked, and the row must be the token's
# --------------------------------------------------------------------------- #


def test_a_row_of_another_kind_is_refused() -> None:
    owner = Owner()
    run = projected(owner)

    def as_group(token: str) -> NameRow | None:
        row = owner.lookup(token)
        return None if row is None else Row(row.token, "group", row.text)

    with pytest.raises(WrongKindError, match="minted as group"):
        resolve_tokens(run, as_group)


def test_a_row_for_another_token_is_refused() -> None:
    owner = Owner()
    run = projected(owner)

    def shifted(token: str) -> NameRow | None:
        row = owner.lookup(token)
        return (
            None if row is None else Row(secrets.token_urlsafe(16), row.kind, row.text)
        )

    with pytest.raises(WrongRowError, match="another token"):
        resolve_tokens(run, shifted)


def test_an_answer_that_is_not_a_row_is_refused() -> None:
    owner = Owner()
    run = projected(owner)
    with pytest.raises(WrongRowError, match="not a row"):
        resolve_tokens(run, lambda token: "some text")  # pyright: ignore[reportArgumentType, reportUnknownLambdaType]


# --------------------------------------------------------------------------- #
# What else is refused
# --------------------------------------------------------------------------- #


def test_a_run_that_is_not_projected_is_refused() -> None:
    with pytest.raises(NotProjectedError, match="not projected"):
        resolve_tokens(promoted(), Owner().lookup)


@pytest.mark.parametrize(
    ("kind", "text"),
    [
        ("target_config_key", "provider"),
        ("target_config_value", "acme-private-model"),
        ("judge_config_key", "max_tokens"),
        ("judge_identity", "anthropic/claude-opus-5-5"),
    ],
)
def test_a_configuration_with_an_erased_row_is_refused(
    kind: TokenKind, text: str
) -> None:
    owner = Owner()
    run = projected(owner)
    owner.erase(kind, text)
    with pytest.raises(UnresolvedConfigError, match=kind):
        resolve_tokens(run, owner.lookup)


def test_every_resolver_refusal_is_classified() -> None:
    for refusal in (
        NothingResolvedError,
        NotProjectedError,
        UnresolvedConfigError,
        WrongKindError,
        WrongRowError,
    ):
        assert refusal in REFUSALS


def test_the_projection_and_the_resolver_read_one_map() -> None:
    """Every (kind, text) the projection minted is asked back under the same
    kind: nothing the projection wrote is outside the resolver's reach."""
    owner = Owner()
    run = projected(owner)
    asked: list[str] = []

    def recording(token: str) -> NameRow | None:
        asked.append(token)
        return owner.lookup(token)

    resolve_tokens(run, recording)
    assert set(asked) == set(owner.table.rows.values())


def test_redact_keeps_the_round_trip() -> None:
    """Resolving a projection that was redacted again changes nothing."""
    owner = Owner()
    run = projected(owner)
    assert run_to_json(resolve_tokens(redact(run), owner.lookup)) == run_to_json(
        resolve_tokens(run, owner.lookup)
    )


def test_a_resolved_run_can_be_projected_again_with_the_same_tokens() -> None:
    owner = Owner()
    first = projected(owner)
    again = project(resolve_tokens(first, owner.lookup), owner.mint)
    assert run_to_json(again) == run_to_json(first)
