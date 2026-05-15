# Import Guide — Detailed Reference

Companion to [SKILL.md](../SKILL.md). The skill describes the *flow*; this file describes the *judgment* — when to deviate, how to handle edge cases, and the deeper reasoning behind each step.

## How import procedures work

An import procedure is a prompt template saved as markdown in `{KB_ROOT}/imports/`. It tells the LLM exactly how to process a specific source type.

Each procedure has:
- **YAML frontmatter**: `name`, `trigger`, `source_destination`.
- **Extraction Steps**: what to look for in the source.
- **Wiki Updates**: what pages to create or update.
- **Cross-Linking Rules**: how new content connects to existing pages.
- **Quality Check**: validation rules to apply post-import.

## Phase reference

### Phase A — Seed-pull (Step 3)

The skill's hardest "soft" judgment is here, before extraction begins. Two seed sources, used in sequence:

1. **Nominal seeds via `disambiguate.py`** — for every named entity / org / place / program in the source's title, abstract, headers, and obvious mentions. Reads cheap (no body parsing). Returns ranked candidates with type, summary, degree, folder. Tells you *what already exists that the source will hit*.

2. **Semantic seeds via `qmd vsearch`** — for the source's main *themes* (topics, not entities). Top 5–8 hits per theme, then read those pages. Tells you *the local neighborhood the source is going to land in*.

Together: nominal seeds prevent duplicate creation; semantic seeds prevent the source from being extracted as if it landed in vacuum.

**Why qmd is forbidden after this point.** kb-query's "embeddings to enter, graph to ground" rule applies here too. Once you have a foothold on the graph, every further decision is graph-grounded — alias matches, neighborhood overlap, anchor sentences. Embeddings can find a *related* page; the graph tells you *how* it's related.

### Phase B — Extraction with the alias gate (Step 5)

The alias gate is the only thing standing between the import skill and a duplicate problem. Be strict about it.

**Reading `disambiguate.py` output:**

```json
{
  "query": "DOD",
  "stage": "exact",
  "candidates": [
    {"slug": "department-of-defense", "title": "department-of-defense", "match_kind": "exact-alias", "match_score": 1.0, "degree": 10, "folder": "entities/organizations"}
  ]
}
```

- **`stage = "exact"`** + **exactly one candidate** → reuse, auto-applied. The alias `dod` is bound to `department-of-defense`. Use that slug.
- **`stage = "exact"`** + multiple candidates → ambiguous alias collision. Ask the user. Independently a maintenance signal — kb-maintain's `duplicates` detector should already be flagging this; if it isn't, that's worth noting.
- **`stage = "substring"` or `"fuzzy"`** → never auto-create. The classic trap is "mit" fuzzy-matching "smith" — disambiguate's substring scoring guards against that, but fuzzy candidates with high scores (e.g. typos: `grsuch` → `david-grusch`) still need user confirmation. Show the candidates with their scores and ask: pick existing, or confirm "create new."
- **`stage = "none"`** → safe to create. Use the procedure's slug-naming convention.

**When you create a new page**, satisfy the CONSTITUTION's per-folder schema *during creation*, not as cleanup:

- Required frontmatter fields populated.
- Required sections present (`## Connections` is universal; specific entity types have more).
- ≥1 link to a concept page (CONSTITUTION rule for entities).
- Naming convention matches (`firstname-lastname.md`, `YYYY-shortname.md`, etc.).

Step 8's audit will catch what you miss — but each missed item is a triage cost the LLM pays later.

### Phase C — Predicted connections (Step 6)

The new `predict-connections.py` is the engine for non-obvious links. Three signals, all graph-topology only:

| Signal | What it surfaces | Default threshold | Best for |
|--------|------------------|-------------------|----------|
| Jaccard | High symmetric overlap regardless of degree | ≥ 0.3 | Same-context pages that for some reason don't link (rare, high-confidence) |
| Adamic-Adar | Connections through niche intermediaries | top 20 | Cross-folder links that depend on rare concepts (most interesting) |
| Common-neighbors | Raw shared count | ≥ 3 | Coarse, high-recall fallback |

