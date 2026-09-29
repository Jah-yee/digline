"""Write a Sigstore bundle for every file this tag put on PyPI — and nothing else.

OpenSSF Scorecard's Signed-Releases looks at the files attached to a GitHub
release and wants one ending in `.sigstore.json`. PyPI already holds a
signature for every file we upload: `pypa/gh-action-pypi-publish` makes a PEP
740 attestation under trusted publishing, signed by `publish.yml` in the `pypi`
environment. This script turns those attestations into bundles. It signs
nothing itself, and it attaches **signatures, never packages** — RELEASING.md,
*Signatures on the GitHub release*, says why, and it is the answer to anybody
who proposes attaching the packages "for completeness".

    python .github/release_bundles.py <tag> <out-dir>

Reads `dist/` for the names and versions to ask about — never for bytes — and
`INDEX` (default https://pypi.org). Writes, for each file this tag published:

    <out-dir>/<file>.sigstore.json    the bundle, which is what gets attached
    <out-dir>/served/<file>           the file as PyPI serves it, to verify against

**Which files are this tag's** is read from the attestation, not from
`to-publish/`: the signing certificate names the ref the upload ran from. Every
tag rebuilds every package, so `dist/` also holds plugin versions an earlier tag
released; their certificates name that tag and they are skipped by name. A
re-run of the release finds the same attestations and writes the same bytes,
which is what makes `gh release upload --clobber` safe.

**The read of the ref selects; it does not prove.** The workflow then runs
`sigstore verify github --ref refs/tags/<tag>` on every bundle against the
served file, so a misread ref can fail the job but cannot pass one.

**It waits for the index, and it keeps a third word.** This job runs right
after the upload, and `/pypi/<name>/<version>/json` can answer 404 for a
version that `/simple/` already serves. It did so on v0.22.0 and again on
v0.23.0, each time within a minute of the upload. The `pypi` job's
wait (`await_index.py`) asks `/simple/`, which is not the question asked here,
so this script waits for its own: every page and every attestation it needs is
read until it answers or `TIMEOUT` runs out. A read then ends in one of three
words, never two:

- **an answer**, a page or a 404 that held for the whole wait;
- **absent**: a 404, and the last read was a 404 too;
- **unread**: the index never answered at all (a 5xx, a timeout, no route).

The last one is refused by a different sentence and a different exit code,
because it is not a fact about PyPI. A 404 read once and believed is an
absence of an answer taken for an answer, which is the shape that produced
v0.22.0's and v0.23.0's red.

    TIMEOUT    seconds each read may wait for an answer, default 600
    INTERVAL   seconds between reads, default 10

`TIMEOUT=0` is one read, which is the behaviour before the wait, and the
test's control.

**Every read waits, including the attestations of files at other versions.**
A plugin this tag published sits at a version that is not the tag's, and
its attestation is exactly as fresh as the core's. A short read there would
skip its bundle in silence. What that costs: a file PyPI really holds no
attestation for is skipped only after the whole wait. None does. Checked on
2026-09-29, every file of the six versions a tag builds today answered 200
at `/integrity/…/provenance`.

It refuses — exit 1, by name — when:

- **the list comes out empty.** A job that attaches nothing and passes is the
  check that cannot fail, and the tag's own release would go out unsigned with
  a green on it. Anticipated here rather than discovered.
- **a package at the tag's own version has a file without this tag's
  attestation.** Those files are this tag's by construction, so a missing or
  foreign signature on one is a fault, not a skip.
- **PyPI serves a file whose bytes do not match its own digest**, or an
  attestation that does not name this repository and `publish.yml`.

And it stops — exit 2, *not judged* — when a read it needs was never answered.
That is not a refusal of the release: nothing was learned about it, and a
re-run is the remedy.

Standard library only: like the other scripts here it runs under the runner's
bare `python3`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Literal

INDEX = os.environ.get("INDEX", "https://pypi.org").rstrip("/")

#: The two words a read ends in besides an answer. `absent` is a fact about the
#: index, and `unread` is the absence of one.
ABSENT: Literal["absent"] = "absent"
UNREAD: Literal["unread"] = "unread"
Reading = bytes | Literal["absent", "unread"]
REPOSITORY = "digline/digline"
WORKFLOW = "publish.yml"

#: Fulcio's "Source Repository Ref" extension, 1.3.6.1.4.1.57264.1.14, as the
#: DER bytes of its OBJECT IDENTIFIER. The value is a UTF8String such as
#: `refs/tags/v0.19.1`, wrapped in the extension's OCTET STRING.
SOURCE_REF_OID = bytes.fromhex("060a2b0601040183bf30010e")

BUNDLE_MEDIA_TYPE = "application/vnd.dev.sigstore.bundle.v0.3+json"
IN_TOTO = "application/vnd.in-toto+json"


class Refused(Exception):
    """A reason to fail the job, worded for the log."""


class NotJudged(Exception):
    """A read the index never answered: nothing was learned, so nothing is refused."""


def name_and_version(path: pathlib.Path) -> tuple[str, str]:
    """The same parse as `select_unpublished.py`, normalised for PyPI's URLs."""
    if path.name.endswith(".whl"):
        name, version = path.name.split("-")[:2]
    else:
        name, version = path.name.removesuffix(".tar.gz").rsplit("-", 1)
    return name.replace("_", "-").lower(), version


