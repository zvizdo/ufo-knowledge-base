#!/usr/bin/env python3
"""Find densely connected clusters of wiki pages and bridge pages between them.

Usage:
    python cluster-detection.py <wiki-dir> [--min-cluster 3] [--iterations 10]

Uses label propagation for community detection — each node adopts the most
common label among its neighbors, iterating until stable.

Output:
    - Clusters (groups of tightly connected pages)
    - Bridge pages (pages connecting multiple clusters)
    - Hub pages (high-degree pages that may need splitting)
    - Isolated pages (not in any meaningful cluster)
"""

import sys
import re
import random
from collections import defaultdict, Counter
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

    # Undirected neighbors
    neighbors: dict[str, set[str]] = defaultdict(set)
    for page in title_map:
        neighbors[page] = (forward.get(page, set()) | reverse.get(page, set())) & set(title_map.keys())

    return neighbors, title_map


def label_propagation(
    neighbors: dict[str, set[str]], pages: list[str], iterations: int = 10
) -> dict[str, int]:
    """Run label propagation to detect communities."""
    # Initialize: each node gets its own label
    labels: dict[str, int] = {page: i for i, page in enumerate(pages)}

    for _ in range(iterations):
        changed = False
        # Process nodes in random order
        order = list(pages)
        random.shuffle(order)

        for node in order:
            nbrs = neighbors.get(node, set())
            if not nbrs:
                continue

            # Count neighbor labels
            label_counts: Counter = Counter()
            for nbr in nbrs:
                if nbr in labels:
                    label_counts[labels[nbr]] += 1

            if not label_counts:
                continue

            # Adopt most common label (break ties randomly)
            max_count = max(label_counts.values())
            candidates = [l for l, c in label_counts.items() if c == max_count]
            new_label = random.choice(candidates)

            if new_label != labels[node]:
                labels[node] = new_label
                changed = True

        if not changed:
            break

    return labels


def display_title(title_lower: str, title_map: dict[str, Path]) -> str:
    if title_lower in title_map:
        return page_title_from_path(title_map[title_lower])
    return title_lower


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Detect clusters in wiki graph")
    parser.add_argument("wiki_dir", help="Path to the wiki/ directory")
    parser.add_argument("--min-cluster", type=int, default=3, help="Minimum cluster size to report (default: 3)")
    parser.add_argument("--iterations", type=int, default=10, help="Label propagation iterations (default: 10)")
    args = parser.parse_args()

    wiki_dir = Path(args.wiki_dir)
    if not wiki_dir.is_dir():
        print(f"Error: {wiki_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    neighbors, title_map = build_graph(wiki_dir)
    pages = list(title_map.keys())

    if not pages:
        print("No pages found in wiki directory.")
        sys.exit(0)

    # Run label propagation (multiple times for stability)
    random.seed(42)
    labels = label_propagation(neighbors, pages, args.iterations)

    # Group pages by cluster
    clusters: dict[int, list[str]] = defaultdict(list)
    for page, label in labels.items():
        clusters[label].append(page)

    # Sort clusters by size
    sorted_clusters = sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True)

    # Identify bridge pages (connected to pages in multiple clusters)
    bridge_pages: list[tuple[str, set[int]]] = []
    for page in pages:
        nbr_clusters = set()
        for nbr in neighbors.get(page, set()):
            if nbr in labels:
                nbr_clusters.add(labels[nbr])
        if len(nbr_clusters) > 1:
            bridge_pages.append((page, nbr_clusters))

    bridge_pages.sort(key=lambda x: len(x[1]), reverse=True)

    # Identify hub pages (high degree)
    degree = {page: len(neighbors.get(page, set())) for page in pages}
    hub_threshold = max(10, sum(degree.values()) / len(pages) * 3) if pages else 10
    hubs = [(p, d) for p, d in degree.items() if d >= hub_threshold]
    hubs.sort(key=lambda x: x[1], reverse=True)

    # Report
    print(f"Graph: {len(pages)} pages, {sum(degree.values()) // 2} edges")
    print(f"Average degree: {sum(degree.values()) / len(pages):.1f}\n")

    # Clusters
    significant_clusters = [(cid, members) for cid, members in sorted_clusters if len(members) >= args.min_cluster]
    print(f"Clusters (>= {args.min_cluster} pages): {len(significant_clusters)}\n")

    for i, (cid, members) in enumerate(significant_clusters, 1):
        print(f"  Cluster {i} ({len(members)} pages):")
        for m in sorted(members):
            deg = degree.get(m, 0)
            print(f"    - [[{display_title(m, title_map)}]] (degree {deg})")
        print()

    # Bridge pages
    if bridge_pages:
        print(f"Bridge pages ({len(bridge_pages)} connecting multiple clusters):\n")
        for page, cluster_ids in bridge_pages[:10]:
            print(f"  - [[{display_title(page, title_map)}]] bridges {len(cluster_ids)} clusters")
        if len(bridge_pages) > 10:
            print(f"  ... and {len(bridge_pages) - 10} more")
        print()

    # Hubs
    if hubs:
        print(f"Hub pages (degree >= {hub_threshold:.0f}):\n")
        for page, deg in hubs[:10]:
            print(f"  - [[{display_title(page, title_map)}]] (degree {deg}) — consider splitting?")
        print()

    # Isolated pages
    isolated = [p for p in pages if degree.get(p, 0) == 0]
    if isolated:
        print(f"Isolated pages ({len(isolated)}, no connections):\n")
        for p in sorted(isolated):
            print(f"  - [[{display_title(p, title_map)}]]")
        print()


if __name__ == "__main__":
    main()
