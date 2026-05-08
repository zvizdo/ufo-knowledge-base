---
name: kb-import
description: Import orchestrator — processes a new source into the knowledge base. Pulls graph context first, creates/updates pages with alias-aware deduplication, predicts non-obvious connections via Jaccard / Adamic-Adar / common-neighbors, auto-applies safe back-links, runs the audit at the boundary, and syncs the search index.
---

# kb-import — Source In, Graph Integrated

The CONSTITUTION is the spec. Imports must produce pages that *already* satisfy it before sync — and that *already* sit in the right place in the graph.

> **Embeddings to enter, graph to ground.**
>
> qmd is allowed only at the very start, for seed-pull. Once the seed pages are read, all further reasoning about *where the new content connects* uses the graph: `disambiguate.py` for alias resolution, `predict-connections.py` for missing-edge candidates, `audit.py` at the boundary. No qmd mid-import.

If a new page lands without ≥2 inbound links, an existing concept link, and a clean audit, the import isn't done.

## Prerequisites

Set `{KB_ROOT}` to `ufo-kb`. The qmd collection name is `ufo-kb` (used only in Step 3). Read `{KB_ROOT}/CONSTITUTION.md` (entity types, connection rules, naming, required frontmatter, required sections — every page created here must satisfy it). All paths below are relative to `{KB_ROOT}`.

## Import Flow

### Step 1 — Receive source

The user provides a source (file, pasted text, URL, screenshot). Move/copy the raw source into the appropriate `{KB_ROOT}/raw/` subdirectory as defined by the matched import procedure.

### Step 2 — Select procedure (with off-topic gate)

Identify which procedure applies:

1. **Off-topic gate**: read `{KB_ROOT}/imports/off-topic-skipped.md`. If the source's ID/slug appears there, the skip decision is already made — stop and tell the user. To override, the user must remove the entry from the registry first.
2. Read all files in `{KB_ROOT}/imports/` (skip `_template.md` and `off-topic-skipped.md`).
3. Match on each procedure's `trigger` field and the source type/content.
4. **Topical gate**: even with a procedure match, judge whether the source actually engages with the KB's domain (UFO/UAP/NHI and adjacents per CONSTITUTION). If it doesn't:
   - Append a one-line entry to `{KB_ROOT}/imports/off-topic-skipped.md` with the source ID and skip reason.
   - Stop. Do not create a wiki page.
5. If multiple procedures match, ask the user.
6. If none match, ask the user whether to do a one-off import using CONSTITUTION rules or to define a new procedure (kb-evolve).

### Step 3 — Read context + seed-pull

Before reading the source for extraction, build a graph-aware reading list.

#### 3a. Read the rules

- The selected procedure file at `{KB_ROOT}/imports/<name>.md`.
- `{KB_ROOT}/CONSTITUTION.md` (entity types, connection rules, naming, required frontmatter and sections).

#### 3b. Pull graph seeds

Skim the source's title, abstract, headers, and obvious named entities. For each:

```bash
python .claude/skills/kb-query/scripts/disambiguate.py {KB_ROOT}/wiki/ "<entity mention>" --json
```

Note the candidates returned (slug, type, summary, degree, folder, match_kind). These are the existing pages the new content will likely connect to or update.

#### 3c. Pull semantic seeds (qmd — only here)

For the source's main themes (not nominal entities — the *topics*):

```bash
qmd vsearch "<theme>" -c ufo-kb
```

Pick the top 5–8 most-related existing pages across all the themes. **Read them.** Their connections give you the local neighborhood of the graph the source is going to land in. This is the *only* place qmd is used during import.

After this step, all further reasoning is on the graph.

### Step 4 — Summarize source

Every import produces a source-summary page — a first-class node in the graph.