def _der_length(data: bytes, at: int) -> tuple[int, int]:
    """The length at `at`, and where its content starts. Short and long form."""
    first = data[at]
    if first < 0x80:
        return first, at + 1
    count = first & 0x7F
    return int.from_bytes(data[at + 1 : at + 1 + count]), at + 1 + count


def source_ref(certificate: bytes) -> str | None:
    """The ref a Fulcio certificate says the signing workflow ran from.

    A minimal DER read, not a certificate parser: find the extension's OID,
    step over the optional `critical` BOOLEAN, open the OCTET STRING and read
    the UTF8String inside. `None` when the extension is absent.
    """
    at = certificate.find(SOURCE_REF_OID)
    if at < 0:
        return None
    at += len(SOURCE_REF_OID)
    if certificate[at] == 0x01:  # critical BOOLEAN
        length, start = _der_length(certificate, at + 1)
        at = start + length
    if certificate[at] != 0x04:  # OCTET STRING
        return None
    _, at = _der_length(certificate, at + 1)
    if certificate[at] != 0x0C:  # UTF8String
        return None
    length, start = _der_length(certificate, at + 1)
    return certificate[start : start + length].decode()


def to_bundle(attestation: dict[str, Any]) -> dict[str, Any]:
    """A PEP 740 attestation as a Sigstore bundle, field for field.

    The mapping `pypi_attestations.Attestation.to_bundle` makes, without the
    dependency: the two carry the same certificate, log entry and envelope.

    Hand-rolled where a library exists, and safe for one reason: on
    2026-09-24 this output was compared against the library's (0.0.30) for
    `digline-0.19.1-py3-none-any.whl` and they matched exactly. That
    comparison is kept, not remembered — the library's bundle is the expected
    fixture `tests/test_release_bundles.py` asserts equality against, so a
    drift here fails there.
    """
    material = attestation["verification_material"]
    envelope = attestation["envelope"]
    return {
        "mediaType": BUNDLE_MEDIA_TYPE,
        "verificationMaterial": {
            "certificate": {"rawBytes": material["certificate"]},
            "tlogEntries": [material["transparency_entries"][0]],
            "timestampVerificationData": {"rfc3161Timestamps": []},
        },
        "dsseEnvelope": {
            "payload": envelope["statement"],
            "payloadType": IN_TOTO,
            "signatures": [{"sig": envelope["signature"]}],
        },
    }


def serialise(bundle: dict[str, Any]) -> bytes:
    """One byte sequence per bundle, so a re-run writes the file it wrote before."""
    return (json.dumps(bundle, sort_keys=True, indent=2) + "\n").encode()


def _get_once(url: str, accept: str | None = None) -> Reading:
    """One request, and which of the three words it earned."""
    request = urllib.request.Request(url, headers={"Accept": accept} if accept else {})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return ABSENT
        if exc.code >= 500:
            return UNREAD
        raise
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return UNREAD


class Index:
    """Reads that wait: each one is asked again until it answers or `timeout`
    runs out, and ends in the last word it heard."""

    def __init__(self, timeout: float, interval: float) -> None:
        self.timeout = timeout
        self.interval = interval

    def read(self, url: str, accept: str | None = None) -> Reading:
        deadline = time.monotonic() + self.timeout
        started = time.monotonic()
        count = 0
        while True:
            got = _get_once(url, accept)
            count += 1
            if isinstance(got, bytes):
                if count > 1:
                    waited = time.monotonic() - started
                    print(f"served   {url}  (after {waited:.0f}s, read {count})")
                return got
            if time.monotonic() >= deadline:
                return got
            said = "404" if got == ABSENT else "no answer"
            print(f"waiting  {url}  — {said}, read {count}")
            time.sleep(self.interval)

    def answer(self, url: str, accept: str | None = None) -> bytes | None:
        """A page, or `None` for an absence that held. Never an unread."""
        got = self.read(url, accept)
        if got == UNREAD:
            raise NotJudged(
                f"{url} did not answer on any read in {self.timeout:.0f}s. That is "
                "not a finding about this release, so nothing is refused: re-run "
                "the job"
            )
        return None if got == ABSENT else got


