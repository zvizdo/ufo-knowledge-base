#!/usr/bin/env python3
"""Predict graph connections for newly imported / updated pages.

Usage:
    python predict-connections.py <wiki-dir> --slugs slug1,slug2,slug3 [options]

For each input slug, computes three signals using only graph topology
(no embeddings, no qmd) — mirroring kb-query's "embeddings to enter,
graph to ground" rule:

    1. Jaccard ≥ threshold (symmetric neighborhood overlap)
    2. Adamic-Adar (rare-intermediary weighted common neighbors)
    3. Common-neighbors ≥ min-common (raw shared-context signal)

Candidates that are already linked (forward or reverse) are filtered out.

Each candidate ships with anchor sentences pulled from the candidate's page
body — the line(s) where shared neighbors appear — so the LLM has diagnostic
prose, not just slug pairs, to decide whether the suggested link is real.

Output is Markdown by default; --json for programmatic use.

Options:
    --slugs        Comma-separated list of slugs (touched pages). Required.
    --jaccard-threshold   Minimum Jaccard score (default: 0.3)
    --jaccard-top         Top-N Jaccard candidates per slug (default: 10)
    --aa-top              Top-N Adamic-Adar candidates per slug (default: 20)
    --cn-min              Minimum common neighbors (default: 3)
    --cn-top              Top-N common-neighbors candidates per slug (default: 10)
    --max-anchors         Max anchor sentences per candidate (default: 2)
    --json                Emit JSON instead of Markdown.

Examples:
    python predict-connections.py wiki/ --slugs david-grusch,mk-ultra
    python predict-connections.py wiki/ --slugs jim-semivan --jaccard-threshold 0.25
    python predict-connections.py wiki/ --slugs eric-davis --json
"""

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path


WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]*?)?\]\]")


# ---------- File parsing ----------

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
            fm[key.strip()] = value.strip()
    if body_start is None:
        return fm, ""
    return fm, "".join(lines[body_start:])


def extract_anchor_sentence(body: str, link_target: str, max_chars: int = 200) -> str:
    """Return the cleaned line where [[link_target]] appears (lowercase match)."""
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
                return clean[: max_chars - 1].rstrip() + "…"
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


# ---------- Graph build ----------

class Graph:
    """Single-pass graph build over a wiki/ directory.

    forward[slug]    : set of slugs this page links to
    reverse[slug]    : set of slugs that link to this page
    neighbors[slug]  : forward ∪ reverse (undirected adjacency)
    bodies[slug]     : raw body text (used for anchor sentences)
    summaries[slug]  : frontmatter summary
    path_map[slug]   : Path object on disk
    degree[slug]     : len(neighbors[slug])
    """

    def __init__(self, wiki_dir: Path):
        self.wiki_dir = wiki_dir.resolve()
        self.path_map: dict[str, Path] = {}
        self.bodies: dict[str, str] = {}
        self.summaries: dict[str, str] = {}
        self.forward: dict[str, set[str]] = defaultdict(set)
        self.reverse: dict[str, set[str]] = defaultdict(set)

        for f in self.wiki_dir.rglob("*.md"):
            slug = page_title_from_path(f).lower()
            self.path_map[slug] = f
            try:
                text = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            fm, body = split_frontmatter(text)
            self.bodies[slug] = body
            self.summaries[slug] = fm.get("summary", "").strip().strip('"').strip("'")
            for link in WIKILINK_RE.findall(body):
                link_slug = link.strip().lower()
                if not link_slug or link_slug == slug:
                    continue
                self.forward[slug].add(link_slug)
                self.reverse[link_slug].add(slug)

        self.neighbors: dict[str, set[str]] = {}
        for slug in self.path_map:
            self.neighbors[slug] = self.forward.get(slug, set()) | self.reverse.get(slug, set())
        self.degree: dict[str, int] = {s: len(n) for s, n in self.neighbors.items()}

    def folder_of(self, slug: str) -> str:
        return folder_of(slug, self.path_map, self.wiki_dir)

    def title_of(self, slug: str) -> str:
        if slug in self.path_map:
            return page_title_from_path(self.path_map[slug])
        return slug


# ---------- Candidate pre-filtering ----------

