#!/usr/bin/env python3
"""Extract YAML frontmatter from wiki pages without reading full content.

Usage:
    python frontmatter.py <wiki-dir> [<glob-pattern>] [--fields summary,type,tags]

Arguments:
    wiki-dir        Path to the wiki/ directory
    glob-pattern    Optional glob to filter pages (default: **/*.md)
    --fields        Comma-separated list of frontmatter fields to show (default: all)

Output:
    One block per page: filename and requested frontmatter fields.

Examples:
    python frontmatter.py wiki/
    python frontmatter.py wiki/ "entities/*.md" --fields summary,type,tags
    python frontmatter.py wiki/ "concepts/*.md" --fields summary
"""

import argparse
import sys
from pathlib import Path


def extract_frontmatter(filepath: Path) -> dict[str, str]:
    """Read only the YAML frontmatter block from a markdown file."""
    try:
        lines = filepath.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return {}

    if not lines or lines[0].strip() != "---":
        return {}

    fields = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def main():
    parser = argparse.ArgumentParser(description="Extract frontmatter from wiki pages")
    parser.add_argument("wiki_dir", type=Path, help="Path to the wiki/ directory")
    parser.add_argument("pattern", nargs="?", default="**/*.md",
                        help="Glob pattern to filter pages (default: **/*.md)")
    parser.add_argument("--fields", type=str, default=None,
                        help="Comma-separated fields to display (default: all)")
    args = parser.parse_args()

    wiki_dir = args.wiki_dir.resolve()
    if not wiki_dir.is_dir():
        print(f"Error: {wiki_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    filter_fields = [f.strip() for f in args.fields.split(",")] if args.fields else None

    pages = sorted(wiki_dir.glob(args.pattern))
    if not pages:
        print("No pages found.")
        return

    for page in pages:
        fm = extract_frontmatter(page)
        if not fm:
            continue

        if filter_fields:
            fm = {k: v for k, v in fm.items() if k in filter_fields}
            if not fm:
                continue

        rel = page.relative_to(wiki_dir)
        print(f"[[{page.stem}]] ({rel})")
        for key, value in fm.items():
            print(f"  {key}: {value}")
        print()


if __name__ == "__main__":
    main()
