"""The release's signatures, driven against an index that answers like PyPI.

`.github/release_bundles.py` turns PyPI's PEP 740 attestations into the
`.sigstore.json` files attached to a GitHub release. What is pinned here is the
part that is ours: **which files it picks**, **when it refuses**, and that the
bundle is the one the reference library makes — **byte for byte the same on a
second run**, which is what makes `gh release upload --clobber` safe.

The attestations are real: PyPI's own, for `digline 0.19.1` (signed from
`refs/tags/v0.19.1`) and `digline-anthropic 0.5.3` (signed from
`refs/tags/v0.17.0`), saved under `tests/fixtures/provenance/`. The expected
bundle beside them is what `pypi_attestations.Attestation.to_bundle` produced
from the first, 0.0.30, on 2026-09-24.

**What no test here proves**: that a signature is valid. That is
`sigstore verify github --ref`, which the workflow runs on every bundle against
the served file — the script selects, the verifier proves. The served bytes
here are stand-ins with their own digests, so a signature check against them
would fail by construction and would not be a test of anything of ours.

The index is local, like `test_await_index.py`'s, for fixed decision 5 and
because the refusals cannot be produced on purpose against the real one.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "release_bundles.py"
FIXTURES = ROOT / "tests" / "fixtures" / "provenance"

CORE = "digline-0.19.1-py3-none-any.whl"
PLUGIN = "digline_anthropic-0.5.3-py3-none-any.whl"


def provenance(filename: str) -> bytes:
    return (FIXTURES / f"{filename}.provenance.json").read_bytes()


@contextmanager
def index(
    releases: dict[tuple[str, str], list[str]],
    attestations: dict[str, bytes],
    *,
    corrupt: frozenset[str] = frozenset(),
    lag: dict[str, int] | None = None,
    down: frozenset[str] = frozenset(),
) -> Generator[str]:
    """An index serving `releases` — (name, version) to filenames — and their
    attestations by filename. A file in `corrupt` is served with bytes that do
    not match the digest its JSON page states.

    `lag` is PyPI after an upload: a path starting with one of its keys answers
    404 to that many requests before it answers at all, which is what
    `/pypi/digline/0.23.0/json` did for 36 seconds on v0.23.0. A path starting
    with one of `down` answers 503 every time: an index that does not answer."""
    pending = dict(lag or {})
    lock = Lock()

    def body(filename: str) -> bytes:
        return f"stand-in for {filename}".encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's name
            if any(self.path.startswith(prefix) for prefix in down):
                self.send_error(503)
                return
            with lock:
                prefix = next((p for p in pending if self.path.startswith(p)), None)
                if prefix is not None and pending[prefix] > 0:
                    pending[prefix] -= 1
                    self.send_error(404)
                    return
            parts = self.path.strip("/").split("/")
            if parts[0] == "pypi" and (parts[1], parts[2]) in releases:
                urls = [
                    {
                        "filename": filename,
                        "url": f"http://{self.headers['Host']}/files/{filename}",
                        "digests": {
                            "sha256": hashlib.sha256(body(filename)).hexdigest()
                        },
                    }
                    for filename in releases[(parts[1], parts[2])]
                ]
                self._send(json.dumps({"urls": urls}).encode())
            elif parts[0] == "integrity" and parts[3] in attestations:
                self._send(attestations[parts[3]])
            elif parts[0] == "files":
                data = body(parts[1])
                self._send(data + b"!" if parts[1] in corrupt else data)
            else:
                self.send_error(404)

        def _send(self, data: bytes) -> None:
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def run(
    tmp_path: Path,
    url: str,
    tag: str,
    dist: list[str],
    out: str = "out",
    *,
    timeout: str = "1",
) -> subprocess.CompletedProcess[str]:
    """The script as the workflow runs it: from a checkout with `dist/` in it.

    The wait is a second here and not the workflow's ten minutes, with reads
    a hundredth of a second apart; `timeout="0"` is one read, the script as it
    was before it waited."""
    (tmp_path / "dist").mkdir(exist_ok=True)
    for filename in dist:
        (tmp_path / "dist" / filename).write_bytes(b"built here, never read")
    return subprocess.run(
        [sys.executable, str(SCRIPT), tag, out],
        cwd=tmp_path,
        env={"INDEX": url, "PATH": "", "TIMEOUT": timeout, "INTERVAL": "0.01"},
        capture_output=True,
        text=True,
        timeout=60,
    )


BOTH = {("digline", "0.19.1"): [CORE], ("digline-anthropic", "0.5.3"): [PLUGIN]}
BOTH_SIGNED = {CORE: provenance(CORE), PLUGIN: provenance(PLUGIN)}


def test_the_tag_s_own_file_gets_the_bundle_the_reference_library_makes(
    tmp_path: Path,
) -> None:
    with index(BOTH, BOTH_SIGNED) as url:
        result = run(tmp_path, url, "v0.19.1", [CORE, PLUGIN])

    assert result.returncode == 0, result.stderr
    written = json.loads((tmp_path / "out" / f"{CORE}.sigstore.json").read_text())
    expected = json.loads((FIXTURES / f"{CORE}.expected.sigstore.json").read_text())
    assert written == expected
    assert (
        tmp_path / "out" / "served" / CORE
    ).read_bytes() == f"stand-in for {CORE}".encode()


def test_a_file_an_earlier_tag_published_is_skipped_by_name(tmp_path: Path) -> None:
    """Every tag rebuilds every package, so `dist/` holds older plugin versions
    too. Their attestations name the tag that published them, and that is how
    they are told apart — not by a list a re-run would find empty."""
    with index(BOTH, BOTH_SIGNED) as url:
        result = run(tmp_path, url, "v0.19.1", [CORE, PLUGIN])

    assert f"skip     {PLUGIN}  — published by refs/tags/v0.17.0" in result.stdout
    assert not (tmp_path / "out" / f"{PLUGIN}.sigstore.json").exists()
    assert sorted(p.name for p in (tmp_path / "out").glob("*.sigstore.json")) == [
        f"{CORE}.sigstore.json"
    ]


def test_the_same_input_twice_writes_the_same_bytes(tmp_path: Path) -> None:
    """What makes `--clobber` safe: a re-run replaces a bundle with itself."""
    with index(BOTH, BOTH_SIGNED) as url:
        first = run(tmp_path, url, "v0.19.1", [CORE, PLUGIN], out="first")
        second = run(tmp_path, url, "v0.19.1", [CORE, PLUGIN], out="second")

    assert first.returncode == second.returncode == 0
    name = f"{CORE}.sigstore.json"
    assert (tmp_path / "first" / name).read_bytes() == (
        tmp_path / "second" / name
    ).read_bytes()


def test_an_empty_list_is_refused_rather_than_passed(tmp_path: Path) -> None:
    """A job that attaches nothing and passes is the check that cannot fail,
    and the release would go out unsigned with a green on it."""
    only_plugin = {("digline-anthropic", "0.5.3"): [PLUGIN]}
    with index(only_plugin, {PLUGIN: provenance(PLUGIN)}) as url:
        result = run(tmp_path, url, "v0.19.1", [PLUGIN])

    assert result.returncode == 1
    assert "no file on" in result.stderr
    assert "the check that cannot fail" in result.stderr
    assert not list((tmp_path / "out").glob("*.sigstore.json"))


def test_the_tag_s_own_version_signed_from_another_ref_is_refused(
    tmp_path: Path,
) -> None:
    """A file at the tag's own version is this tag's by construction: a foreign
    signature on it is a fault, not a skip."""
    with index({("digline", "0.19.1"): [CORE]}, {CORE: provenance(PLUGIN)}) as url:
        result = run(tmp_path, url, "v0.19.1", [CORE])

    assert result.returncode == 1
    assert (
        f"{CORE} is at the tag's own version and was signed from refs/tags/v0.17.0"
        in result.stderr
    )


def test_the_tag_s_own_version_without_an_attestation_is_refused(
    tmp_path: Path,
) -> None:
    with index({("digline", "0.19.1"): [CORE]}, {}) as url:
        result = run(tmp_path, url, "v0.19.1", [CORE])

    assert result.returncode == 1
    assert (
        f"{CORE} is at the tag's own version and PyPI holds no attestation"
        in result.stderr
    )


def test_bytes_that_do_not_match_the_index_s_own_digest_are_refused(
    tmp_path: Path,
) -> None:
    with index(BOTH, BOTH_SIGNED, corrupt=frozenset({CORE})) as url:
        result = run(tmp_path, url, "v0.19.1", [CORE, PLUGIN])

    assert result.returncode == 1
    assert f"{CORE}: the bytes PyPI serves do not match" in result.stderr
    assert not (tmp_path / "out" / f"{CORE}.sigstore.json").exists()


CORE_PAGE = "/pypi/digline/0.19.1/json"
CORE_PROVENANCE = f"/integrity/digline/0.19.1/{CORE}/provenance"


def test_a_page_that_404s_after_the_upload_is_waited_for(tmp_path: Path) -> None:
    """v0.22.0 and v0.23.0: `/simple/` served the version, and the JSON page
    this script asks for answered 404 for another half a minute. Read again,
    it answers, and the release gets its signatures on the first attempt."""
    with index(BOTH, BOTH_SIGNED, lag={CORE_PAGE: 3}) as url:
        result = run(tmp_path, url, "v0.19.1", [CORE, PLUGIN])

    assert result.returncode == 0, result.stderr
    assert f"served   {url}{CORE_PAGE}" in result.stdout
    assert "read 4" in result.stdout
    assert (tmp_path / "out" / f"{CORE}.sigstore.json").exists()


def test_the_same_lag_read_once_is_refused(tmp_path: Path) -> None:
    """The control for the test above, and the one that must fail: the same
    index, read once, as the script read it before it waited. If this passed,
    the lag in the fixture would not be what the wait is being credited with."""
    with index(BOTH, BOTH_SIGNED, lag={CORE_PAGE: 3}) as url:
        result = run(tmp_path, url, "v0.19.1", [CORE, PLUGIN], timeout="0")

    assert result.returncode == 1
    assert "digline 0.19.1 is in dist/ and" in result.stderr
    assert "answered 404" in result.stderr


def test_an_attestation_that_lags_its_file_is_waited_for(tmp_path: Path) -> None:
    """The second read the job makes has the same race as the first, and a
    404 there is refused at the tag's own version and skipped at any other,
    which for a plugin this tag published would lose its bundle in silence."""
    with index(BOTH, BOTH_SIGNED, lag={CORE_PROVENANCE: 2}) as url:
        result = run(tmp_path, url, "v0.19.1", [CORE, PLUGIN])

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "out" / f"{CORE}.sigstore.json").exists()


def test_a_404_that_holds_for_the_whole_wait_is_still_refused(
    tmp_path: Path,
) -> None:
    """Waiting does not turn a real absence into a pass: a version the index
    never serves is refused, after the wait and by the same name."""
    with index(BOTH, BOTH_SIGNED, lag={CORE_PAGE: 10_000}) as url:
        result = run(tmp_path, url, "v0.19.1", [CORE, PLUGIN], timeout="0.3")

    assert result.returncode == 1
    assert "No signatures for this release" in result.stderr
    assert "answered 404 for it until the last read" in result.stderr


def test_an_index_that_never_answers_is_not_judged_rather_than_refused(
    tmp_path: Path,
) -> None:
    """The third word. A 503 on every read says nothing about the release, so
    it must not come out as *not on PyPI* or as *no attestation*: exit 2, and
    a title that says nothing was judged."""
    with index(BOTH, BOTH_SIGNED, down=frozenset({CORE_PAGE})) as url:
        page = run(tmp_path, url, "v0.19.1", [CORE, PLUGIN], timeout="0.3")
    with index(BOTH, BOTH_SIGNED, down=frozenset({CORE_PROVENANCE})) as url:
        provenance = run(tmp_path, url, "v0.19.1", [CORE, PLUGIN], timeout="0.3")

    for result in (page, provenance):
        assert result.returncode == 2, result.stderr
        assert "Signatures not judged" in result.stderr
        assert "No signatures for this release" not in result.stderr
        assert "re-run the job" in result.stderr
