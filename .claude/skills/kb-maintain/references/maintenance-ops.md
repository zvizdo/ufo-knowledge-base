# Maintenance Operations — Detailed Reference

The kb-maintain skill is a CONSTITUTION-aware audit pipeline. The detectors compare reality to the rules already in `CONSTITUTION.md` and to graph-structural invariants (orphans, islands, hub fan, cluster bridges). This document covers the detector reference, the severity rubric, the auto-fix scope, the analytics scripts, and recurring fix recipes.

---

## Detector reference

All detectors run from a single graph build. Invoke with `python scripts/audit.py <wiki-dir> <subcommand>`. Default subcommand is `all`.

### `constitution`  · severity Critical

Per-folder schema enforcement, drawn from CONSTITUTION.md. Sub-issues:

- **`constitution.missing-frontmatter`** — required field absent. Schema is per entity-type folder (people, organizations, programs, places, incidents, craft-phenomena, documents, tech-artifacts, symbols-glyphs).
- **`constitution.missing-connections-section`** — entity page has no `## Connections` H2 heading. CONSTITUTION says every entity ends with a Connections section.
- **`constitution.no-concept-link`** — entity page links to 0 pages in `wiki/concepts/`. CONSTITUTION says every entity must link to ≥1 concept page.
- **`constitution.naming-convention`** — slug doesn't match the folder's naming pattern (e.g., incidents must be `YYYY-shortname`).

Pages outside `entities/<type>/` are not lint-checked here (synthesis, articles, transcripts, concepts have their own conventions).

### `dangling`  · severity Critical

Wikilinks pointing to non-existent pages. Each finding carries the page where the link appears, the line number, and a candidate suggestion (or none if no fuzzy match exists).

Auto-fix gate: **only when the dangling target has an exact alias or normalized-title match to one existing page.** Substring and fuzzy candidates are surfaced as suggestions but never auto-applied — a 0.7-fuzzy "david-smith → mit" rewrite is wrong even when the score looks plausible.

### `orphans`  · severity High

Pages with 0 inbound wikilinks. Action: link from related pages or merge into a related entity. Newly-created synthesis pages may legitimately appear here briefly until back-links are added.

### `islands`  · severity High

Connected components of size 2–10 that are disconnected from the giant component. The maintenance-ops "Orphan Island Problem" is detected here. Each member of an island gets a finding listing the other members; the fix is to add at least one wikilink from the island to a relevant page in the giant component.

### `duplicates`  · severity High

Page pairs with:

1. Overlapping aliases (any shared alias) OR normalized-title `difflib` similarity ≥ 0.7
2. AND neighborhood Jaccard > 0.5

Surfaces alias-collision patterns (e.g., the historical `james-madden ↔ jim-madden` style). Findings include shared-aliases evidence, title-similarity ratio, and a sample of shared neighbors. Action: read both pages, decide if same entity, merge if so.

### `synthesis`  · severity High

Synthesis-page health. For every page where `type: synthesis`, `synthesis-type:` is set, or path is under `wiki/synthesis/`:

- **`synthesis.missing-derived-from`** — synthesis page has no `derived-from:` frontmatter at all.
- **`synthesis.derived-from-missing`** — `derived-from` references a page slug that doesn't exist.
- **`synthesis.missing-backlink`** — synthesis declares page A in `derived-from`, but A's body doesn't link back to the synthesis. **Auto-fixable** — `--apply` appends `- Synthesized in [[S]]` under A's `## Connections` section (creating the section if missing).

No date checks. The synthesis being "older" than its derived-from sources is not a signal here — the KB is long-lived and content evolves outside time-windows.

### `stubs`  · severity Medium / High

Pages with body < 10 non-empty lines. Excludes `youtube-transcripts/` (deliberately raw) and `synthesis/` (summaries by design). Severity scaling:

- **High** if body < 5 OR best-neighbor degree > 30 (a stub adjacent to a hub is a connectivity gap that punches above its weight)
- **Medium** otherwise

Action: flesh out the page (background, claims, sources, connections) or merge into a related entity if redundant.

### `bridges`  · severity Medium

Pages that are load-bearing structural bridges but underwritten:

- body < 10 non-empty lines (stub-quality content)
- AND degree ≥ 8 (load-bearing in the graph, not a small stub)
- AND neighbors span ≥3 distinct folder paths (e.g. `entities/people` + `entities/programs` + `concepts`)

The page's structural role doesn't match its content quality — a bridge whose body is thin is "rotting." Action: flesh out the page so its content matches its role, or split its connections across more substantive intermediaries.

