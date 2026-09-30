# ADR 0038 — The projection of a run nobody promoted

- Status: proposed 2026-09-30 — the text first, before any code, the way
  [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md)
  and [ADR 0037](0037-the-review-interface-and-the-election-recorded-where-the-text-is-not.md)
  were. **Unlike ADR 0037, nothing in its decision was ruled before it was
  written.** It records what reading found and the options the reading leaves
  open. The ruling is owed, and it is Alessandro's. **One thing it rests on was
  ruled**, in discussion on 2026-09-30: pages served to the software house show
  **projected** documents by default. Seeing a case in clear is a disclosure
  that is asked for, seen and recorded. That ruling is written in no record in
  this repository yet, so it is stated here, where it is used
- Shipped: unreleased
- Date: 2026-09-30
- Opens: **nothing on landing.** No `SCHEMA_VERSION`, no `OUTPUT_VERSION`, no
  migration. What each option would open is priced beside it (§*The
  decision owed*)
- Requires, at implementation: **depends on the ruling.** Under one option,
  nothing new in digline. Under the other, a projection that starts from a
  run rather than from a reference, and whatever declares the difference
  (§1)
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §4 (a
  `Comparison` does not cross a boundary) and §8 (promotion's conditions);
  [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md) §5 (a baseline carries no answers);
  [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md)
  §2, §3, §4, §8, §9 and §12;
  [ADR 0036](0036-the-name-table-and-the-process-that-owns-it.md) §6 and §7;
  [ADR 0037](0037-the-review-interface-and-the-election-recorded-where-the-text-is-not.md)
  (a served page at the data owner's side)
- Touches, whichever way it is ruled: ADR 0034 §2, read or amended; ADR 0036
  §7, whose projection writer *"mints the tokens of a reference"*; and
  `CLAUDE.md`'s fixed decision 9 as ADR 0034 narrowed it. That last one is why
  this is a record and not an issue
- Read at digline `main` = `26cdc9c` (#296). Code and records were read.
  Nothing was run or measured

## Context

A page served at the data owner's side to a person at the software house shows
six kinds of document:
- the list of a suite's runs;
- one run;
- a run against its baseline;
- a run against another run;
- one case across runs;
- the suspension snippet.

Under the ruling above, each one is shown projected.

**`digline.core.project` refuses every run on those pages except one.** It
refuses a run with no `promoted_at` (`core/projection.py:85`) and a run that
still carries recorded answers (`:91`). The one document it will project is
the reference the run is compared against. **It cannot project the run under
review**, and showing what the last round did is the whole job of those pages.

The refusal is ADR 0034 §2's, and §2 was written for **the committed file**:
the reference the software house keeps in its repository. **Whether it binds a
page that is served and not committed has not been ruled.** That question
touches what a projected document carries, which is fixed decision 9 as ADR
0034 narrowed it, so the rule is text before code.

### What reading found

**1. §2 makes two arguments, and its "three" belongs to the second.** A first
reading, the same day, counted three reasons and found that two still apply.
The three it counted were not one list.
- **Argument A, §2's second paragraph: start from a promotion.** *"Nothing
  re-implements promotion's conditions … A producer that built a projection
  straight from a stored run would have to repeat them or skip them, and
  skipping them is how 'a comparison that runs anyway and returns numbers
  anyway' gets committed. Deriving from the returned reference inherits every
  refusal for free."*
- **Argument B, §2's third paragraph: a `Comparison` is refused "three
  ways".**
  1. *"The run envelope is absent"*: a `Comparison` has no `created_at`,
     `config_hash`, `results`, `aggregate`, `artifacts`, `pinned`, `usage` or
     `promoted_at`, and it carries `config_changed` as a bool where promotion
     needs the hash.
  2. *"Suspended cases produce no deltas at all"*, so a rebuild drops every
     case that was set aside.
  3. *"`missing` deltas carry baseline-only verdicts"*, so a rebuild imports
     rows that were never in the run.
- **§2's fourth paragraph, on order.** *"`without_responses` applied to an
  already-projected run drops the response count … it is promote, then
  project."*

The two that were said to still apply are B2 and B3. The third was argument A,
which is not one of B's three ways, and B1 was not counted. **This matters for
the question, because only argument A bears on projecting a run.** B1, B2 and
B3 are about building a document out of a `Comparison`. They say nothing about
projecting a `Run` that exists. §3 below takes them up.

**2. Promotion changes two fields, and refuses five states.**
`promote_baseline` writes `replace(without_responses(run),
promoted_at=promoted_at)` (`store/file_store.py`). Before it writes, it refuses
five states that a run carries in the document itself (`refusals_for`,
`store/promotion.py`):
- a `config_hash` that is not the current one;
- a run judged from recorded answers (`rejudged_from`);
- a run that does not reconcile with what its suite asked;
- a run with errored verdicts;
- a run whose calibration lost its band.

**Those five are the runs a reviewer most needs to see.** Argument A keeps them
out of a reference. A served page is not a reference, and it shows them for
the reason promotion refuses them.

**3. The ten `TokenKind`s cover a current run as fully as a reference.**
`rename` maps by place in the document, and promotion adds no named place. The
two places no kind covers are the same for both:
- a target-side identity, which `project` refuses;
- the keys of a verdict's metadata, which ADR 0034 §4 has not classified
  (`_check_projected`'s docstring).

What a current run adds, run through `redact(run, NOTHING_EXTRA)` and then
`rename`:

| In a run, not in a reference | What a projection would carry | Covered? |
|---|---|---|
| Recorded answers | `RecordedResponse(withheld=True)` placeholders: **the number of answers per case crosses**. A projected reference never carries it, because its list is empty. Per-call usage goes with the answers | No name is involved. **The count is a number**, and numbers are the axis ADR 0034 §4 does not decide |
| No `promoted_at` | Absent | Nothing to cover. `_check_projected` treats empty as absent |
| Errored verdicts | The `error` status. The reason is redacted. String metadata is dropped by `travels()`, which lets through only `bool`, `int` and `float`. So nothing a string check could refuse reaches `_check_projected` | The name is `verdict_name` |
| An unreconciled run | `unreconciled()` reads a case id, a verdict name and the `UNRECONCILED` marker, which is `True` on an errored verdict. The marker is a `bool` and travels, and the two names become tokens | Yes. **A projected run still says it does not reconcile, in tokens** |
| `rejudged_from` | A run key | Class (a). Its form has been checked on a projected document since #296 |
| An old `config_hash` | A digest | Class (a), and form-checked since #296 |

Carried by both kinds of document, and worth stating once so that nobody reads
it as new:
- a suspension reason masked to the marker;
- artifacts withheld, so artifact drift reads `unknown` (ADR 0034 §9);
- `reasons_available` false;
- no run-level metadata;
- `usage` totals in clear.

**4. The table would gain a writer on page views.** ADR 0036 §7 describes the
projection writer as the one that *"mints the tokens of a reference"*. A page
that projects a run mints a token for every name no earlier projection met, so
**serving a page writes the table**. It stays inside the owning process, which
is §7's condition, and it satisfies that condition only if the process that
serves the page is the process that owns the table. §7's sentence names a
reference, and a served run is not one.

**5. ADR 0002 §4 already speaks to the comparison.** *"A `Comparison` does not
cross a boundary. What crosses is a redacted `Run`, and the comparison is redone
on the other side. Whoever writes a transport for `Comparison` is going down the
wrong road."* Its reason is that a `Comparison` *"contains the verdicts it
received, so it carries the payload of what it was given."*

## The decision owed

Three questions. They are written in the order they depend on each other, and
**none of them is answered here.**

### 1. Does §2's refusal bind a served projection of a run?

**(a) It binds as written.** A served page projects the reference and nothing
else. The run under review reaches the software house only through a
disclosure, one case at a time and on the record.
- It costs every page except the list and the reference. Whether the list
  names anything was not checked (issue #276).
- Nothing new is needed in digline.
- It is the reading that asks least of the ruling of 2026-09-30. Under it,
  *projected by default* in practice means *not shown by default*.

**(b) It narrows to its reason.** On this reading §2's reason is argument A,
which keeps a non-reference out of a committed reference. A served page is
neither committed nor a reference. So the refusals at `:85` and `:91` belong to
the committed file, and a second way in projects a run for serving. Under (b),
three things follow and must be decided with it:
- **Two projected documents that differ in kind would look alike.** ADR 0034
  §8's rule is *verified, not believed*. So whatever tells a served projection
  from a projected reference has to be on the document, and it has to be
  checked.
- **A served projection must not become a reference.** `promote_baseline` reads
  from its own store by address, and that store holds runs in clear. So a
  served projection reaches promotion only if something writes it into a
  store. That is a **condition**, and it is stated as one: if a served
  projection is ever written where a promotion can read it, this paragraph
  stops holding, and ADR 0034 §9's regime question reopens for it.
- **ADR 0036 §7's writer widens** from *"the tokens of a reference"* to the
  tokens of whatever is served.

**Whether §2's sentence is broader than its reason is the whole question.** The
difference between (a) and (b) is not about what a token hides. It is about
whether a rule written for one artefact reaches a second artefact the rule did
not name.

### 2. What may a served projection carry: the same as a committed one, more, or less?

**The difference that may decide it.** A committed reference is a file, kept in
the software house's history for good. A served page is looked at, and not
kept.

**For "more", because a page does not accumulate:**
- ADR 0034's acceptance argues from what history keeps: *"a reference that
  carries no text has nothing to erase … erasure happens where the mapping
  lives."* A page that is never committed leaves no history for that argument
  to protect.
- ADR 0034 §3: *"Reading to work is not residency; writing a copy is."* It
  names the committed projection as *"the one declared exception"*. A served
  page is on the reading side of that sentence.

**For "less", because nobody reviews a page and nothing records it:**
- **No approval, no commit.** §3 sends the committed file through one approval
  at the data owner's side and a commit that records it. A served page has
  neither.
- **ADR 0034 §12's condition.** The ruling on the digests holds *"only while a
  reference cannot reach a place the suite does not"*. A page open to its
  readers is such a place, unless whoever can open it can also read the suite.
- **"Not kept" is a property of the reader, not of the bytes.** `render_html`
  produces a self-contained document. Nothing stops somebody saving it, and
  nothing on it says it was never meant to be a copy.
- **Its tokens are the kept vocabulary.** ADR 0036 §4 and §6 give one token per
  (kind, text) per (tenant, suite). So a served page's tokens join with every
  committed reference's tokens, and what a page showed can be linked to what is
  kept.
- **The table accumulates even if the page does not** (finding 4). It stays
  inside the data owner's perimeter, but every row is one that erasure has to
  reach.
- **The ruling of 2026-09-30 moves control from permission to trace.** A page
  that showed more than the projection, with no record of what it showed, is
  the untraced case the disclosure exists to prevent.

**What the records support.** *No more than the projection, except through the
disclosure* is ruled: projected by default, clear on request and on the record.
**Nothing in the records supports "more".** Whether a served projection should
carry **less** than a committed one is not addressed anywhere. **The one
concrete place where it would carry more is the response count** (finding 3).
That is a special case of the undecided number axis, and it arises only under
§1(b).

### 3. Is the refusal of a `Comparison` the same question?

**There are three shapes, and they split the answer.** The same three apply to
a run against another run (`diff`) and to one case across runs.

- **(A) Rebuild a run document from a `Comparison`.** This is what ADR 0034 §2
  refuses. B2 and B3 hold for a page exactly as for a file, because a page
  shows the dropped cases and the imported rows as surely as a file stores
  them. B1's half about promotion needing the hash does not apply to a page.
  Its half about the missing envelope does. **So this is a separate question,
  and the records already answer it.**
- **(B) Project each run, then compare the two projections.** Nothing is built
  from a `Comparison`, so §2's refusal is not engaged. This is ADR 0002 §4's
  own shape: redacted runs cross, and the comparison is redone. ADR 0034 §9's
  addendum of 2026-09-30 expects it, because `DifferentRegimesError` refuses
  only a pair whose regimes differ. **So this is the same question as §1**,
  because under §1(a) the run cannot be projected. It also carries two
  conditions of its own:
  - **Both projections must come from one table.** ADR 0034 §9 leaves open two
    projections minted from different tables, and nothing on a projected
    document says which table minted it. A single owning process per (tenant,
    suite) keeps the case from arising. Nothing checks for it.
  - **It answers less than a comparison in clear.** Artifact drift reads
    `unknown`, and no reason is available.
- **(C) Compare in clear at the data owner's side, then tokenise the result.**
  No record speaks to it except ADR 0002 §4, whose sentence refuses a
  `Comparison` crossing a boundary. **Whether its reason refuses it too** turns
  on whether the tokenising also redacts. A `Comparison` that kept its
  verdicts' reasons would carry the payload §4 names. No function does this
  today: `rename` takes a `Run`. The comparison in clear exists at the data
  owner's side whichever shape is chosen, because the default reason for a
  disclosure (*"worse in the run of <date> against the reference"*) needs one.

## Consequences

Whichever way §1 is ruled:
- **ADR 0034 §2 gains a sentence** that says whether it reaches a served page,
  as a reading under (a) or an amendment under (b).
- **ADR 0036 §7's projection writer** is either confirmed as the writer of
  references only, or widened.
- **Issues #277 and #278** can be answered only after this record is. Each
  renders a run that public digline cannot project today. **#279's snippet**
  hands over a case id in clear. On a projected page that is either a
  disclosure or a token that no suite reads, and which one is not ruled here.

## Alternatives considered

- **An issue beside #276 to #279.** Refused on 2026-09-30. Those four ask for
  something that exists to be made public. This asks for a function that does
  not exist, whose nearest relative an ADR refuses in the case it was written
  for, and it touches fixed decision 9.
- **Serving documents as they are.** Refused by the ruling this record rests
  on. That would make the served page a step towards a client who agrees to
  show their data, which is a different product from the one the records
  describe.

## Not decided here

- **Numbers**, including the response count: ADR 0034 §4's open axis.
- **The keys of a verdict's metadata**, which are in no class yet.
- **Two projections minted from different tables**: ADR 0036's question.
- **How `render_html` renders a document whose names are tokens.** It reads
  `redacted` and says so in its header. Nothing else about it was measured.
- **Where the disclosure's record lives, whether a disclosed case stays
  disclosed, and whether the client is told.** These are open in the ruling of
  2026-09-30, and this record does not reach them.

## What this record does not claim

- **That anything was run.** Every finding above is a reading of the code at
  `26cdc9c` and of the records. None of it was measured.
- **That "ephemeral" is a property of anything.** Nothing in digline marks a
  page as not a copy, or enforces that it is not kept. §2's "for more" case
  rests on how a page is used, not on anything a page can prove.
- **That shape (B) needs nothing new beyond §1.** It needs one table per
  (tenant, suite). That holds by how the owning process is arranged. It is not
  checked.
