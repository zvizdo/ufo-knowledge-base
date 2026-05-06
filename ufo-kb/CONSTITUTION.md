# CONSTITUTION — ufo-kb

> This document governs the identity, purpose, and rules of this knowledge base. Every import, query, and maintenance operation reads this file first.

## Purpose

Map the UFO/UAP discourse as a connected graph — who is who, where things happened, what concepts/entities recur, and how they all link. The KB is a personal sense-making instrument for navigating a fragmented field whose sources rarely cite each other directly.

## Domain

All UFO/UAP discourse and adjacent topics:
- Mainline UFO/UAP (sightings, incidents, witnesses, programs, hardware, disclosure politics)
- Adjacent: consciousness research, intelligence community, paranormal, contactee history, NHI, ancient mysteries / pre-history, government secrecy, mind-control programs (MK-Ultra etc.)

Pure off-domain content (general philosophy, sports, business interviews) is excluded at import.

## North Star Question

**How is everything connected?** — Surface non-obvious links between people, places, programs, entities, and ideas across the whole field. Every page should make the connective tissue more visible.

## Core Entities

Each gets its own page under `wiki/entities/<type>/`.

### people
- **Definition**: Any named individual who appears as a witness, whistleblower, journalist, researcher, official, contactee, debunker, host, or recurring discourse participant.
- **Frontmatter**: `name`, `aliases`, `roles[]` (witness/whistleblower/journalist/official/researcher/contactee/host/debunker/other), `affiliations[]`, `firsthand_claims[]`, `first_seen_in`, `tags[]`
- **Required sections**: Background · Notable Claims · Sources Where They Appear · Connections

### organizations
- **Definition**: Government agencies, private companies, civilian research groups, media outlets, religious/occult orders.
- **Frontmatter**: `name`, `aliases`, `type` (gov-agency/private-co/research-group/media/religious/other), `parent_org`, `country`, `active_period`, `tags[]`
- **Required sections**: Overview · Key People · Programs / Activities · Connections

### programs
- **Definition**: Named gov or black projects, classified efforts, public initiatives (AAWSAP, AATIP, Project Blue Book, Gateway Process, Stargate, MK-Ultra).
- **Frontmatter**: `name`, `aliases`, `parent_org`, `period`, `status` (active/terminated/alleged/declassified), `tags[]`
- **Required sections**: Mandate · Personnel · Outputs / Findings · Connections

### places
- **Definition**: Bases, incident sites, named geographic regions (Wright-Patterson, S4, Roswell, Skinwalker Ranch, Rendlesham Forest, Dulce).
- **Frontmatter**: `name`, `aliases`, `region`, `country`, `coordinates`, `type` (base/incident-site/region/installation/landmark), `tags[]`
- **Required sections**: Description · Associated Incidents · Connections

### incidents
- **Definition**: Discrete encounters, sightings, hearings, leaks, public events.
- **Frontmatter**: `name`, `date`, `location`, `witnesses[]`, `craft_type`, `corroboration` (firsthand/multi-witness/instrumented/hearsay), `tags[]`
- **Filename convention**: `YYYY-shortname.md` (e.g. `2004-tic-tac-nimitz.md`)
- **Required sections**: Account · Witnesses · Evidence · Aftermath · Connections

### craft-phenomena
- **Definition**: Named UAP types (Tic-Tac, Black Triangle, Foo Fighter), entity types (Greys, Tall Whites, Mantids, Reptilians, Nordics).
- **Frontmatter**: `name`, `aliases`, `category` (craft/entity/effect), `first_reported`, `tags[]`
- **Required sections**: Description · Reported Encounters · Connections

### documents
- **Definition**: Leaked docs, FOIAs, books, reports, memos (Wilson-Davis memo, COMETA, Grusch complaint, AARO reports). Books also live here when treated as primary sources.
- **Frontmatter**: `title`, `authors[]`, `date`, `type` (memo/foia/book/report/complaint/article), `classification`, `tags[]`
- **Required sections**: Summary · Key Claims · Provenance · Connections

### tech-artifacts
- **Definition**: Alleged or confirmed alien tech, recovered materials, implants, propulsion patents, classified weapons systems (Pais patents, Garry Nolan samples, "metamaterials").
- **Frontmatter**: `name`, `category` (material/device/patent/implant/weapon/other), `custodian`, `provenance`, `tags[]`
- **Required sections**: Description · Provenance Chain · Analysis / Findings · Connections

