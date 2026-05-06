#!/usr/bin/env python3
"""Render a path A → B → C with sentence-level citations from each page.

Given a sequence of page slugs/titles, this script extracts — for each consecutive
pair — the line on the predecessor page where the wikilink to the successor appears.
If the predecessor doesn't link to the successor directly but the successor links
back, the reverse anchor is used instead (paths are bidirectional in this KB).

The output is the citation backbone of any path-cited answer.

Usage:
    python linearize-path.py <wiki-dir> <slug1> <slug2> [<slug3> ...] [--json] [--max-chars N]

Examples:
    python linearize-path.py wiki/ david-grusch eric-davis 1933-magenta-crash
    python linearize-path.py wiki/ aatip aawsap uap-task-force --json
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]*?)?\]\]")


def page_title_from_path(filepath: Path) -> str:
    return filepath.stem


def split_frontmatter(text: str) -> str:
    """Return body without the leading frontmatter block."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return text
    body_start = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body_start = i + 1
            break
    if body_start is None:
        return ""
    return "".join(lines[body_start:])


def extract_anchor_sentence(body: str, link_target: str, max_chars: int = 240) -> str:
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
    path_map: dict[str, Path] = {}
    bodies: dict[str, str] = {}
    forward: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    for f in wiki_dir.rglob("*.md"):
        slug = page_title_from_path(f).lower()
        path_map[slug] = f
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            bodies[slug] = ""
            continue
        body = split_frontmatter(text)
        bodies[slug] = body
        for link in WIKILINK_RE.findall(body):
            link_slug = link.strip().lower()
            if link_slug == slug:
                continue
            forward[slug].add(link_slug)
            reverse[link_slug].add(slug)
    return path_map, bodies, forward, reverse


def resolve_slug(query: str, path_map: dict[str, Path]) -> str | None:
    q = query.lower().strip()
    if q in path_map:
        return q
    matches = [t for t in path_map if q in t]
    if len(matches) == 1:
        return matches[0]
    if matches:
        exact = [t for t in matches if t == q]
        if exact:
            return exact[0]
        print(f"Ambiguous: '{query}' matches {len(matches)} pages. Using {matches[0]}.", file=sys.stderr)
        return matches[0]
    return None


def linearize(path: list[str], path_map, bodies, forward, reverse, max_chars: int):
    """Return a list of {from, to, direction, anchor, exists} for each hop."""
    hops: list[dict] = []
    for a, b in zip(path, path[1:]):
        a_title = page_title_from_path(path_map[a]) if a in path_map else a
        b_title = page_title_from_path(path_map[b]) if b in path_map else b
        forward_anchor = extract_anchor_sentence(bodies.get(a, ""), b, max_chars)
        backward_anchor = extract_anchor_sentence(bodies.get(b, ""), a, max_chars)
        # Pick the strongest direction
        if forward_anchor:
            hops.append({
                "from": a, "from_title": a_title,
                "to": b, "to_title": b_title,
                "direction": "forward",
                "anchor": forward_anchor,
                "anchor_source": a,
                "edge_exists": b in forward.get(a, set()),
            })
        elif backward_anchor:
            hops.append({
                "from": a, "from_title": a_title,
                "to": b, "to_title": b_title,
                "direction": "backward",
                "anchor": backward_anchor,
                "anchor_source": b,
                "edge_exists": a in forward.get(b, set()),
            })
        else:
            hops.append({
                "from": a, "from_title": a_title,
                "to": b, "to_title": b_title,
                "direction": "missing",
                "anchor": "",
                "anchor_source": None,
                "edge_exists": (b in forward.get(a, set())) or (a in forward.get(b, set())),
            })
    return hops


def render_human(hops: list[dict]):
    if not hops:
        print("Empty path.")
        return
    print("Linearized path:\n")
    for h in hops:
        if h["direction"] == "forward":
            arrow = "→"
        elif h["direction"] == "backward":
            arrow = "←"
        else:
            arrow = "?"
        print(f"  [[{h['from_title']}]] {arrow} [[{h['to_title']}]]")
        if h["anchor"]:
            source_title = page_title_from_path(Path(h['anchor_source'])) if h.get("anchor_source") else "?"
            print(f"    (per [[{h['anchor_source']}]]) \"{h['anchor']}\"")
        else:
            note = "no anchor sentence found" if h["edge_exists"] else "edge does not exist in graph"
            print(f"    [{note}]")
        print()


def main():
    parser = argparse.ArgumentParser(description="Linearize a graph path with sentence-level citations")
    parser.add_argument("wiki_dir", type=Path)
    parser.add_argument("path", nargs="+", help="Sequence of page slugs/titles forming the path")
    parser.add_argument("--max-chars", type=int, default=240, help="Max chars per anchor sentence")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    wiki_dir = args.wiki_dir.resolve()
    if not wiki_dir.is_dir():
        print(f"Error: {wiki_dir} is not a directory", file=sys.stderr)
        sys.exit(1)
    if len(args.path) < 2:
        print("Error: path must contain at least 2 nodes.", file=sys.stderr)
        sys.exit(1)

    path_map, bodies, forward, reverse = build_index(wiki_dir)
    resolved = []
    for q in args.path:
        slug = resolve_slug(q, path_map)
        if slug is None:
            print(f"Page not found: '{q}'", file=sys.stderr)
            sys.exit(1)
        resolved.append(slug)

    hops = linearize(resolved, path_map, bodies, forward, reverse, args.max_chars)

    if args.json:
        print(json.dumps({
            "path": [page_title_from_path(path_map[s]) for s in resolved],
            "slugs": resolved,
            "hops": hops,
        }, indent=2))
    else:
        render_human(hops)


if __name__ == "__main__":
    main()
