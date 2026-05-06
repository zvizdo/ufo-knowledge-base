#!/usr/bin/env python3
"""Find the shortest path(s) between two wiki pages via [[wikilinks]].

Usage:
    python shortest-path.py <wiki-dir> "<Page A>" "<Page B>" [--max-extra N]

Arguments:
    wiki-dir    Path to the wiki/ directory
    Page A      Title of the start page (case-insensitive match)
    Page B      Title of the target page (case-insensitive match)
    --max-extra Maximum extra hops beyond shortest to show (default: 1)

Output:
    All shortest paths between the two pages, plus near-shortest alternatives.
"""

import sys
import re
from collections import defaultdict, deque
from pathlib import Path


WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]*?)?\]\]")


def parse_wikilinks(filepath: Path) -> list[str]:
    """Extract all [[wikilink]] targets from a markdown file."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return [m.strip() for m in WIKILINK_RE.findall(text)]


def page_title_from_path(filepath: Path) -> str:
    """Derive a page title from its filename (without extension)."""
    return filepath.stem


def build_graph(wiki_dir: Path) -> tuple[dict[str, set[str]], dict[str, Path]]:
    """Build a bidirectional adjacency list from all markdown files' wikilinks.

    Links are treated as undirected: if A links to B, both A→B and B→A exist
    in the graph. Wikilinks express relationships, not one-way dependencies.

    Returns:
        graph: dict mapping page title (lowercase) -> set of neighbor page titles (lowercase)
        title_map: dict mapping lowercase title -> Path for display
    """
    graph: dict[str, set[str]] = defaultdict(set)
    title_map: dict[str, Path] = {}

    md_files = list(wiki_dir.rglob("*.md"))
    for f in md_files:
        title = page_title_from_path(f)
        title_lower = title.lower()
        title_map[title_lower] = f
        links = parse_wikilinks(f)
        for link in links:
            link_lower = link.lower()
            graph[title_lower].add(link_lower)
            graph[link_lower].add(title_lower)

    return graph, title_map


def find_all_shortest_paths(
    graph: dict[str, set[str]], start: str, end: str
) -> list[list[str]]:
    """BFS to find ALL shortest paths between start and end."""
    if start == end:
        return [[start]]

    # BFS tracking all parents
    visited_dist: dict[str, int] = {start: 0}
    parents: dict[str, list[str]] = defaultdict(list)
    queue = deque([start])
    found_dist = None

    while queue:
        node = queue.popleft()
        current_dist = visited_dist[node]

        if found_dist is not None and current_dist >= found_dist:
            break

        for neighbor in graph.get(node, set()):
            if neighbor not in visited_dist:
                visited_dist[neighbor] = current_dist + 1
                parents[neighbor].append(node)
                queue.append(neighbor)
                if neighbor == end:
                    found_dist = current_dist + 1
            elif visited_dist[neighbor] == current_dist + 1:
                parents[neighbor].append(node)

    if end not in parents and start != end:
        return []

    # Reconstruct all shortest paths
    paths: list[list[str]] = []

    def backtrack(node: str, path: list[str]):
        if node == start:
            paths.append(list(reversed(path)))
            return
        for parent in parents[node]:
            path.append(parent)
            backtrack(parent, path)
            path.pop()

    backtrack(end, [end])
    return paths


def find_near_shortest_paths(
    graph: dict[str, set[str]], start: str, end: str, max_extra: int = 1
) -> list[list[str]]:
    """Find paths up to max_extra hops longer than the shortest."""
    shortest = find_all_shortest_paths(graph, start, end)
    if not shortest:
        return []

    shortest_len = len(shortest[0])
    max_len = shortest_len + max_extra

    # DFS with depth limit for near-shortest paths
    near_paths: list[list[str]] = []

    def dfs(node: str, target: str, path: list[str], visited: set[str]):
        if len(path) > max_len:
            return
        if node == target:
            if len(path) > shortest_len:
                near_paths.append(list(path))
            return
        for neighbor in graph.get(node, set()):
            if neighbor not in visited:
                visited.add(neighbor)
                path.append(neighbor)
                dfs(neighbor, target, path, visited)
                path.pop()
                visited.discard(neighbor)

    visited = {start}
    dfs(start, end, [start], visited)
    return near_paths


def resolve_title(query: str, title_map: dict[str, Path]) -> str | None:
    """Resolve a user query to a page title (case-insensitive)."""
    query_lower = query.lower()
    if query_lower in title_map:
        return query_lower
    # Partial match
    matches = [t for t in title_map if query_lower in t]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Ambiguous: '{query}' matches: {', '.join(matches)}", file=sys.stderr)
        return matches[0]
    return None


def format_path(path: list[str], title_map: dict[str, Path]) -> str:
    """Format a path for display with proper casing."""
    parts = []
    for p in path:
        if p in title_map:
            parts.append(f"[[{page_title_from_path(title_map[p])}]]")
        else:
            parts.append(f"[[{p}]]")
    return " → ".join(parts)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Find shortest paths between wiki pages")
    parser.add_argument("wiki_dir", help="Path to the wiki/ directory")
    parser.add_argument("page_a", help="Start page title")
    parser.add_argument("page_b", help="Target page title")
    parser.add_argument("--max-extra", type=int, default=1, help="Max extra hops beyond shortest (default: 1)")
    args = parser.parse_args()

    wiki_dir = Path(args.wiki_dir)
    if not wiki_dir.is_dir():
        print(f"Error: {wiki_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    graph, title_map = build_graph(wiki_dir)

    start = resolve_title(args.page_a, title_map)
    end = resolve_title(args.page_b, title_map)

    if start is None:
        print(f"Page not found: '{args.page_a}'", file=sys.stderr)
        print(f"Available pages: {', '.join(sorted(title_map.keys()))}", file=sys.stderr)
        sys.exit(1)
    if end is None:
        print(f"Page not found: '{args.page_b}'", file=sys.stderr)
        sys.exit(1)

    shortest = find_all_shortest_paths(graph, start, end)

    if not shortest:
        print(f"No path found between '{args.page_a}' and '{args.page_b}'")
        sys.exit(0)

    print(f"Shortest paths ({len(shortest[0]) - 1} hops):\n")
    for i, path in enumerate(shortest, 1):
        print(f"  {i}. {format_path(path, title_map)}")

    if args.max_extra > 0:
        near = find_near_shortest_paths(graph, start, end, args.max_extra)
        if near:
            print(f"\nNear-shortest paths (+{args.max_extra} hop{'s' if args.max_extra > 1 else ''}):\n")
            for i, path in enumerate(near, 1):
                print(f"  {i}. {format_path(path, title_map)} ({len(path) - 1} hops)")


if __name__ == "__main__":
    main()