**Reading the output:**

```markdown
- **0.456** [[candidate-b]] (entities/people, deg 24) — 8 shared / 18 union
  - shared via: [[concept-z]], [[program-y]], [[place-x]]
  - on candidate's page (re [[concept-z]]): "...[[concept-z]] is the central organizing principle..."
```

The score is the trigger; the anchor sentence is the diagnostic. Pattern:

1. **Score** says "topology agrees." Read the score; ignore if below your gate.
2. **Shared neighbors** says "via what." If you don't recognize them, pause — you may be in unfamiliar territory and should read the candidate.
3. **Anchor sentence** says "concretely, the candidate frames the shared concept this way." Read this. If the framing aligns with what you wrote on the new page, the link is real. If the framing is from a totally different angle, the topology lied.

**Curation rules in detail:**

- **Add only what the anchor confirms.** Never add a link because "Jaccard says so." Topology is a search heuristic, not evidence.
- **Cross-folder beats same-folder.** Extraction itself usually catches obvious same-folder connections (entity↔entity in the same source). The predictor's high leverage is on cross-folder: entity → concept never explicitly named, place → person mentioned only via shared infrastructure, etc.
- **Adamic-Adar via low-degree intermediaries is the highest signal.** A connection through a degree-3 niche concept is far more informative than through a degree-100 hub. Pay attention to the per-intermediary degree shown in the output.
- **Stop at ~5 added links per page.** If the predictor surfaces 30 candidates and they all look real, the new page may be too broad — consider whether it should be split, or whether you're being lured into adding low-quality links because the topology *looks* impressive.

### Phase D — Auto-fix (Step 7)

Only one auto-fix at the import-orchestrator layer: source-summary reciprocal back-links.

**Why this is safe to auto-apply:**

The source summary's body forward-links every entity / concept it created or updated. Those forward links are a constitution-derived obligation — the source is the canonical record of what was imported. The reciprocal (`Mentioned in [[<source-summary>]]` on the target) is the same obligation viewed from the other side. Same rationale kb-maintain uses to auto-apply `Synthesized in [[<synthesis>]]` for synthesis pages.

**What this is NOT:**

- Not a "predicted-link" auto-apply. The predictor (Step 6) never auto-applies — those are suggestions.
- Not a "merge candidate" auto-apply. The alias gate (Step 5) is single-exact-match only; multi-candidate situations always ask.
- Not a "content patch." Auto-fix is bullet-additions to the `## Connections` section, never edits to anything the LLM wrote.

### Phase E — Audit gate (Step 8)

Running `audit.py all --apply` against the *full graph* (not scoped to touched slugs) is intentional:

- **Touched slugs may have broken something elsewhere.** A new entity page introducing `[[unknown-org]]` is a dangling link; the audit catches it.
- **Pre-existing critical findings shouldn't be ignored at the import boundary.** If there's already a constitution violation on a page you just updated, fix it.
- **Auto-fixes flow.** kb-maintain's `--apply` performs synthesis back-links and exact-alias dangling rewrites — both of which the import may have introduced opportunities for.

But: **don't drown in the report.** Filter to findings that touch the imported slug set or are critical-severity. Leave long-standing stub findings on unrelated pages for a kb-maintain run.

## Common patterns

### A NEW source type has no matching procedure

Two options:

1. **One-off import** using CONSTITUTION's general extraction rules. Good for rare sources.
2. **Define a new procedure** via kb-evolve. Better when the source type will recur.

The skill should ask the user; don't decide on their behalf.

### LARGE sources (books, long reports, long video transcripts)

