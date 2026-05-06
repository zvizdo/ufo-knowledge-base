#!/usr/bin/env python3
"""Render the activated subgraph from a walk as Mermaid + JSON.

Given a list of slugs that the walker visited, this script:

- Reconstructs the induced subgraph (edges between those nodes only)
- Emits a Mermaid `graph LR` block suitable for embedding in Markdown
- Emits a JSON sidecar with nodes (title, type, folder, degree) and edges (direction)

Pass --anchors to include the anchor sentence on each edge in the JSON output.

Usage:
    python render-provenance.py <wiki-dir> <slug1> <slug2> [<slug3> ...]
                                [--seed <slug>] [--anchors] [--out <file>]

Examples:
    python render-provenance.py wiki/ david-grusch eric-davis harold-malmgren 1933-magenta-crash
    python render-provenance.py wiki/ aatip aawsap uap-task-force --seed aatip --anchors
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


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
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
            fm[key.strip()] = value.strip().strip('"').strip("'")
    if body_start is None:
        return fm, ""
    return fm, "".join(lines[body_start:])


def extract_anchor_sentence(body: str, link_target: str, max_chars: int = 200) -> str:
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


def folder_of(slug: str, path_map: dict[str, Path], wiki_dir: Path) -> str:
    p = path_map.get(slug)
    if p is None:
        return "missing"
    rel = p.relative_to(wiki_dir)
    parts = rel.parts
    return "/".join(parts[:-1]) if len(parts) > 1 else "."


def build_index(wiki_dir: Path):
    path_map: dict[str, Path] = {}
    metadata: dict[str, dict[str, str]] = {}
    bodies: dict[str, str] = {}
    forward: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    for f in wiki_dir.rglob("*.md"):
        slug = page_title_from_path(f).lower()
        path_map[slug] = f
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            metadata[slug] = {}
            bodies[slug] = ""
            continue
        fm, body = split_frontmatter(text)
        metadata[slug] = fm
        bodies[slug] = body
        for link in WIKILINK_RE.findall(body):
            link_slug = link.strip().lower()
            if link_slug == slug:
                continue
            forward[slug].add(link_slug)
            reverse[link_slug].add(slug)
    return path_map, metadata, bodies, forward, reverse


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
        print(f"Ambiguous: '{query}' → {matches[0]}", file=sys.stderr)
        return matches[0]
    return None


def mermaid_id(slug: str) -> str:
    """Produce a Mermaid-safe node ID."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", slug)


def render_mermaid(nodes: list[dict], edges: list[dict], seed: str | None) -> str:
    lines = ["```mermaid", "graph LR"]
    for n in nodes:
        nid = mermaid_id(n["slug"])
        label = n["title"].replace('"', "'")
        if n.get("is_seed"):
            lines.append(f'    {nid}(["{label}"]):::seed')
        elif n["type"] == "synthesis":
            lines.append(f'    {nid}["{label}"]:::synthesis')
        elif n["type"] == "concept":
            lines.append(f'    {nid}["{label}"]:::concept')
        else:
            lines.append(f'    {nid}["{label}"]')
    for e in edges:
        a = mermaid_id(e["from"])
        b = mermaid_id(e["to"])
        if e["direction"] == "both":
            lines.append(f"    {a} <--> {b}")
        else:
            lines.append(f"    {a} --> {b}")
    lines.append("    classDef seed fill:#fde68a,stroke:#92400e,stroke-width:2px;")
    lines.append("    classDef synthesis fill:#bbf7d0,stroke:#065f46;")
    lines.append("    classDef concept fill:#bfdbfe,stroke:#1e40af;")
    lines.append("```")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Render the activated subgraph from a walk")
    parser.add_argument("wiki_dir", type=Path)
    parser.add_argument("slugs", nargs="+", help="Slugs of pages visited during the walk")
    parser.add_argument("--seed", action="append", default=[],
                        help="Mark slug(s) as seed nodes (highlighted in mermaid). Repeatable.")
    parser.add_argument("--anchors", action="store_true",
                        help="Include anchor sentence on each edge in the JSON output")
    parser.add_argument("--out", type=Path, default=None,
                        help="Write output to file instead of stdout")
    args = parser.parse_args()

    wiki_dir = args.wiki_dir.resolve()
    if not wiki_dir.is_dir():
        print(f"Error: {wiki_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    path_map, metadata, bodies, forward, reverse = build_index(wiki_dir)

    resolved: list[str] = []
    for q in args.slugs:
        s = resolve_slug(q, path_map)
        if s is None:
            print(f"Page not found: '{q}'", file=sys.stderr)
            sys.exit(1)
        if s not in resolved:
            resolved.append(s)
    seed_slugs = {resolve_slug(s, path_map) for s in args.seed}
    seed_slugs.discard(None)

    node_set = set(resolved)
    nodes = []
    for slug in resolved:
        fm = metadata.get(slug, {})
        nodes.append({
            "slug": slug,
            "title": page_title_from_path(path_map[slug]),
            "type": fm.get("type", ""),
            "summary": fm.get("summary", ""),
            "folder": folder_of(slug, path_map, wiki_dir),
            "degree": len(forward.get(slug, set()) | reverse.get(slug, set())),
            "is_seed": slug in seed_slugs,
        })

    # Induced edges
    edges: list[dict] = []
    seen_pairs = set()
    for a in resolved:
        for b in forward.get(a, set()):
            if b not in node_set:
                continue
            pair = tuple(sorted([a, b]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            reverse_link = a in forward.get(b, set())
            direction = "both" if reverse_link else "forward"
            edge = {
                "from": a,
                "to": b,
                "direction": direction,
            }
            if args.anchors:
                fwd_anchor = extract_anchor_sentence(bodies.get(a, ""), b)
                bwd_anchor = extract_anchor_sentence(bodies.get(b, ""), a)
                if fwd_anchor:
                    edge["anchor_forward"] = fwd_anchor
                if bwd_anchor:
                    edge["anchor_backward"] = bwd_anchor
            edges.append(edge)

    mermaid_block = render_mermaid(nodes, edges, None)
    payload = {
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }

    out_text = mermaid_block + "\n\n```json\n" + json.dumps(payload, indent=2) + "\n```\n"

    if args.out:
        args.out.write_text(out_text, encoding="utf-8")
        print(f"Wrote provenance to {args.out}", file=sys.stderr)
    else:
        print(out_text)


if __name__ == "__main__":
    main()