def candidate_set(graph: Graph, slug: str) -> set[str]:
    """All pages that share at least one neighbor with `slug` and aren't already
    linked to it. Limits the O(n²) search to a much smaller candidate pool."""
    own_neighbors = graph.neighbors.get(slug, set())
    if not own_neighbors:
        return set()
    candidates: set[str] = set()
    for z in own_neighbors:
        # Pages that also have z as a neighbor (i.e. z's own neighborhood).
        # z may not exist as a page (dangling link); skip if so.
        if z not in graph.path_map:
            # z is a dangling target; skip — we can't expand through it.
            continue
        for other in graph.neighbors.get(z, set()):
            if other == slug:
                continue
            if other not in graph.path_map:
                continue  # candidate must be a real page to suggest a link
            if other in own_neighbors:
                continue  # already linked
            candidates.add(other)
    return candidates


# ---------- Scorers ----------

def jaccard(a_neighbors: set[str], b_neighbors: set[str]) -> tuple[float, set[str]]:
    if not a_neighbors or not b_neighbors:
        return 0.0, set()
    inter = a_neighbors & b_neighbors
    union = a_neighbors | b_neighbors
    if not union:
        return 0.0, set()
    return len(inter) / len(union), inter


def adamic_adar(a_neighbors: set[str], b_neighbors: set[str], degree: dict[str, int]) -> tuple[float, list[tuple[str, float]]]:
    common = a_neighbors & b_neighbors
    if not common:
        return 0.0, []
    score = 0.0
    contribs: list[tuple[str, float]] = []
    for z in common:
        d = degree.get(z, 0)
        if d <= 1:
            continue
        contribution = 1.0 / math.log(d)
        score += contribution
        contribs.append((z, contribution))
    contribs.sort(key=lambda t: t[1], reverse=True)
    return score, contribs


# ---------- Anchor extraction ----------

def best_anchors(graph: Graph, candidate: str, shared: list[str], max_anchors: int) -> list[tuple[str, str]]:
    """For a candidate page, find anchor sentences where shared neighbors appear.

    Tries shared neighbors in order (caller passes them sorted by signal).
    Returns up to max_anchors (shared_slug, sentence) pairs.
    """
    body = graph.bodies.get(candidate, "")
    if not body:
        return []
    out: list[tuple[str, str]] = []
    seen_sentences: set[str] = set()
    for s in shared:
        sentence = extract_anchor_sentence(body, s)
        if not sentence or sentence in seen_sentences:
            continue
        seen_sentences.add(sentence)
        out.append((s, sentence))
        if len(out) >= max_anchors:
            break
    return out


# ---------- Per-slug prediction ----------

def predict_for_slug(
    graph: Graph,
    slug: str,
    jaccard_threshold: float,
    jaccard_top: int,
    aa_top: int,
    cn_min: int,
    cn_top: int,
    max_anchors: int,
) -> dict:
    """Compute Jaccard / Adamic-Adar / Common-Neighbors candidates for slug."""
    if slug not in graph.path_map:
        return {
            "slug": slug,
            "exists": False,
            "folder": "missing",
            "degree": 0,
            "neighbors": 0,
            "jaccard": [],
            "adamic_adar": [],
            "common_neighbors": [],
        }

    a_neighbors = graph.neighbors.get(slug, set())
    candidates = candidate_set(graph, slug)

    jaccard_results: list[dict] = []
    aa_results: list[dict] = []
    cn_results: list[dict] = []

    for cand in candidates:
        b_neighbors = graph.neighbors.get(cand, set())

        # Jaccard
        j_score, j_shared = jaccard(a_neighbors, b_neighbors)
        if j_score >= jaccard_threshold:
            shared_sorted = sorted(j_shared, key=lambda s: -graph.degree.get(s, 0))
            anchors = best_anchors(graph, cand, shared_sorted, max_anchors)
            jaccard_results.append({
                "score": round(j_score, 4),
                "candidate": cand,
                "candidate_title": graph.title_of(cand),
                "candidate_folder": graph.folder_of(cand),
                "candidate_degree": graph.degree.get(cand, 0),
                "candidate_summary": graph.summaries.get(cand, "")[:200],
                "shared": shared_sorted[:8],
                "shared_count": len(j_shared),
                "union_count": len(a_neighbors | b_neighbors),
                "anchors": [{"shared": s, "sentence": sent} for s, sent in anchors],
            })

        # Adamic-Adar
        aa_score, aa_contribs = adamic_adar(a_neighbors, b_neighbors, graph.degree)
        if aa_score > 0:
            top_contribs = aa_contribs[:5]
            shared_sorted = [z for z, _ in top_contribs]
            anchors = best_anchors(graph, cand, shared_sorted, max_anchors)
            aa_results.append({
                "score": round(aa_score, 4),
                "candidate": cand,
                "candidate_title": graph.title_of(cand),
                "candidate_folder": graph.folder_of(cand),
                "candidate_degree": graph.degree.get(cand, 0),
                "candidate_summary": graph.summaries.get(cand, "")[:200],
                "intermediaries": [
                    {
                        "slug": z,
                        "title": graph.title_of(z),
                        "degree": graph.degree.get(z, 0),
                        "weight": round(w, 4),
                    }
                    for z, w in top_contribs
                ],
                "anchors": [{"shared": s, "sentence": sent} for s, sent in anchors],
            })

        # Common neighbors
        common = a_neighbors & b_neighbors
        if len(common) >= cn_min:
            shared_sorted = sorted(common, key=lambda s: -graph.degree.get(s, 0))
            anchors = best_anchors(graph, cand, shared_sorted, max_anchors)
            cn_results.append({
                "count": len(common),
                "candidate": cand,
                "candidate_title": graph.title_of(cand),
                "candidate_folder": graph.folder_of(cand),
                "candidate_degree": graph.degree.get(cand, 0),
                "candidate_summary": graph.summaries.get(cand, "")[:200],
                "shared": shared_sorted[:8],
                "anchors": [{"shared": s, "sentence": sent} for s, sent in anchors],
            })

    jaccard_results.sort(key=lambda r: (-r["score"], -r["candidate_degree"]))
    aa_results.sort(key=lambda r: (-r["score"], -r["candidate_degree"]))
    cn_results.sort(key=lambda r: (-r["count"], -r["candidate_degree"]))

    return {
        "slug": slug,
        "exists": True,
        "title": graph.title_of(slug),
        "folder": graph.folder_of(slug),
        "degree": graph.degree.get(slug, 0),
        "neighbors": len(a_neighbors),
        "jaccard": jaccard_results[:jaccard_top],
        "adamic_adar": aa_results[:aa_top],
        "common_neighbors": cn_results[:cn_top],
    }


