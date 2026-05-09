---
name: documents
trigger: "A primary-source document (FOIA, leaked memo, gov report, complaint, briefing) is added to raw/documents/"
source_destination: raw/documents/
summary_destination: wiki/documents/
---

# Documents Import

Handles primary-source documents: FOIAs, leaked memos, government reports, the Grusch complaint, AARO reports, hearing exhibits, briefing slides, declassified cables.

## Why Documents Matter

Documents are the highest-credibility source type in the discourse. A claim sourced to a document outweighs hearsay in nearly every framework. Treat documents as **canonical sources** — when a claim has a documentary source, that document becomes the citation of record on the relevant claims-theses page, even if existing hearsay-sourced versions of the claim already exist.

## Staging

Documents arrive as PDFs, scanned images, or text. Land the original in `raw/documents/<slug>.<ext>` (PDF preferred; always keep the original alongside any derived text). Slug convention: `YYYY-MM-DD-author-keywords` (e.g. `2023-07-26-grusch-complaint`, `2024-03-08-aaro-historical-report-vol1`). If the date is unknown, use `undated-keywords` and resolve later.

If the document is a scanned image or non-searchable PDF, run OCR first (`ocrmypdf <input> <output>`) and store the OCR'd text alongside as `raw/documents/<slug>.txt`. **Note OCR confidence** — flag pages where OCR clearly mangled words. Redactions can masquerade as garbled text and vice versa.

Prefill the wiki frontmatter from **the document itself** — letterhead, signature block, date stamps, classification banners, exhibit numbers. **Copy these fields verbatim into the wiki source-summary frontmatter — do not paraphrase the title, normalize author names, or guess at classification.** Use a `display_title` field if the original is unwieldy. Cite redaction exemption codes (`b(1)`, `b(3)`, `b(7)(C)`) exactly as printed. Re-derived metadata — especially dates, classification levels, and author affiliations — has historically caused documents to be cited incorrectly downstream; the document's own surface is authoritative.

The remaining required wiki frontmatter fields (`tags[]`, plus `type: source-summary`, `created`, `sources`) are derived during import as in other source types.

## Pre-filter

Before import: read the cover page / first 1–2 pages. If the document is **pure off-domain** (unrelated FOIA release, mislabeled file, general administrative content with zero UFO/UAP/adjacent content), skip and log to LOG.md as `[skipped: off-domain]`. If the document is mostly off-domain but contains a UFO-relevant section, import lightly — extract only the UFO-relevant entities/claims and note the page range.

If the document's **provenance is unclear** (no chain of custody, no public release record, looks possibly fabricated), still import it but mark `provenance: disputed` in frontmatter and add a `> ⚠ Provenance:` callout at the top of the summary. Disputed-provenance documents must NOT become the citation of record on claims-theses pages until provenance is resolved.

## Source Summary

Every import creates a summary page in `wiki/documents/<slug>.md` containing:

- Frontmatter: `title`, `display_title` (optional), `authors[]`, `recipients[]`, `date`, `type` (memo/foia/report/complaint/briefing/exhibit/letter/hearing-transcript/cable), `classification` (TS//SCI / SECRET / CONFIDENTIAL / U//FOUO / UNCLASSIFIED / unknown), `provenance` (FOIA requester, leak source, official release, disputed), `pages`, `source_url` (if public), `tags[]`, `type: source-summary`, `created`, `sources`
- **Headline claims** — 3–7 bullet points capturing the most surprising or load-bearing assertions the document makes or implies
- **What's revealed** — facts the document establishes, each with a page citation
- **What's redacted** — every redaction worth noting, with exemption code and page; redactions are themselves a signal
- **Entities mentioned** — `[[wikilinks]]` to every person/org/program/place/incident/craft-phenomenon/document/tech-artifact/symbol-glyph extracted
- **Concepts/claims engaged** — `[[wikilinks]]` to concepts and claims-theses pages
- **Notable quotes** — verbatim lines worth preserving, with page number
- **Open questions raised** — anything the document flags but doesn't resolve, including what the redactions likely conceal

## Extraction Steps

1. Read the staged document end-to-end (move it to `raw/documents/<slug>.<ext>` as part of `/kb-import` Step 1; for very long docs see chunking rules below).
2. Identify author(s), recipient(s), date, classification level, and provenance from letterhead, signature block, and classification banners.
3. Extract entities (default depth = every named entity worth a page):
   - **people** — authors, recipients, anyone named in body or footnotes
   - **organizations** — every named org, including office codes (e.g. `OSD/AT&L`, `OUSD(I&S)`)
   - **programs** — every named gov/black/research program (codenames count as separate entities)
   - **places** — every named base, site, region, facility
   - **incidents** — every specific encounter/event referenced
   - **craft-phenomena** — every named craft type or NHI category
   - **documents** — every cited memo/book/report/FOIA (cross-document links are load-bearing here)
   - **tech-artifacts** — every alleged hardware/material/patent
   - **symbols-glyphs** — any visual motif, seal, insignia, or glyph reproduced or described
4. Extract concepts and claims:
   - Tag the document with applicable `concepts` (disclosure-narratives, classification-frameworks, oversight-gaps, etc.)
   - For each discrete assertion the document makes or implies, link to or create a `claims-theses` page. **Documents often imply more than they state** — if the implication is load-bearing, surface it explicitly with an `(implied)` annotation.
5. Mark **stated vs. implied** for every extracted claim, and capture the exact page citation. Note the chain-of-custody for any claim sourced to a redacted or partially redacted passage.

### Chunking rules for long documents

Documents over ~50 pages (Grusch complaint, AARO reports, hearing transcripts, multi-volume FOIA releases) have historically been thinned during single-pass extraction — claims on later pages get dropped. For these:

- Process in chunks of ~20–30 pages.
- After each chunk, write claims/entities directly into the summary before moving on; do not hold extracted material in working memory across chunks.
- Apply the **density rule**: a substantive document should yield roughly 1 summary line per 2 pages of source content (more for dense reports, less for repetitive form letters). If your summary feels thin, re-read the chunks you skimmed.
- After full extraction, run the auto-wikilink pass (Step 7.5 in `kb-import`) to catch entity references missed during chunked reading.

## Wiki Updates

- Document gets a page in BOTH `wiki/documents/` (this digest) and `wiki/entities/documents/` (the entity record). The entity-record page is a stub linking back to the digest.
- Create or update entity pages in `wiki/entities/<type>/`.
- Create or update concept and claims-theses pages in `wiki/concepts/`.
- Every claims-theses page that references this document MUST cite it explicitly with the document's slug AND page number.
- Add `[[wikilinks]]` back from entity/concept pages to this document (back-link pass).
- If the document contradicts an existing claim, flag with `> ⚠ Conflict:` on both pages — and because documents outrank hearsay, **update the claims-theses page to make the documentary source the new citation of record**, demoting prior hearsay-sourced versions.
- Update `wiki/synthesis/` only if the import meaningfully strengthens or contradicts an existing synthesis page.

## Cross-Linking Rules

- Author(s) ↔ recipient(s) link bidirectionally on person pages.
- Authors/recipients ↔ their orgs/programs **at the time of writing** (note the date — affiliations change; do not back-port a current title onto a 1995 memo).
- Document → every named entity.
- Document → every claim it makes or implies.
- Document → its provenance (who leaked it, who FOIA'd it, who released it).
- If the document references another document, link both ways.
- Auto-link ambiguous names only when the existing page is the unique plausible match in the KB; otherwise flag for review.
- Every new entity page MUST link to at least one concept page.
- Every claim asserted (or implied) in the document MUST link to a `claims-theses` page (creating one if necessary).

## Log

- Add entry to LOG.md (insert below header, above existing entries — newest first):
  `[YYYY-MM-DD] import:documents | <slug> | <title> | type: <type>, classification: <level>, entities: N, claims: M`

## Quality Check

- Verify all new pages have at least 2 inbound `[[wikilinks]]`.
- Verify no orphan pages were created.
- Verify author(s) and at least one recipient (if applicable) are linked.
- Verify every claims-theses page citing this document includes the exact page number.
- Verify redaction notes preserve exemption codes verbatim.
- Verify the document appears in BOTH `wiki/documents/` and `wiki/entities/documents/`.
- Run `qmd update --collections ufo-kb && qmd embed`.