The QA pass found that long-documentary YouTube imports (~2-hour episodes) systematically lost firsthand-claim density when summarized in a single pass. The 110-minute Elizondo documentary (`1f16VvXaSSE`) was missing the entire Cuban-exile/Bay-of-Pigs/Alpha-66 backstory, the VA implant story, the astral-projection-of-terrorist claim, and ~7 entities that already had pages but were never linked. The 45-minute Michaels solo essay (`5udx_SDdL3Y`) was nearly fully captured. The pattern correlates with raw input length, not topic complexity.

**Mechanical chunking, not "read more carefully":**

- **Video transcripts > 60 minutes**: identify natural section breaks (sponsor read transitions, topic pivots, "let's now talk about X"). Process each section as its own pass: extract entities, claims, quotes; only after all sections are processed do you write the consolidated source-summary.
- **Books / long reports > 50 pages**: process by chapter. The source-summary covers the full source but is built from per-chapter extraction notes, not a single read.
- **Anything else > ~25k tokens of source text**: chunk to keep each pass within a clear cognitive frame.

**Per-section discipline:**

- After each chunk, re-run `disambiguate.py` on any newly-mentioned entities — long sources tend to introduce people in chunk 1 and re-mention them in chunk 5 with different phrasing ("Lou's father" → "Lou Sr." → "Luis Elizondo Senior" → "his father"). The alias gate's value compounds across chunks.
- Run `predict-connections.py` after the full extraction (not after each chunk) — early-section predictions get noisy without late-section context.
- The source-summary's "Headline Claims" section should have one bullet per major claim *per chunk*, not one bullet per claim total. A 110-minute documentary that produces a 7-bullet headline list is under-summarizing.

**The density check:**

Two complementary checks — run both:

**1. Quantitative (pass/fail — youtube-transcripts procedure):**

```bash
target=$(python3 -c "import os; print(int(os.path.getsize('transcripts/FILE.md') / 563.6))")
actual=$(awk 'NF > 0' ufo-kb/wiki/youtube-transcripts/FILE.md | wc -l)
echo "actual=$actual target=$target"
```

If `actual < target`, the file is not done. The `/563.6` divisor is calibrated from three reference files that are known to be fully captured:

| File | Raw bytes | Non-empty lines | Ratio |
|---|---|---|---|
| `CiQTBOQ1dTg` | 280,337 | 499 | 563.9 b/line |
| `09KP8XVf5nY` | 161,040 | 285 | 565.1 b/line |
| `nTiFs8LudUo` | 155,499 | 283 | 549.5 b/line |

Light/partial imports (source pre-filtered as mostly off-domain) are exempt — cap those at ~50 lines regardless of raw size.

**Critical**: entity/concept wikilink list sections (`## Entities Mentioned`, flat `[[wikilink]]` grids) do **not** count toward meaningful density. They contribute to the non-empty line count but their presence is not a proxy for captured content. Density must come from claim bullets in substantive H2 content sections: firsthand testimony, named anecdotes, technical claims, specific incidents, direct quotes with context. A file can pass the entity-count smell-check while failing the formula if entities are listed but not explained.

**2. Qualitative smell-check (supplement, not substitute):**

Before declaring done, also eyeball the entity count against runtime:
- Video: ~1 named entity / minute (rough). A 90-minute interview yielding 30 entities is light; 60 is normal; 100+ is dense.
- Books: ~3 named entities / chapter (narrative); ~10 / chapter (reference).

Numbers well below the rough range are a smell even if the line count passes — it may mean the lines are padding (section headers, blank-ish bullets) rather than content. Use judgment.

### THIN DOCUMENTS (< 100 source lines)

AARO range fouler debriefs, short mission reports, and single-page administrative docs
are heavily redacted forms where most lines are table structure or boilerplate. A single-
pass extraction yielding 8–12 lines is correct — do not pad with inferred content.

**Floor rule:** target = max(8, source_lines / 80) summary lines. A 63-line range fouler
debrief floors at 8 lines; a 2,700-line COMETA report targets ≥ 34 lines.

