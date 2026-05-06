---
name: {{PROCEDURE_NAME}}
trigger: "{{TRIGGER_DESCRIPTION}}"
source_destination: raw/{{SOURCE_SUBDIR}}/
summary_destination: wiki/{{PROCEDURE_NAME}}/
---

# {{PROCEDURE_TITLE}} Import

## Source Summary

Every import creates a summary page in `wiki/{{PROCEDURE_NAME}}/`. Include:
- {{SUMMARY_FOCUS}}
- Links to the raw source file
- `[[wikilinks]]` to all entities and concepts touched

## Extraction Steps

1. Read the source.
2. Identify: {{EXTRACTION_TARGETS}}
3. Extract entities → `wiki/entities/`: {{ENTITY_TYPES_TO_EXTRACT}}
4. Extract concepts → `wiki/concepts/`: {{CONCEPT_TYPES_TO_EXTRACT}}

## Wiki Updates

- Create the summary page.
- Create/update entity pages.
- Create/update concept pages.
- Add back-links from entity/concept pages.

## Cross-Linking Rules

- Every new entity page MUST link to at least one concept page.
- Every new concept page MUST link to related entities.
- Flag contradictions with existing pages.

## Log

`[YYYY-MM-DD] import:{{PROCEDURE_NAME}} | <slug> | <details>`

## Quality Check

- All new pages have ≥2 inbound `[[wikilinks]]`.
- No orphans created.
- Run `qmd update --collections ufo-kb && qmd embed`.