> **Why folder-fan, not cluster-fan?** Label-propagation on this graph reliably collapses into 2–3 mega-communities, which makes cluster-based fan signal too sparse to be useful. Folder spread (using the wiki's directory structure as a coarse semantic partition) is a more stable indicator of "this page touches genuinely different sub-domains."

### `hubs`  · severity Low

Multi-criterion split candidates:

- degree > 50
- AND body > 100 non-empty lines
- AND ≥4 H2 headings (sub-topic structure exists)
- AND neighbors span ≥3 distinct folders (not concentrated in one sub-domain)
- AND folder is NOT `youtube-transcripts/` or `synthesis/`

Action: propose split — parent page becomes overview; H2 sub-topics become standalone pages with bidirectional links. Always ask before splitting.

---

## Severity rubric

| Tier | Meaning | Default response |
|------|---------|------------------|
| **Critical** | violates CONSTITUTION schema or breaks queryability (dangling links, missing required frontmatter, missing Connections section, no concept-link, wrong naming) | fix or surface immediately; don't ignore |
| **High** | structurally weak (orphans, islands, duplicates, synthesis broken back-links / missing derived-from); high-priority stubs | propose action this run; auto-fix back-links with `--apply` |
| **Medium** | content quality concerns (stubs, rotting bridges) — flag for incremental improvement | surface; user decides priority |
| **Low** | optimization candidates (hubs that could be split) — almost always discretionary | surface; user decides priority |

A finding's severity is impact, not novelty. A new dangling link from a hub is critical; a long-standing stub-orphan in a low-degree corner is low.

---

## Auto-fix scope

`--apply` performs only these two classes of edit:

### 1. Reciprocal back-links from `derived-from`

For every synthesis page S with `derived-from: [A, B, C]`, ensure each A/B/C body links to S. If A's body has no `[[S]]` wikilink:

- If A has a `## Connections` section, append `- Synthesized in [[S]]` at the end of that section (before the next H2 or end of file).
- If A has no `## Connections` section, append `## Connections\n\n- Synthesized in [[S]]` at the end of the file.

The CONSTITUTION already requires synthesis pages to be linked from every page they derive from. This is an enforcement, not a guess.

### 2. Single-candidate dangling-link rewrite

For every dangling wikilink `[[X]]`:

- Run normalize-and-resolve over all page slugs and aliases.
- If exactly one page matches at the **exact** stage (normalized title equals the dangling target, OR an `aliases:` entry matches exactly), rewrite `[[X]]` → `[[<that page's title>]]` in place.
- **Substring and fuzzy candidates are never auto-applied.** They appear in the report as suggestions for human review.

Pattern matched: `[[X]]`, `[[X|alt-text]]`, `[[X#anchor]]` — alt-text and anchor are preserved.

### What is NOT auto-fixed

- Merging duplicate pages
- Splitting hubs
- Creating synthesis pages
- Rewriting body content (CONSTITUTION schema fixes that need new prose)
- Adding missing frontmatter fields (the user must supply values)
- Adding missing concept-page links (the user must pick the right concept)
- Insertingmissing `> ⚠ Conflict:` callouts
- Adding aliases
- Anything else

These flag for the user with evidence and a suggested action, but require approval before any change.

---

## Graph analytics scripts

These complement the audit. Audit finds rule violations; analytics find candidate *new* connections.

### `jaccard-similarity.py`

`J(A, B) = |neighbors(A) ∩ neighbors(B)| / |neighbors(A) ∪ neighbors(B)|`

High Jaccard + no direct link = strong missing-link prediction.

```bash
python scripts/jaccard-similarity.py <wiki-dir> [--threshold 0.3] [--top 20]
```

Score interpretation:
- > 0.5: Very likely missing link
- 0.3–0.5: Probable missing link, worth reviewing
- < 0.3: Weak signal

### `adamic-adar.py`

`AA(A, B) = Σ 1/log(degree(z))` for common neighbors z. Weights rare intermediaries more heavily than hubs — surfaces *interesting* (non-obvious) connections.

```bash
python scripts/adamic-adar.py <wiki-dir> [--top 20]
```

Use this when raw common-neighbors is dominated by a few hubs.

### `common-neighbors.py`

Raw count of shared neighbors. Useful as a sanity-check baseline against Jaccard / Adamic-Adar.

```bash
python scripts/common-neighbors.py <wiki-dir> [--min-common 2] [--top 20]
```

### `cluster-detection.py`

Label-propagation communities + bridge pages + hub identification.

```bash
python scripts/cluster-detection.py <wiki-dir> [--min-cluster 3]
```

Useful for understanding the macro-structure of the graph and spotting cluster-bridging synthesis opportunities.

---

## Common patterns and fix recipes

### The Orphan Island

A batch import created several new pages that reference each other but not the rest of the wiki.

**Signs**: `audit.py islands` returns small components; multiple orphans found in the same import folder.

**Fix**:
1. Run `python scripts/jaccard-similarity.py {KB_ROOT}/wiki/ --threshold 0.3` filtered to involve island members on one side. Top scores point to candidate connections to the giant component.
2. Open each suggested anchor: confirm the relationship exists in source material.
3. Add a wikilink from the relevant island page to the suggested giant-component page (or vice versa, if direction matters).
4. Re-run `audit.py islands` to confirm zero remaining components.

### The Alias Collision (duplicate pages for the same entity)

Two pages describe the same person/org/program because slug normalization differed (e.g., `james-madden.md` and `jim-madden.md`, both legitimate spellings of one person). The pages have overlapping aliases and large neighborhood overlap.

**Signs**: `audit.py duplicates` surfaces the pair with shared-aliases evidence + Jaccard ≥ 0.5.

**Fix**:
1. Open both pages. Confirm same entity (anchor sentences via `kb-query/scripts/neighbors.py` help: read what each page says about shared neighbors).
2. Decide canonical slug (usually the spelling matching the CONSTITUTION naming convention or the form most-cited externally).
3. Merge content into the canonical page: union frontmatter (especially `aliases:` — add all forms), union body sections, union sources.
4. Run `python scripts/audit.py {KB_ROOT}/wiki/ dangling` to find pages that linked to the deprecated slug. With `--apply`, the canonical page's alias entry will auto-rewrite those links on the next pass.
5. Delete the deprecated file. Re-run `audit.py duplicates` to confirm zero remaining for this pair.

### The Growing Hub (a page now does too much)

A concept or central entity page has accreted enough scope that it bridges multiple sub-themes and has a high heading-count body — it should be split.

**Signs**: `audit.py hubs` flags the page (degree > 50, body > 100 lines, ≥4 H2 headings, fan ≥3 clusters).

**Fix**:
1. Read the H2 heading list — each should suggest a sub-topic.
2. Propose a split outline to the user. Example for `[[mk-ultra]]`: parent stays as overview; new pages for `[[mk-ultra-bluebird-precursor]]`, `[[mk-ultra-subprojects]]`, `[[mk-ultra-mind-control-techniques]]`, etc.
3. After approval: create new pages with content from the corresponding H2 sections; replace those sections in the parent with one-paragraph summaries linking to the new pages; back-link from each new page to the parent.
4. Re-run `audit.py orphans dangling` after to catch any new structural debt.

### The Rotting Bridge

A page bridges 3+ clusters but its body is a stub. The graph treats it as load-bearing; the content doesn't carry that weight.

**Signs**: `audit.py bridges` surfaces it (body < 10 lines, fan ≥ 3).

**Fix**:
- **Option A**: flesh out the page so its content matches its role. Add background, claims, sources, connections.
- **Option B**: if no real content exists yet, redirect the bridge through a more substantive page. Move some links from the rotting bridge to a related concept or entity page that has the depth, then delete the bridge.

### The Concept-Linkless Entity

A new entity page exists but doesn't link to any `wiki/concepts/` page — violates the CONSTITUTION rule that every entity must touch ≥1 concept.

**Signs**: `audit.py constitution` flags `constitution.no-concept-link`.

**Fix**:
- People → typically link to `[[credibility-frameworks]]` (or a more specific concept page if the person's role is narrow).
- Documents → typically link to `[[recurring-claims]]` or `[[source-type-frameworks]]`.
- Incidents → typically link to `[[phenomenology-categories]]`.
- Places → typically link to a concept that captures why the place matters (e.g., `[[reverse-engineered-craft]]` for a base associated with retrieval programs).

Add the link in the body where it makes contextual sense, not just in `## Connections` — the link should be where the relationship is described.

### The Frontmatter-incomplete Page

`audit.py constitution` flags `constitution.missing-frontmatter` for a page in `entities/<type>/`.

**Fix**:
- Read the CONSTITUTION schema for that folder.
- For each missing field, supply the value from source material. If the value isn't known, use `[]` for list fields and a placeholder like `unknown` for scalar fields (better than absent — the audit doesn't flag empty values, only missing keys).
- Re-run `audit.py constitution --json | jq '.findings.constitution[] | select(.slug == "<page>")'` to confirm the finding cleared.

---

## Stateless by design

There is no maintenance log file, no snapshot, no diff-since-last-run. Every audit reflects current reality. If the same finding persists across runs, it persists because nothing has been done about it — that's the right signal. The audit's job is to surface what's true now, not to remember what was true before.
