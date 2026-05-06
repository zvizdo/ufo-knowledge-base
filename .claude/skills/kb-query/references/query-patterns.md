# Query Patterns — Detailed Reference

## Graph-Traversal-First Philosophy

Traditional RAG: embed query → retrieve chunks → generate answer.

Knowledge base querying: find entry nodes → walk the graph → synthesize from connections.

The difference: RAG treats documents as isolated chunks. Graph traversal treats pages as nodes in a network where **the relationships carry as much meaning as the content**.

When answering "How does X relate to Y?", the shortest path between X and Y through intermediary concept pages IS the answer. No embedding similarity score can give you that.

## Query Type Deep Dives

### Factual Queries

"What do we know about attachment theory?"

1. Find [[Attachment Theory]] via filename match or `qmd search`
2. Read it
3. Follow its `## Related` links to see connected entities and concepts
4. Synthesize a comprehensive answer from the page and its immediate neighbors

Keep it grounded — don't speculate beyond what the wiki contains.

### Relational Queries

"How does running relate to conscientiousness?"

1. Find entry points: [[Running]], [[Conscientiousness]]
2. Run `shortest-path.py` between them
3. Read every page on the path(s)
4. The path tells the story: maybe [[Running]] → [[Discipline Signals]] → [[Conscientiousness]]
5. Answer describes the connection through intermediary concepts

If no path exists, that's informative too: "These concepts aren't connected in the KB yet."

### Analytical Queries

"Compare Person A and Person B"

1. Find both entity pages
2. Run `shared-connections.py` to find what they have in common
3. Run `neighborhood.py` on each to see their local graphs
4. Build a comparison across dimensions defined in the CONSTITUTION's evaluation criteria
5. Output as a structured table or side-by-side analysis

### Gap Queries

"What don't we know about this topic?"

1. Find the topic page
2. Check its source count and last updated date
3. Look for stub links (`[[Page]]` references with no actual page)
4. Check if the CONSTITUTION defines entity types or concept areas not yet covered
5. Report what exists vs what's missing

### Exploratory Queries

"What's interesting in the KB right now?"

1. Run `neighborhood.py` on high-degree nodes (pages with many connections)
2. Find unexpected connections (pages linked through surprising intermediaries)
3. Surface clusters and bridges

## Using qmd for Entry Point Discovery

Three search modes, use the right one:

- `qmd search "exact terms" -c ufo-kb` — BM25 keyword search. Fast. Use when you know the exact terms.
- `qmd vsearch "conceptual query" -c ufo-kb` — Vector semantic search. Use when the question uses different words than the wiki pages.
- `qmd query "complex question" -c ufo-kb` — Hybrid + LLM re-ranking. Best quality, slowest. Use for ambiguous or complex queries.

**Always specify the collection** with `-c ufo-kb`. Never run unscoped searches.

After finding entry points via qmd, switch to graph traversal. qmd finds the door; the graph walk finds the answer.

## Synthesis Pages

### What Synthesis Is

A synthesis page is a **cached inference** — it captures reasoning the LLM derived by traversing multiple pages, so future queries can read one page instead of re-walking the same subgraph and re-deriving the same conclusions.

Synthesis pages contain:
- **Derived relationships** that don't exist on any single entity or concept page (e.g., "A and B share pattern X, which contradicts C")
- **Cross-cutting patterns** across multiple entities or concepts that only become visible when you traverse a subgraph
- **Evaluated conclusions** — the "so what?" that requires combining evidence from multiple sources

### What Synthesis Is NOT

- A summary of a single source (that's `source-summary`)
- A restatement of what one entity page already says (that's a factual lookup)
- A concept definition (that belongs in `wiki/concepts/`)
- An index or table of contents (that's structure, not reasoning)

### Litmus Tests

1. **Grounded?** Could the LLM reconstruct this page's conclusions by reading only the pages listed in its `derived-from` field? If yes, the synthesis is valid — it captures real inference from real sources.
2. **Worth caching?** Will a future query likely need this same traversal? If the derivation is non-trivial or the connected ideas are far apart in the graph, it's worth persisting.

### When to File

**Prompt the user to file when the answer meets ANY of these:**
- The traversal touched 4+ pages across 2+ wiki subdirectories
- The answer reveals a relationship not stated on any single page
- The answer resolves or documents a contradiction between pages
- The answer compares 3+ entities
- The answer identifies a gap pattern (systematic missing knowledge)
- The user says "that's useful, keep it"

**Do NOT prompt when:**
- The answer restates what a single entity or concept page already says
- The query was about KB health or structure
- The answer is purely factual with no derived inference

### Synthesis Page Structure

```markdown
---
type: synthesis
synthesis-type: comparison | pattern | contradiction | gap-analysis | framework-application
summary: "One-line statement of the conclusion"
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: [raw/... if applicable]
derived-from: [page-slug-1, page-slug-2, ...]
tags: [domain-specific tags]
---

# Title (a claim or question, not just a topic)

## Key Finding
2-3 sentences stating the core insight. This is the pre-computed answer —
a future query can read just this section and get the conclusion.

## Evidence
Reasoning chain with [[wikilink]] citations.
Structure: evidence → inference → conclusion.

## Caveats
What this synthesis doesn't account for. Gaps in source material.
Conditions under which the conclusion might not hold.

## Related
- [[Page1]] — role in this synthesis (e.g., "primary evidence for X")
- [[Page2]] — role in this synthesis
```

**Frontmatter fields:**
- `synthesis-type` — the kind of synthesis: `comparison`, `pattern`, `contradiction`, `gap-analysis`, or `framework-application`
- `derived-from` — every wiki page slug whose content was used to produce this synthesis. Enables staleness detection during maintenance and impact analysis during import.

### Quality Guidelines

- **Lead with the conclusion.** The Key Finding section should be self-contained — 80% of the value without reading linked pages.
- **Wikilinks are citations, not required reading.** A synthesis page that requires you to read its linked pages to understand it has failed. The links are for verification and deeper exploration.
- **Aim for under 200 lines.** If longer, consider splitting. A synthesis page as long as the pages it synthesizes defeats the purpose.
- **Name as a claim or question.** `impact-of-sleep-on-training-adaptations.md` is better than `sleep-and-training.md`. The filename should hint at the conclusion.
- **Stand alone.** Someone reading just this page should understand it without context.
