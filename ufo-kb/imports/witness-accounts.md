---
name: witness-accounts
trigger: "A raw firsthand witness account is added to raw/witness-accounts/ (MUFON report, NUFORC entry, direct interview, contactee write-up)"
source_destination: raw/witness-accounts/
summary_destination: wiki/witness-accounts/
---

# Witness Accounts Import

Handles raw firsthand accounts: MUFON reports, NUFORC entries, direct interview transcripts not already covered by youtube-transcripts, contactee write-ups, abductee narratives.

## Source Summary

Summary page in `wiki/witness-accounts/<slug>.md` with frontmatter: `witness`, `date_of_event`, `date_reported`, `location`, `phenomenology` (lighted-craft/black-triangle/entity-encounter/abduction/etc.), `corroboration` (firsthand-only/multi-witness/instrumented), `source_org` (MUFON/NUFORC/direct/other), `tags[]`. Body sections: Account · Corroboration · Connections.

## Extraction Steps

1. Read the account.
2. Identify: witness, date, place, type of phenomenon.
3. Determine: is this a *new incident* or does it corroborate/dispute an existing incident page? If new, create the incident; if existing, add this account as supporting (or contradicting) evidence on the incident page.
4. Apply phenomenology-categories concept (Hynek, Vallée, abductee/contactee/experiencer).

## Wiki Updates

- Account gets a digest page in `wiki/witness-accounts/`.
- Incident page is created or updated in `wiki/entities/incidents/`.
- Witness gets/updates a person page (mark as witness-role).
- Place gets/updates a place page.

## Cross-Linking Rules

- Account → incident (every account links to exactly one incident).
- Account → witness → place.
- Multiple accounts of the same incident MUST cross-link to each other via the incident page.
- Apply phenomenology-categories concept link.

## Log

`[YYYY-MM-DD] import:witness-accounts | <slug> | witness: <name>, location: <place>`

## Quality Check

- Incident page reflects this account.
- Witness and place pages exist.
- Run `qmd update --collections ufo-kb && qmd embed`.
