---
name: congressional-hearings
trigger: "A congressional hearing transcript is added to raw/congressional-hearings/"
source_destination: raw/congressional-hearings/
summary_destination: wiki/congressional-hearings/
---

# Congressional Hearings Import

Handles UAP-related congressional hearings (2023 House Oversight UAP hearing, Grusch/Graves/Fravor testimony, Senate Armed Services UAP markup, future hearings).

## Why This Is Its Own Procedure

Sworn testimony has special epistemic status — it carries perjury liability, which raises a witness's claim above ordinary podcast hearsay. The **questions** asked also reveal what congress knows or wants to know, which is a separate signal from the answers. And classified-portion / closed-session callouts are themselves discourse signals — what congress could not say in open session is often more telling than what it did.

## Staging

Hearing transcripts arrive from one of:
- **govinfo.gov** — official record (most authoritative)
- **C-SPAN** — video transcript (timestamped, useful for cross-reference)
- **committee website** — sometimes earlier than govinfo
- **third-party transcription** — flag as `transcription_provenance: third-party`

Land the transcript in `raw/congressional-hearings/<slug>.md`. Slug convention: `YYYY-MM-DD-chamber-committee-keywords` (e.g. `2023-07-26-house-oversight-uap`, `2024-11-13-house-oversight-uap-followup`).

Prefill frontmatter from **the official hearing record cover page**: hearing title, committee, subcommittee, chamber, date, witnesses (with affiliations as listed on the witness panel), members present (from the attendance roster). Don't paraphrase committee names; use the official designation (e.g. "Subcommittee on National Security, the Border, and Foreign Affairs"). The hearing record's masthead is authoritative.

If the hearing has both **open and closed sessions**, separate them — closed-session content (if leaked or later released) gets its own slug `<base-slug>-closed`.

## Pre-filter

