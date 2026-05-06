# Walker Patterns — How to Walk the KB Graph

The kb-query skill is a graph walker. The graph is the truth substrate; embeddings (qmd) exist *only* to land on a seed node when no obvious title match exists. Once you're on the graph, you stop calling qmd and start walking.

This document defines four traversal patterns, one per query class. The SKILL.md prompt selects between them based on query classification.

---

## Universal walker rules

These apply to every pattern.

1. **Embeddings to enter, graph to ground.** qmd is allowed for the very first seed-finding step when title/alias resolution fails. After that, do not call qmd again. Every subsequent expansion is via wikilinks.
2. **The graph is the truth substrate.** If you can't trace a claim to a path, you can't make the claim. The line on the page where a wikilink appears is the relation — read it, don't infer.
3. **Read pages opportunistically, not exhaustively.** The walker is the LLM. At each hop, decide what's worth following based on `neighbors.py` output (anchor sentences, summaries, degrees), not by reading everything.
4. **Hubs swallow neighborhoods.** When a page has degree > 50, pass `--diverse` to `neighbors.py` (it's auto-on at >50 anyway). Sample by folder; don't expand every link.
5. **Stubs are evidence.** A page with degree 2 and a 3-line body is meaningful in a *gap* walk. It's noise in a *factoid* walk.
6. **Cite the path, not just the page.** The default output for any non-trivial answer includes a `linearize-path.py`-rendered chain.
7. **Token budget per query** (soft caps, the model can override with reason):
   - Factoid: read 1–3 pages
   - Relational: read up to 8 pages, max 3 cited paths
   - Comparison: 4–6 pages per branch, intersection only
   - Thematic: up to 12 pages, sampled diversely
   - Gap: up to 10 pages, prioritize stubs and dangling references

---

## Pattern 1 — Relational walk (X → Y)

**Trigger queries:** "How does X relate to Y?", "What's the connection between X and Y?", "Why does X matter for Y?"

**Goal:** find the most informative path(s) between two anchored entities and cite each hop.

### Steps

1. **Disambiguate both endpoints** with `disambiguate.py`. If either has multiple candidates, pick by neighborhood overlap with the other endpoint (the candidate whose neighbors include or are 1-hop from the other endpoint is almost always the right one).
2. **Find candidate paths** with `shortest-path.py`. This returns all shortest paths *and* near-shortest (+1 hop). Don't stop at the first; the third or fourth path is often more illuminating because it routes through a meaningful concept page rather than a generic source-summary page.
3. **Read intermediate nodes selectively.** For each candidate path, look at the intermediates. Skip paths that route through transcript IDs (`youtube-transcripts/*`) when an entity-pages-only path exists. Prefer paths through concept pages — they carry semantic weight.
4. **Linearize 1–3 paths** with `linearize-path.py`. The anchor sentences *are* the relational claim; read them.
5. **Synthesize.** Lead with one sentence stating the connection. Then show the linearized path(s). Then add interpretation drawn from the anchor sentences.

### Example

> Q: "How does David Grusch relate to the 1933 Magenta crash?"

```
$ disambiguate.py wiki/ "David Grusch"           # → david-grusch (exact)
$ disambiguate.py wiki/ "1933 Magenta crash"     # → 1933-magenta-crash (substring; prefer over magenta-italy)
$ shortest-path.py wiki/ david-grusch 1933-magenta-crash
  Shortest paths (1 hops):  david-grusch → 1933-magenta-crash
  Near-shortest (+1):       david-grusch → harold-malmgren → 1933-magenta-crash
                            david-grusch → richard-bissell → 1933-magenta-crash
                            david-grusch → reverse-engineered-craft → 1933-magenta-crash

$ linearize-path.py wiki/ david-grusch harold-malmgren 1933-magenta-crash
```

The +1-hop path through `harold-malmgren` is more interesting than the direct edge: it shows *how* Grusch ties to Magenta — through the Bissell-to-Malmgren disclosure chain. Lead with that.

---

## Pattern 2 — Comparison walk (X, Y, Z)

**Trigger queries:** "Compare X and Y", "How are A, B, C similar/different?", "What do X and Y have in common?"

**Goal:** find the *common ground* and the *differentiators*. The shared region of the graph is the common ground; the exclusive regions are the differentiators.

### Steps

1. **Disambiguate all entities.**
2. **Get neighborhoods.** For each entity, call `neighbors.py` (limit ~25, diverse if degree > 50).
3. **Compute intersections.**
   - For two entities, use `shared-connections.py` directly.
   - For three or more, take pairwise intersections of their neighbor sets. Pages in *all* sets are the common ground; pages in *one* set are exclusive.
4. **Read the shared and exclusive pages selectively.** Cap at 4–6 pages per branch.
5. **Build a comparison table.** Columns = entities. Rows = dimensions that emerge from the data (people, programs, places, claims, period). Each cell contains `[[wikilink]]` citations grounding the entry.
6. **Linearize key relationships** if any cross-entity path is itself the punchline (e.g., "AAWSAP and AATIP are linked by Lacatski in this exact way" — show the path).

### Example

> Q: "Compare AATIP, AAWSAP, and the UAP Task Force."

```
$ disambiguate.py wiki/ "AATIP"
$ disambiguate.py wiki/ "AAWSAP"
$ disambiguate.py wiki/ "UAP Task Force"

$ neighbors.py wiki/ aatip      --limit 25
$ neighbors.py wiki/ aawsap     --limit 25
$ neighbors.py wiki/ uap-task-force --limit 25

$ shared-connections.py wiki/ aatip aawsap
$ shared-connections.py wiki/ aatip uap-task-force
```

Look for entities that show up in all three neighborhoods (e.g., key people like Lacatski, Kelleher; places like Skinwalker Ranch). Those go in shared rows. Period, congressional reception, declassification status differ — those go in differentiator rows.

---

## Pattern 3 — Thematic walk (around X)

**Trigger queries:** "What's interesting about X?", "What are the major themes around X?", "What's in the X cluster?"

**Goal:** surface the diverse themes around a hub without getting trapped in any single subcluster. The hardest part: hubs (e.g., `mk-ultra`, `david-grusch`, `disclosure-narratives`) have ~100+ neighbors and naive expansion collapses into the densest sub-region.

### Steps

1. **Disambiguate the hub.**
2. **Diverse 1-hop expansion.** Call `neighbors.py` with `--diverse --limit 20`. The script round-robins by folder (entities/people, entities/orgs, concepts, synthesis, …) so you see variety, not just the densest folder.
3. **Read a few pages from each folder bucket.** 2–3 from each of the 4–6 folders the hub spans.
4. **Name themes from the anchor sentences.** The walker reads the anchor sentence for each link — those sentences cluster naturally. Group them into 3–6 themes and label each.
5. **Cite entry points per theme.** For each theme, show 2–3 cited pages. Don't go deeper than 1 hop per branch unless one theme demands it.
6. **Surface synthesis pages.** If `entities/synthesis/` neighbors exist, lead with them — they're already cached inferences for this hub.

### Anti-pattern

Do *not* expand to depth 2 from a hub. The number of pages explodes. Pick one or two themes that *most* warrant deeper exploration based on the question's intent, and recurse only into those.

### Example

> Q: "What are the major themes around MK-Ultra?"

```
$ neighbors.py wiki/ mk-ultra --diverse --limit 24
```

Folder buckets that come back: `entities/people` (handlers, victims, witnesses), `entities/programs` (Bluebird, Artichoke, Monarch), `entities/places` (Fort Detrick, McGill, Edgewood), `concepts` (mind-control, false-memory, induced-amnesia), `entities/synthesis` (mk-ultra-mind-control-ecosystem). Lead with the synthesis page; group the rest by theme; cite 2–3 entry points per theme.

---

## Pattern 4 — Gap walk (about X)

**Trigger queries:** "What don't we know about X?", "Where is the KB thin on X?", "What's missing from X?"

**Goal:** identify what *should* be on the page but isn't, what *should* be linked but isn't, and what *should* be corroborated but isn't.

### Steps

1. **Disambiguate the topic.**
2. **Read the page.** Look explicitly at:
   - `## Open Questions` headings (first-class gaps in this KB by CONSTITUTION rule)
   - `firsthand_claims:` frontmatter entries that have no corroborating wikilinks in the body
   - `derived-from:` (synthesis pages) — note any page that has been updated since the synthesis (impact-of-staleness signal)
3. **Find dangling wikilinks.** Use `neighbors.py --json` and check `exists: false` on any neighbors. Those are pages mentioned but not yet written — direct evidence of intended-but-missing knowledge.
4. **Surface low-degree neighbors.** Pages in the 1-hop neighborhood with degree < 5 are stubs. Stubs of important neighbors are first-order gaps.
5. **Run missing-link prediction.** Call `kb-maintain/jaccard-similarity.py` (or `adamic-adar.py`) seeded on this page. Top predictions are pages that *look* connected by neighborhood overlap but aren't linked yet — second-order gaps.
6. **Structure the answer:**
   - **What we know:** 2–3 sentences from the page itself.
   - **What's thin:** stubs in the neighborhood, missing corroboration on firsthand claims.
   - **What's missing:** dangling references (pages mentioned but not written), dangling Open Questions.
   - **What should be connected:** Jaccard/Adamic-Adar predictions worth pursuing.

### Example

> Q: "What don't we know about Eric Davis?"

```
$ disambiguate.py wiki/ "Eric Davis"
$ neighbors.py wiki/ eric-davis --json | jq '.neighbors[] | select(.exists == false)'
$ python kb-maintain/scripts/jaccard-similarity.py wiki/ --seed eric-davis --top 10
```

Filter the neighbor list for `exists: false` (dangling). Read his page for `## Open Questions`. Run Jaccard for predicted missing edges. Compose answer.

---

## When the walker is stuck

If a walk hits a dead end (no path between endpoints, or no relevant neighbors), don't escalate to qmd. Instead:

- **For relational queries with no path:** report the gap explicitly. "These two entities are not connected in the KB. The closest indirect link is via [intermediary], but no direct path exists." This is a valuable answer.
- **For comparison with empty intersection:** report the absence of common ground as the finding. Often the most informative answer.
- **For thematic with no useful diversity:** the hub may be too narrow or the question too broad; ask the user to refine.
- **For gap walks:** an empty gap report means the page is well-connected — say so.

A graph-grounded "I can't answer this from the graph" is more useful than a hallucinated response from semantic search.

---

## Provenance (opt-in)

When the user passes `--with-provenance` or asks "show me the trace", call `render-provenance.py` with all visited slugs (and `--seed` for the disambiguated query entities). Append the resulting Mermaid + JSON block to the answer. By default, do not emit provenance — most queries don't need it and it inflates output.