# ---------- Rendering ----------

def render_markdown(results: list[dict], jaccard_threshold: float, cn_min: int, graph: "Graph") -> str:
    out: list[str] = []
    out.append(f"# Predicted connections — {len(results)} slug(s)\n")

    summary_rows: list[str] = []
    for r in results:
        if not r["exists"]:
            summary_rows.append(f"- **[[{r['slug']}]]** — page not found in wiki (skipped)")
            continue
        summary_rows.append(
            f"- **[[{r['title']}]]** ({r['folder']}, deg {r['degree']}): "
            f"{len(r['jaccard'])} Jaccard, {len(r['adamic_adar'])} AA, "
            f"{len(r['common_neighbors'])} CN"
        )
    out.append("## Summary\n")
    out.extend(summary_rows)
    out.append("")

    for r in results:
        if not r["exists"]:
            out.append(f"\n## [[{r['slug']}]] — NOT FOUND\n")
            out.append(f"This slug doesn't exist in `{r['folder']}`. Did you typo it?\n")
            continue

        out.append(f"\n## [[{r['title']}]] ({r['folder']}, deg {r['degree']})\n")

        # Jaccard
        out.append(f"### Jaccard candidates (threshold ≥ {jaccard_threshold}, top {len(r['jaccard'])})\n")
        if not r["jaccard"]:
            out.append("_None above threshold._\n")
        else:
            for row in r["jaccard"]:
                out.append(
                    f"- **{row['score']:.3f}** [[{row['candidate_title']}]] "
                    f"({row['candidate_folder']}, deg {row['candidate_degree']}) — "
                    f"{row['shared_count']} shared / {row['union_count']} union"
                )
                if row["candidate_summary"]:
                    out.append(f"  - summary: {row['candidate_summary']}")
                shared_links = ", ".join(f"[[{graph.title_of(s)}]]" for s in row["shared"])
                out.append(f"  - shared via: {shared_links}")
                for a in row["anchors"]:
                    out.append(f"  - on candidate's page (re [[{a['shared']}]]): \"{a['sentence']}\"")
            out.append("")

        # Adamic-Adar
        out.append(f"### Adamic-Adar candidates (top {len(r['adamic_adar'])})\n")
        if not r["adamic_adar"]:
            out.append("_No common neighbors via rare intermediaries._\n")
        else:
            for row in r["adamic_adar"]:
                out.append(
                    f"- **{row['score']:.3f}** [[{row['candidate_title']}]] "
                    f"({row['candidate_folder']}, deg {row['candidate_degree']})"
                )
                if row["candidate_summary"]:
                    out.append(f"  - summary: {row['candidate_summary']}")
                for inter in row["intermediaries"][:3]:
                    out.append(
                        f"  - via [[{inter['title']}]] (deg {inter['degree']}, weight {inter['weight']:.3f})"
                    )
                if len(row["intermediaries"]) > 3:
                    out.append(f"  - (+{len(row['intermediaries']) - 3} more intermediaries)")
                for a in row["anchors"]:
                    out.append(f"  - on candidate's page (re [[{a['shared']}]]): \"{a['sentence']}\"")
            out.append("")

        # Common neighbors
        out.append(f"### Common-neighbors candidates (≥ {cn_min}, top {len(r['common_neighbors'])})\n")
        if not r["common_neighbors"]:
            out.append("_No candidates with that many shared neighbors._\n")
        else:
            for row in r["common_neighbors"]:
                out.append(
                    f"- **{row['count']} shared** [[{row['candidate_title']}]] "
                    f"({row['candidate_folder']}, deg {row['candidate_degree']})"
                )
                if row["candidate_summary"]:
                    out.append(f"  - summary: {row['candidate_summary']}")
                shared_links = ", ".join(f"[[{graph.title_of(s)}]]" for s in row["shared"])
                out.append(f"  - shared via: {shared_links}")
                for a in row["anchors"]:
                    out.append(f"  - on candidate's page (re [[{a['shared']}]]): \"{a['sentence']}\"")
            out.append("")

    out.append("\n---\n")
    out.append("**How to read this report:**")
    out.append(
        "- **Jaccard** measures symmetric neighborhood overlap — high = same context, "
        "even if they have very different total degrees."
    )
    out.append(
        "- **Adamic-Adar** weighs shared neighbors by their rarity — a connection through "
        "a niche concept (low degree) is more informative than through a hub."
    )
    out.append(
        "- **Common-neighbors** is the raw shared-context count — coarse but reliable."
    )
    out.append(
        "- **None of these are auto-applied.** Curate against the anchor sentences: add only "
        "where the connection is real, not just topologically plausible."
    )
    return "\n".join(out)


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(
        description="Predict connections for newly imported / updated pages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("wiki_dir", type=Path, help="Path to wiki/ directory")
    parser.add_argument("--slugs", required=True, help="Comma-separated list of touched slugs")
    parser.add_argument("--jaccard-threshold", type=float, default=0.3,
                        help="Minimum Jaccard score (default: 0.3)")
    parser.add_argument("--jaccard-top", type=int, default=10,
                        help="Top-N Jaccard candidates per slug (default: 10)")
    parser.add_argument("--aa-top", type=int, default=20,
                        help="Top-N Adamic-Adar candidates per slug (default: 20)")
    parser.add_argument("--cn-min", type=int, default=3,
                        help="Minimum common neighbors (default: 3)")
    parser.add_argument("--cn-top", type=int, default=10,
                        help="Top-N common-neighbors candidates per slug (default: 10)")
    parser.add_argument("--max-anchors", type=int, default=2,
                        help="Max anchor sentences per candidate (default: 2)")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    wiki_dir = args.wiki_dir.resolve()
    if not wiki_dir.is_dir():
        print(f"Error: {wiki_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    slugs = [s.strip().lower() for s in args.slugs.split(",") if s.strip()]
    if not slugs:
        print("Error: --slugs must be a comma-separated list of at least one slug",
              file=sys.stderr)
        sys.exit(1)

    graph = Graph(wiki_dir)

    results = [
        predict_for_slug(
            graph,
            slug,
            jaccard_threshold=args.jaccard_threshold,
            jaccard_top=args.jaccard_top,
            aa_top=args.aa_top,
            cn_min=args.cn_min,
            cn_top=args.cn_top,
            max_anchors=args.max_anchors,
        )
        for slug in slugs
    ]

    if args.json:
        payload = {
            "wiki_dir": str(wiki_dir),
            "graph": {
                "pages": len(graph.path_map),
                "edges": sum(len(v) for v in graph.forward.values()),
            },
            "thresholds": {
                "jaccard": args.jaccard_threshold,
                "common_neighbors_min": args.cn_min,
            },
            "results": results,
        }
        print(json.dumps(payload, indent=2))
    else:
        print(render_markdown(results, args.jaccard_threshold, args.cn_min, graph))


if __name__ == "__main__":
    main()