**What to extract from thin docs:**
- All factual metadata: agency, date, time (DTG), location (named area or lat/long),
  sensor type (FMV, radar, visual, IR), platform callsign prefix (even if redacted)
- The UAP observation text verbatim — usually in a "Gentext/Observation", "Mission
  Narrative", or numbered item section. Prioritize this even when the rest is redacted.
- Shape/size/speed/behavior descriptors (check-box fields on range fouler forms: round /
  balloon-shaped / moving, metallic / translucent, apparent propulsion, etc.)
- Resolution: "possible missile," "possible bird," "unknown," or blank (blank = unresolved)
- Classification + release authority (declassification date or MDR number)

**What to skip in thin docs:**
- ACEQUIP form fields (radar software load, RWR designator, ECM name) — no KB value
- Repeated classification headers (`SECRET//REL TO USA, FVEY`) throughout the form
- Admin POC fields: redacted names `(b)(6)`, phone numbers, email fields
- Form instruction text ("Please complete this form to the best of your ability…")
- OCR artifacts and multilingual watermark noise

**Stub incident entities from thin docs:**
Even if a mission report yields only 3 readable facts (date, location, object count),
create an incident stub: `wiki/entities/incidents/YYYY-<theater>-aaro-<docid>.md`.
That stub becomes a graph node future imports can link to when more context emerges.

### GOV-RELEASE batch sequencing

The 2026 gov-release batch (69 files, staged in `raw/documents/`) should be processed
in 4 tiers to maximize early graph density. Tier 1 files anchor the graph with hundreds
of new entities; when Tier 2–4 files reference the same places, people, and incidents,
`disambiguate.py` resolves them to existing slugs rather than creating duplicates.

**Tier 1 — Landmark documents (7 files, dedicated sessions each)**

Files > 2,000 source lines; use the chunking rule from the LARGE sources section above.
Process one file per import session:

1. `fbi-62-hq-83894-ufo-investigations-1947-1968.md` (66K lines) — chunk by Section N
   dividers (`<!-- END OF SECTION N -->`). Produce a per-section source-summary plus a
   master summary aggregating all 9 sections.
2. `usaf-blue-book-era-incident-summaries-box-7.md` (11.8K lines) — chunk by incident
   ranges (1–80, 81–160, 161–233); one consolidated source-summary.
3. `usaaf-1949-flying-discs-box186-incident-reports.md` (3.7K lines) — two passes.
4. `dow-uap-d48-modeling-space-booster-failures-1996-09.md` (3.7K lines) — chunk by section.
5. `dow-uap-d49-vandenberg-launch-summary-1958-2000.md` (3K lines) — two passes.
6. `cometa-ufos-and-defense-what-should-we-prepare-for.md` (2.7K lines) — chunk by Part
   (Part 1: cases/testimonies, Part 2: scientific org, Part 3: hypotheses).
7. `dow-general-flying-disc-files-1946-1948.md` (2.2K lines) — single pass or two passes.

**Tier 2 — Substantial documents (~15 files, 2–3 per session)**

Files 200–2,000 source lines; single-pass extraction. Group thematically related files in
one session (e.g. all NASA files together, all DoS cables together):

- Historical FBI: `fbi-germany-1957-krasuski-circular-vertical-object.md`,
  `fbi-detroit-1958-circular-object-crystal-dome.md`,
  `fbi-september-2023-uap-sighting-us-transport-facility.md`,
  `fbi-western-us-late-2025-uap-investigation.md`
- Historical military: `dow-1945-03-shaef-foo-fighters-german-armament.md`,
  `usaf-1948-11-netherlands-flying-saucers-intel-report.md`,
  `usaf-1955-10-azerbaijan-unconventional-aircraft.md`
- NASA: `nasa-uap-d1` through `nasa-uap-d7`
- DoS cables: `dos-uap-d1` through `dos-uap-d5`,
  `dos-1952-07-18-increased-ufo-reports-memo.md`,
  `dos-1963-07-18-executive-office-nasc-memo.md`
