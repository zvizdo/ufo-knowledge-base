#!/usr/bin/env python3
"""Get a page's neighbors with anchor sentences, summaries, and degrees.

Unlike neighborhood.py (which returns slugs only), this gives the LLM walker
enough context to decide which links to follow next:

- The exact line where each link appears (anchor sentence)
- The neighbor's frontmatter `summary:` and total degree
- Direction (outbound from this page, inbound to it, or both)
- The folder the neighbor lives in (for diversity-aware sampling)

Usage:
    python neighbors.py <wiki-dir> "<Page Name>" [--direction both|out|in]
                                                 [--limit N] [--diverse] [--json]

Examples:
    python neighbors.py wiki/ "David Grusch"
    python neighbors.py wiki/ "MK-Ultra" --diverse --limit 20
    python neighbors.py wiki/ "Eric Davis" --json
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]*?)?\]\]")
DIVERSE_THRESHOLD = 50


def page_title_from_path(filepath: Path) -> str:
    return filepath.stem


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return (top-level frontmatter dict, body without the frontmatter block)."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    fm: dict[str, str] = {}
    body_start = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body_start = i + 1
            break
        if line and not line[0].isspace() and ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip()
    if body_start is None:
        return fm, ""
    return fm, "".join(lines[body_start:])


def extract_anchor_sentence(body: str, link_target: str, max_chars: int = 200) -> str:
    """Return the cleaned line where [[link_target]] appears, truncated to max_chars.

    Empty string if the link doesn't appear in the body.
    """
    target_lower = link_target.lower()
    for line in body.splitlines():
        if not line.strip():
            continue
        for m in WIKILINK_RE.finditer(line):
            if m.group(1).strip().lower() != target_lower:
                continue
            clean = re.sub(r"\s+", " ", line).strip()
            clean = re.sub(r"^[-*+]\s+", "", clean)
            clean = re.sub(r"^#+\s+", "", clean)
            if len(clean) <= max_chars:
                return clean
            link_text = m.group(0)
            link_pos = clean.find(link_text)
            if link_pos < 0:
                return clean[:max_chars - 1].rstrip() + "…"
            half = max_chars // 2
            ss = max(0, link_pos - half)
            se = min(len(clean), link_pos + len(link_text) + half)
            prefix = "…" if ss > 0 else ""
            suffix = "…" if se < len(clean) else ""
            return prefix + clean[ss:se] + suffix
    return ""


def build_index(wiki_dir: Path):
    """Scan wiki and build forward/reverse adjacency, path map, bodies, summaries."""
    forward: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    path_map: dict[str, Path] = {}
    bodies: dict[str, str] = {}
    summaries: dict[str, str] = {}

    for f in wiki_dir.rglob("*.md"):
        title_lower = page_title_from_path(f).lower()
        path_map[title_lower] = f
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm, body = split_frontmatter(text)
        bodies[title_lower] = body
        summaries[title_lower] = fm.get("summary", "").strip().strip('"').strip("'")
        for link in WIKILINK_RE.findall(body):
            link_lower = link.strip().lower()
            if link_lower == title_lower:
                continue
            forward[title_lower].add(link_lower)
            reverse[link_lower].add(title_lower)

    return forward, reverse, path_map, bodies, summaries


def resolve_title(query: str, path_map: dict[str, Path]) -> str | None:
    query_lower = query.lower()
    if query_lower in path_map:
        return query_lower
    matches = [t for t in path_map if query_lower in t]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        exact = [t for t in matches if t == query_lower]
        if exact:
            return exact[0]
        print(f"Ambiguous: '{query}' matches {len(matches)} pages. Using {matches[0]}.", file=sys.stderr)
        return matches[0]
    return None


def degree_of(title_lower: str, forward, reverse) -> int:
    return len(forward.get(title_lower, set()) | reverse.get(title_lower, set()))


def folder_of(title_lower: str, path_map: dict[str, Path], wiki_dir: Path) -> str:
    p = path_map.get(title_lower)
    if p is None:
        return "missing"
    rel = p.relative_to(wiki_dir)
    parts = rel.parts
    return "/".join(parts[:-1]) if len(parts) > 1 else "."


def build_neighbor_records(
    start: str, direction: str,
    forward, reverse, path_map, bodies, summaries, wiki_dir,
) -> list[dict]:
    out_links = forward.get(start, set()) if direction in ("both", "out") else set()
    in_links = reverse.get(start, set()) if direction in ("both", "in") else set()
    start_body = bodies.get(start, "")

    records: dict[str, dict] = {}

    for n in out_links:
        records[n] = {
            "slug": n,
            "title": page_title_from_path(path_map[n]) if n in path_map else n,
            "direction": "out",
            "exists": n in path_map,
            "degree": degree_of(n, forward, reverse),
            "summary": summaries.get(n, ""),
            "anchor_sentence": extract_anchor_sentence(start_body, n),
            "folder": folder_of(n, path_map, wiki_dir),
        }

    for n in in_links:
        anchor_back = extract_anchor_sentence(bodies.get(n, ""), start)
        if n in records:
            records[n]["direction"] = "both"
            if anchor_back:
                records[n]["anchor_back"] = anchor_back
            continue
        records[n] = {
            "slug": n,
            "title": page_title_from_path(path_map[n]) if n in path_map else n,
            "direction": "in",
            "exists": n in path_map,
            "degree": degree_of(n, forward, reverse),
            "summary": summaries.get(n, ""),
            "anchor_sentence": anchor_back,
            "folder": folder_of(n, path_map, wiki_dir),
        }

    return list(records.values())


def diverse_sample(records: list[dict], limit: int) -> list[dict]:
    """Round-robin by folder; within each folder, prefer high-degree neighbors."""
    if len(records) <= limit:
        return sorted(records, key=lambda r: -r["degree"])
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        groups[r["folder"]].append(r)
    for g in groups.values():
        g.sort(key=lambda r: -r["degree"])
    selected: list[dict] = []
    folders = sorted(groups.keys())
    while len(selected) < limit:
        progressed = False
        for folder in folders:
            if not groups[folder]:
                continue
            selected.append(groups[folder].pop(0))
            progressed = True
            if len(selected) >= limit:
                break
        if not progressed:
            break
    return selected


def render_human(start_title: str, start_degree: int, records: list[dict], diversified: bool):
    print(f"Neighbors of [[{start_title}]] (degree: {start_degree}):\n")
    by_dir = {"out": [], "in": [], "both": []}
    for r in records:
        by_dir[r["direction"]].append(r)

    for label, key, arrow in [
        ("Bidirectional", "both", "↔"),
        ("Outbound", "out", "→"),
        ("Inbound", "in", "←"),
    ]:
        bucket = by_dir[key]
        if not bucket:
            continue
        print(f"  {label} ({len(bucket)}):")
        for r in sorted(bucket, key=lambda x: -x["degree"]):
            missing = " [MISSING]" if not r["exists"] else ""
            print(f"    {arrow} [[{r['title']}]] (deg {r['degree']}, {r['folder']}){missing}")
            if r["summary"]:
                summary = r["summary"][:140]
                print(f"       summary: {summary}")
            if r["anchor_sentence"]:
                print(f"       anchor:  \"{r['anchor_sentence']}\"")
            if r.get("anchor_back"):
                print(f"       back:    \"{r['anchor_back']}\"")
        print()

    if diversified:
        print("  (diversified by folder — pass --limit higher to see more)")


def main():
    parser = argparse.ArgumentParser(description="Rich neighbor lookup for the LLM walker")
    parser.add_argument("wiki_dir", type=Path)
    parser.add_argument("page", help="Starting page title")
    parser.add_argument("--direction", choices=["both", "out", "in"], default="both")
    parser.add_argument("--limit", type=int, default=30, help="Max neighbors to return (default: 30)")
    parser.add_argument("--diverse", action="store_true",
                        help="Round-robin sample by folder (auto-on if degree > 50)")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    wiki_dir = args.wiki_dir.resolve()
    if not wiki_dir.is_dir():
        print(f"Error: {wiki_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    forward, reverse, path_map, bodies, summaries = build_index(wiki_dir)

    start = resolve_title(args.page, path_map)
    if start is None:
        print(f"Page not found: '{args.page}'", file=sys.stderr)
        sys.exit(1)

    start_title = page_title_from_path(path_map[start])
    start_deg = degree_of(start, forward, reverse)

    records = build_neighbor_records(
        start, args.direction, forward, reverse, path_map, bodies, summaries, wiki_dir,
    )

    use_diverse = args.diverse or start_deg > DIVERSE_THRESHOLD
    if use_diverse:
        records = diverse_sample(records, args.limit)
    else:
        records.sort(key=lambda r: -r["degree"])
        records = records[:args.limit]

    if args.json:
        print(json.dumps({
            "page": start_title,
            "slug": start,
            "degree": start_deg,
            "direction_filter": args.direction,
            "diversified": use_diverse,
            "neighbors": records,
        }, indent=2))
    else:
        render_human(start_title, start_deg, records, use_diverse)


if __name__ == "__main__":
    main()
