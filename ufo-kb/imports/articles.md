---
name: articles
trigger: "A web article, Substack post, or piece of journalism is added to raw/articles/"
source_destination: raw/articles/
summary_destination: wiki/articles/
---

# Articles Import

Handles web articles, Substack posts, longform journalism (Shellenberger, Coulthart, Knapp, Kean, etc.). Article date matters a lot for timeline placement.

## Staging

Articles arrive as URLs. Land each one in `raw/articles/<slug>.md` as cleaned markdown — strip nav/ads/related-stories chrome but preserve byline, dateline, body, and inline citations. Slug convention: `YYYY-MM-DD-outlet-keywords` (e.g. `2023-06-05-debrief-grusch-whistleblower`).

**Always capture an archive.org snapshot URL** alongside the live URL (`https://web.archive.org/save/<url>`). Articles get edited, retracted, or paywalled silently — the archive snapshot is the canonical reference; the live URL is convenience.

Prefill frontmatter from **the article's own masthead**: byline as printed (don't normalize "By Jane Doe with reporting from John Smith" to a single name), outlet exactly as branded, published date from the article's own dateline (NOT the page-load date). If the article has been edited post-publication, capture the original `published` date AND an `updated` date with the visible change-note. Re-derived bylines and dates have caused mis-attribution; the masthead is authoritative.

## Pre-filter

Before import: read the headline + dek + first 2–3 paragraphs. If the article is **pure off-domain** (general politics, sports, business with zero UFO/UAP/adjacent content), skip and log to LOG.md as `[skipped: off-domain]`. If the article is mostly off-domain but contains a UFO-relevant section, import lightly — extract only the UFO-relevant entities/claims and note the section.

If the article has been **retracted, significantly corrected, or pulled**, still import it but mark `retracted: true` (or `corrected: true`) in frontmatter and add a `> ⚠ Retraction:` callout with the publisher's note verbatim. Retracted articles do not become citation of record, but the retraction itself is a discourse signal worth preserving.

## Source Summary

Every import creates a summary page in `wiki/articles/<slug>.md` containing:

- Frontmatter: `title`, `authors[]`, `outlet`, `published`, `updated` (optional), `url`, `archive_url`, `paywalled` (true/false), `retracted` / `corrected` (optional), `tags[]`, `type: source-summary`, `created`, `sources`
- **Headline claims** — 3–7 bullet points capturing the most surprising or load-bearing assertions
- **Entities mentioned** — `[[wikilinks]]` to every person/org/program/place/incident/craft-phenomenon/document/tech-artifact/symbol-glyph extracted
- **Concepts/claims engaged** — `[[wikilinks]]` to concepts and claims-theses pages
- **Citations / sources cited** — every named source the article relies on (other articles, documents, named human sources, anonymous sources flagged as such); each citation is a graph edge
- **Notable quotes** — verbatim lines worth preserving
- **Open questions raised** — what the article surfaces but does not resolve

## Extraction Steps

1. Read the article end-to-end (move it to `raw/articles/<slug>.md` as part of `/kb-import` Step 1; for 10k+ word longform see chunking rules below).
2. Identify byline, outlet, publication date, any updates/corrections, and named/anonymous sources.
3. Extract entities (default depth = every named entity worth a page):
   - **people** — author(s), named subjects, named sources, anyone quoted
   - **organizations** — every named org; the outlet itself is an organization
   - **programs** — every named gov/black/research program
   - **places** — every named base, site, region
   - **incidents** — every specific encounter/event referenced
   - **craft-phenomena** — every named craft type or NHI category
   - **documents** — every cited memo/book/report/FOIA
   - **tech-artifacts** — every alleged hardware/material/patent
   - **symbols-glyphs** — any visual motif described or shown in article art
4. Extract concepts and claims:
   - Tag the article with applicable `concepts` (disclosure-narratives, credibility-frameworks, etc.)
   - For each discrete recurring assertion, link to or create a `claims-theses` page
5. **Citations are first-class connections**: when the article cites another article, document, person, or prior incident, capture each citation as an explicit graph edge (not just a mention). Anonymous sources still get edges — flagged as `(anonymous: <description from article>)` annotation on the relevant claim, not as a person page.
6. Date the article precisely — articles slot into `wiki/timeline/` views by date.

### Chunking rules for longform pieces

For articles over ~10,000 words (Coulthart deep-dives, multi-part Substack series, magazine longform):
- Process in logical sections (intro, body subheadings, conclusion).
- After each section, write claims/entities directly into the summary before moving on.
- Apply the **density rule**: a substantive longform article should yield roughly 1 summary line per 500 source words. If thinner, re-read the sections you skimmed.
- After full extraction, run the auto-wikilink pass (Step 7.5 in `kb-import`).

## Wiki Updates

- Create the article summary page in `wiki/articles/`.
- Create or update entity pages in `wiki/entities/<type>/`.
- Author gets/updates a person page; outlet gets/updates an organization page.
- Create or update concept and claims-theses pages in `wiki/concepts/`.
- Add `[[wikilinks]]` back from entity/concept pages to this article.
- If the article contradicts an existing claim, flag with `> ⚠ Conflict:` on both pages.
- Update `wiki/synthesis/` only if the import meaningfully strengthens or contradicts an existing synthesis page.

## Cross-Linking Rules

- Article ↔ author bidirectional; author ↔ outlet (employed-by / contributing-to relationship).
- Article → outlet (the outlet's page lists this article).
- Article → every claim it makes (claims-theses pages).
- Article → every cited source (other articles, documents, named human sources).
- If the article cites another article in the KB, link both ways.
- Anonymous sources: capture as `(anonymous: <article's description>)` annotation on the relevant claim, not as a person page.
- Auto-link ambiguous names only when the existing page is the unique plausible match.
- Every new entity page MUST link to at least one concept page.
- Every claim asserted in the article MUST link to a `claims-theses` page.

## Log

`[YYYY-MM-DD] import:articles | <slug> | <title> | author: <name>, outlet: <outlet>, entities: N, claims: M`

## Quality Check

- Verify all new pages have at least 2 inbound `[[wikilinks]]`.
- Verify no orphan pages were created.
- Verify author and outlet pages exist and back-link to the article.
- Verify every claim links to a claims-theses page.
- Verify the archive.org snapshot URL is captured.
- Run `qmd update --collections ufo-kb && qmd embed`.