- Larger AARO mission reports: `dow-uap-d74`, `dow-uap-d23`, `dow-uap-d32`,
  `dow-uap-d19`, `dow-uap-d65`, `dow-uap-d75`, `dow-uap-d25`, `dow-uap-d14`
- Other: `western-us-event-slides-2023-incident-released-2026-05-08.md`

**Tier 3 — Standard AARO forms (~10 files, 5–8 per session)**

Files 100–400 source lines; moderate redaction. Each gets its own source-summary + one
incident stub entity. Batch 5–8 files per session with a shared seed-pull on AARO/CENTCOM themes.

**Tier 4 — Thin forms (~20 files, 10–15 per session)**

Files < 100 source lines; apply thin-document floor rule above. Batch:
- All `dow-uap-d*-range-fouler-*` files
- `dow-uap-d4` through `dow-uap-d8`, `dow-uap-d54`
- `dow-uap-d50-email-correspondence-indopacom-2025-04.md`
- `dow-uap-d52-email-correspondence-na-2024-10-31.md`
- `dow-uap-pr20-unresolved-uap-report-kuwait-2022-05.md`

### OFF-TOPIC sources

Not every source the user hands in deserves a full import. The CONSTITUTION's domain section excludes pure off-topic content; an off-topic-skipped registry at `{KB_ROOT}/imports/off-topic-skipped.md` makes those decisions persistent.

**When to skip:**

- The source doesn't engage with UFOs/UAPs/NHI/disclosure-politics/anti-gravity/consciousness-with-UAP-framing/abduction-or-experiencer phenomena/intelligence-suppression-of-any-of-the-above.
- The source is from a known UAP-adjacent channel/author but covers an unrelated topic (e.g. an American Alchemy episode on philosophy or fertility decline).

**When NOT to skip:**

- The source seems off-topic but contains a UAP-relevant claim. Import lightly: a stub source-summary capturing just that claim is better than nothing.
- The source is by a major UAP figure on any topic — at minimum, link it from their entity page so future researchers can see the broader output.

**The skip mechanic:**

- Append a row to `{KB_ROOT}/imports/off-topic-skipped.md` with the source ID, title, channel/author, and one-line reason.
- Don't create a wiki page.
- Don't move the raw artifact (it can stay in `raw/` as evidence the decision was considered).

**Re-evaluation:**

A skip is reversible by removing the registry entry. Before re-importing, the user should explicitly want the off-topic content captured — the registry is the audit trail that the skip was deliberate.

### TRANSCRIPTION ARTIFACTS / NAME VARIANTS

Speakers don't pronounce names canonically. Transcripts compound the problem with auto-generated subtitles. The QA pass found:

- "Solas" (transcript) for `robert-salas` (canonical witness)
- "SCOD Works" (transcript, single source) for `Škoda Works` / `kammler-stab` (canonical facility from multi-source corroboration)
- "andre-puharich" was created as a duplicate of `andrija-puharich` because one transcript used the French form

**Rules:**

1. **Never create a page for the variant.** If the transcript says "Solas" but disambiguate.py finds `robert-salas` as a fuzzy match (Levenshtein 1), pause and ask: is this the same person? In ~95% of cases, yes.
2. **Add the variant as an alias on the canonical page** (`aliases:` frontmatter list).
3. **In prose, preserve the speaker's term** but link to the canonical slug: `[[robert-salas|Solas]]` or just `[[robert-salas]]` with a parenthetical "(also rendered 'Solas' in some transcripts)" if the variant matters for searchability.
4. **One-source-only entities are suspect.** If `kammler-stab` exists from 3 sources and `scod-works` would be created from 1, and they're geographically and command-structure consistent, fold into the well-attested entity. The QA pass surfaced this exact case; fixing it required merging scod-works into kammler-stab + rewriting 18 wikilinks.

The audit's `duplicates` detector catches some of these post-hoc via alias-collision + neighborhood-overlap, but catching them at import time is much cheaper than rewriting links across the graph later.