Before import: read the hearing title and witness list. UAP-relevant hearings will be obvious. If a hearing was filed under "UAP" tags but the actual content is off-topic (rare — perhaps an exhibit was UAP-related but the hearing wasn't), skip and log to LOG.md as `[skipped: off-domain]`. Adjacent hearings (general intelligence oversight, classification reform) without specific UAP content can be imported lightly — extract only UAP-adjacent witness statements and questions.

## Source Summary

Every import creates a summary page in `wiki/congressional-hearings/<slug>.md` containing:

- Frontmatter: `title`, `date`, `committee`, `subcommittee` (optional), `chamber` (house/senate), `session_type` (open/closed/mixed), `witnesses[]` (with affiliations), `members_present[]`, `exhibits[]` (slugs of any documents entered into the record), `transcription_provenance` (govinfo/c-span/committee/third-party), `tags[]`, `type: source-summary`, `created`, `sources`
- **Witnesses & testimony** — for each witness: identity, prepared remarks summary, key sworn claims, hedges/qualifications, demeanor notes if observable
- **Key claims (sworn)** — every load-bearing claim made under oath, marked `sworn:true`, with the witness who made it and rough timestamp/page
- **Key questions asked** — questions worth surfacing because they reveal congressional priors, classified knowledge, or lines of inquiry; tag each by member
- **Exhibits referenced** — documents/images/charts entered into the record (each gets cross-imported via `documents`)
- **Aftermath** — follow-up letters, subsequent hearings, witness commentary post-hearing
- **Entities mentioned** — `[[wikilinks]]` to every person/org/program/place/incident/craft-phenomenon/document/tech-artifact/symbol-glyph extracted
- **Concepts/claims engaged** — `[[wikilinks]]` to concepts and claims-theses pages
- **Notable quotes** — verbatim sworn statements worth preserving (with timestamp/page)
- **Open questions raised** — anything testimony surfaces but does not resolve, including what closed-session deferrals likely conceal

## Extraction Steps

1. Read the transcript end-to-end (move it to `raw/congressional-hearings/<slug>.md` as part of `/kb-import` Step 1; for multi-hour hearings see chunking rules below).
2. From the cover page: identify chamber, committee/subcommittee, date, witnesses, members present.
3. For each witness, distinguish three claim types — they have different epistemic weight:
   - **Prepared remarks** — pre-submitted; check for differences between prepared and delivered
   - **Sworn Q&A answers** — under oath, perjury liability, highest weight
   - **Pre-/post-hearing public statements** — same witness, lower weight (not sworn)
4. Extract entities (default depth = every named entity worth a page):
   - **people** — witnesses, members of congress present, anyone named in testimony
   - **organizations** — every named org (witness affiliations, agencies referenced)
   - **programs** — every named gov/black/research program (codenames count as separate entities)
   - **places** — every named base, site, region, facility
   - **incidents** — every specific encounter/event referenced
   - **craft-phenomena** — every named craft type or NHI category
   - **documents** — every cited memo/book/report/FOIA, plus exhibits entered into the record
   - **tech-artifacts** — every alleged hardware/material/patent
   - **symbols-glyphs** — any visual motif described
5. For each member of congress: extract the **substance of their questions**. Their questions reveal their priors and access. Add to that member's person page under "Stated positions / lines of inquiry" with date.
6. Capture the hearing as an **incident** in `wiki/entities/incidents/` — hearings are events with timeline placement.
7. Mark every extracted claim's epistemic status: `sworn:true` / `prepared-remarks` / `pre-hearing-statement` / `post-hearing-statement` / `member-question` (questions are not claims, but they are signals).

### Chunking rules for multi-hour hearings

Hearings over ~3 hours (Senate UAP hearings, multi-witness panels) have historically been thinned during single-pass extraction — testimony from later witnesses gets dropped:
- Process in chunks by witness or by panel.
- After each witness, write their sworn claims directly into the summary before moving on.
- Apply the **density rule**: a substantive hearing should yield roughly 1 summary line per 4 transcript pages. If thinner, re-read.
- After full extraction, run the auto-wikilink pass (Step 7.5 in `kb-import`).

## Wiki Updates

- Hearing gets a digest page in `wiki/congressional-hearings/` AND an incident entry in `wiki/entities/incidents/`.
- Each witness gets/updates a person page; sworn testimony recorded as firsthand sworn claims.
- Each member-of-congress question contributes to that member's person page (under "Stated positions / lines of inquiry").
- Each exhibit referenced is cross-imported via the `documents` procedure (or stub-linked if not yet ingested).
- Create or update `claims-theses` pages for each load-bearing sworn claim. **Sworn claims outrank ordinary hearsay** — when a sworn version exists, it becomes the citation of record on the claims-theses page, demoting prior hearsay-sourced versions.
- If sworn testimony contradicts an existing claim, flag with `> ⚠ Conflict:` on both pages and promote the sworn version.
- Update `wiki/synthesis/` only if the hearing meaningfully strengthens or contradicts an existing synthesis page.

## Cross-Linking Rules

- Hearing → every witness (bidirectional).
- Hearing → every congressperson present (bidirectional).
- Each sworn claim → its claims-theses page (with `sworn:true` annotation).
- Hearing → any prior incident, document, or program referenced in testimony.
- Hearing → every exhibit (entered-into-record edge).
- Witness ↔ their employer/affiliation **at the time of the hearing** (note the date — affiliations change).
- Auto-link ambiguous names only when the existing page is the unique plausible match.
- Every new entity page MUST link to at least one concept page.
- Every sworn claim MUST link to a `claims-theses` page.

## Log

`[YYYY-MM-DD] import:congressional-hearings | <slug> | witnesses: N, sworn-claims: M, exhibits: K`

## Quality Check

- Verify all new pages have at least 2 inbound `[[wikilinks]]`.
- Verify no orphan pages were created.
- Verify all witnesses are linked, with affiliation as of the hearing date.
- Verify all members present are linked.
- Verify all sworn claims are marked `sworn:true` on claims-theses pages.
- Verify all exhibits have stub or full pages in `wiki/documents/`.
- Verify session type (open/closed/mixed) is captured in frontmatter.
- Run `qmd update --collections ufo-kb && qmd embed`.
