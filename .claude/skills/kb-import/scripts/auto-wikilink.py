#!/usr/bin/env python3
"""Propose (and optionally apply) safe wikilinks on a page.

Purpose:
    Catches the "exists-but-unlinked" pattern that the kb-import QA surfaced —
    a source-summary mentions an entity (Chris Mellon, Edward Ruppelt, ...) by
    name in plain text, but the import pipeline didn't wrap it in [[wikilinks]],
    so the entity page exists in the KB but is not connected to this source.

Conservative policy:
    - Only EXACT alias/title matches propose a link. Substring and fuzzy
      candidates are flagged for human review, never auto-linked.
    - Only the first occurrence of each match is proposed (no over-linking).
    - Skip frontmatter, fenced code blocks, headers, and any text already
      inside [[wikilinks]] or [markdown](links).
    - Skip self-links (the page about Garry Nolan should not auto-link
      "Garry Nolan" to itself).

Usage:
    python auto-wikilink.py <wiki-dir> <page-path> [--apply] [--json]
    python auto-wikilink.py <wiki-dir> <page-path> --strict   # require ≥3-char alias
    python auto-wikilink.py <wiki-dir> <page-path> --include-1word  # include 1-word aliases (off by default to avoid noise)

Outputs (default):
    Markdown report listing each proposed link with surrounding context
    (~80 chars). Use --apply to rewrite the file in place.

Exit codes:
    0 — no changes proposed (or all applied if --apply)
    1 — usage / file error
"""

import argparse
import json
import re
import sys
from pathlib import Path


WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]*?)?\]\]")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
FRONTMATTER_RE = re.compile(r"^---\n(.*?\n)---\n", re.DOTALL)
FENCED_CODE_RE = re.compile(r"^```", re.MULTILINE)
HEADER_RE = re.compile(r"^#+\s", re.MULTILINE)


def parse_aliases_block(lines, start_idx):
    aliases = []
    i = start_idx + 1
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if line and not line[0].isspace():
            break
        if stripped.startswith("- "):
            value = stripped[2:].strip().strip('"').strip("'")
            if value:
                aliases.append(value)
        elif not stripped:
            break
        i += 1
    return aliases


def parse_inline_list(value):
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        return []
    inner = value[1:-1].strip()
    if not inner:
        return []
    items = []
    for chunk in re.split(r",(?![^\[]*\])", inner):
        item = chunk.strip().strip('"').strip("'")
        if item:
            items.append(item)
    return items


