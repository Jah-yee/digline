"""The projection: a promoted reference with every name replaced by a token.

The committed file, when the store lives with the end company, is a
projection of a promotion that already happened (ADR 0034 §2). It is produced
inside the process that owns the name table (ADR 0036 §7), which is not
digline's: this module is what that process calls, and it is handed the minting
function rather than a table.
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from digline.core.aggregate import grouped_name, split_grouped_name
from digline.core.run import CaseResult, Run, SystemConfig, redact
from digline.core.tokens import Minter, TokenKind, is_token
from digline.core.types import NOTHING_EXTRA, ConfigValue, Verdict

__all__ = ["ProjectionRefusedError", "project"]


class ProjectionRefusedError(ValueError):
    """Raised when a run cannot be projected, or the minter answered wrong.

    A `ValueError` like the core's other refusals, and listed in
    `host.REFUSALS` so a front end translates it rather than crashing.
    """


def project(run: Run, mint: Minter) -> Run:
    """`run` as the software house may commit it: redacted, then every name
    replaced by the token `mint` returns for it.

    **The order is the definition.** The projection is `redact(run)` first and
    tokenisation after it, never the reverse. Redaction withholds the
    perimeter fields while their keys are still text: `base_url` and
    `fingerprint`, and `resolved_model` wherever `base_url` names an endpoint.
    Tokenise first and the keys are tokens, so nothing recognises them. The
    perimeter fields then cross under tokens, and the widening that withholds
    `resolved_model` never switches on. `Run`'s perimeter check does not catch
    that: on a projected document it cannot fire. It holds because nothing is
    there to find, and only this order puts nothing there. (ADR 0034 §8,
    §7.2's route)

    **No `Disclosure`.** Redaction here is with `NOTHING_EXTRA`. So the owning
    process needs no suite, and nothing a suite disclosed crosses a projection.
    That is a narrowing, and `projected` declares it.

    Where each name goes, by kind:

    - a case's id: `case_id`;
    - a verdict's name, and an aggregate's family: `verdict_name`;
    - the group inside `family[group=…]`: `group`, and the name is rebuilt
      with `grouped_name`, so it still parses;
    - a calibration band's check: `calibration_check`;
    - artifact paths, as keys and in `pinned`: `artifact_path`;
    - configuration keys, in `values` and in `withheld`, and string values:
      the key and value kinds of their side;
    - a judge's `provider/model` label: `judge_identity`.

    Numbers are left as they are: ADR 0034 §4 has not decided them.

    It returns a `Run`. It writes nothing, commits nothing, and knows neither
    the store nor where the document goes. `run_to_json` serializes it.

    **Refused**, as `ProjectionRefusedError`:

    - a run that is already projected;
    - a run that is not a promoted reference. **This is checked from what the
      document says, and nothing more**: `promoted_at` must be set and no
      recorded answer may remain. A `Run` built by hand with a stamp and no
      answers passes. Nothing on the value says that `promote_baseline`
      returned it, and nothing here can;
    - a token that is not a token: `mint` answered something without a
      token's form, gave one (kind, text) two tokens within this call, or
      gave two (kind, text) one token. **The check on a token is of its form**:
      a minter that echoed a 22-character name of the token alphabet back
      would pass;
    - an identity on the target side, which no kind covers. It is empty
      whenever digline wrote the run.

    What `Run` refuses of a projected document, it refuses here too, because
    the result is built through it.
    """
    if run.projected:
        raise ProjectionRefusedError(
            "this run is already projected: its names are tokens, and "
            "projecting it again would mint tokens for tokens"
        )
    if not run.promoted_at:
        raise ProjectionRefusedError(
            "this run was not promoted: a projection starts from the reference "
            "promote_baseline returns, which carries the time it was signed "
            "off, and this carries none"
        )
    if any(case.responses for case in run.results):
        raise ProjectionRefusedError(
            "this run still carries the target's recorded answers, and a "
            "promoted reference carries none: project the run promote_baseline "
            "returned"
        )
    if run.target_config.identities:
        raise ProjectionRefusedError(
            "the target configuration lists identities, which no token kind "
            "covers: digline records them on the judge side only"
        )
    # First, and for the reason in the docstring: withheld while the keys are
    # still text.
    source = redact(run, NOTHING_EXTRA)
    tokens = _Tokens(mint)
    return replace(
        source,
        results=tuple(_case(case, tokens) for case in source.results),
        aggregate=tuple(_aggregate(v, tokens) for v in source.aggregate),
        artifacts={
            tokens("artifact_path", path): artifact
            for path, artifact in source.artifacts.items()
        },
        pinned=tuple(tokens("artifact_path", path) for path in source.pinned),
        target_config=_config(
            source.target_config, tokens, "target_config_key", "target_config_value"
        ),
        judge_config=_config(
            source.judge_config, tokens, "judge_config_key", "judge_config_value"
        ),
        projected=True,
    )


class _Tokens:
    """`mint`, asked every time and held to one answer per (kind, text).

    Asked every time rather than cached, because a cache would hide the one
    inconsistency this call can see: a minter that answers one (kind, text)
    with two tokens. Two tokens for one name pair as `new` plus `missing`,
    which exits 0. (ADR 0036 §6)
    """

    def __init__(self, mint: Minter) -> None:
        self._mint = mint
        self._by_text: dict[tuple[TokenKind, str], str] = {}
        self._by_token: dict[str, tuple[TokenKind, str]] = {}

    def __call__(self, kind: TokenKind, text: str) -> str:
        # Held as `object`: the minter is the owning process's code, and its
        # annotation is a promise this checks rather than trusts.
        answer = cast(object, self._mint(kind, text))
        if not isinstance(answer, str) or not is_token(answer):
            raise ProjectionRefusedError(
                f"the minter answered {answer!r} for a {kind}, which does not "
                "have a token's form: 22 characters of url-safe base64"
            )
        token = answer
        seen = self._by_text.setdefault((kind, text), token)
        if seen != token:
            raise ProjectionRefusedError(
                f"the minter gave one {kind} two tokens in one projection: the "
                "same name would pair as new and missing"
            )
        owner = self._by_token.setdefault(token, (kind, text))
        if owner != (kind, text):
            raise ProjectionRefusedError(
                f"the minter gave a {kind} a token it had already given "
                f"another {owner[0]} in this projection: two names would read "
                "as one"
            )
        return token


def _verdict(verdict: Verdict, name: str) -> Verdict:
    return replace(verdict, score=replace(verdict.score, name=name))


def _case(case: CaseResult, tokens: _Tokens) -> CaseResult:
    return replace(
        case,
        case_id=tokens("case_id", case.case_id),
        verdicts=tuple(
            _verdict(v, tokens("verdict_name", v.score.name)) for v in case.verdicts
        ),
        calibration=(
            None
            if case.calibration is None
            else replace(
                case.calibration,
                check=tokens("calibration_check", case.calibration.check),
            )
        ),
    )


def _aggregate(verdict: Verdict, tokens: _Tokens) -> Verdict:
    family, group = split_grouped_name(verdict.score.name)
    name = tokens("verdict_name", family)
    if group is not None:
        name = grouped_name(name, tokens("group", group))
    return _verdict(verdict, name)


def _config(
    config: SystemConfig, tokens: _Tokens, key: TokenKind, value: TokenKind
) -> SystemConfig:
    def mapped(v: ConfigValue) -> ConfigValue:
        return tokens(value, v) if isinstance(v, str) else v

    return SystemConfig(
        values={tokens(key, k): mapped(v) for k, v in config.values.items()},
        withheld=frozenset(tokens(key, k) for k in config.withheld),
        identities=tuple(
            tokens("judge_identity", label) for label in config.identities
        ),
        projected=True,
    )
