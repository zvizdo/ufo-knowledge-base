---
name: off-topic-skipped
purpose: registry of raw sources that were intentionally not imported because they fall outside the KB's UFO/UAP scope; prevents repeated re-evaluation of the same skip decision
---

# Off-Topic Skipped Sources

This is a flat registry of sources that have been considered for import and **deliberately not imported** because their content is outside the UFO/UAP/NHI scope of this KB. Anyone running an import pass should consult this file before evaluating a candidate source — if it's listed here, the skip decision is already made.

## How to use

- **Before importing**: grep this file for the source ID. If present, skip.
- **When skipping a new source**: append it here with a one-line reason. Don't write a full source-summary.
- **When changing your mind**: delete the entry, then run the import skill normally.

A skip decision is reversible — listing a source here does not block re-import, but it does require explicit removal first so the skip is a deliberate undo, not an accident.

## Skip criteria

A source is off-topic when it does not engage with at least one of:

- UFOs / UAPs / NHI / non-human intelligence
- Adjacent classified-program / disclosure-politics topics
- Consciousness / parapsychology research with UAP-relevant framing
- Anti-gravity / exotic-propulsion physics
- Crash retrieval, contactee, abduction, or experiencer phenomena
- The intelligence/government suppression apparatus around any of the above

Adjacent topics (general physics, philosophy, defense policy without UAP angle) are **not** automatic skips — they may be imported lightly if a clear UAP-relevant claim appears.

## Registry

### YouTube transcripts

| Source ID | Title | Channel | Reason |
|---|---|---|---|
| `5Ne8ZbYxjKs` | Why American Sperm Count Dropped 41% in 50 years | American Alchemy | Fertility / demographic decline; no UAP content |
| `fJ6xNDu8MPU` | How to Find your Calling \| Robert Greene & Ryan Holiday | American Alchemy | Self-help / philosophy interview; no UAP content |
| `fZDlqneYEYY` | How This Investor Helped After a Nuclear Disaster | American Alchemy | VC profile (Josh Wolfe / Lux Capital); investor / hard-tech interview without UAP framing |

### Articles, books, etc.

(none yet)

## Maintenance notes

- This file is **not** loaded as part of normal kb-import flow guidance — only consulted at the start of an import to short-circuit known-skips.
- If the same source ID appears here with different reasons over time, the most recent reason wins.
- If a source was previously imported but should be retired (rare), do not list it here — that requires a deletion pass with link cleanup.
