---
name: congressional-hearings
trigger: "A congressional hearing transcript is added to raw/congressional-hearings/"
source_destination: raw/congressional-hearings/
summary_destination: wiki/congressional-hearings/
---

# Congressional Hearings Import

Handles UAP-related congressional hearings (2023 House Oversight UAP hearing, Grusch/Graves/Fravor testimony, future Senate hearings).

## Why This Is Its Own Procedure

Sworn testimony has special epistemic status — it carries perjury liability. The questions asked also reveal what congress knows or wants to know, which is a separate signal from the answers.

## Source Summary

Summary page in `wiki/congressional-hearings/<slug>.md` with frontmatter: `title`, `date`, `committee`, `chamber` (house/senate), `witnesses[]`, `members_present[]`, `tags[]`. Body sections: Witnesses & Testimony · Key Claims (sworn) · Key Questions Asked · Aftermath · Connections.

## Extraction Steps

1. Read the transcript.
2. For each witness: extract identity, claims made under oath (mark as `sworn:true`), and any qualifications/hedges.
3. For each member of congress present: extract the substance of their questions (their questions reveal their priors and access).
4. Capture the hearing as an **incident** in `wiki/entities/incidents/` as well — hearings are events.

## Wiki Updates

- Hearing gets a digest page in `wiki/congressional-hearings/` AND an incident entry in `wiki/entities/incidents/`.
- Each witness gets/updates a person page; testimony is recorded as firsthand sworn claims.
- Each member-of-congress question contributes to that member's person page (under "Stated positions / lines of inquiry").

## Cross-Linking Rules

- Hearing → every witness (bidirectional).
- Hearing → every congressperson present.
- Each sworn claim → its claims-theses page (with `sworn:true` annotation).
- Hearing → any prior incident, document, or program referenced in testimony.

## Log

`[YYYY-MM-DD] import:congressional-hearings | <slug> | witnesses: N, sworn-claims: M`

## Quality Check

- All witnesses linked.
- All sworn claims marked as such on claims-theses pages.
- Run `qmd update --collections ufo-kb && qmd embed`.