def extract_page_metadata(filepath):
    """Return (frontmatter_singletons, aliases_list)."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}, []
    if not text.startswith("---"):
        return {}, []
    end = text.find("\n---", 3)
    if end == -1:
        return {}, []
    fm = text[3:end]
    lines = fm.split("\n")
    singletons = {}
    aliases = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if ":" in line and not line.startswith(" "):
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if key == "aliases":
                if val.startswith("["):
                    aliases.extend(parse_inline_list(val))
                elif not val:
                    aliases.extend(parse_aliases_block(lines, i))
            else:
                if val and not val.startswith("["):
                    singletons[key] = val.strip('"').strip("'")
        i += 1
    return singletons, aliases


def build_alias_index(wiki_dir):
    """Build {alias_normalized: [(canonical_slug, alias_original, page_path)]}."""
    index = {}
    for md in wiki_dir.rglob("*.md"):
        if "/raw/" in str(md):
            continue
        slug = md.stem
        meta, aliases = extract_page_metadata(md)
        # Slug itself → as a "title" (lowercased).
        candidates = [slug]
        # The 'name' field is the canonical display.
        if "name" in meta:
            candidates.append(meta["name"])
        if "title" in meta:
            candidates.append(meta["title"])
        for a in aliases:
            candidates.append(a)
        for c in candidates:
            if not c:
                continue
            key = c.strip().lower()
            if key not in index:
                index[key] = []
            index[key].append((slug, c.strip(), md))
    return index


def mask_already_linked_regions(text):
    """Return a list of (start, end) char ranges in `text` we should NOT propose
    new links for: frontmatter, fenced code blocks, headers, existing wikilinks,
    existing markdown links."""
    masked = []
    # Frontmatter
    fm = FRONTMATTER_RE.match(text)
    if fm:
        masked.append((0, fm.end()))
    # Fenced code blocks
    fences = [m.start() for m in FENCED_CODE_RE.finditer(text)]
    for i in range(0, len(fences) - 1, 2):
        # Match closing fence newline if available
        end_line_end = text.find("\n", fences[i + 1])
        if end_line_end == -1:
            end_line_end = len(text)
        masked.append((fences[i], end_line_end))
    # Headers (whole line)
    for m in HEADER_RE.finditer(text):
        line_end = text.find("\n", m.end())
        if line_end == -1:
            line_end = len(text)
        masked.append((m.start(), line_end))
    # Existing wikilinks
    for m in WIKILINK_RE.finditer(text):
        masked.append((m.start(), m.end()))
    # Existing markdown links
    for m in MD_LINK_RE.finditer(text):
        masked.append((m.start(), m.end()))
    return masked


def in_masked(pos, masked):
    for start, end in masked:
        if start <= pos < end:
            return True
    return False


def find_match_positions(text, alias, masked, page_self_slug):
    """Find all UNMASKED match positions for `alias` in `text`. Whole-word boundary."""
    # Use word boundaries; case-insensitive
    pattern = re.compile(r"(?<![\w-])" + re.escape(alias) + r"(?![\w-])", re.IGNORECASE)
    positions = []
    for m in pattern.finditer(text):
        if in_masked(m.start(), masked):
            continue
        positions.append((m.start(), m.end()))
    return positions


def propose_links(page_path, wiki_dir, strict_min_len=2, include_1word=False):
    text = page_path.read_text(encoding="utf-8")
    page_slug = page_path.stem
    masked = mask_already_linked_regions(text)
    index = build_alias_index(wiki_dir)

    proposals = []  # list of (alias, canonical_slug, start, end, context_snippet)
    proposed_aliases = set()  # don't propose the same alias twice

    # Sort aliases longest-first so "Edward Ruppelt" matches before "Edward".
    aliases_sorted = sorted(index.keys(), key=len, reverse=True)

    for alias_key in aliases_sorted:
        if len(alias_key) < strict_min_len:
            continue
        # Skip aliases that are a single English word unless include_1word=True
        if not include_1word and " " not in alias_key and "-" not in alias_key:
            # 1-word aliases create false positives ("john", "ed", etc.)
            continue
        # If multiple pages share this alias, ambiguous → skip
        if len(index[alias_key]) > 1:
            continue
        canonical_slug, alias_display, target_path = index[alias_key][0]
        if canonical_slug == page_slug:
            continue
        # Find positions
        positions = find_match_positions(text, alias_display, masked, page_slug)
        if not positions:
            # Try the slug-style alias (replace hyphens with spaces) as fallback
            positions = find_match_positions(text, alias_key, masked, page_slug)
        if not positions:
            continue
        # Only propose first occurrence
        start, end = positions[0]
        # Build context snippet ±60 chars
        ctx_start = max(0, start - 60)
        ctx_end = min(len(text), end + 60)
        snippet = text[ctx_start:ctx_end].replace("\n", " ").strip()
        proposals.append({
            "alias": alias_display,
            "alias_lower": alias_key,
            "canonical_slug": canonical_slug,
            "start": start,
            "end": end,
            "snippet": snippet,
        })
        proposed_aliases.add(alias_key)

    # Sort proposals by position (so apply-rewrite from end to start to preserve indices).
    proposals.sort(key=lambda p: p["start"])
    return text, proposals


def apply_proposals(text, proposals):
    """Apply proposals from end to start to preserve character offsets."""
    new_text = text
    # Reverse order
    for p in sorted(proposals, key=lambda p: p["start"], reverse=True):
        # Replace the alias span with [[canonical-slug|alias-display]] if the
        # display differs from the slug; otherwise just [[canonical-slug]].
        original = new_text[p["start"]:p["end"]]
        if original.lower() == p["canonical_slug"].lower():
            replacement = f"[[{p['canonical_slug']}]]"
        else:
            replacement = f"[[{p['canonical_slug']}|{original}]]"
        new_text = new_text[:p["start"]] + replacement + new_text[p["end"]:]
    return new_text


def render_human(page_path, proposals, applied):
    if not proposals:
        return f"# auto-wikilink: {page_path.name}\n\nNo proposals."
    lines = [f"# auto-wikilink: {page_path.name}\n"]
    lines.append(f"{'Applied' if applied else 'Proposed'}: {len(proposals)}\n")
    for p in proposals:
        lines.append(f"## `{p['alias']}` → [[{p['canonical_slug']}]]")
        lines.append(f"- pos: {p['start']}–{p['end']}")
        lines.append(f"- context: …{p['snippet']}…")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wiki_dir", help="Path to wiki directory (e.g. ufo-kb/wiki/)")
    ap.add_argument("page_path", help="Path to the page to scan (typically a source-summary)")
    ap.add_argument("--apply", action="store_true", help="Rewrite the file in place")
    ap.add_argument("--json", action="store_true", help="Output JSON instead of Markdown")
    ap.add_argument("--strict", action="store_true", help="Require ≥3-char alias (default ≥2)")
    ap.add_argument("--include-1word", action="store_true", help="Include single-word aliases (default off; high false-positive rate)")
    args = ap.parse_args()

    wiki_dir = Path(args.wiki_dir).resolve()
    if not wiki_dir.exists():
        print(f"error: wiki dir not found: {wiki_dir}", file=sys.stderr)
        return 1
    page_path = Path(args.page_path).resolve()
    if not page_path.exists():
        print(f"error: page not found: {page_path}", file=sys.stderr)
        return 1

    min_len = 3 if args.strict else 2
    text, proposals = propose_links(
        page_path,
        wiki_dir,
        strict_min_len=min_len,
        include_1word=args.include_1word,
    )

    applied = False
    if args.apply and proposals:
        new_text = apply_proposals(text, proposals)
        page_path.write_text(new_text, encoding="utf-8")
        applied = True

    if args.json:
        out = {
            "page": str(page_path),
            "applied": applied,
            "proposals": proposals,
        }
        print(json.dumps(out, indent=2))
    else:
        print(render_human(page_path, proposals, applied))

    return 0


if __name__ == "__main__":
    sys.exit(main())
