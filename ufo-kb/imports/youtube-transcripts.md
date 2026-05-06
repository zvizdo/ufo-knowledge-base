---
name: youtube-transcripts
trigger: "A YouTube transcript file (.md) is added to raw/youtube-transcripts/"
source_destination: raw/youtube-transcripts/
summary_destination: wiki/youtube-transcripts/
---

# YouTube Transcripts Import

Handles American Alchemy episodes and any other UFO/UAP-relevant YouTube channel transcripts (Need to Know, Theories of Everything, UAP Society, Joe Rogan UFO eps, etc.). Channel name is captured as a tag, not a separate procedure.

## Pre-filter

Before import: check the title and first ~500 words. If the episode is **pure off-domain** (general philosophy, sports, business with zero UFO/UAP/adjacent content), skip and log to LOG.md as `[skipped: off-domain]`. If the episode is mostly off-domain but mentions UFO topics in passing, import lightly (extract only the UFO-relevant entities and a one-line summary).

## Source Summary

Every import creates a summary page in `wiki/youtube-transcripts/<video-id>.md` containing:

- Frontmatter: `video_id`, `title`, `channel`, `host`, `guest[]`, `published`, `url`, `duration_minutes`, `tags[]`
- **Headline claims** — 3–7 bullet points capturing the most surprising or load-bearing assertions
- **Entities mentioned** — `[[wikilinks]]` to every person/org/program/place/incident/document/etc. extracted
- **Concepts/claims engaged** — `[[wikilinks]]` to concepts and claims-theses pages
- **Notable quotes** — verbatim lines worth preserving (with rough timestamp if derivable)
- **Open questions raised** — anything the conversation flags but doesn't resolve

## Extraction Steps

1. Read the transcript from `raw/youtube-transcripts/<video-id>.md`.
2. Identify host(s) and guest(s) from the title and intro section.
3. Extract entities (default depth = every named entity worth a page):
   - **people** — speakers, anyone they reference by name
   - **organizations** — every named org
   - **programs** — every named gov/black/research program
   - **places** — every named base, site, region
   - **incidents** — every specific encounter/event referenced
   - **craft-phenomena** — every named craft type or NHI category
   - **documents** — every cited memo/book/report/FOIA
   - **tech-artifacts** — every alleged hardware/material/patent
   - **symbols-glyphs** — any visual motif described
4. Extract concepts and claims:
   - Tag the conversation with applicable `concepts` (disclosure-narratives, credibility-frameworks, etc.)
   - For each discrete recurring assertion, link to or create a `claims-theses` page
5. Mark **firsthand vs. hearsay** for every speaker claim.

## Wiki Updates

- Create the source summary page in `wiki/youtube-transcripts/`.
- Create or update entity pages in `wiki/entities/<type>/`.
- Create or update concept and claims-theses pages in `wiki/concepts/`.
- Add `[[wikilinks]]` back from entity/concept pages to this transcript (back-link pass).
- If a new firsthand claim contradicts an existing page, flag with `> ⚠ Conflict:` on both pages.
- Update `wiki/synthesis/` only if the import meaningfully strengthens or contradicts an existing synthesis page.

## Cross-Linking Rules

- Host (Jesse Michaels for AA) ↔ guest(s) link bidirectionally on person pages.
- Guest ↔ their orgs/programs/claims.
- Auto-link ambiguous names only when the existing page is the unique plausible match in the KB; otherwise flag for review.
- Every new entity page MUST link to at least one concept page.
- Every claim asserted in the transcript MUST link to a `claims-theses` page (creating one if necessary).

## Log

- Add entry to LOG.md (insert below header, above existing entries — newest first):
  `[YYYY-MM-DD] import:youtube-transcripts | <video-id> | <title> | entities: N, claims: M`

## Quality Check

- Verify all new pages have at least 2 inbound `[[wikilinks]]`.
- Verify no orphan pages were created.
- Verify host and at least one guest are linked.
- Run `qmd update --collections ufo-kb && qmd embed`.
