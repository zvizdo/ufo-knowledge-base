#!/usr/bin/env python3
"""Weighted link prediction using the Adamic-Adar index.

Usage:
    python adamic-adar.py <wiki-dir> [--top 20]

Adamic-Adar weighs shared connections through rare (low-degree) intermediate
pages more heavily than through hubs:

    AA(A, B) = Σ 1/log(degree(z)) for all common neighbors z

A shared link through a niche concept page (degree 3) is more informative than
one through a broad hub page (degree 30).
"""

import sys
import re
import math
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

    parser = argparse.ArgumentParser(description="Adamic-Adar link prediction")
    parser.add_argument("wiki_dir", help="Path to the wiki/ directory")
    parser.add_argument("--top", type=int, default=20, help="Max results (default: 20)")
    args = parser.parse_args()

    wiki_dir = Path(args.wiki_dir)
    if not wiki_dir.is_dir():
        print(f"Error: {wiki_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    forward, reverse, title_map = build_graph(wiki_dir)

    # Undirected neighbors and degree
    neighbors: dict[str, set[str]] = defaultdict(set)
    for page in title_map:
        neighbors[page] = forward.get(page, set()) | reverse.get(page, set())

    degree: dict[str, int] = {page: len(neighbors[page]) for page in title_map}

    # Direct connections
    connected: dict[str, set[str]] = defaultdict(set)
    for page in title_map:
        connected[page] = forward.get(page, set()) | reverse.get(page, set())

    pages = list(title_map.keys())
    predictions: list[tuple[float, str, str, list[tuple[str, float]]]] = []

    for a, b in combinations(pages, 2):
        if b in connected.get(a, set()):
            continue

        common = neighbors.get(a, set()) & neighbors.get(b, set())
        if not common:
            continue

        score = 0.0
        contributions: list[tuple[str, float]] = []
        for z in common:
            deg = degree.get(z, 1)
            if deg <= 1:
                continue
            contribution = 1.0 / math.log(deg)
            score += contribution
            contributions.append((z, contribution))

        if score > 0:
            contributions.sort(key=lambda x: x[1], reverse=True)
            predictions.append((score, a, b, contributions))

    predictions.sort(key=lambda x: x[0], reverse=True)
    predictions = predictions[:args.top]

    if not predictions:
        print("No link predictions found.")
        sys.exit(0)

    print(f"Adamic-Adar link predictions (top {args.top}):\n")
    for score, a, b, contributions in predictions:
        a_display = display_title(a, title_map)
        b_display = display_title(b, title_map)
        print(f"  {score:.3f}  [[{a_display}]] ↔ [[{b_display}]]")
        # Show top contributing intermediaries
        for z, contrib in contributions[:3]:
            z_display = display_title(z, title_map)
            z_deg = degree.get(z, 0)
            print(f"         via [[{z_display}]] (degree {z_deg}, weight {contrib:.3f})")
        if len(contributions) > 3:
            print(f"         (+{len(contributions) - 3} more intermediaries)")
        print()

    print(f"Total predictions: {len(predictions)}")


if __name__ == "__main__":
    main()