### FRONTMATTER must parse — YAML scalar gotchas

The audit's graph-builder silently skips a page whose YAML frontmatter is unparseable, so a parse-broken page is *invisible* to constitution / dangling / synthesis checks. Run `python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]).read().split('---',2)[1])" {KB_ROOT}/wiki/<procedure>/<slug>.md` before declaring a page done.

The QA pass found these recurring failure patterns:

- **Title with embedded double quotes** is the #1 break (`title: "NASA Doctor: "I Saw This UFO!""`). Single-quote the scalar instead: `title: 'NASA Doctor: "I Saw This UFO!"'`.
- **Multi-line summaries** that contain a colon, double quote, or `[`/`]` parse the colon as a map separator. Wrap in single quotes.
- **Tags as a YAML block list** (lines starting with `-`) confuse some readers — keep tags inline: `tags: [foo, bar]`.
- **Closing `---` glued to the last field** breaks block parsing. Always have a blank line between the closing `---` and the body's first heading; bulk-edit scripts can otherwise paste them together.

### What the audit doesn't catch (and your QA pass must)

`audit.py all --apply` catches structural breakage on the *graph* — constitution violations, dangling wikilinks, synthesis health. It does *not* catch:

- **Self-references in `## Connections`** (a page bulleting itself). Audit doesn't flag self-edges; they add no signal but inflate degree counts.
- **`## Connections` heading drift** (`## Key Connections`, `## Related`, `## See Also`). The constitution check matches `## Connections` literally; near-misses silently fail and the page is treated as missing the section.
- **Frontmatter parse failures on individual pages.** As above — graph-builder skips them silently.
- **`sources:` paths pointing to non-existent raw files.** The audit reads only the wiki tree, not the raw tree.

Until a kb-maintain QA-pass script lands, run these manually after each import batch:

```bash
# Per new page:
python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]).read().split('---',2)[1])" <page>
test -f <each-sources-entry>
grep -n '\[\[<own-slug>\]\]' <page>          # should return nothing
grep -n '## \(Key Connections\|Related\|See Also\)' <page>   # should return nothing
```

### MISSING RAW ARTIFACT

The QA pass found one wiki page (`p0S0BfoZy0w` — Brandenburg/Mars) whose `sources:` list pointed to a raw transcript that didn't exist on disk. The wiki page had been authored from a transient buffer (paste, voice transcription, etc.) and the raw was never saved.

**Rule:** Before writing any wiki page's `sources:` field, verify the file exists at the path. If not:

- Move/save the raw to `{KB_ROOT}/raw/<procedure-name>/<slug>.<ext>` first, then write the wiki page.
- If the raw is irretrievable (transient source already closed), set `sources: []` and add a `raw_status:` frontmatter field documenting the gap. This makes the missing-evidence state visible to future kb-query walkers and to maintenance.

### CONFLICTING information

When new source contradicts existing content:

- **Do NOT silently overwrite.** Add the new perspective alongside the existing one.
- Use the CONSTITUTION's `> ⚠ Conflict:` callout format:
  ```markdown
  > ⚠ Conflict: [[Source A]] claims X, while [[Source B]] claims Y.
  ```
- Where the contradiction is structural (not just two competing claims), consider creating a `synthesis-type: contradiction` synthesis page that documents the conflict and links both sources via `derived-from`.
- **Never** delete or rewrite an existing claim. Add, don't subtract.

### UPDATE sources (new version of something already imported)

- Find the existing source-summary in `wiki/<procedure-name>/`.
- Update its `sources` to include the new file.
- Update its body with the changes.
- Propagate updates to entity / concept pages it derives.
- Re-run `predict-connections.py` on the affected slugs — the update may unlock new links.

### Synthesis pages affected

The skill's Step 10 surfaces synthesis pages whose `derived-from` lists a page just updated. **Do not auto-update synthesis pages during import.** Synthesis is interpretive; the LLM doing the import is in extraction mode, not synthesis mode. Surface for the user / a later kb-query session to reconsider.

