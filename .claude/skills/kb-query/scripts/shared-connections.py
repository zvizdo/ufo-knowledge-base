#!/usr/bin/env python3
"""Find pages that two wiki pages both connect to via [[wikilinks]].

Usage:
    python shared-connections.py <wiki-dir> "<Page A>" "<Page B>"

Output:
    - Common outbound links (pages both A and B link to)
    - Common inbound links (pages that link to both A and B)
    - Exclusive connections (pages only one links to, for contrast)
"""

import sys
import re
from collections import defaultdict
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

    parser = argparse.ArgumentParser(description="Find shared connections between two wiki pages")
    parser.add_argument("wiki_dir", help="Path to the wiki/ directory")
    parser.add_argument("page_a", help="First page title")
    parser.add_argument("page_b", help="Second page title")
    args = parser.parse_args()

    wiki_dir = Path(args.wiki_dir)
    if not wiki_dir.is_dir():
        print(f"Error: {wiki_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    forward, reverse, title_map = build_graphs(wiki_dir)

    a = resolve_title(args.page_a, title_map)
    b = resolve_title(args.page_b, title_map)

    if a is None:
        print(f"Page not found: '{args.page_a}'", file=sys.stderr)
        sys.exit(1)
    if b is None:
        print(f"Page not found: '{args.page_b}'", file=sys.stderr)
        sys.exit(1)

    a_display = display_title(a, title_map)
    b_display = display_title(b, title_map)

    a_out = forward.get(a, set()) - {b}
    b_out = forward.get(b, set()) - {a}
    a_in = reverse.get(a, set()) - {b}
    b_in = reverse.get(b, set()) - {a}

    # Direct connection
    a_links_b = b in forward.get(a, set())
    b_links_a = a in forward.get(b, set())

    print(f"Shared connections between [[{a_display}]] and [[{b_display}]]:\n")

    if a_links_b or b_links_a:
        print("  Direct connection:")
        if a_links_b:
            print(f"    [[{a_display}]] → [[{b_display}]]")
        if b_links_a:
            print(f"    [[{b_display}]] → [[{a_display}]]")
        print()

    # Common outbound
    common_out = a_out & b_out
    if common_out:
        print(f"  Both link to ({len(common_out)}):")
        for p in sorted(common_out):
            print(f"    - [[{display_title(p, title_map)}]]")
        print()
    else:
        print("  No common outbound links.\n")

    # Common inbound
    common_in = a_in & b_in
    if common_in:
        print(f"  Both linked from ({len(common_in)}):")
        for p in sorted(common_in):
            print(f"    - [[{display_title(p, title_map)}]]")
        print()
    else:
        print("  No common inbound links.\n")

    # Exclusive connections (for contrast)
    only_a_out = a_out - b_out
    only_b_out = b_out - a_out

    if only_a_out or only_b_out:
        print("  Exclusive connections:")
        if only_a_out:
            print(f"    Only [[{a_display}]] links to: {', '.join(f'[[{display_title(p, title_map)}]]' for p in sorted(only_a_out))}")
        if only_b_out:
            print(f"    Only [[{b_display}]] links to: {', '.join(f'[[{display_title(p, title_map)}]]' for p in sorted(only_b_out))}")
        print()

    # Summary
    total_shared = len(common_out) + len(common_in)
    if total_shared == 0:
        print("  These pages share no connections. They may be in different clusters.")
    else:
        print(f"  Total shared connections: {total_shared}")


if __name__ == "__main__":
    main()
