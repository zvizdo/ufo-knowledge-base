#!/usr/bin/env python3
"""Return all pages within N hops of a starting page via [[wikilinks]].

Usage:
    python neighborhood.py <wiki-dir> "<Page Name>" [--hops N] [--direction both|out|in]

Arguments:
    wiki-dir    Path to the wiki/ directory
    Page Name   Title of the starting page (case-insensitive match)
    --hops      Number of hops to traverse (default: 2)
    --direction Link direction: 'out' (follows links), 'in' (follows backlinks), 'both' (default)

Output:
    Pages grouped by hop distance from the starting page.
"""

import sys
import re
from collections import defaultdict, deque
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


def build_graphs(wiki_dir: Path) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, Path]]:
    """Build forward and reverse adjacency lists.

    Returns:
        forward: page -> pages it links to
        reverse: page -> pages that link to it
        title_map: lowercase title -> Path
    """
    forward: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    title_map: dict[str, Path] = {}

    for f in wiki_dir.rglob("*.md"):
        title = page_title_from_path(f)
        title_lower = title.lower()
        title_map[title_lower] = f
        links = parse_wikilinks(f)
        for link in links:
            link_lower = link.lower()
            forward[title_lower].add(link_lower)
            reverse[link_lower].add(title_lower)

    return forward, reverse, title_map


def get_neighborhood(
    forward: dict[str, set[str]],
    reverse: dict[str, set[str]],
    start: str,
    max_hops: int,
    direction: str = "both",
) -> dict[int, set[str]]:
    """BFS to find all pages within max_hops of start.

    Returns dict mapping hop distance -> set of page titles.
    """
    visited: dict[str, int] = {start: 0}
    queue = deque([start])
    by_distance: dict[int, set[str]] = defaultdict(set)

    while queue:
        node = queue.popleft()
        dist = visited[node]
        if dist > 0:
            by_distance[dist].add(node)
        if dist >= max_hops:
            continue

        neighbors: set[str] = set()
        if direction in ("out", "both"):
            neighbors |= forward.get(node, set())
        if direction in ("in", "both"):
            neighbors |= reverse.get(node, set())

        for neighbor in neighbors:
            if neighbor not in visited:
                visited[neighbor] = dist + 1
                queue.append(neighbor)

    return by_distance


def resolve_title(query: str, title_map: dict[str, Path]) -> str | None:
    query_lower = query.lower()
    if query_lower in title_map:
        return query_lower
    matches = [t for t in title_map if query_lower in t]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Ambiguous: '{query}' matches: {', '.join(matches)}", file=sys.stderr)
        return matches[0]
    return None


def display_title(title_lower: str, title_map: dict[str, Path]) -> str:
    if title_lower in title_map:
        return page_title_from_path(title_map[title_lower])
    return title_lower


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Find neighborhood of a wiki page")
    parser.add_argument("wiki_dir", help="Path to the wiki/ directory")
    parser.add_argument("page", help="Starting page title")
    parser.add_argument("--hops", type=int, default=2, help="Number of hops (default: 2)")
    parser.add_argument("--direction", choices=["both", "out", "in"], default="both",
                        help="Link direction (default: both)")
    args = parser.parse_args()

    wiki_dir = Path(args.wiki_dir)
    if not wiki_dir.is_dir():
        print(f"Error: {wiki_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    forward, reverse, title_map = build_graphs(wiki_dir)

    start = resolve_title(args.page, title_map)
    if start is None:
        print(f"Page not found: '{args.page}'", file=sys.stderr)
        print(f"Available pages: {', '.join(sorted(title_map.keys()))}", file=sys.stderr)
        sys.exit(1)

    neighborhood = get_neighborhood(forward, reverse, start, args.hops, args.direction)

    total = sum(len(pages) for pages in neighborhood.values())
    start_display = display_title(start, title_map)
    print(f"Neighborhood of [[{start_display}]] ({total} pages within {args.hops} hops):\n")

    for dist in sorted(neighborhood.keys()):
        pages = neighborhood[dist]
        print(f"  {dist} hop{'s' if dist != 1 else ''} ({len(pages)} pages):")
        for p in sorted(pages):
            display = display_title(p, title_map)
            # Show link direction
            links_to = p in forward.get(start, set()) or any(
                p in forward.get(mid, set()) for mid in forward.get(start, set())
            )
            linked_from = start in forward.get(p, set()) or any(
                start in forward.get(mid, set()) for mid in reverse.get(start, set())
            )
            print(f"    - [[{display}]]")
        print()


if __name__ == "__main__":
    main()
