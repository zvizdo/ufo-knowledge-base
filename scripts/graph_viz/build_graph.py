"""Walk ufo-kb/wiki, parse wikilinks, dump a JSON graph.

Output: scripts/graph_viz/graph.json
  {
    "nodes": [{"id": slug, "folder": "concepts" | "entities/people" | ... ,
                "type": "concept" | "person" | "transcript" | ... ,
                "degree": int,
                "exists": bool}],
    "edges": [[src_slug, dst_slug], ...]   (undirected, deduped)
  }
"""
from __future__ import annotations
import json, os, re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WIKI = ROOT / "ufo-kb" / "wiki"
OUT = Path(__file__).parent / "graph.json"

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")

def slugify(s: str) -> str:
    return s.strip().lower().replace(" ", "-")

def folder_of(rel_path: Path) -> str:
    parts = rel_path.parts
    if parts[0] == "entities" and len(parts) > 1:
        return f"entities/{parts[1]}"
    return parts[0]

TYPE_MAP = {
    "concepts": "concept",
    "synthesis": "synthesis",
    "youtube-transcripts": "transcript",
    "entities/people": "person",
    "entities/organizations": "org",
    "entities/places": "place",
    "entities/programs": "program",
    "entities/incidents": "incident",
    "entities/documents": "document",
    "entities/tech-artifacts": "tech",
    "entities/craft-phenomena": "craft",
    "entities/symbols-glyphs": "symbol",
}

def main() -> None:
    nodes: dict[str, dict] = {}     # slug -> {folder, type, exists}
    edges: set[tuple[str, str]] = set()
    raw_links: dict[str, set[str]] = defaultdict(set)

    for path in WIKI.rglob("*.md"):
        rel = path.relative_to(WIKI)
        slug = path.stem
        folder = folder_of(rel)
        nodes[slug] = {
            "folder": folder,
            "type": TYPE_MAP.get(folder, "other"),
            "exists": True,
        }
        with open(path, encoding="utf-8") as fp:
            txt = fp.read()
        for m in WIKILINK_RE.finditer(txt):
            target = slugify(m.group(1))
            if target == slug:
                continue
            raw_links[slug].add(target)

    # Materialize edges; tag any unknown targets as dangling stubs.
    for src, dsts in raw_links.items():
        for dst in dsts:
            if dst not in nodes:
                nodes[dst] = {"folder": "dangling", "type": "dangling", "exists": False}
            a, b = sorted((src, dst))
            edges.add((a, b))

    deg: dict[str, int] = defaultdict(int)
    for a, b in edges:
        deg[a] += 1
        deg[b] += 1

    out_nodes = [
        {"id": slug, "degree": deg[slug], **meta}
        for slug, meta in nodes.items()
    ]

    OUT.write_text(json.dumps({
        "nodes": out_nodes,
        "edges": sorted(edges),
    }, indent=None, separators=(",", ":")))

    print(f"nodes: {len(out_nodes)}")
    print(f"edges: {len(edges)}")
    print(f"existing nodes: {sum(1 for n in out_nodes if n['exists'])}")
    print(f"dangling nodes: {sum(1 for n in out_nodes if not n['exists'])}")
    print(f"max degree: {max(deg.values())}")
    print(f"wrote {OUT}")

if __name__ == "__main__":
    main()
