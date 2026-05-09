---
name: books
trigger: "A book (PDF, EPUB, or text excerpt) is added to raw/books/"
source_destination: raw/books/
summary_destination: wiki/books/
---

# Books Import

Handles book-length sources (Vallée, Dolan, Pasulka, Knapp, Kean, Sheehan, Jacobs, Strieber, etc.).

## Depth — read this before anything else

**Thematic, not chapter-by-chapter.** Capture the book's thesis, key cases discussed, key people interviewed/cited, and major claims advanced. Do NOT extract every minor mention. Books drown the KB if treated like transcripts — a 400-page book with line-by-line extraction would dominate the graph and obscure the actual signal.

This **inverts the density rule** used for transcripts and documents: for books, terseness is a feature, not a regression. The success criterion is "thesis and load-bearing claims captured," not "every name mentioned linked." See the Reverse density check in Quality Check below.

## Staging

Books arrive as PDF, EPUB, or text excerpt. Land the original in `raw/books/<slug>.<ext>`. Slug convention: `<lastname>-<year>-<keywords>` (e.g. `vallee-1969-passport-to-magonia`, `dolan-2014-uap-secret-history`).

If the book is a scanned PDF, run OCR (`ocrmypdf <input> <output>`) and store the OCR'd text alongside as `raw/books/<slug>.txt`. EPUBs can be converted with `pandoc -o <slug>.txt <input>.epub`.

Prefill frontmatter from **the title page and copyright page** of the actual edition you have in hand. Editions matter — a 1969 first edition and a 1993 reprint may have different forewords, corrections, or chapter additions. Capture `edition`, `published` (original year), and `edition_year` (if different) verbatim. ISBN is the canonical ID — copy it from the copyright page exactly. Don't paraphrase the title; subtitles often carry load-bearing framing.

## Pre-filter

Before import: read the back-cover blurb + foreword/introduction + table of contents. If the book is **pure off-domain** (a general philosophy book mistakenly filed here, an unrelated memoir, etc.), skip and log to LOG.md as `[skipped: off-domain]`. Most books reaching `raw/books/` will be on-topic, but adjacent-genre books (general consciousness, occult history, defense policy) should pass the same UFO-relevance test.

If the book is **fiction with UAP themes** (e.g. Strieber's novels), import lightly with `genre: fiction` and treat all in-book claims as fictional unless the author cross-references to nonfiction reportage. Fictional books do NOT contribute to claims-theses pages as evidence; they contribute to discourse-history and influence pages.

## Source Summary

Every import creates a summary page in `wiki/books/<slug>.md` containing:

- Frontmatter: `title`, `subtitle` (optional), `authors[]`, `published`, `edition` (optional), `edition_year` (optional), `publisher`, `publisher_type` (trade/academic/self-published/imprint), `isbn`, `pages`, `genre` (nonfiction/fiction/memoir/academic), `tags[]`, `type: source-summary`, `created`, `sources`
- **Thesis** — 1–3 sentences capturing what the book argues
- **Key cases discussed** — 5–15 incidents the book treats in depth, with `[[wikilinks]]`
- **Key people cited** — 10–30 people central to the book's argument or interviewed by the author, with `[[wikilinks]]`
- **Major claims** — 5–15 load-bearing assertions linked to `claims-theses` pages
- **Concepts engaged** — `[[wikilinks]]` to concepts the book advances or critiques
- **Notable quotes** — verbatim lines worth preserving (with chapter/page if derivable)
- **Response literature** — books/articles in the KB that respond to or are responded to by this book

## Extraction Steps

1. Skim or read the book.
2. Capture the thesis in 1–3 sentences.
3. Identify 5–15 key cases (incidents) and 10–30 key people. **Resist the urge to extract every name** — minor mentions belong as flat text, not wikilinks.
4. Identify 5–15 major claims/theses. Each goes to a `claims-theses` page.
5. Extract entities at the depths above only — for books, the standard 9-type hierarchy applies but the cap is per-category (≤15 incidents, ≤30 people, etc.). Other entity types (programs, places, craft-phenomena, documents, tech-artifacts, symbols-glyphs) should be linked only when central to the book's argument.
6. Note significant inter-book connections — does this book engage with another book in the KB (cite, critique, build on)?
7. Categorize: nonfiction reportage / nonfiction memoir / fiction / academic / self-published. Provenance shapes credibility weight.

## Wiki Updates

- Book gets a digest page in `wiki/books/` AND an entity record in `wiki/entities/documents/` (since books are documents). The entity-record page is a stub linking back to the digest.
- Create or update author pages.
- Create or update entity pages for each key case (incident) and key person.
- Create or update `claims-theses` pages for each major claim.
- If the book responds to or is responded to by another work in the KB, link both ways (response-literature edge).
- Update `wiki/synthesis/` only if the book meaningfully strengthens or contradicts an existing synthesis page.

## Cross-Linking Rules

- Book ↔ author bidirectional.
- Book → publisher (organization).
- Book → every key case → corresponding incident page.
- Book → every claim → claims-theses page.
- If the book discusses another book in the KB, link both ways (response-literature edge).
- Auto-link ambiguous names only when the existing page is the unique plausible match.
- Every new entity page MUST link to at least one concept page.
- Every major claim MUST link to a `claims-theses` page.

## Log

`[YYYY-MM-DD] import:books | <slug> | <title> | author: <name>, key-cases: N, claims: M`

## Quality Check

- Verify both `wiki/books/<slug>.md` and `wiki/entities/documents/<slug>.md` exist.
- Verify all key people pages back-link to the book.
- Verify all key cases (incidents) back-link to the book.
- Verify all major claims have claims-theses pages with this book cited.
- **Reverse density check**: if the summary contains more than ~50 wikilinks, you over-extracted; demote minor mentions to flat text.
- Verify ISBN is preserved verbatim from the copyright page.
- Run `qmd update --collections ufo-kb && qmd embed`.
