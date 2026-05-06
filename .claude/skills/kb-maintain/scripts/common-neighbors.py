#!/usr/bin/env python3
"""Surface pages that share many neighbors but don't link to each other.

Usage:
    python common-neighbors.py <wiki-dir> [--min-common 2] [--top 20]

Classic link prediction: if A and B both link to (or are linked from) many of
the same pages but don't link to each other, they probably should.
"""

import sys
import re
from collections import defaultdict
from itertools import combinations
from pathlib import Path


WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]*?)?\]\]")


def parse_wikilinks(filepath: Path) -> list[str]:
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return [m.strip() for m in WIKILINK_RE.findall(text)]


def page_title_from_path(filepath: Path) -> str:
    return filepath.stem


def build_graph(wiki_dir: Path) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, Path]]:
    forward: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    title_map: dict[str, Path] = {}

    for f in wiki_dir.rglob("*.md"):
        title = page_title_from_path(f).lower()
        title_map[title] = f
        links = parse_wikilinks(f)
        for link in links:
            link_lower = link.lower()
            forward[title].add(link_lower)
            reverse[link_lower].add(title)

    return forward, reverse, title_map


def display_title(title_lower: str, title_map: dict[str, Path]) -> str:
    if title_lower in title_map:
        return page_title_from_path(title_map[title_lower])
    return title_lower


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Common neighbors link prediction")
    parser.add_argument("wiki_dir", help="Path to the wiki/ directory")
    parser.add_argument("--min-common", type=int, default=2, help="Minimum common neighbors (default: 2)")
    parser.add_argument("--top", type=int, default=20, help="Max results (default: 20)")
    args = parser.parse_args()

    wiki_dir = Path(args.wiki_dir)
    if not wiki_dir.is_dir():
        print(f"Error: {wiki_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    forward, reverse, title_map = build_graph(wiki_dir)

    # Undirected neighbors
    neighbors: dict[str, set[str]] = defaultdict(set)
    for page in title_map:
        neighbors[page] = forward.get(page, set()) | reverse.get(page, set())

    # Direct connections
    connected: dict[str, set[str]] = defaultdict(set)
    for page in title_map:
        connected[page] = forward.get(page, set()) | reverse.get(page, set())

    pages = list(title_map.keys())
    predictions: list[tuple[int, str, str, list[str]]] = []

    for a, b in combinations(pages, 2):
        if b in connected.get(a, set()):
            continue

        common = neighbors.get(a, set()) & neighbors.get(b, set())
        if len(common) >= args.min_common:
            predictions.append((len(common), a, b, sorted(common)))

    predictions.sort(key=lambda x: x[0], reverse=True)
    predictions = predictions[:args.top]

    if not predictions:
        print(f"No page pairs found with >= {args.min_common} common neighbors.")
        sys.exit(0)

    print(f"Pages sharing neighbors but not directly linked (min {args.min_common}):\n")
    for count, a, b, common in predictions:
        a_display = display_title(a, title_map)
        b_display = display_title(b, title_map)
        common_display = ", ".join(f"[[{display_title(c, title_map)}]]" for c in common[:5])
        more = f" (+{len(common) - 5} more)" if len(common) > 5 else ""
        print(f"  {count} shared  [[{a_display}]] ↔ [[{b_display}]]")
        print(f"           Via: {common_display}{more}")
        print()

    print(f"Total predictions: {len(predictions)}")


if __name__ == "__main__":
    main()