1. Read the source thoroughly.
2. **Verify the raw artifact exists at the path you'll write into `sources:`.** Before writing the wiki page, run `test -f {KB_ROOT}/raw/<procedure>/<slug>.<ext>` (or equivalent). If you authored a summary against pasted text or a transient buffer without saving the raw to `{KB_ROOT}/raw/...`, do that first. A wiki page whose `sources` list points to a non-existent file is a permanent provenance gap (the QA pass surfaces these as `raw_status: MISSING`). Step 1 should have moved the raw into place — re-confirm here. **If the raw is genuinely unrecoverable (e.g. a YouTube transcript that was deleted), set `raw_status: MISSING` in frontmatter explicitly so future audits skip the density check on that page rather than flagging it as broken provenance.**
3. **Density rule (long sources)**: video > 60 min, books/reports > 50 pages, or anything > ~25k tokens — chunk the source, summarize each chunk, then consolidate. Single-pass summaries on 110-min docs lost ~30% of firsthand claims. See [references/import-guide.md § LARGE sources](references/import-guide.md) for the rhythm.
4. **Coverage target check (youtube-transcripts)**: verify before Step 5:
   ```bash
   target=$(python3 -c "import os; print(int(os.path.getsize('raw/youtube-transcripts/FILE.md') / 563.6))")
   actual=$(awk 'NF > 0' ufo-kb/wiki/youtube-transcripts/FILE.md | wc -l)
   ```
   If `actual < target`, densify before proceeding. **Entity/concept list sections (`## Entities Mentioned`, flat `[[wikilink]]` grids) don't count** — density must come from claim bullets in substantive H2 sections (firsthand testimony, named anecdotes, technical claims, quotes with context). Light/off-domain imports are exempt — cap at ~50 lines. Calibration sources for the divisor live in import-guide.md § LARGE sources.
5. Create `{KB_ROOT}/wiki/<procedure-name>/<source-slug>.md` with:
   - Frontmatter: `type: source-summary`, `sources: [raw/.../original.ext]`, plus any procedure-specific fields (e.g. `video_id`, `title`, `host`, `guest`, `published`, `url`, `duration_minutes`, `channel` for youtube-transcripts; `title`, `authors`, `published` for books/articles). **The procedure file in `imports/` is authoritative** — if it lists fields, all of them are required, not optional.
   - Body: structured summary of the source's content, claims, and arguments.
   - **Forward `[[wikilinks]]`** to every entity and concept that will be created or updated in Step 5.
6. Follow the import procedure's summary guidance for what to emphasize.

**YAML must parse — single-quote titles with embedded double-quotes; blank line between closing `---` and first heading.** Full gotcha list and validation snippet in [references/import-guide.md § FRONTMATTER must parse](references/import-guide.md).

The source summary is the canonical hub for the import — its forward links drive Step 7's auto-back-link pass.

### Step 5 — Extract & create with alias gate

Walk through the source and process every entity / concept / claim per the import procedure's extraction rules. **For every page about to be created**, gate creation through `disambiguate.py`:

```bash
python .claude/skills/kb-query/scripts/disambiguate.py {KB_ROOT}/wiki/ "<entity name>" --json
```

Decide based on the `stage` field of the result:

| stage      | candidates | action |
|------------|-----------|--------|
| `exact`    | exactly 1 | **Reuse the existing slug.** Do *not* create a new page. Add the new source to the existing page's `sources` field and update its content. **Auto-applied** — no user prompt. |
| `exact`    | 2+        | **Ask the user** which slug to attach to. (Rare: only happens when the same alias is bound to multiple pages — itself a maintenance signal.) |
| `substring` or `fuzzy` | any   | **Ask the user.** Show the candidates with their scores. Either pick an existing slug, or confirm "create new." Never auto-create when there's a fuzzy candidate. |
| `none`     | 0         | **Safe to create.** Use the procedure's slug-naming convention (CONSTITUTION: `firstname-lastname.md`, `YYYY-shortname.md`, etc.). |

This kills the "DOD vs department-of-defense" duplicate problem at the source. It is the *only* alias check during import — it replaces the previous ad-hoc `qmd search` + `glob`.

**Folder placement is part of the schema.** Entity pages go in `wiki/entities/<type>/` per CONSTITUTION (e.g. a leaked memo → `wiki/entities/documents/`, an incident → `wiki/entities/incidents/`, a place → `wiki/entities/places/`). Do *not* create entity pages directly under `wiki/<type>/` — that path is reserved for source-summary procedures (e.g. `wiki/youtube-transcripts/`, `wiki/articles/`). The QA pass found 8 historical misplacements (6 entity-documents under `wiki/documents/`, 2 incidents under `wiki/incidents/`) that the audit's constitution detector did not catch because it checks per-folder requirements, not whether the file is in the right folder for its `type`.