### symbols-glyphs
- **Definition**: Recurring visual motifs — hieroglyphics on craft, crop circles, contactee writing, ritual symbols.
- **Frontmatter**: `name`, `aliases`, `type` (glyph/symbol/inscription/crop-formation), `first_observed`, `tags[]`
- **Required sections**: Description · Where Observed · Interpretations · Connections

## Core Concepts & Frameworks

Lenses applied when analyzing sources. Each gets a page in `wiki/concepts/`.

### disclosure-narratives
- Competing meta-theories about how UFO truth is/isn't being released (slow disclosure, controlled opposition, psyop, genuine reveal, false-flag prep).
- Apply when a source explicitly or implicitly endorses a narrative model.

### credibility-frameworks
- How witness reliability is weighed (firsthand vs. hearsay, documented access vs. claimed access, corroboration count, track record). Used as a lens, not a numeric score (no scoring in v1).
- Apply on every person page.

### phenomenology-categories
- Hynek scale (CE1–CE5), Vallée classification, abductee vs. contactee vs. experiencer typology.
- Apply to incident pages and entity-encounter descriptions.

### recurring-claims
- High-frequency assertions in the discourse (reverse engineering, crash retrievals, NHI biologics, consciousness link, breakaway civilization, time-travelling humans). Differs from claims-theses below: these are *categories* of claim.
- Apply when categorizing what a source is asserting.

### source-type-frameworks
- Official / leaked / witness / researcher / cultural — and how each is weighted against the others.
- Apply at import time and on document pages.

### claims-theses
- Specific, recurring discrete assertions ("Moon is artificial," "Mars had nuclear war," "Aliens are interdimensional," "NHI = future humans," "Consciousness is non-local"). Each gets its own page aggregating who makes it, who pushes back, supporting/refuting evidence.
- This is the primary unit of "how is everything connected" — links converge on claims-theses pages.
- Apply when a source advances a discrete, repeatable claim.

## Extraction Rules

For every source the LLM processes, extract:

1. **All named entities** matching one of the entity types above. Default depth: every named entity worth its own page (skip purely incidental name-drops without context).
2. **All recurring claims and specific theses** asserted by the source.
3. **Firsthand vs. hearsay attribution** for every claim — track who is the original source of an assertion vs. who is repeating it.
4. **Dates, places, programs** mentioned in any claim — these are connection anchors.
5. **Cited sources** — when a speaker/author cites a document, person, or prior incident, capture that as a connection edge.
6. **Contradictions** with existing wiki pages — flag explicitly rather than silently overwriting.

## Connection Rules

- Every entity page MUST link to at least one concept page (typically `credibility-frameworks` for people, `recurring-claims` for documents, `phenomenology-categories` for incidents).
- Every concept page MUST link to related entities that exemplify it.
- `claims-theses` pages MUST link to: every entity that asserts the claim, every entity that disputes it, and every document that adduces evidence.
- Synthesis pages link to everything they reference.
- Contradictions between pages MUST be flagged explicitly with a `> ⚠ Conflict:` callout.
- **Ambiguous-name resolution**: auto-link only when the existing page is the unique plausible match in the KB; otherwise flag for review (e.g. "Greer" auto-links to `steven-greer.md` only while no other Greer exists).
- **Naming conventions**:
  - People: `firstname-lastname.md` (e.g. `david-grusch.md`)
  - Orgs/programs: lowercase-with-hyphens; **acronyms canonical when commonly used** (`cia.md`, `nasa.md`, `aatip.md`); full-name pages may exist as redirects
  - Incidents: `YYYY-shortname.md`
  - Places: `lowercase-name.md`
  - Claims-theses: `<short-slug>.md` capturing the gist (e.g. `moon-is-artificial.md`)

## Evaluation Criteria

No formal scoring/credibility ratings in v1 (deliberate). Credibility is captured qualitatively via the `credibility-frameworks` concept and per-page narrative. Add scoring via `kb-evolve` if it becomes useful later.

## Tone & Style

**Investigative / connective with structured frontmatter.**

- Prose is short and analytical — facts, not advocacy.
- Every page ends with a **Connections** section that surfaces non-obvious links ("X overlaps with Y because…", "Curiously, both Z and W appear at this location").
- Frontmatter is dense and queryable; body prose is supporting context.
- Open questions are first-class — capture them explicitly under a `## Open Questions` heading rather than burying them.
- No epistemic flattening: when a claim is contested, the page reflects the contest. Don't pick winners that the evidence hasn't picked.

---

*This constitution evolves. Update it via kb-evolve as your understanding of the domain deepens.*
