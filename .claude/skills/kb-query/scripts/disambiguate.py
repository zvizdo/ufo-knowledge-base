#!/usr/bin/env python3
"""Resolve a fuzzy entity mention to ranked candidate pages.

Pipeline (each stage runs only if the prior stage returned nothing):
  1. Exact match on slug or any frontmatter alias (case-insensitive).
  2. Substring match on slug or alias.
  3. difflib SequenceMatcher fuzzy match (threshold 0.6).

Each candidate is returned with `(slug, title, type, summary, degree, folder, match_kind)`
so the LLM walker can pick the right one using neighborhood context.

Usage:
    python disambiguate.py <wiki-dir> "<mention>" [--limit N] [--json]

Examples:
    python disambiguate.py wiki/ "David Grusch"
    python disambiguate.py wiki/ "Ike" --limit 5
    python disambiguate.py wiki/ "Magenta crash" --json
"""

import argparse
import difflib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]*?)?\]\]")
FUZZY_THRESHOLD = 0.6


def page_title_from_path(filepath: Path) -> str:
    return filepath.stem


def parse_aliases_block(lines: list[str], start_idx: int) -> list[str]:
    """Collect items from a YAML block list starting at lines[start_idx + 1]."""
    aliases: list[str] = []
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


def parse_inline_list(value: str) -> list[str]:
    """Parse `[a, b, "c d"]` into ['a', 'b', 'c d']."""
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        return []
    inner = value[1:-1].strip()
    if not inner:
        return []
    items: list[str] = []
    for chunk in re.split(r",(?![^\[]*\])", inner):
        item = chunk.strip().strip('"').strip("'")
        if item:
            items.append(item)
    return items