## Quality checklist

After every import, before reporting "done":

- [ ] Source summary exists in `wiki/<procedure-name>/` and links the raw file in `sources`.
- [ ] **Raw artifact exists at the path in `sources:`** (verified on disk). If the raw is irretrievable, `sources: []` and `raw_status:` frontmatter is set.
- [ ] **Off-topic gate consulted** — source ID was not pre-skipped in `imports/off-topic-skipped.md`; if topical gate was tripped, source is now in that registry instead of in `wiki/`.
- [ ] **Density check — quantitative**: `actual_lines ≥ raw_bytes / 563.6` (youtube-transcripts; see "LARGE sources" guidance). Run: `awk 'NF > 0' wiki/youtube-transcripts/FILE.md | wc -l`. Entity/concept list sections do not count; density must come from claim-bullet H2 sections.
- [ ] **Density check — qualitative**: entity count roughly proportional to runtime (see "LARGE sources" guidance).
- [ ] All new pages have correct frontmatter (`type`, `created`, `sources`, plus per-folder required fields).
- [ ] All new pages have a `## Connections` section with ≥2 `[[wikilinks]]` (CONSTITUTION minimum).
- [ ] All new entity pages have ≥1 link to a concept page (CONSTITUTION rule).
- [ ] No alias-gate failures left unresolved (if disambiguate returned multi-candidate, the user has decided).
- [ ] **Wikilink restraint applied** — every `[[wikilink]]` is to an entity worth a node in the graph; tangential proper-noun mentions are plain text.
- [ ] **Name-variant rule applied** — speaker variants (Solas/Salas, SCOD/Škoda) point to canonical slugs; no new pages created for variants; aliases added on canonical pages.
- [ ] `predict-connections.py` was run on every touched slug; curated suggestions added.
- [ ] Source-summary reciprocal back-links applied (Step 7 auto-fix).
- [ ] **`auto-wikilink.py` was run** on the source-summary; proposals reviewed and applied (Step 7.5).
- [ ] `audit.py all --apply` ran cleanly; any critical/high finding touching imported slugs is resolved or surfaced.
- [ ] `qmd update --collections <name> && qmd embed` ran successfully.
- [ ] Contradictions (if any) are flagged with `> ⚠ Conflict:` callouts, not silently resolved.
- [ ] Affected synthesis pages noted for user review.

## Anti-patterns

- **Skipping the alias gate "just this one time"** — every duplicate page in the KB started as a "just this one time."
- **Adding all predicted connections** — the predictor surfaces *candidates*, not *truths*. The anchor is the test.
- **Using qmd mid-import** — once you're on the graph, stay on the graph. qmd is for entry, not navigation.
- **Treating the audit gate as decoration** — if the audit flags a critical finding on a page you just created, fix it before sync. The whole point of the boundary check is that it catches what extraction missed.
- **Auto-creating synthesis pages from contradictions found during extraction** — extraction surfaces evidence; synthesis is a separate cognitive mode (kb-query handles).
- **Single-pass summarizing of long documentaries** — see "LARGE sources" guidance. The QA pass found ~30% claim loss for 110-min videos summarized in one pass. Chunk first.
- **Wikilinking every proper noun** — `[[Friedrich Nietzsche]]` in a UFO KB creates a permanent dangling-link debt for an entity that will never have a useful page. Plain text is the right call for tangential mentions.
- **Creating a new page for a transcription artifact** — if "Solas" sounds like an existing entity Salas, ask. The graph cannot afford one duplicate per transcript.
- **Writing `sources: [raw/path.md]` without verifying the file exists** — creates a permanent provenance gap that QA finds and flags as `raw_status: MISSING`.
- **Skipping the topical gate** — importing a sponsor-read or off-domain American Alchemy episode "because it's by the same channel" pollutes the graph with low-signal nodes. Use the off-topic-skipped registry.
