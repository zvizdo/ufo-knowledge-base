---
name: books
trigger: "A book (PDF, EPUB, or text excerpt) is added to raw/books/"
source_destination: raw/books/
summary_destination: wiki/books/
---

# Books Import

Handles book-length sources (Vallée, Dolan, Pasulka, Knapp, Kean, Sheehan, etc.).

## Depth

**Thematic, not chapter-by-chapter.** Capture the book's thesis, key cases discussed, key people interviewed/cited, and major claims advanced. Don't extract every minor mention — books drown the KB if treated like transcripts.

## Source Summary

Summary page in `wiki/books/<slug>.md` with frontmatter: `title`, `authors[]`, `published`, `publisher`, `isbn`, `tags[]`. Body sections: Thesis · Key Cases Discussed · Key People Cited · Major Claims · Connections.

## Extraction Steps

1. Skim or read the book.
2. Extract: thesis (1–3 sentences), 5–15 key cases, 10–30 key people cited, 5–15 major claims/theses.
3. Note significant inter-book connections (does this book engage with another book in the KB?).

## Wiki Updates

- Book also gets an entry in `wiki/entities/documents/` (since books are documents). The summary page in `wiki/books/` is the *digest*; the documents entry is the *entity*.
- Create/update author pages.
- Create/update entity pages for each key case (incident) and person.
- Create/update `claims-theses` pages for each major claim.

## Cross-Linking Rules

- Book ↔ author bidirectional.
- Book → every key case → corresponding incident page.
- Book → every claim → claims-theses page.
- If the book discusses another book in the KB, link both ways.

## Log

`[YYYY-MM-DD] import:books | <slug> | <title> | author: <name>`

## Quality Check

- Both `wiki/books/<slug>.md` and `wiki/entities/documents/<slug>.md` exist.
- All key people pages back-link to the book.
- Run `qmd update --collections ufo-kb && qmd embed`.
