---
name: kb-maintain
description: Health-check and consistency pass for the knowledge base — finds orphans, contradictions, missing links, stale pages, and uses graph analysis algorithms (Jaccard, Adamic-Adar, clustering) to predict missing connections.
---

# kb-maintain — Audit, Auto-fix, Triage

The CONSTITUTION is the spec. Maintenance enforces it.

The audit walks the graph once, compares reality to the rules already in `CONSTITUTION.md` (per-folder frontmatter, required sections, naming, connection rules), surfaces structural problems (orphans, islands, duplicates, dangling links, stub pages, multi-cluster hubs), and produces a single severity-tagged report. Two classes of finding are auto-applied with `--apply`; everything else is flagged for human triage with concrete evidence.

> **Stateless. Single-mode. No staleness.** Every run starts fresh — there is no snapshot file, no maintenance log, no diff-since-last-run. The KB is long-lived; calendar-age signals are not used. Contradiction detection is not in this skill — kb-query handles ad-hoc contradiction queries.

## Prerequisites

Set `{KB_ROOT}` to `ufo-kb`. The qmd collection name is `ufo-kb`. Read `{KB_ROOT}/CONSTITUTION.md` (entity types, connection rules, synthesis structure — the audit enforces these). All paths below are relative to `{KB_ROOT}`.

## Procedure

### 1. Run the audit

```bash
python scripts/audit.py {KB_ROOT}/wiki/ all
```

One graph build, all detectors (`constitution`, `dangling`, `orphans`, `islands`, `duplicates`, `synthesis`, `stubs`, `bridges`, `hubs`). Report is severity-tagged Markdown. For detector specifics and the severity rubric, see [references/maintenance-ops.md § Detector reference](references/maintenance-ops.md). Re-run a single subcommand when zooming in: `audit.py <wiki> duplicates`.

### 2. Run graph analytics (when surfacing *new* connections)

```bash
python scripts/cluster-detection.py {KB_ROOT}/wiki/
python scripts/jaccard-similarity.py {KB_ROOT}/wiki/ --threshold 0.3
python scripts/adamic-adar.py {KB_ROOT}/wiki/ --top 20
python scripts/common-neighbors.py {KB_ROOT}/wiki/ --min-common 2
```

These propose missing edges, not rule violations. Adamic-Adar (rare intermediaries) is the most interesting; Jaccard catches same-context same-folder pairs; common-neighbors is the coarse fallback.

### 3. Triage

Read the audit report top-down (Critical → High → Medium → Low). For each finding decide one of:

- **Auto-fixable** (covered by the `--apply` scope below) → apply it.
- **Propose to user** → present evidence, recommend an action, ask before doing it.
- **Flag-only** → note in the report; no immediate action.

Use kb-query primitives during triage when prose evidence sharpens the call:
- **`.claude/skills/kb-query/scripts/neighbors.py`** for anchor sentences ("page A says X about Z; page B says Y about Z — same person?") when triaging duplicates.
- **`.claude/skills/kb-query/scripts/disambiguate.py`** to manually resolve fuzzy dangling-link candidates the audit didn't auto-fix.

### 4. Act

#### Auto-fix (with `--apply`)

```bash
python scripts/audit.py {KB_ROOT}/wiki/ all --apply
```

`--apply` performs only two classes of edit, both grounded in CONSTITUTION rules:

1. **Reciprocal back-links from `derived-from`.** When a synthesis page S has `derived-from: [A, B, C]` but A's body doesn't link back, the audit appends `- Synthesized in [[S]]` under A's `## Connections` section (creating the section if it doesn't exist). The CONSTITUTION already requires synthesis pages to be linked from every page they derive from — this just enforces.
2. **Single-candidate dangling-link rewrite.** When a wikilink points to a non-existent page AND `disambiguate.py` returns *exactly one exact alias/title match*, the link is rewritten in place. Substring and fuzzy candidates are *never* auto-applied — those are suggestions only, even at high scores. (A `[[david-smith]]` link must not be auto-rewritten to `[[mit]]` because "mit" fuzzy-matches "smith.")

