---
name: kb-query
description: Query the knowledge base by walking the wikilink graph one hop at a time. Disambiguates query entities, classifies query intent, runs the matching walker pattern (relational / comparison / thematic / gap / factoid), and renders answers with sentence-level path-as-citation grounding. Embeddings are used only for cold seed-finding; once on the graph, traversal is the sole grounding mechanism.
---

# kb-query — Walk the Graph, Cite the Path

The knowledge base is a graph. **The connections carry the meaning.** Every answer this skill produces is the trace of a walk across that graph, with each cited claim grounded in the line on the page where the wikilink appears.

> **Embeddings to enter, graph to ground.**
>
> qmd is allowed only at the very first step, and only when title/alias resolution fails. Once a seed page is identified, all further expansion is via wikilinks. Do not call qmd again mid-walk.

If you can't trace a claim to a path, you can't make the claim.

## Prerequisites

Set `{KB_ROOT}` to `ufo-kb`. The qmd collection name is `ufo-kb` (used only for cold seed-finding). Read `{KB_ROOT}/CONSTITUTION.md` (entity types, connection rules, synthesis structure). All paths below are relative to `{KB_ROOT}`.

## Query Flow

### Step 1 — Disambiguate query entities

For every entity mentioned in the question, run:

```bash
python scripts/disambiguate.py {KB_ROOT}/wiki/ "<mention>" --json
```

The script tries (in order) exact slug/alias match → substring → difflib fuzzy. It returns ranked candidates with type, summary, degree, folder.

**When more than one candidate comes back:** pick the candidate whose 1-hop neighborhood includes or sits adjacent to the other query entities. For bare single-entity queries, prefer the higher-degree candidate of the most-fitting type.

If `disambiguate.py` returns nothing (stage `none`) and the mention is conceptual rather than nominal, *only then* fall back to:

```bash
qmd vsearch "<mention>" -c ufo-kb
```

Always specify the collection. After qmd lands a seed, stop using qmd.

### Step 1.5 — Check for a cached synthesis

Run `python scripts/frontmatter.py {KB_ROOT}/wiki/synthesis/ --fields summary,derived-from`. If any synthesis page's `derived-from` covers most of your query's entities, **read it first** — it's already done the walk. Synthesis pages are sparse (~13) and curated; every one earned its keep.

### Step 2 — Classify the query

Pick exactly one mode:

| Mode          | Trigger phrasing                                         |
|---------------|----------------------------------------------------------|
| **factoid**   | "What do we know about X?", "Who is X?"                  |
| **relational**| "How does X relate to Y?", "Connection between X and Y?" |
| **comparison**| "Compare X, Y, Z", "How are A and B different?"          |
| **thematic**  | "What's interesting about X?", "Themes around X?"        |
| **gap**       | "What don't we know about X?", "Where is X thin?"        |

If a query genuinely spans modes (e.g. "Compare X and Y, focusing on what we don't know about Z"), pick the dominant mode and treat the rest as constraints during synthesis.

### Step 3 — Walk

Each mode has its own pattern. Follow the matching recipe in [references/walker-patterns.md](references/walker-patterns.md). Quick map:

- **factoid** → read the page; `neighbors.py --limit 8` for context; cite the page directly.
- **relational** → `shortest-path.py` between endpoints; pick informative paths; `linearize-path.py`.
- **comparison** → `neighbors.py` per entity; pairwise `shared-connections.py`; build comparison table.
- **thematic** → `neighbors.py --diverse --limit 20` from the hub; group by folder; name themes.
- **gap** → read page's `## Open Questions`; find dangling refs (`neighbors.py --json` filter `exists: false`); call `kb-maintain/scripts/jaccard-similarity.py` for missing-link predictions.

**Chained relational queries** ("How is A connected to B, and how does that relate to C?") are not a separate mode — they are two relational walks stitched together. Resolve A↔B first, then B↔C, then identify the shared intermediary that makes the chain a single story. The intermediary is almost always a concept page or a synthesis page — that's the punchline.