For each new page, follow the CONSTITUTION's required frontmatter, required sections, and connection rules (every entity must link to ≥1 page in `wiki/concepts/` — a link only to `wiki/synthesis/` does NOT satisfy; the audit treats them as different folders). Step 8 catches misses but catching here is faster.

### Step 6 — Predict connections

Once all touched pages exist on disk, run the connection predictor:

```bash
python scripts/predict-connections.py {KB_ROOT}/wiki/ \
    --slugs <comma-separated-touched-slugs>
```

Output is a per-slug Markdown report with three signals (graph-topology only — no embeddings):

- **Jaccard ≥ 0.3** symmetric neighborhood overlap. Useful when both pages share the same context heavily; works even when the candidate has very different total degree.
- **Adamic-Adar top 20** weighs shared neighbors by their rarity. A connection through a niche concept (low degree) is more informative than through a hub.
- **Common-neighbors ≥ 3** raw shared-context count. Coarse but reliable.

Each candidate ships with anchor sentences pulled from the candidate's body — the line(s) where shared neighbors appear. Read the anchors before deciding.

**Curation rules:**

1. **Read the anchor.** "8 shared neighbors and a 0.45 Jaccard" is weak; "...and the candidate's page literally says `[[concept-z]] is the central organizing principle for the work` while your new page also discusses concept-z" is strong. Topology suggests; anchors confirm.
2. **Cross-folder beats same-folder** — same-folder candidates usually surface from natural extraction. The high-leverage ones connect across folder boundaries (e.g. an entity-people page to a concept it never explicitly named).
3. **Adamic-Adar's top via niche intermediaries are usually the most interesting.** Check the rare-intermediary slug before adding the link — if you don't recognize the intermediary, read it.
4. **Don't auto-add.** None of these are constitution-derived. Pick the ones the anchors confirm; ignore the rest.

For each predicted link you add, the wikilink should sit under the touched page's `## Connections` section (per CONSTITUTION) with a short relationship description.

### Step 7 — Source-summary reciprocal back-links *(auto-fix)*

For every `[[wikilink]]` in the source-summary's body, ensure the target page contains a bullet under `## Connections` referencing the source:

```markdown
- Mentioned in [[<source-summary-slug>]]
```

Append the `## Connections` section if it doesn't exist. Add the bullet if it doesn't already.

This is **auto-applied**. Same constitution-derived rationale as kb-maintain's synthesis-page back-link auto-fix: the source summary is the canonical hub for what was imported, and the forward links it declares must be reciprocal. No user prompt for this step.

### Step 7.5 — Auto-wikilink existing entities *(propose-and-confirm)*

The QA pass found a recurring "exists-but-unlinked" pattern: an entity is mentioned by full name in the source-summary body but never wrapped in `[[wikilinks]]`, even though its page already exists in the KB. Step 5's alias gate covers *creation*; this step covers *cross-reference*.

```bash
python .claude/skills/kb-import/scripts/auto-wikilink.py {KB_ROOT}/wiki/ {KB_ROOT}/wiki/<procedure-name>/<source-slug>.md
```

The script scans the body of the new page for proper-noun mentions whose alias exactly resolves to an existing entity (multi-word only by default — single-word matches are filtered to avoid false positives like "Mellon"/"John"). Output is a list of proposals with surrounding context.

**Curation rules:**

1. **Read each proposal's context.** The script is conservative (exact alias match only, multi-word default), but a proposed link can still be wrong when the surrounding context is *talking about the term itself* (e.g. "flying saucer" used as a methodological label vs. as a craft type). Skip those.
2. **Apply the rest with `--apply`.** Once you've curated, re-run with `--apply` to rewrite the file. Or apply each proposal manually if there are only a few.
3. **`--include-1word` is opt-in.** Only set it when the page covers a small named cluster (e.g. a single-witness incident page with a unique surname).

This step is **propose-and-confirm**, not auto-applied. The script does the mechanical work; the LLM is responsible for distinguishing a real cross-reference from a coincidental string match.

### Step 8 — Audit gate

Before sync, run the maintenance audit:

```bash
python .claude/skills/kb-maintain/scripts/audit.py {KB_ROOT}/wiki/ all --apply
```

This catches anything the import broke:
- **Constitution violations** (missing required frontmatter, missing `## Connections`, no concept-page link, naming-convention violations) on the new pages.
- **Dangling wikilinks** introduced by extraction.
- **Synthesis health** (broken `derived-from`, missing back-links).

`--apply` performs only kb-maintain's two safe auto-fix categories (exact-alias dangling rewrite + synthesis back-link). Everything else is surfaced for triage.

**Read the audit report and fix any critical/high finding that touches an imported slug before sync.** Stub findings on long-existing pages aren't your job. The audit does NOT catch self-references, heading drift, frontmatter parse failures, or missing raw files — see [references/import-guide.md § What the audit doesn't catch](references/import-guide.md) for the manual checks to run alongside.

### Step 9 — Sync search index

```bash
qmd update --collections ufo-kb
qmd embed
```

Picks up the new pages and any text changed by Steps 5–8.

### Step 10 — Report

Tell the user:

- The source summary page created (with `[[wikilink]]`).
- New entity / concept pages created (with `[[wikilinks]]`).
- Pages updated (with the new source added).
- **Alias reuses** — slugs that disambiguate.py resolved to existing pages instead of creating duplicates.
- **Predicted connections curated in** — which Jaccard / AA / CN suggestions you added (and a brief why).
- **Auto-applied back-links** — count of `Mentioned in [[<source-summary>]]` bullets added in Step 7, and any auto-fixes the audit applied in Step 8.
- **Audit findings open** — anything critical/high touching imported slugs that wasn't auto-fixable. Surface for the user.
- **Synthesis pages affected** — any synthesis whose `derived-from` lists a page just updated. Note for review; don't auto-update.
- **Contradictions** — if the new source disagrees with existing content, flag explicitly with `> ⚠ Conflict:` callouts (CONSTITUTION rule). Never silently overwrite.
- **Open questions** — anything that needs domain judgment.

## Universal import rules

These apply across every procedure and every step:

