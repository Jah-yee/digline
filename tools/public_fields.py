"""The fields of every dataclass a public package lists, and what moved.

The third kind of new public surface the delta-pass lists (`RELEASING.md`,
*After the green, before the announcement*): **a dataclass is its fields**, so
a field added to a class an `__all__` already listed is new surface, and a
diff of the `__all__`s cannot see it. 0.25.3 is why: `SuiteRuns.unnamed`
arrived on a class that was public since 0.25.2.

Two modes, because the fields of a tag are only known by importing that tag:

    uv run python tools/public_fields.py > fields.json
    uv run python tools/public_fields.py --diff THEN.json NOW.json

The first prints the fields of the tree it runs in, as JSON. The second prints
every class and field added or removed between two such files, one per line,
and nothing when nothing moved. It exits 0 either way: what it prints is a
list to read, not a verdict.

**What it does not see**, and the rule says so where it is written: a class
that is not a dataclass, a `Protocol` and its methods first (`NameRow` is
one), and anything that changes inside a function without changing a name or
a field (#312).
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import sys
from pathlib import Path

#: Every package whose `__all__` is public: the core's six, then each plugin.
#: A plugin that is not installed is named on stderr and skipped, never dropped
#: in silence.
PACKAGES = (
    "digline.core",
    "digline.run",
    "digline.host",
    "digline.wire",
    "digline.store",
    "digline.report",
    "digline_anthropic",
    "digline_openai",
    "digline_bedrock",
    "digline_mcp",
    "pytest_digline",
)


def fields() -> dict[str, list[str]]:
    """`{"package.Name": [field, ...]}` for every dataclass an `__all__` lists."""
    found: dict[str, list[str]] = {}
    for package in PACKAGES:
        try:
            module = importlib.import_module(package)
        except ImportError as exc:
            print(f"not installed, not read: {package} ({exc})", file=sys.stderr)
            continue
        names: list[str] = list(getattr(module, "__all__", []))
        for name in names:
            value: object = getattr(module, name, None)
            if isinstance(value, type) and dataclasses.is_dataclass(value):
                found[f"{package}.{name}"] = [f.name for f in dataclasses.fields(value)]
    return found


def diff(then: dict[str, list[str]], now: dict[str, list[str]]) -> list[str]:
    """One line per class or field added or removed, in name order."""
    lines: list[str] = []
    for key in sorted(set(then) | set(now)):
        if key not in then:
            lines.append(f"class added    {key}: {', '.join(now[key])}")
        elif key not in now:
            lines.append(f"class removed  {key}")
        else:
            for name in now[key]:
                if name not in then[key]:
                    lines.append(f"field added    {key}.{name}")
            for name in then[key]:
                if name not in now[key]:
                    lines.append(f"field removed  {key}.{name}")
    return lines


def main(argv: list[str]) -> int:
    if argv[:1] == ["--diff"] and len(argv) == 3:
        then = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        now = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
        for line in diff(then, now):
            print(line)
        return 0
    if argv:
        print("usage: public_fields.py [--diff THEN.json NOW.json]", file=sys.stderr)
        return 64
    json.dump(fields(), sys.stdout, indent=1, sort_keys=True)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
