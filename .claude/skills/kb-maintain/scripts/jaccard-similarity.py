#!/usr/bin/env python3
"""Predict missing links via Jaccard similarity of link neighborhoods.

Usage:
    python jaccard-similarity.py <wiki-dir> [--threshold 0.3] [--top 20]

For every pair of pages that are NOT directly linked, computes:
    J(A, B) = |neighbors(A) ∩ neighbors(B)| / |neighbors(A) ∪ neighbors(B)|

High similarity + no direct link = strong candidate for a missing connection.
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


def build_graph(wiki_dir: Path) -> tuple[dict[str, set[str]], dict[str, Path]]:
    """Build undirected neighbor sets (union of outbound and inbound links)."""
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

    # Undirected neighbors = outbound ∪ inbound
    neighbors: dict[str, set[str]] = defaultdict(set)
    for page in title_map:
        neighbors[page] = forward.get(page, set()) | reverse.get(page, set())

    # Direct connections (either direction)
    direct: dict[str, set[str]] = defaultdict(set)
    for page in title_map:
        direct[page] = forward.get(page, set()) | reverse.get(page, set())

    return neighbors, direct, title_map


def display_title(title_lower: str, title_map: dict[str, Path]) -> str:
    if title_lower in title_map:
        return page_title_from_path(title_map[title_lower])
    return title_lower


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Jaccard similarity link prediction")
    parser.add_argument("wiki_dir", help="Path to the wiki/ directory")
    parser.add_argument("--threshold", type=float, default=0.3, help="Minimum Jaccard score (default: 0.3)")
    parser.add_argument("--top", type=int, default=20, help="Max results to show (default: 20)")
    args = parser.parse_args()

    wiki_dir = Path(args.wiki_dir)
    if not wiki_dir.is_dir():
        print(f"Error: {wiki_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    neighbors, direct, title_map = build_graph(wiki_dir)
    pages = list(title_map.keys())

    predictions: list[tuple[float, str, str, set[str]]] = []

    for a, b in combinations(pages, 2):
        # Skip if already directly connected
        if b in direct.get(a, set()):
            continue

        n_a = neighbors.get(a, set())
        n_b = neighbors.get(b, set())

        if not n_a or not n_b:
            continue

        intersection = n_a & n_b
        union = n_a | n_b

        if not union:
            continue

        jaccard = len(intersection) / len(union)

        if jaccard >= args.threshold:
            predictions.append((jaccard, a, b, intersection))

    predictions.sort(key=lambda x: x[0], reverse=True)
    predictions = predictions[:args.top]

    if not predictions:
        print("No missing link predictions above threshold.")
        print(f"Total pages: {len(pages)}")
        sys.exit(0)

    print(f"Suggested missing links (Jaccard >= {args.threshold}):\n")
    for score, a, b, shared in predictions:
        a_display = display_title(a, title_map)
        b_display = display_title(b, title_map)
        shared_display = ", ".join(f"[[{display_title(s, title_map)}]]" for s in sorted(shared)[:5])
        more = f" (+{len(shared) - 5} more)" if len(shared) > 5 else ""
        print(f"  {score:.3f}  [[{a_display}]] ↔ [[{b_display}]]")
        print(f"         Shared neighbors: {shared_display}{more}")
        print()

    print(f"Total predictions: {len(predictions)}")


if __name__ == "__main__":
    main()
