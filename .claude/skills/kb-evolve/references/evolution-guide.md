# Evolution Guide — Detailed Reference

## When to Evolve

The KB should evolve when:

1. **New source types appear** that don't fit existing import procedures
2. **New patterns emerge** from the data that weren't anticipated at creation
3. **The user's understanding deepens** and they want to extract different things
4. **Scale demands restructuring** — categories that were fine at 20 pages don't work at 200
5. **The domain itself changes** — new frameworks, updated models, new terminology

Evolution is expected and healthy. A KB that never evolves is either too new or not being used.

## CONSTITUTION Updates

The CONSTITUTION is the most impactful file to change because it affects how every future import is processed.

### Adding Entity Types

When a new kind of thing deserves its own pages:

1. Define the entity type in the CONSTITUTION (name, definition, frontmatter fields, required sections)
2. Create the entity's subdirectory if needed (or use existing `wiki/entities/`)
3. Consider: should any existing wiki content be refactored into this new type?
4. Consider: should existing import procedures be updated to extract this entity type?

### Adding Concept Frameworks

When a new analytical lens should be applied:

1. Define the concept in the CONSTITUTION
2. Create a page for it in `wiki/concepts/` with the framework description
3. Consider: should this framework be retroactively applied to existing entities?
4. If yes, this is a bulk re-process operation

### Refining Extraction Rules

As you learn what's actually useful:

- Remove extraction targets that produce low-value content
- Add extraction targets discovered through queries that revealed gaps
- Tighten or loosen specificity based on what the KB actually needs

### Adjusting Connection Rules

- Increase minimum link counts if the graph is too sparse
- Add specific required connections (e.g., "every entity MUST link to at least one evaluation dimension")
- Define new relationship types (e.g., "contradicts", "supports", "extends")

## Restructuring Best Practices

### Renaming Pages

The trickiest operation because it requires updating all references.

1. Find all inbound `[[wikilinks]]` to the page being renamed
2. Rename the file
3. Update all `[[wikilinks]]` across the entire wiki
4. Run `qmd update --collections ufo-kb && qmd embed`

Use `grep -r '[[Old Name]]' wiki/` to find all references before renaming.

### Merging Pages

When two pages should be one:

1. Read both pages
2. Decide which survives (usually the more comprehensive one)
3. Merge content from the other page into the survivor
4. Consolidate the `sources` frontmatter list
5. Update all `[[wikilinks]]` from the deleted page to point to the survivor
6. Delete the merged-away page

### Splitting Pages

When one page has grown too large:

1. Identify natural split boundaries (by section, by sub-topic, by time period)
2. Create the new sub-pages
3. Convert the original into an overview page that links to all sub-pages
4. Update external `[[wikilinks]]` — decide whether they should point to the overview or a specific sub-page

### Adding Directories

New wiki subdirectories for new content categories:

1. Create the directory: `wiki/<new-category>/`
2. Update the CONSTITUTION if this represents a new content type
3. Existing pages don't need to move unless they better fit the new category

## Bulk Re-processing

This is the most intensive evolution operation. Use it carefully.

**Before bulk re-processing:**
1. Commit the current wiki state with git (so you can roll back)
2. Update the CONSTITUTION with the new rules
3. Identify which sources need re-processing and why

**During bulk re-processing:**
- Process one source at a time
- After each source, verify the wiki is consistent
- This will likely create many new pages and connections

**After bulk re-processing:**
1. Run full kb-maintain
2. Review the results — bulk operations can create duplicates or conflicts
3. Run `qmd update --collections ufo-kb && qmd embed --force`

## Custom Scripts

When extending the KB with new scripts:

- Follow the pattern of existing scripts (argparse, Path-based, parse wikilinks, human-readable output)
- Document the script in the relevant SKILL.md (kb-query or kb-maintain)
- Test on the actual wiki before relying on results
- Keep scripts independent — no shared library imports beyond stdlib
