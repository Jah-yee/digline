"""Condition 8 is an obligation no signature states, so a walk states it.

`promote_baseline`'s eight conditions live in three places (see
`digline/store/promotion.py`): the reading answers 1 and 7, `refusals_for`
answers the five that follow from the document, and **8 is left to each
backend, beside its own write** — because it asks what the store holds now, and
a parameter carrying that answer in would hide the window ADR 0031 leaves open
rather than close it.

The cost of that shape is that a backend can simply omit 8 and nothing catches
it: the pure function is silent about it by construction, and the type checker
cannot see a missing refusal. The protocol states the obligation in prose. This
file is the half that fails out loud, and the precedent is
`tests/test_refusals.py`: *"the list is not the guard. `tests/test_refusals.py`
is"*.

**What it reaches, stated rather than discovered.** The walk covers classes
defined under `digline`. A backend published as a separate distribution is out
of its reach, and so is one written by somebody else entirely — no device in
this repository can hold those, which is the same footing ADR 0034 §12 ruled
for the digests. What it does hold is every store this repository grows,
starting with the production store ADR 0002 §6 plans.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import textwrap

import digline
from digline.store import FileResultStore
from digline.store.promotion import refusal_for_a_moved_baseline, refusals_for

#: The name a class must reach to have met condition 8, and the name of the
#: function that writes its sentence.
CONDITION_8 = refusal_for_a_moved_baseline.__name__

#: The five that answer from the document, for the same reason.
THE_FIVE = refusals_for.__name__


def _promoting_classes() -> dict[str, type[object]]:
    """Every class defined under `digline` that implements `promote_baseline`.

    A `Protocol` is skipped: it *declares* the method, which is how the
    obligation is written down, not a place the obligation is met.
    `__main__` modules are skipped because importing one runs a command line.
    """
    found: dict[str, type[object]] = {}
    for info in pkgutil.walk_packages(digline.__path__, "digline."):
        if info.name.rsplit(".", 1)[-1] == "__main__":
            continue
        module = importlib.import_module(info.name)
        for value in vars(module).values():
            if (
                inspect.isclass(value)
                and value.__module__ == info.name
                and "promote_baseline" in vars(value)
                and not getattr(value, "_is_protocol", False)
            ):
                found[f"{info.name}.{value.__qualname__}"] = value
    return found


def _reaches(cls: type[object], target: str) -> bool:
    """Whether `promote_baseline` can reach `target`, following `self.…` calls
    within the class.

    **Not a text search over the class**, and the difference is the whole
    guard: `FileResultStore` calls the helper from a private method, so a class
    that kept that method and stopped calling it would satisfy a text search
    while promoting without condition 8. That mutation passed against the first
    version of this file, and this is what replaced it. It is held by
    `test_a_helper_that_is_kept_and_never_called_is_not_reached`, not by this
    sentence: a defect a docstring records is one nothing stops anybody from
    putting back.

    Reached through `getattr` it does not see — as `tests/test_plugin_floors.py`
    says of the same dodge, code written to be invisible to a check built to
    catch it is the worst remedy on the table, and the answer there holds here.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(cls)))
    classdef = tree.body[0]
    assert isinstance(classdef, ast.ClassDef)
    methods = {
        node.name: node
        for node in classdef.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    seen: set[str] = set()
    stack = ["promote_baseline"]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        node = methods.get(name)
        if node is None:
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and sub.id == target:
                return True
            if isinstance(sub, ast.Attribute):
                if sub.attr == target:
                    return True
                if isinstance(sub.value, ast.Name) and sub.value.id == "self":
                    stack.append(sub.attr)
    return False


def test_every_store_that_promotes_reaches_condition_8() -> None:
    """A class that promotes and never reaches `refusal_for_a_moved_baseline`
    has skipped the one condition the pure function cannot carry for it."""
    missing = sorted(
        name
        for name, cls in _promoting_classes().items()
        if not _reaches(cls, CONDITION_8)
    )
    assert not missing, (
        f"{', '.join(missing)} implements promote_baseline without reaching "
        f"{CONDITION_8}. Condition 8 — the baseline present is not the one the "
        "run was compared against — is the one condition left to each backend, "
        "beside its own write, and nothing else checks that it was met. Read "
        "the baseline inside whatever makes your write atomic and pass it to "
        f"{CONDITION_8}; see ResultStore.promote_baseline."
    )


def test_every_store_that_promotes_reaches_the_five() -> None:
    """The same for 2 to 6, where the failure is quieter: a backend that
    restates them has a second copy to keep in step with this one, and the
    protocol's own docstring records what that costs — it said "five
    conditions" while there were six."""
    missing = sorted(
        name
        for name, cls in _promoting_classes().items()
        if not _reaches(cls, THE_FIVE)
    )
    assert not missing, (
        f"{', '.join(missing)} implements promote_baseline without calling "
        f"{THE_FIVE}. The five conditions that answer from the document are a "
        "function so that no backend restates them."
    )


def test_the_walk_sees_the_one_store_there_is() -> None:
    """The control on both tests above, which pass on a walk that found
    nothing — and a walk over an installed package is exactly the kind of thing
    that quietly finds nothing. `FileResultStore` is the store this repository
    has; when there is a second, it is here too or this fails."""
    walked = _promoting_classes()
    assert walked, "the walk found no class implementing promote_baseline"
    assert "digline.store.file_store.FileResultStore" in walked, sorted(walked)
    assert walked["digline.store.file_store.FileResultStore"] is FileResultStore


class _KeepsTheHelperNeverCallsIt:
    """The mutation, kept: `FileResultStore`'s shape with the one call removed.
    The private method still names condition 8, so a text search over the class
    finds it; `promote_baseline` never reaches the method, so nothing is
    refused."""

    def promote_baseline(self) -> None:
        self._write()

    def _refuse_a_moved_baseline(self) -> object:
        return refusal_for_a_moved_baseline

    def _write(self) -> None:
        pass


class _KeepsTheHelperAndCallsIt:
    """The same class with the call in place — the control that says the
    mutant's `False` is the walk's answer, not a walk that answers `False` to
    everything."""

    def promote_baseline(self) -> None:
        self._refuse_a_moved_baseline()
        self._write()

    def _refuse_a_moved_baseline(self) -> object:
        return refusal_for_a_moved_baseline

    def _write(self) -> None:
        pass


def test_a_helper_that_is_kept_and_never_called_is_not_reached() -> None:
    """The defect `_reaches` was written to replace: a text search passes the
    mutant, and the walk must not."""
    assert CONDITION_8 in inspect.getsource(_KeepsTheHelperNeverCallsIt), (
        "the mutant no longer names condition 8, so it no longer fools a text "
        "search and this test proves nothing"
    )
    assert _reaches(_KeepsTheHelperAndCallsIt, CONDITION_8)
    assert not _reaches(_KeepsTheHelperNeverCallsIt, CONDITION_8)
