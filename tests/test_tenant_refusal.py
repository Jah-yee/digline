"""The tenant's refusal has a name. (Delta-pass over 0.25.0, beside F-2)

`compare()` and `diff()` refused two tenants with a bare `ValueError`, which
`host.REFUSALS` does not name, so a front end that translates refusals by name
let it through as a crash. It was also the model `DifferentRegimesError`
copied, one line below it in `compare()`. Both now raise
`DifferentTenantsError`, a `ValueError` still, so a caller that caught the
builtin keeps working.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from digline.core import DifferentTenantsError, compare, diff
from digline.host import REFUSALS
from test_projection import promoted


def test_compare_refuses_two_tenants_by_name() -> None:
    run = promoted()
    with pytest.raises(DifferentTenantsError, match="across tenants"):
        compare(run, replace(run, tenant="globex"))


def test_diff_refuses_two_tenants_by_name() -> None:
    run = promoted()
    with pytest.raises(DifferentTenantsError, match="across tenants"):
        diff(run, replace(run, tenant="globex"))


def test_it_is_still_a_value_error() -> None:
    assert issubclass(DifferentTenantsError, ValueError)


def test_the_refusal_is_classified() -> None:
    assert DifferentTenantsError in REFUSALS
