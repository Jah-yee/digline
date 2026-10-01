"""The first round, read and rendered through documented names only. (#277)

`read_baseline` answers `None` on a first round, `render_html` cannot take
that `None`, and `render_run_html` is what renders a run on its own. These
tests hold the chain `docs/api.md` gives a program outside digline: that it
produces the document `digline report` writes, and that on a projected page
it names nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.test_project_served import LEAKED, unpromoted
from tests.test_projection import Table

from digline.core import Contains, key_of
from digline.host import reported, suite_runs
from digline.report import Locale, render_run_html
from digline.run import Case, Suite
from digline.store import FileResultStore, RunRef

TENANT, SUITE = "acme", "support"


def first_round(root: Path) -> tuple[FileResultStore, str]:
    """A store holding one run and no baseline."""
    store = FileResultStore(root)
    run = unpromoted()
    store.write_run(run)
    return store, key_of(run.created_at, run.config_hash)


@pytest.mark.parametrize("locale", ["en", "it"])
def test_the_documented_chain_gives_the_document_report_writes(
    tmp_path: Path, locale: Locale
) -> None:
    store, key = first_round(tmp_path)
    assert store.read_baseline(TENANT, SUITE) is None

    run = store.read_run(RunRef(tenant=TENANT, suite=SUITE, key=key))
    suite = Suite(
        tenant=TENANT,
        environment="production",
        name=SUITE,
        assertions=[Contains(needle="x")],
        cases=[Case(id="unused")],
    )

    written = reported(store, suite, key, locale=locale, redacted=False)

    assert written.baseline is None
    assert render_run_html(run, locale=locale) == written.document


@pytest.mark.parametrize("locale", ["en", "it"])
def test_on_a_projected_page_the_first_round_names_nothing(
    tmp_path: Path, locale: Locale
) -> None:
    store, key = first_round(tmp_path)
    table = Table()

    listed = suite_runs(store, TENANT, SUITE, mint=table)
    assert listed.baseline_key is None and not listed.baseline_refused
    [(listed_key, shown)] = listed.runs

    html = render_run_html(shown, locale=locale)

    assert listed_key == key
    for name in LEAKED:
        assert name not in html, name
