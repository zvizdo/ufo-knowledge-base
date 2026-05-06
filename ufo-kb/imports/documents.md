---
name: documents
trigger: "A primary-source document (FOIA, leaked memo, gov report, complaint, briefing) is added to raw/documents/"
source_destination: raw/documents/
summary_destination: wiki/documents/
---

# Documents Import

Handles primary-source documents: FOIAs, leaked memos, government reports, the Grusch complaint, AARO reports, hearing exhibits, briefing slides.

## Why Documents Matter

Documents are the highest-credibility source type in the discourse. A claim sourced to a document outweighs hearsay in nearly every framework. Treat documents as **canonical sources** — when a claim has a documentary source, that document becomes the citation of record on the relevant claims-theses page.

## Source Summary

Summary page in `wiki/documents/<slug>.md` with frontmatter: `title`, `authors[]`, `recipients[]`, `date`, `type` (memo/foia/report/complaint/briefing/exhibit), `classification`, `provenance` (how it became public), `tags[]`. Body sections: Summary · What's Revealed · What's Redacted · Named Entities · Connections.

## Extraction Steps

1. Read the document.
2. Identify: author(s), recipient(s), date, classification level, provenance.
3. Extract every named person, org, program, place, incident, tech-artifact.
4. Note redactions explicitly — what's missing is itself a signal.
5. Extract every claim made or implied. Documents often imply more than they state.

## Wiki Updates

- Document gets a page in BOTH `wiki/documents/` (this digest) and `wiki/entities/documents/` (the entity record).
- Every claims-theses page that references this document MUST cite it explicitly with the document's slug.

## Cross-Linking Rules

- Document → every named entity.
- Document → every claim it makes/implies.
- Document → its provenance (who leaked it, who FOIA'd it, who released it).
- If the document references another document, link both.

## Log

`[YYYY-MM-DD] import:documents | <slug> | <title> | type: <type>, classification: <level>`

## Quality Check

- Every named entity has a back-link to the document.
- Every claim sourced from the document is updated to cite it.
- Run `qmd update --collections ufo-kb && qmd embed`.