### Universal walker rules

Full rules in [references/walker-patterns.md](references/walker-patterns.md). The non-negotiable gates:

- **Graph is the truth substrate.** Every claim cites a page; every relationship cites a path's anchor sentence. No inference without a wikilink to back it.
- **Concept-mediated paths beat transcript-mediated paths.** A path through `concepts/` or `synthesis/` carries semantic weight; a path through `youtube-transcripts/` only says "they shared a podcast." When `shortest-path.py` returns equal-length paths, pick the one without transcript intermediates.
- **Read opportunistically, cap depth at 1.** The KB is ~2,200 pages with avg degree ~19 — a depth-2 walk reaches several hundred pages. Don't expand depth-2 unless you've named a specific theme.
- **Soft token caps:** factoid 1–3 pages; relational ≤8 pages and ≤3 cited paths; comparison 4–6 per branch; thematic ≤12; gap ≤10.
- **Frontmatter is a structured channel.** `firsthand_claims:` answers "what does X claim themselves?" without reading the body; `derived-from:` is the synthesis-coverage map; `corroboration:` is the incident credibility cue. `frontmatter.py` reads many pages cheaply.
- **A graph-grounded "I can't" beats a hallucinated "I can".** Report dead ends as findings.

### Step 4 — Linearize cited paths

For every relational or comparative path that ends up in the answer, render it with sentence-level citations:

```bash
python scripts/linearize-path.py {KB_ROOT}/wiki/ <slug1> <slug2> [<slug3> ...]
```

The output gives you, for each hop, the *line on the predecessor page* where the link appears (or, if missing, the line on the successor page that mentions the predecessor). That line is the relation. Quote it in the answer.

### Step 5 — Synthesize

- **Lead with the conclusion.** One sentence stating the answer.
- **Cite paths, not just pages.** `[[A]] → [[B]] → [[C]]` with the linearized anchors.
- **Surface contradictions.** If two pages disagree, say so; don't pick a winner.
- **Flag gaps.** If the walk found unwritten pages or thin neighborhoods relevant to the question, name them.
- **Match output format to the mode**: prose+citations (factoid), linearized path (relational), table (comparison), themed bullets (thematic), what-we-know/what's-missing (gap).

### Step 6 — Optional provenance

Off by default. Emit only when:
- The user passes `--with-provenance` or `--show-trace`.
- The user asks "show me the trace" / "show your work" / "render the subgraph".

When emitting:

```bash
python scripts/render-provenance.py {KB_ROOT}/wiki/ <visited-slug-1> <visited-slug-2> ... \
    --seed <disambiguated-seed-1> --seed <disambiguated-seed-2>
```

Append the resulting Mermaid block + JSON sidecar to the answer.

### Step 7 — Optionally file back

Synthesis-as-reasoning is ephemeral by default. Prompt to file when the walk touched 4+ pages across 2+ subdirs, revealed a relationship not stated on any single page, resolved a contradiction, compared 3+ entities, or identified a systematic gap. Do NOT prompt when the answer restates a single page, was about KB health, or is purely factual.

If filing, follow the synthesis-page template in [references/query-patterns.md](references/query-patterns.md), populate `derived-from:`, back-link from every referenced page, and run `qmd update --collections ufo-kb && qmd embed`.

## Tools

All under `scripts/` (Python stdlib only). Run `<script>.py --help` for arguments. The walker primitives — `disambiguate.py`, `neighbors.py` (anchor-sentence retrieval; auto-diversifies at degree > 50), `linearize-path.py`, `render-provenance.py` — are the canonical surface. Legacy primitives `shortest-path.py`, `neighborhood.py`, `shared-connections.py`, `frontmatter.py` cover specific walks (see [references/walker-patterns.md](references/walker-patterns.md) for which primitive each pattern uses).

For gap walks, `kb-maintain/scripts/jaccard-similarity.py` and `adamic-adar.py` surface predicted missing edges (Jaccard = symmetric overlap; Adamic-Adar = rare-intermediary weighted — run both for richer signal).