def attestation_for(
    index: Index, name: str, version: str, filename: str
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """PyPI's attestation for one file, and the publisher it names."""
    body = index.answer(
        f"{INDEX}/integrity/{name}/{version}/{filename}/provenance",
        accept="application/vnd.pypi.integrity.v1+json",
    )
    if body is None:
        return None
    provenance = json.loads(body)
    bundles = provenance["attestation_bundles"]
    if len(bundles) != 1 or len(bundles[0]["attestations"]) != 1:
        raise Refused(
            f"{filename}: expected one attestation, PyPI holds a different shape"
        )
    return bundles[0]["attestations"][0], bundles[0]["publisher"]


def main(tag: str, out: pathlib.Path) -> int:
    # Read here and not at import, like `await_index.py`: a mistyped value
    # fails the job that uses it, by name.
    index = Index(
        timeout=float(os.environ.get("TIMEOUT", "600")),
        interval=float(os.environ.get("INTERVAL", "10")),
    )
    ref = f"refs/tags/{tag}"
    tag_version = tag.rpartition("-v")[2] if "-v" in tag else tag.removeprefix("v")
    served_dir = out / "served"
    served_dir.mkdir(parents=True, exist_ok=True)

    releases = sorted(
        {
            name_and_version(p)
            for p in pathlib.Path("dist").iterdir()
            if p.suffix in {".whl", ".gz"}
        }
    )
    if not releases:
        raise Refused(
            "dist/ holds no distributions, so there is nothing to ask PyPI about"
        )

    written: list[str] = []
    for name, version in releases:
        page = index.answer(f"{INDEX}/pypi/{name}/{version}/json")
        if page is None:
            raise Refused(
                f"{name} {version} is in dist/ and {INDEX} answered 404 for it "
                f"until the last read, {index.timeout:.0f}s after the first: "
                "this runs after the upload"
            )
        ours = version == tag_version
        for file in json.loads(page)["urls"]:
            filename: str = file["filename"]
            found = attestation_for(index, name, version, filename)
            if found is None:
                if ours:
                    raise Refused(
                        f"{filename} is at the tag's own version and PyPI holds "
                        "no attestation for it"
                    )
                print(f"skip     {filename}  — no attestation; an older upload")
                continue
            attestation, publisher = found
            signed_from = source_ref(
                base64.b64decode(attestation["verification_material"]["certificate"])
            )
            # This reads as bookkeeping and it is the guard. On the v0.19.1
            # rehearsal ten of the twelve files in `dist/` belonged to other
            # tags; without this skip the backfill would have attached bundles
            # for versions that release did not publish — "attach dist/ whole"
            # arriving through a different door.
            if signed_from != ref:
                if ours:
                    raise Refused(
                        f"{filename} is at the tag's own version and was signed "
                        f"from {signed_from}, not {ref}"
                    )
                print(f"skip     {filename}  — published by {signed_from}")
                continue
            if (
                publisher.get("repository") != REPOSITORY
                or publisher.get("workflow") != WORKFLOW
            ):
                raise Refused(
                    f"{filename}: attestation names {publisher}, "
                    f"not {REPOSITORY} {WORKFLOW}"
                )
            data = index.answer(file["url"])
            if (
                data is None
                or hashlib.sha256(data).hexdigest() != file["digests"]["sha256"]
            ):
                raise Refused(
                    f"{filename}: the bytes PyPI serves do not match PyPI's own digest"
                )
            (served_dir / filename).write_bytes(data)
            (out / f"{filename}.sigstore.json").write_bytes(
                serialise(to_bundle(attestation))
            )
            written.append(filename)
            print(f"bundle   {filename}")

    if not written:
        raise Refused(
            f"no file on {INDEX} carries an attestation from {ref}. Attaching "
            "nothing and passing would be the check that cannot fail, and this "
            "release would go out unsigned"
        )
    print(f"\n{len(written)} bundle(s) for {ref} in {out}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1], pathlib.Path(sys.argv[2])))
    except Refused as exc:
        print(f"::error title=No signatures for this release::{exc}", file=sys.stderr)
        sys.exit(1)
    except NotJudged as exc:
        print(f"::error title=Signatures not judged::{exc}", file=sys.stderr)
        sys.exit(2)
