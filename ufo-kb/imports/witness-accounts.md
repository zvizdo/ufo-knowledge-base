---
name: witness-accounts
trigger: "A raw firsthand witness account is added to raw/witness-accounts/ (MUFON report, NUFORC entry, direct interview, contactee write-up)"
source_destination: raw/witness-accounts/
summary_destination: wiki/witness-accounts/
---

# Witness Accounts Import

Handles raw firsthand accounts: MUFON reports, NUFORC entries, direct interview transcripts not already covered by youtube-transcripts, contactee write-ups, abductee narratives, experiencer journals.

## Staging

Accounts arrive from one of:
- **MUFON CMS** — case number is the canonical ID, includes investigator notes
- **NUFORC** — raw witness submission, less curated
- **Direct interview** — transcript or written summary
- **Contactee/abductee write-up** — first-person narrative, often longer-form

Land the account in `raw/witness-accounts/<slug>.md`. Slug convention: `YYYY-MM-DD-witness-location` (e.g. `1995-08-12-blitch-daniels-park`). If the witness is anonymous, use `YYYY-MM-DD-anonymous-location`.

Prefill frontmatter from **the source-org's own record** when available: MUFON case number, NUFORC report ID, original submission date. Use the witness's name **as given in the source** — do not normalize spellings or guess at full names from initials. If a name is given as "John D." in the source, frontmatter is "John D." (not "John Doe"). Re-derived names have caused mis-attribution and false-merge incidents; the source-org record is authoritative.

## Pre-filter

Witness accounts in this domain are almost always on-topic by definition — but check anyway. If the account turns out to be **about a non-UAP phenomenon** (Bigfoot, ghost, paranormal-but-non-UAP), skip and log to LOG.md as `[skipped: off-domain]`. Hybrid accounts (UAP + entity encounter, UAP + missing time, UAP + abduction) are in-scope and should be imported normally.

If the account is **flagged as a hoax** by the source organization, or the witness has subsequently **recanted**, still import it with `disposition: hoax` or `disposition: recanted` in frontmatter and a `> ⚠ Disposition:` callout. Hoax/recant status is itself a signal worth preserving — patterns of hoaxing in a region or witness pool are research-relevant.

## Source Summary

Every import creates a summary page in `wiki/witness-accounts/<slug>.md` containing:

- Frontmatter: `witness`, `witness_anonymity` (named/initials/anonymous), `date_of_event`, `date_reported`, `location` (city/region/coordinates if given), `phenomenology` (lighted-craft/black-triangle/entity-encounter/abduction/missing-time/etc.), `corroboration` (firsthand-only/multi-witness/instrumented/physical-trace), `source_org` (MUFON/NUFORC/direct/other), `source_org_case_id` (if applicable), `disposition` (active/hoax/recanted/disputed; default `active`), `tags[]`, `type: source-summary`, `created`, `sources`
- **Account** — narrative summary in the witness's own framing, with key details preserved verbatim where possible
- **Phenomenology classification** — Hynek (CE-1/CE-2/CE-3/CE-4/CE-5), Vallée categorization, contactee/abductee/experiencer designation
- **Corroboration** — other witnesses, physical traces, instrumented data (radar, photo, video), media reports
- **Entities mentioned** — `[[wikilinks]]` to every person/org/program/place/incident/craft-phenomenon/document/tech-artifact/symbol-glyph extracted
- **Concepts/claims engaged** — `[[wikilinks]]` to concepts and claims-theses pages
- **Notable quotes** — verbatim lines worth preserving from the witness
- **Connections** — to other accounts, incidents, or patterns

## Extraction Steps

1. Read the account.
2. Identify: witness, date(s), location, phenomenology category, source org and case ID.
3. **Decide: new incident or existing incident?** This is the most consequential step.
   - If date + location + phenomenology match an existing `wiki/entities/incidents/` page, this account is **corroborating evidence** — add to that incident, do not create a new one.
   - If date + location are unique, this account creates a new incident page.
   - When in doubt, search by location and date radius (±2 days, same county). False-merges are harder to undo than late-merges, so default to new-incident when unsure and merge later.
4. Extract entities (default depth = every named entity worth a page):
   - **people** — witness, anyone the witness names (other witnesses, investigators, family present, military/law enforcement responders)
   - **organizations** — investigating org (MUFON/NUFORC), military units involved, media that reported it
   - **programs** — any gov/research program implicated
   - **places** — exact location, nearby landmarks, base/airport proximity
   - **incidents** — the incident itself; any prior similar local incidents the witness references
   - **craft-phenomena** — every craft type, NHI entity type, light-formation type described
   - **documents** — any reports, photos, or media coverage referenced
   - **tech-artifacts** — physical traces, recovered artifacts, alleged implants
   - **symbols-glyphs** — any glyph/symbol/marking the witness reports seeing
5. Apply phenomenology-categories concept (Hynek, Vallée, abductee/contactee/experiencer).
6. Capture the **source-org reliability gradient** as context — not as truth-judgment, but as an annotation: MUFON-investigated > NUFORC-raw > anonymous-blog. This shapes downstream weight on claims-theses pages without auto-rejecting any source.

## Wiki Updates

- Account gets a digest page in `wiki/witness-accounts/`.
- Incident page is created or updated in `wiki/entities/incidents/`. **Every account links to exactly one incident.**
- Witness gets/updates a person page (mark `roles: [witness]`; if multiple roles, append).
- Place gets/updates a place page.
- Each load-bearing claim from the account links to a claims-theses page (firsthand-only annotation unless multi-witness/instrumented).
- If the account contradicts another account of the same incident, flag with `> ⚠ Conflict:` on the incident page; do not silently reconcile.

## Cross-Linking Rules

- Account → incident (every account links to exactly one incident).
- Account → witness → place.
- Multiple accounts of the same incident MUST cross-link to each other via the incident page.
- Apply phenomenology-categories concept link.
- If the witness has multiple accounts in the KB, link the witness page → each account.
- Auto-link ambiguous names only when the existing page is the unique plausible match.
- Every new entity page MUST link to at least one concept page.
- Every load-bearing claim MUST link to a `claims-theses` page.

## Log

`[YYYY-MM-DD] import:witness-accounts | <slug> | witness: <name>, location: <place>, incident: <incident-slug>`

## Quality Check

- Verify all new pages have at least 2 inbound `[[wikilinks]]`.
- Verify no orphan pages were created.
- Verify the incident page reflects this account.
- Verify witness and place pages exist and back-link.
- Verify phenomenology classification is applied.
- Verify disposition (active/hoax/recanted/disputed) is captured if non-default.
- Verify source-org case ID is preserved verbatim if available.
- Run `qmd update --collections ufo-kb && qmd embed`.