def extract_page_metadata(filepath: Path) -> tuple[dict[str, str], list[str]]:
    """Return (frontmatter_singletons, aliases_list) for a page.

    frontmatter_singletons: top-level scalar fields (e.g. summary, type, name).
    aliases_list: parsed `aliases:` field.
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}, []
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, []

    fm: dict[str, str] = {}
    aliases: list[str] = []
    end_idx = None
    i = 1
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            end_idx = i
            break
        if line and not line[0].isspace() and ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if key == "aliases":
                if value:
                    aliases = parse_inline_list(value)
                else:
                    aliases = parse_aliases_block(lines, i)
            else:
                fm[key] = value.strip('"').strip("'")
        i += 1

    return fm, aliases


def folder_of(slug: str, path_map: dict[str, Path], wiki_dir: Path) -> str:
    p = path_map.get(slug)
    if p is None:
        return "missing"
    rel = p.relative_to(wiki_dir)
    parts = rel.parts
    return "/".join(parts[:-1]) if len(parts) > 1 else "."


def build_index(wiki_dir: Path):
    """Scan all pages; build slug→Path, slug→metadata, slug→aliases, degree map."""
    path_map: dict[str, Path] = {}
    metadata: dict[str, dict[str, str]] = {}
    aliases_by_slug: dict[str, list[str]] = {}
    forward: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)

    for f in wiki_dir.rglob("*.md"):
        slug = page_title_from_path(f).lower()
        path_map[slug] = f
        fm, aliases = extract_page_metadata(f)
        metadata[slug] = fm
        aliases_by_slug[slug] = aliases
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for link in WIKILINK_RE.findall(text):
            link_slug = link.strip().lower()
            if link_slug == slug:
                continue
            forward[slug].add(link_slug)
            reverse[link_slug].add(slug)

    degree_map = {
        slug: len(forward.get(slug, set()) | reverse.get(slug, set()))
        for slug in path_map
    }
    return path_map, metadata, aliases_by_slug, degree_map


def normalize(s: str) -> str:
    """Lowercase, replace hyphens/underscores/punct with spaces, collapse whitespace."""
    s = s.lower()
    s = re.sub(r"[-_/.,]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def build_lookup(path_map, aliases_by_slug, metadata):
    """Build normalized-string → list of (slug, match_kind) from titles + aliases + name field."""
    lookup: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for slug, p in path_map.items():
        title_normalized = normalize(slug)
        lookup[title_normalized].append((slug, "slug"))
        name = metadata.get(slug, {}).get("name", "")
        if name:
            lookup[normalize(name)].append((slug, "name"))
        for alias in aliases_by_slug.get(slug, []):
            lookup[normalize(alias)].append((slug, "alias"))
    return lookup


def candidate_record(slug: str, match_kind: str, score: float, path_map, metadata, degree_map, wiki_dir):
    fm = metadata.get(slug, {})
    return {
        "slug": slug,
        "title": page_title_from_path(path_map[slug]),
        "type": fm.get("type", ""),
        "summary": fm.get("summary", "")[:200],
        "degree": degree_map.get(slug, 0),
        "folder": folder_of(slug, path_map, wiki_dir),
        "match_kind": match_kind,
        "match_score": round(score, 3),
    }


def disambiguate(query: str, path_map, metadata, aliases_by_slug, degree_map, wiki_dir, limit: int):
    lookup = build_lookup(path_map, aliases_by_slug, metadata)
    q_norm = normalize(query)

    # Stage 1: exact match
    exact = lookup.get(q_norm, [])
    if exact:
        seen = set()
        records = []
        for slug, kind in exact:
            if slug in seen:
                continue
            seen.add(slug)
            records.append(candidate_record(slug, f"exact-{kind}", 1.0, path_map, metadata, degree_map, wiki_dir))
        records.sort(key=lambda r: -r["degree"])
        return records[:limit], "exact"

    # Stage 2: substring match
    substring_hits: dict[str, tuple[str, float]] = {}
    for key, entries in lookup.items():
        if q_norm in key or key in q_norm:
            score = len(q_norm) / max(len(key), len(q_norm)) if key else 0
            for slug, kind in entries:
                prev = substring_hits.get(slug)
                if prev is None or score > prev[1]:
                    substring_hits[slug] = (f"substring-{kind}", score)
    if substring_hits:
        records = [
            candidate_record(slug, kind, score, path_map, metadata, degree_map, wiki_dir)
            for slug, (kind, score) in substring_hits.items()
        ]
        records.sort(key=lambda r: (-r["match_score"], -r["degree"]))
        return records[:limit], "substring"

    # Stage 3: difflib fuzzy
    keys = list(lookup.keys())
    fuzzy_matches = difflib.get_close_matches(q_norm, keys, n=limit * 2, cutoff=FUZZY_THRESHOLD)
    fuzzy_hits: dict[str, tuple[str, float]] = {}
    for k in fuzzy_matches:
        score = difflib.SequenceMatcher(None, q_norm, k).ratio()
        for slug, kind in lookup[k]:
            prev = fuzzy_hits.get(slug)
            if prev is None or score > prev[1]:
                fuzzy_hits[slug] = (f"fuzzy-{kind}", score)
    if fuzzy_hits:
        records = [
            candidate_record(slug, kind, score, path_map, metadata, degree_map, wiki_dir)
            for slug, (kind, score) in fuzzy_hits.items()
        ]
        records.sort(key=lambda r: (-r["match_score"], -r["degree"]))
        return records[:limit], "fuzzy"

    return [], "none"


def render_human(query: str, records: list[dict], stage: str):
    if not records:
        print(f"No candidates found for: '{query}'")
        print("Hint: try a partial name, an alias, or pass --json to see what was searched.")
        return
    print(f"Candidates for '{query}' (stage: {stage}):\n")
    for r in records:
        print(f"  [[{r['title']}]] (deg {r['degree']}, {r['folder']}) — {r['match_kind']} {r['match_score']}")
        if r["type"]:
            print(f"    type: {r['type']}")
        if r["summary"]:
            print(f"    summary: {r['summary']}")
    print()
    if len(records) > 1:
        print("Multiple candidates — disambiguate using neighborhood overlap with the rest of the query.")


def main():
    parser = argparse.ArgumentParser(description="Resolve a fuzzy mention to candidate wiki pages")
    parser.add_argument("wiki_dir", type=Path)
    parser.add_argument("mention", help="The fuzzy entity mention to resolve")
    parser.add_argument("--limit", type=int, default=8, help="Max candidates to return (default: 8)")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    wiki_dir = args.wiki_dir.resolve()
    if not wiki_dir.is_dir():
        print(f"Error: {wiki_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    path_map, metadata, aliases_by_slug, degree_map = build_index(wiki_dir)
    records, stage = disambiguate(
        args.mention, path_map, metadata, aliases_by_slug, degree_map, wiki_dir, args.limit
    )

    if args.json:
        print(json.dumps({
            "query": args.mention,
            "stage": stage,
            "candidates": records,
        }, indent=2))
    else:
        render_human(args.mention, records, stage)


if __name__ == "__main__":
    main()