The report shows what was auto-fixed and what was not.

#### Propose-to-user (everything else)

For each non-auto finding, surface concrete evidence (anchor sentences from `neighbors.py` are the diagnostic) and ask before acting. Finding classes:

- **Merge** (from `duplicates`) — show shared aliases + neighborhood overlap.
- **Split** (from `hubs`) — propose H2-decomposition outline; parent stays as overview.
- **New-link** (from Jaccard / Adamic-Adar / common-neighbors) — only candidates passing a semantic-sense check on the anchor sentence.
- **Synthesis health** beyond back-links (e.g., `derived-from` points nowhere) — propose creating the missing page or removing the entry.
- **Stubs** — propose merge or expansion.
- **Constitution violations** beyond auto-fix scope (frontmatter gaps, missing Connections, no concept-page link, naming) — propose the specific edit.
- **Misplaced files** — entity pages living directly under `wiki/<type>/` instead of `wiki/entities/<type>/` (the constitution detector currently misses this; check by listing top-level `wiki/` subdirs — anything other than `concepts/`, `synthesis/`, `entities/`, and the source-summary procedure folders is suspect). Propose `git mv` + a wikilink-rewrite pass.
- **Dangling-link debt (long tail of singletons)** — the import flow's Rule 8 ("wikilink only what's worth a page") leaves a long-running residue when prior imports created bare `[[wikilinks]]` to genuine domain entities and never stubbed them. Triage by *source* (group by the page emitting the dangling link) rather than by individual link — if `transcript-X` emits 49 dangling refs, work that one source end-to-end with the user: per link, decide *stub now*, *plain-text rewrite*, or *fuzzy-rewrite to existing slug*. Per-link triage across 800 findings is intractable; per-source is one decision context.

### 5. qmd sync

```bash
qmd update --collections ufo-kb
qmd embed
```

Catches anything the audit's auto-fixes (or your manual edits) changed.

### 6. Report

Summarize for the user:

- **Graph health metrics**: page count, edge count, average degree, largest component size, orphan count, dangling-ref count, synthesis-page health summary.
- **What was auto-fixed**: list every back-link added and dangling rewrite performed.
- **What was acted on after approval**: merges performed, splits done, new links added.
- **What's flagged**: open findings the user still needs to call.
- **Open questions**: anything that needs domain judgment beyond the audit's reach.


## Universal maintenance rules

1. **CONSTITUTION first.** Schema/section/naming violations are critical — they erode graph queryability.
2. **The graph is the diagnostic tool, not just the target.** Use `neighbors.py` anchor sentences to verify findings before flagging. "8 shared neighbors" is weak; "shared neighbors AND both reference the same firsthand-claim about Skinwalker Ranch" is strong.
3. **Auto-fix only what the CONSTITUTION already mandates** (synthesis back-links + exact-alias dangling rewrites). Substring/fuzzy candidates are suggestions only — `[[smith]]` must never auto-rewrite to `[[mit]]`. When a finding has multiple plausible candidates, ask the user; never guess.
4. **Severity is impact, not novelty.** New dangling link from a hub is critical; long-standing stub-orphan in a low-degree corner is low. Group stable patterns ("three orphan-islands all from the same source folder") rather than flagging ten individual findings.

## Tools

Under `scripts/`: `audit.py` (single pipeline; `--apply` runs the two safe auto-fixes; `--json` machine-readable), `jaccard-similarity.py`, `adamic-adar.py`, `common-neighbors.py`, `cluster-detection.py`. Cross-skill: `kb-query/scripts/disambiguate.py` (also used internally by `audit.py` to gate dangling-link auto-fixes) and `kb-query/scripts/neighbors.py` (anchor-sentence retrieval for triage). Run `--help` for arguments.

For detailed detector reference, severity rubric, auto-fix scope, and common-patterns recipes, load [references/maintenance-ops.md](references/maintenance-ops.md).