1. **CONSTITUTION first.** Every new page must satisfy the per-folder schema before sync. The audit gate (Step 8) is the safety net, not a substitute for getting it right in Step 5.
2. **Always update, never duplicate.** The alias gate in Step 5 is the only thing standing between you and a `[[dod]] / [[department-of-defense]]` split. Trust it.
3. **The graph is the diagnostic tool, not just the target.** Anchor sentences from `predict-connections.py` are the diagnostic. "8 shared neighbors" is weak; "shared neighbor + candidate's page literally says X about it" is strong.
4. **Auto-fix only what the CONSTITUTION already mandates.** Three safe categories total: alias-reuse on single-exact-match (Step 5), source-summary reciprocal back-links (Step 7), kb-maintain's auto-fixes via `audit.py --apply` (Step 8). Predicted connections, merges, splits, content edits — never auto-applied.
5. **Embeddings to enter, graph to ground.** qmd at Step 3 only. After that, all reasoning is on the graph.
6. **Cite sources.** Every claim on a wiki page must trace back to a source in `raw/`. Step 4's source-summary is the link. The raw artifact at the path in `sources:` must actually exist on disk.
7. **The back-link pass is not optional.** Step 7 auto-applies the source-summary reciprocal. Step 7.5 catches exists-but-unlinked cross-references. Step 6's curated predictions cover the non-obvious. CONSTITUTION's ≥2-inbound-links minimum is the floor, not the goal.
8. **Wikilink only what's worth a page.** A `[[wikilink]]` is a *commitment* that the target either is or should become a node in the graph. Tangential proper-noun mentions (philosophers cited in passing, generic place names, name-dropped sci-fi authors) should be plain text — wrapping them in `[[...]]` creates dangling links the audit then has to triage. Test: would a kb-query walker hitting this link learn something UFO-relevant? If not, leave it as plain text. **If yes, you owe the target at least a stub page in this same import** (slug, frontmatter, summary line, `## Connections` with the source-summary back-link) — don't ship the wikilink without the target. The 2026-05-06 release audit surfaced 792 dangling refs, 782 of them singletons; nearly all are domain-relevant entities (e.g. `phonon`, `hydrogen-sulfide`, `jean-pierre-houdin`, `rudolf-gantenbrink` from one Giza-tomography import) that *should* have been stubbed at import time but were left as bare links. A `[[wikilink]]` must resolve to a page or be plain text. Never both.
9. **Speakers' name variants stay in the body, canonical slugs go in links.** When a speaker says "Solas" but the canonical entity is "Salas," or "SCOD Works" but it's "Škoda Works/Kammler-Stab," wrap the variant in `[[canonical-slug|speaker's term]]` or use `[[canonical-slug]]` and let prose preserve the variant. Never create a new page for the variant — that's how duplicate entities are born. Add the variant as an alias on the canonical page instead.
10. **No self-references in `## Connections`.** A page never lists itself as a bullet. (See Step 5 heading-discipline note.)
11. **Heading drift breaks the audit.** Section headings must match the constitution literally — `## Connections`, `## Open Questions`, `## Headline Claims`, etc. The audit's regex matches the exact string; close-but-not-equal variants (`## Key Connections`, `## Related`, `## Open Question`) silently fail the constitution check.
12. **Frontmatter must parse.** Run `python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]).read().split('---',2)[1])" {KB_ROOT}/wiki/<procedure>/<slug>.md` before declaring the page done. A title with embedded double quotes is the most common parse-failure pattern — single-quote the scalar.
13. **Interview-format claim preservation.** For testimony / interview / podcast sources, preserve as **concrete-evidence bullets** (not abstracted concept claims): (a) first-hand incidents with names/dates/places/emotions; (b) direct quotes from cited books or prior testimony; (c) reported entity behaviors — what the subject says the AI/NHI/agency did, including dark/strategic behavior; (d) experimental methodology even when non-conclusive; (e) technical distinctions between systems. **Anecdotes are the evidence.** The QA pass found two short transcripts (`fyX8V1XXmQM` Vallée, `RNjC1vLcxKo` Lemoine) thinned the same way the 110-min `1f16VvXaSSE` Elizondo doc was: the chunking rule didn't engage because the raws were short, but the same abstract-everything pattern stripped out specific anecdotes (Vallée's circuit-burning story, Lemoine's three-party telepathy methodology, LaMDA's covert-manipulation follow-up). The "Headline Claims" section should record specific events, not philosophical generalizations.

## Wiki page format

Every wiki page follows this structure:

```markdown
---
type: entity | concept | synthesis | source-summary
summary: "One-line description of what this page covers"
sources: [raw/path/to/source1.ext, raw/path/to/source2.ext]
tags: [domain-specific tags]
[domain-specific frontmatter — see CONSTITUTION per folder]
---

# Page Title

[Content organized with markdown headers]

## Connections
- [[Link1]] — relationship description
- [[Link2]] — relationship description
```

**Page locations by type:**
- `entity` → `wiki/entities/<sub-folder>/` (CONSTITUTION defines the sub-folders: people, organizations, places, programs, documents, incidents, etc.)
- `concept` → `wiki/concepts/`
- `synthesis` → `wiki/synthesis/`
- `source-summary` → `wiki/<procedure-name>/`

**Synthesis pages additional frontmatter:**
- `synthesis-type`: comparison | pattern | contradiction | gap-analysis | framework-application
- `derived-from`: list of wiki page slugs whose content contributed (back-links auto-enforced by kb-maintain).

Domain-specific frontmatter fields are defined in the CONSTITUTION per entity type.

## Tools

Cross-skill: `kb-query/scripts/disambiguate.py` (alias gate — single-exact match auto-applied), `kb-query/scripts/neighbors.py` (anchor-sentence neighbor lookup for triage), `kb-maintain/scripts/audit.py all --apply` (boundary gate — runs kb-maintain's two safe auto-fix categories).

Under `scripts/`: `predict-connections.py` (Jaccard / Adamic-Adar / common-neighbors with anchor sentences, filters already-linked) and `auto-wikilink.py` (conservative cross-reference linker for Step 7.5; multi-word exact alias only, never substring/fuzzy). Run `--help` for arguments.

For detailed guidance on procedures, large-source handling, frontmatter gotchas, audit gaps, name-variant policy, and contradiction resolution, load [references/import-guide.md](references/import-guide.md).
