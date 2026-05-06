---
name: articles
trigger: "A web article, Substack post, or piece of journalism is added to raw/articles/"
source_destination: raw/articles/
summary_destination: wiki/articles/
---

# Articles Import

Handles web articles, Substack posts, longform journalism (Shellenberger, Coulthart, Knapp, Kean, etc.). Article date matters a lot for timeline placement.

## Source Summary

Summary page in `wiki/articles/<slug>.md` with frontmatter: `title`, `authors[]`, `outlet`, `published`, `url`, `tags[]`. Body sections: Headline Claims · Entities Mentioned · Citations / Sources Cited · Connections.

## Extraction Steps

1. Read the article.
2. Extract: entities (per CONSTITUTION's nine entity types), claims, citations.
3. **Citations are first-class connections** — when an article cites another article, document, person, or prior incident, capture each citation as an edge.
4. Date the article precisely — articles slot into `wiki/timeline/` views by date.

## Wiki Updates

- Create the article summary page.
- Create/update entity pages.
- Create/update `claims-theses` pages for each discrete assertion.
- Link author → outlet (organization) → article.

## Cross-Linking Rules

- Article → author (person, create if missing).
- Author → outlet (organization, create if missing).
- Article → every claim it makes (claims-theses pages).
- Article → every cited source (other documents/articles).
- Auto-link ambiguous names only when uniquely matched.

## Log

`[YYYY-MM-DD] import:articles | <slug> | <title> | author: <name>, outlet: <outlet>`

## Quality Check

- Author and outlet pages exist and back-link to the article.
- Every claim in the article links to a claims-theses page.
- Run `qmd update --collections ufo-kb && qmd embed`.
