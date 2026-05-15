#!/usr/bin/env python3
"""Comprehensive KB audit — constitution lint + structural health checks.

The CONSTITUTION is the spec. Maintenance enforces it.

Subcommands (single graph build per run):

    all            run every check (default)
    constitution   per-folder frontmatter, Connections section, concept-link, naming
    dangling       wikilinks pointing to non-existent pages
    orphans        pages with 0 inbound links
    islands        small disconnected components (size 2-10 outside the giant component)
    duplicates     alias-collision + neighborhood-overlap merge candidates
    collisions     same slug used by >1 file path (graph deduplicates silently)
    synthesis      derived-from existence + reciprocal back-link enforcement
    stubs          short-body + low-degree pages, severity scaled by neighbor importance
    bridges        pages bridging >=3 clusters that are themselves stubs
    hubs           multi-criterion split candidates

Auto-fix scope (with --apply, default is dry-run):

    1. Reciprocal back-links from `derived-from` (synthesis check)
    2. Single-candidate dangling-link rewrite (dangling check)

Anything else (merges, splits, content edits, conflict callouts, alias additions)
is flagged for the user with evidence and a suggested action — never auto-applied.

Usage:
    python audit.py <wiki-dir> [check] [--apply] [--json]

Examples:
    python audit.py ufo-kb/wiki/ all
    python audit.py ufo-kb/wiki/ constitution
    python audit.py ufo-kb/wiki/ dangling --apply
    python audit.py ufo-kb/wiki/ synthesis --apply
"""

import argparse
import difflib
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]*?)?\]\]")
H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
CONFLICT_CALLOUT_RE = re.compile(r"^>\s*[⚠!]+\s*(?:\*\*)?Conflict", re.MULTILINE | re.IGNORECASE)
FUZZY_THRESHOLD = 0.7

# CONSTITUTION schema — folder (relative to wiki root) → required frontmatter fields.
# Required *sections* are deliberately not enforced beyond `Connections` (real pages diverge).
ENTITY_SCHEMAS = {
    "entities/people": {
        "required_frontmatter": ["name", "aliases", "roles", "firsthand_claims", "tags"],
        "filename_re": re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$"),
    },
    "entities/organizations": {
        "required_frontmatter": ["name", "aliases", "type", "tags"],
        "filename_re": re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
    },
    "entities/programs": {
        "required_frontmatter": ["name", "aliases", "status", "tags"],
        "filename_re": re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
    },
    "entities/places": {
        "required_frontmatter": ["name", "aliases", "type", "tags"],
        "filename_re": re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
    },
    "entities/incidents": {
        "required_frontmatter": ["name", "date", "tags"],
        "filename_re": re.compile(r"^\d{4}-[a-z0-9]+(?:-[a-z0-9]+)*$"),
    },
    "entities/craft-phenomena": {
        "required_frontmatter": ["name", "aliases", "category", "tags"],
        "filename_re": re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
    },
    "entities/documents": {
        "required_frontmatter": ["title", "authors", "date", "type", "tags"],
        "filename_re": re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
    },
    "entities/tech-artifacts": {
        "required_frontmatter": ["name", "category", "tags"],
        "filename_re": re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
    },
    "entities/symbols-glyphs": {
        "required_frontmatter": ["name", "aliases", "type", "tags"],
        "filename_re": re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# Frontmatter parsing (stdlib-only YAML subset)
# ──────────────────────────────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, list[str], str]:
    """Return (singletons, list_field_names, body).

    Singletons: top-level scalar fields (string values).
    list_field_names: names of fields that have list/block values (presence-only).
    Body: text after the closing ---.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, [], text
    fm: dict[str, str] = {}
    list_fields: list[str] = []
    body_start = None
    i = 1
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            body_start = i + 1
            break
        if line and not line[0].isspace() and ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                # Inline list
                inner = value[1:-1].strip()
                if inner:
                    list_fields.append(key)
                else:
                    list_fields.append(key)  # empty list is still a "list field"
                fm[key] = value
            elif value == "" or value == "|":
                # Block list / block scalar — peek next lines for `  - ` items
                j = i + 1
                has_items = False
                while j < len(lines):
                    nxt = lines[j]
                    if nxt and not nxt[0].isspace() and ":" in nxt and nxt.strip() != "":
                        break
                    if nxt.strip() == "---":
                        break
                    if nxt.strip().startswith("- "):
                        has_items = True
                    j += 1
                if has_items:
                    list_fields.append(key)
                fm[key] = ""
            else:
                fm[key] = value.strip('"').strip("'")
        i += 1
    if body_start is None:
        return fm, list_fields, ""
    return fm, list_fields, "".join(lines[body_start:])


def parse_inline_list(value: str) -> list[str]:
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        return []
    inner = value[1:-1].strip()
    if not inner:
        return []
    items: list[str] = []
    for chunk in re.split(r",(?![^\[]*\])", inner):
        item = chunk.strip().strip('"').strip("'")
        if item:
            items.append(item)
    return items


def parse_block_list(text: str, key: str) -> list[str]:
    """Extract items from a YAML block list with the given key."""
    pattern = re.compile(rf"^{re.escape(key)}:\s*$\n((?:[ \t]+-\s+.*(?:\n|$))+)", re.MULTILINE)
    m = pattern.search(text)
    if not m:
        return []
    items: list[str] = []
    for line in m.group(1).splitlines():
        s = line.strip()
        if s.startswith("- "):
            v = s[2:].strip().strip('"').strip("'")
            if v:
                items.append(v)
    return items


def get_aliases(filepath: Path, fm_singletons: dict, body: str) -> list[str]:
    """Return parsed aliases for a page."""
    text = filepath.read_text(encoding="utf-8")
    val = fm_singletons.get("aliases", "")
    if val.startswith("[") and val.endswith("]"):
        return parse_inline_list(val)
    return parse_block_list(text, "aliases")


def get_derived_from(filepath: Path, fm_singletons: dict) -> list[str]:
    text = filepath.read_text(encoding="utf-8")
    val = fm_singletons.get("derived-from", "")
    if val.startswith("[") and val.endswith("]"):
        items = parse_inline_list(val)
    else:
        items = parse_block_list(text, "derived-from")
    return [item.strip().lower() for item in items if item.strip()]


def list_field_present(filepath: Path, key: str, fm_singletons: dict) -> bool:
    """True if the frontmatter has a non-empty list at `key`."""
    text = filepath.read_text(encoding="utf-8")
    val = fm_singletons.get(key, "")
    if val.startswith("[") and val.endswith("]"):
        return len(parse_inline_list(val)) > 0
    return len(parse_block_list(text, key)) > 0


# ──────────────────────────────────────────────────────────────────────────────
# Graph builder (single pass)
# ──────────────────────────────────────────────────────────────────────────────

class Graph:
    """Shared in-memory graph. Built once, consumed by every detector."""

    def __init__(self, wiki_dir: Path):
        self.wiki_dir = wiki_dir
        self.path_map: dict[str, Path] = {}
        self.slug_paths: dict[str, list[Path]] = defaultdict(list)  # all paths sharing a slug (collisions)
        self.fm: dict[str, dict] = {}
        self.list_fields: dict[str, list[str]] = {}
        self.bodies: dict[str, str] = {}
        self.body_lines: dict[str, int] = {}
        self.headings: dict[str, list[str]] = {}
        self.has_connections: dict[str, bool] = {}
        self.has_conflict_callout: dict[str, bool] = {}
        self.aliases: dict[str, list[str]] = {}
        self.derived_from: dict[str, list[str]] = {}
        # Adjacency
        self.forward: dict[str, set[str]] = defaultdict(set)
        self.reverse: dict[str, set[str]] = defaultdict(set)
        self.all_link_targets: dict[str, set[str]] = defaultdict(set)  # includes dangling
        self.link_lines: dict[tuple[str, str], int] = {}  # (page_slug, link_target) → line number
        # Cluster labels (filled by run_label_propagation)
        self.labels: dict[str, int] = {}

        self._build()

    def _build(self):
        for f in self.wiki_dir.rglob("*.md"):
            slug = f.stem.lower()
            self.slug_paths[slug].append(f)
            self.path_map[slug] = f
            try:
                text = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            fm_singletons, list_fields, body = parse_frontmatter(text)
            self.fm[slug] = fm_singletons
            self.list_fields[slug] = list_fields
            self.bodies[slug] = body
            self.body_lines[slug] = sum(1 for ln in body.splitlines() if ln.strip())
            self.headings[slug] = [m.group(1).strip() for m in H2_RE.finditer(body)]
            self.has_connections[slug] = any(h.lower() == "connections" for h in self.headings[slug])
            self.has_conflict_callout[slug] = bool(CONFLICT_CALLOUT_RE.search(body))
            self.aliases[slug] = get_aliases(f, fm_singletons, body)
            self.derived_from[slug] = get_derived_from(f, fm_singletons)

            # Parse wikilinks per line so we can report line numbers
            for lineno, line in enumerate(body.splitlines(), start=1):
                for m in WIKILINK_RE.finditer(line):
                    target = m.group(1).strip().lower()
                    if target == slug:
                        continue
                    self.all_link_targets[slug].add(target)
                    self.link_lines.setdefault((slug, target), lineno)

        # Build adjacency restricted to existing pages for forward/reverse
        for slug, targets in self.all_link_targets.items():
            for t in targets:
                if t in self.path_map:
                    self.forward[slug].add(t)
                    self.reverse[t].add(slug)

    def folder_of(self, slug: str) -> str:
        p = self.path_map.get(slug)
        if p is None:
            return ""
        rel = p.relative_to(self.wiki_dir)
        parts = rel.parts
        return "/".join(parts[:-1]) if len(parts) > 1 else ""

    def title_of(self, slug: str) -> str:
        p = self.path_map.get(slug)
        return p.stem if p else slug

    def degree(self, slug: str) -> int:
        return len(self.forward.get(slug, set()) | self.reverse.get(slug, set()))

    def neighbors(self, slug: str) -> set[str]:
        return self.forward.get(slug, set()) | self.reverse.get(slug, set())

    def is_entity(self, slug: str) -> bool:
        return self.folder_of(slug).startswith("entities/")

    def schema_for(self, slug: str) -> dict | None:
        folder = self.folder_of(slug)
        return ENTITY_SCHEMAS.get(folder)

    # Cluster labels
    def run_label_propagation(self, iterations: int = 10, seed: int = 42):
        random.seed(seed)
        # Sorted slugs for deterministic ordering across runs
        slugs = sorted(self.path_map.keys())
        labels = {s: i for i, s in enumerate(slugs)}
        for _ in range(iterations):
            changed = False
            order = list(slugs)
            random.shuffle(order)
            for node in order:
                nbrs = sorted(self.neighbors(node))  # sorted for determinism
                if not nbrs:
                    continue
                counts: Counter = Counter()
                for nbr in nbrs:
                    if nbr in labels:
                        counts[labels[nbr]] += 1
                if not counts:
                    continue
                max_count = max(counts.values())
                cands = sorted(l for l, c in counts.items() if c == max_count)
                new_label = random.choice(cands)
                if new_label != labels[node]:
                    labels[node] = new_label
                    changed = True
            if not changed:
                break
        self.labels = labels

    def cluster_fan(self, slug: str) -> int:
        """Cluster fan = number of distinct label-propagation clusters in neighborhood."""
        nbrs = self.neighbors(slug)
        return len({self.labels[n] for n in nbrs if n in self.labels})

    def folder_fan(self, slug: str) -> int:
        """Folder fan = number of distinct full-path folders in neighborhood.

        More robust than `cluster_fan` on graphs where label-propagation collapses
        into 2-3 mega-clusters. A page whose neighbors span entities/people +
        concepts + entities/programs is structurally a hub regardless of
        how clustering shakes out. Uses full paths so entities/people and
        entities/programs count as distinct.
        """
        nbrs = self.neighbors(slug)
        folders = set()
        for n in nbrs:
            folder = self.folder_of(n)
            if folder:
                folders.add(folder)
        return len(folders)


# ──────────────────────────────────────────────────────────────────────────────
# Findings model
# ──────────────────────────────────────────────────────────────────────────────

class Finding:
    __slots__ = ("slug", "folder", "issue_type", "severity", "evidence",
                 "suggested_action", "auto_fixable", "apply_payload")

    def __init__(self, slug, folder, issue_type, severity, evidence,
                 suggested_action, auto_fixable=False, apply_payload=None):
        self.slug = slug
        self.folder = folder
        self.issue_type = issue_type
        self.severity = severity  # "critical" | "high" | "medium" | "low"
        self.evidence = evidence
        self.suggested_action = suggested_action
        self.auto_fixable = auto_fixable
        self.apply_payload = apply_payload  # dict carrying data needed to fix

    def to_dict(self):
        return {
            "slug": self.slug,
            "folder": self.folder,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "evidence": self.evidence,
            "suggested_action": self.suggested_action,
            "auto_fixable": self.auto_fixable,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Inline fuzzy resolver (for dangling-link auto-fix)
# ──────────────────────────────────────────────────────────────────────────────

def normalize_text(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[-_/.,]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def fuzzy_resolve(query: str, graph: Graph) -> tuple[list[tuple[str, float]], str]:
    """Return ([(slug, score)], stage) candidates for the query string.

    Stages: 'exact' (slug/alias exact match) → 'substring' (proper-fraction overlap)
    → 'fuzzy' (difflib SequenceMatcher).

    Substring scoring: q in key → len(q)/len(key); key in q → len(key)/len(q).
    This avoids the "mit" matching "david smith" trap (3/11 = 0.27, not 1.0).

    The caller decides what to do with each stage. Auto-fix only on stage 'exact'
    with exactly one result — substring and fuzzy are suggestions only.
    """
    q_norm = normalize_text(query)
    if not q_norm:
        return [], "none"

    # Build lookup: normalized-string → [(slug, kind)]
    lookup: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for slug in graph.path_map:
        lookup[normalize_text(slug)].append((slug, "slug"))
        for alias in graph.aliases.get(slug, []):
            lookup[normalize_text(alias)].append((slug, "alias"))

    # Stage 1: exact
    exact = lookup.get(q_norm, [])
    if exact:
        seen = set()
        out: list[tuple[str, float]] = []
        for slug, _ in exact:
            if slug in seen:
                continue
            seen.add(slug)
            out.append((slug, 1.0))
        return out, "exact"

    # Stage 2: substring (proper-fraction scoring)
    subs: dict[str, float] = {}
    for key, entries in lookup.items():
        if q_norm == key:
            continue  # handled in exact stage
        if q_norm in key:
            score = len(q_norm) / len(key) if key else 0.0
        elif key in q_norm:
            score = len(key) / len(q_norm) if q_norm else 0.0
        else:
            continue
        for slug, _ in entries:
            if score > subs.get(slug, 0.0):
                subs[slug] = score
    if subs:
        return sorted(subs.items(), key=lambda x: -x[1]), "substring"

    # Stage 3: difflib fuzzy
    keys = list(lookup.keys())
    fuzz = difflib.get_close_matches(q_norm, keys, n=20, cutoff=0.6)
    fuzz_hits: dict[str, float] = {}
    for k in fuzz:
        score = difflib.SequenceMatcher(None, q_norm, k).ratio()
        for slug, _ in lookup[k]:
            if score > fuzz_hits.get(slug, 0.0):
                fuzz_hits[slug] = score
    if fuzz_hits:
        return sorted(fuzz_hits.items(), key=lambda x: -x[1]), "fuzzy"
    return [], "none"


# ──────────────────────────────────────────────────────────────────────────────
# Detectors
# ──────────────────────────────────────────────────────────────────────────────

def detect_constitution(g: Graph) -> list[Finding]:
    findings: list[Finding] = []
    for slug, path in g.path_map.items():
        folder = g.folder_of(slug)
        schema = g.schema_for(slug)
        fm = g.fm.get(slug, {})
        list_fields = set(g.list_fields.get(slug, []))

        if schema is not None:
            # Required frontmatter
            missing = []
            for field in schema["required_frontmatter"]:
                # Field is present if singleton has a non-empty value OR field appears as list
                singleton_val = fm.get(field, "")
                if field in list_fields:
                    continue
                if singleton_val and not singleton_val.startswith("["):
                    continue
                if field in list_fields:
                    continue
                # Re-check via re-parse for list presence (covers inline empty [])
                if list_field_present(path, field, fm):
                    continue
                missing.append(field)
            if missing:
                findings.append(Finding(
                    slug=slug, folder=folder,
                    issue_type="constitution.missing-frontmatter",
                    severity="critical",
                    evidence=f"folder={folder}; missing required field(s): {', '.join(missing)}",
                    suggested_action=f"add to frontmatter: {', '.join(missing)}",
                ))

            # Naming convention
            fname_re = schema.get("filename_re")
            if fname_re and not fname_re.match(slug):
                findings.append(Finding(
                    slug=slug, folder=folder,
                    issue_type="constitution.naming-convention",
                    severity="critical",
                    evidence=f"slug '{slug}' does not match {fname_re.pattern}",
                    suggested_action="rename file to match folder convention (lowercase-hyphenated; incidents prefixed YYYY)",
                ))

        # Connections section: required for entity pages
        if g.is_entity(slug) and not g.has_connections.get(slug, False):
            findings.append(Finding(
                slug=slug, folder=folder,
                issue_type="constitution.missing-connections-section",
                severity="critical",
                evidence="entity page has no `## Connections` heading",
                suggested_action="append `## Connections` section surfacing non-obvious links",
            ))

        # Concept link: every entity page must link to >=1 page in wiki/concepts/
        if g.is_entity(slug):
            outbound = g.forward.get(slug, set())
            concept_links = {t for t in outbound if g.folder_of(t) == "concepts"}
            if not concept_links:
                findings.append(Finding(
                    slug=slug, folder=folder,
                    issue_type="constitution.no-concept-link",
                    severity="critical",
                    evidence="entity page links to 0 pages in wiki/concepts/",
                    suggested_action="link to >=1 concept page (typically credibility-frameworks for people, recurring-claims for documents, phenomenology-categories for incidents)",
                ))
    return findings


def detect_dangling(g: Graph, apply: bool = False) -> list[Finding]:
    """Find wikilinks whose target doesn't exist.

    Auto-fix gate: only when stage='exact' AND exactly one candidate. Substring
    and fuzzy candidates are *suggestions only* — never auto-applied. (A 'david
    smith' link must not be auto-rewritten to '[[mit]]' because 'mit' fuzzy-matches
    'smith'.) Exact stage means the dangling target is itself an alias or
    normalized-title of an existing page.
    """
    findings: list[Finding] = []
    for slug, targets in g.all_link_targets.items():
        for target in targets:
            if target in g.path_map:
                continue
            line = g.link_lines.get((slug, target), 0)
            cands, stage = fuzzy_resolve(target, g)
            auto_fixable = (stage == "exact" and len(cands) == 1)
            suggestion = ""
            apply_payload = None
            if auto_fixable:
                cand_slug, _ = cands[0]
                suggestion = f"rewrite [[{target}]] → [[{g.title_of(cand_slug)}]] (exact alias/title match)"
                apply_payload = {
                    "page_slug": slug,
                    "old_target": target,
                    "new_target_title": g.title_of(cand_slug),
                }
            elif cands:
                top = ", ".join(f"[[{g.title_of(s)}]] ({sc:.2f})" for s, sc in cands[:3])
                suggestion = f"{stage} candidates: {top} — pick one manually or remove link"
            else:
                suggestion = "no candidate found — create stub page or remove link"
            findings.append(Finding(
                slug=slug, folder=g.folder_of(slug),
                issue_type="dangling-link",
                severity="critical",
                evidence=f"line {line}: [[{target}]] → no target page exists",
                suggested_action=suggestion,
                auto_fixable=auto_fixable,
                apply_payload=apply_payload,
            ))
    return findings


def detect_orphans(g: Graph) -> list[Finding]:
    findings: list[Finding] = []
    for slug in g.path_map:
        # Skip synthesis index pages and concept hubs that are intentionally referenced from many places
        # but might still legitimately have 0 inbound (e.g. a brand-new page).
        if g.reverse.get(slug, set()):
            continue
        # Skip empty placeholder folders / readme-style pages by name heuristic
        findings.append(Finding(
            slug=slug, folder=g.folder_of(slug),
            issue_type="orphan",
            severity="high",
            evidence=f"0 inbound wikilinks; outbound={len(g.forward.get(slug, set()))}",
            suggested_action="add inbound links from related pages, or merge into a related entity if redundant",
        ))
    return findings


def detect_islands(g: Graph) -> list[Finding]:
    """Find connected components of size 2-10 outside the giant component."""
    visited: set[str] = set()
    components: list[list[str]] = []
    for slug in g.path_map:
        if slug in visited:
            continue
        # BFS over undirected adjacency
        stack = [slug]
        comp: list[str] = []
        while stack:
            s = stack.pop()
            if s in visited:
                continue
            visited.add(s)
            comp.append(s)
            for nbr in g.neighbors(s):
                if nbr not in visited:
                    stack.append(nbr)
        components.append(comp)
    if not components:
        return []
    components.sort(key=len, reverse=True)
    giant_size = len(components[0])
    findings: list[Finding] = []
    for comp in components[1:]:
        size = len(comp)
        if 2 <= size <= 10:
            members = ", ".join(f"[[{g.title_of(s)}]]" for s in sorted(comp))
            for s in comp:
                findings.append(Finding(
                    slug=s, folder=g.folder_of(s),
                    issue_type="island",
                    severity="high",
                    evidence=f"member of disconnected component (size {size}/{giant_size}): {members}",
                    suggested_action="link this component to the giant component via a relevant entity or concept page",
                ))
    return findings


def detect_duplicates(g: Graph) -> list[Finding]:
    """Page pairs with: alias overlap OR normalized-title similarity AND neighborhood Jaccard > 0.5."""
    findings: list[Finding] = []
    slugs = list(g.path_map.keys())

    # Build alias index
    alias_to_slug: dict[str, set[str]] = defaultdict(set)
    for s in slugs:
        for a in g.aliases.get(s, []):
            alias_to_slug[normalize_text(a)].add(s)
        alias_to_slug[normalize_text(s)].add(s)

    # Candidate pairs: anything sharing an alias OR title fuzz-match >= 0.7
    candidate_pairs: set[tuple[str, str]] = set()
    for entries in alias_to_slug.values():
        if len(entries) < 2:
            continue
        es = sorted(entries)
        for i in range(len(es)):
            for j in range(i + 1, len(es)):
                candidate_pairs.add((es[i], es[j]))

    # Title-similarity candidates (limit cost: only compare slugs that share a token)
    token_index: dict[str, set[str]] = defaultdict(set)
    for s in slugs:
        for tok in s.split("-"):
            if len(tok) >= 3:
                token_index[tok].add(s)
    for tok, group in token_index.items():
        if len(group) > 200:  # skip pathological tokens (the/and/etc — though these wouldn't appear in slugs)
            continue
        gs = sorted(group)
        for i in range(len(gs)):
            for j in range(i + 1, len(gs)):
                a, b = gs[i], gs[j]
                if (a, b) in candidate_pairs or (b, a) in candidate_pairs:
                    continue
                ratio = difflib.SequenceMatcher(None, a, b).ratio()
                if ratio >= 0.7:
                    candidate_pairs.add((a, b))

    seen_pairs = set()
    for a, b in candidate_pairs:
        if (a, b) in seen_pairs or (b, a) in seen_pairs:
            continue
        seen_pairs.add((a, b))
        # Skip if directly linked (probably already merged in spirit)
        if b in g.forward.get(a, set()) or a in g.forward.get(b, set()):
            continue
        n_a = g.neighbors(a)
        n_b = g.neighbors(b)
        if not n_a or not n_b:
            continue
        intersection = n_a & n_b
        union = n_a | n_b
        if not union:
            continue
        jaccard = len(intersection) / len(union)
        if jaccard < 0.5:
            continue
        # Build evidence
        shared_aliases = sorted(set(normalize_text(x) for x in g.aliases.get(a, [])) &
                                set(normalize_text(x) for x in g.aliases.get(b, [])))
        title_ratio = difflib.SequenceMatcher(None, a, b).ratio()
        evidence_bits = [
            f"neighborhood Jaccard {jaccard:.2f}",
            f"title similarity {title_ratio:.2f}",
        ]
        if shared_aliases:
            evidence_bits.append(f"shared aliases: {', '.join(shared_aliases)}")
        sample_shared = sorted(intersection)[:5]
        sample_str = ", ".join(f"[[{g.title_of(x)}]]" for x in sample_shared)
        if len(intersection) > 5:
            sample_str += f" (+{len(intersection) - 5} more)"
        evidence_bits.append(f"shared neighbors: {sample_str}")

        findings.append(Finding(
            slug=a, folder=g.folder_of(a),
            issue_type="duplicate-candidate",
            severity="high",
            evidence=f"candidate merge with [[{g.title_of(b)}]] — {'; '.join(evidence_bits)}",
            suggested_action=f"verify whether [[{g.title_of(a)}]] and [[{g.title_of(b)}]] are the same entity; if so merge",
        ))
    return findings


def detect_slug_collisions(g: Graph) -> list[Finding]:
    """Same slug used by >1 file path. Graph builds (and Obsidian) silently
    deduplicate by stem, so the duplicate(s) become invisible — incoming
    [[slug]] links collapse onto whichever file the walker picked last.

    Always critical: this corrupts graph integrity. Fix by merging the files
    (keeping one canonical path) or renaming one to a distinct slug.
    """
    findings: list[Finding] = []
    for slug, paths in g.slug_paths.items():
        if len(paths) < 2:
            continue
        rel = sorted(p.relative_to(g.wiki_dir).as_posix() for p in paths)
        for path in paths:
            findings.append(Finding(
                slug=slug, folder=g.folder_of(slug),
                issue_type="slug-collision",
                severity="critical",
                evidence=f"slug '{slug}' shared by {len(paths)} files: {', '.join(rel)}",
                suggested_action="merge into one canonical file, or rename one to a distinct slug; the graph currently treats them as a single node",
            ))
    return findings


def detect_synthesis(g: Graph, apply: bool = False) -> list[Finding]:
    """Synthesis-page health: derived-from existence + reciprocal back-link from each source."""
    findings: list[Finding] = []
    for slug, fm in g.fm.items():
        is_synthesis = (fm.get("type") == "synthesis"
                        or g.folder_of(slug) == "synthesis"
                        or fm.get("synthesis-type"))
        if not is_synthesis:
            continue
        derived = g.derived_from.get(slug, [])
        if not derived:
            findings.append(Finding(
                slug=slug, folder=g.folder_of(slug),
                issue_type="synthesis.missing-derived-from",
                severity="high",
                evidence="synthesis page has no `derived-from:` frontmatter",
                suggested_action="add `derived-from: [...]` listing every wiki page whose content contributed",
            ))
            continue
        for src in derived:
            if src not in g.path_map:
                findings.append(Finding(
                    slug=slug, folder=g.folder_of(slug),
                    issue_type="synthesis.derived-from-missing",
                    severity="high",
                    evidence=f"derived-from references [[{src}]] but no such page exists",
                    suggested_action=f"either create the page [[{src}]] or remove from `derived-from`",
                ))
                continue
            # Back-link check: source page body must contain a wikilink to the synthesis
            if slug not in g.forward.get(src, set()):
                payload = {"source_slug": src, "synthesis_slug": slug}
                findings.append(Finding(
                    slug=src, folder=g.folder_of(src),
                    issue_type="synthesis.missing-backlink",
                    severity="high",
                    evidence=f"synthesis [[{g.title_of(slug)}]] declares this page in derived-from, but body does not link back",
                    suggested_action=f"add `[[{g.title_of(slug)}]]` reference under `## Connections` in [[{g.title_of(src)}]]",
                    auto_fixable=True,
                    apply_payload=payload,
                ))
    return findings


def detect_stubs(g: Graph) -> list[Finding]:
    """Body < 10 non-empty lines. Severity scales with body size and neighbor importance.

    Excludes youtube-transcripts (transcripts are deliberately raw) and synthesis
    (synthesis pages are by-construction short summaries).
    """
    findings: list[Finding] = []
    for slug in g.path_map:
        folder = g.folder_of(slug)
        if folder.startswith("youtube-transcripts") or folder == "synthesis":
            continue
        body_lines = g.body_lines.get(slug, 0)
        if body_lines >= 10:
            continue
        deg = g.degree(slug)
        nbrs = g.neighbors(slug)
        best_neighbor_deg = max((g.degree(n) for n in nbrs), default=0)
        # Severity rubric:
        #   body < 5  → high   (clearly underwritten; or high if neighbor is a hub)
        #   body 5-9 → medium
        if body_lines < 5 or best_neighbor_deg > 30:
            sev = "high"
        else:
            sev = "medium"
        findings.append(Finding(
            slug=slug, folder=folder,
            issue_type="stub",
            severity=sev,
            evidence=f"body {body_lines} non-empty lines; degree {deg}; best-neighbor-degree {best_neighbor_deg}",
            suggested_action="flesh out the page (background, claims, sources, connections) or merge into a related entity",
        ))
    return findings


def detect_bridges(g: Graph) -> list[Finding]:
    """Pages that are load-bearing structural bridges but underwritten.

    Criteria:
      - body < 10 non-empty lines (stub-quality content)
      - folder_fan >= 3 (neighbors span ≥3 distinct folder paths)
      - degree >= 8 (load-bearing — not just a small stub with diverse connections)

    The degree gate matters: a page with 4 connections spanning 3 folders is a
    thin link-page; a page with 8+ connections spanning 3 folders is a
    structural bridge whose content doesn't match its role.
    """
    findings: list[Finding] = []
    for slug in g.path_map:
        body_lines = g.body_lines.get(slug, 0)
        if body_lines >= 10:
            continue
        deg = g.degree(slug)
        if deg < 8:
            continue
        fan = g.folder_fan(slug)
        if fan < 3:
            continue
        findings.append(Finding(
            slug=slug, folder=g.folder_of(slug),
            issue_type="rotting-bridge",
            severity="medium",
            evidence=f"bridges {fan} folder neighborhoods at degree {deg} but body is only {body_lines} non-empty lines",
            suggested_action="flesh out the page so its content matches its structural role, or split its connections across more substantive intermediaries",
        ))
    return findings


def detect_hubs(g: Graph) -> list[Finding]:
    """Multi-criterion split candidates: degree > 50 AND body > 100 lines AND >= 4 H2 headings AND folder_fan >= 3.

    Uses folder_fan rather than cluster_fan because label-propagation on this
    graph collapses into 2-3 mega-clusters; folder spread is the more stable
    signal for "this page touches genuinely different sub-domains."

    Excludes youtube-transcripts (raw sources, not entity pages) and synthesis
    (summaries by design).
    """
    findings: list[Finding] = []
    for slug in g.path_map:
        folder = g.folder_of(slug)
        if folder.startswith("youtube-transcripts") or folder == "synthesis":
            continue
        deg = g.degree(slug)
        if deg <= 50:
            continue
        body_lines = g.body_lines.get(slug, 0)
        if body_lines <= 100:
            continue
        h2s = g.headings.get(slug, [])
        if len(h2s) < 4:
            continue
        fan = g.folder_fan(slug)
        if fan < 3:
            continue
        sample = "; ".join(h2s[:6]) + ("; ..." if len(h2s) > 6 else "")
        findings.append(Finding(
            slug=slug, folder=folder,
            issue_type="hub-split-candidate",
            severity="low",
            evidence=f"degree {deg}, spans {fan} folders, {body_lines} body lines, {len(h2s)} H2 sections: {sample}",
            suggested_action="propose split: parent page becomes overview; H2 sub-topics become standalone pages with bidirectional links",
        ))
    return findings


# ──────────────────────────────────────────────────────────────────────────────
# Auto-fix actions
# ──────────────────────────────────────────────────────────────────────────────

def apply_dangling_rewrite(g: Graph, payload: dict) -> str:
    """Rewrite all [[old_target]] occurrences on page_slug to [[new_target_title]]."""
    page_slug = payload["page_slug"]
    old_target = payload["old_target"]
    new_title = payload["new_target_title"]
    path = g.path_map[page_slug]
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"\[\[\s*" + re.escape(old_target) + r"\s*((?:\|[^\]]*)?(?:#[^\]]*)?)\]\]",
        re.IGNORECASE,
    )
    new_text, count = pattern.subn(lambda m: f"[[{new_title}{m.group(1)}]]", text)
    if count == 0:
        return f"no occurrences rewritten on [[{g.title_of(page_slug)}]]"
    path.write_text(new_text, encoding="utf-8")
    return f"rewrote {count} occurrence(s) of [[{old_target}]] → [[{new_title}]] in [[{g.title_of(page_slug)}]]"


def apply_synthesis_backlink(g: Graph, payload: dict) -> str:
    """Append a Connections-section bullet linking source → synthesis."""
    src_slug = payload["source_slug"]
    syn_slug = payload["synthesis_slug"]
    src_path = g.path_map[src_slug]
    syn_title = g.title_of(syn_slug)
    text = src_path.read_text(encoding="utf-8")
    bullet = f"- Synthesized in [[{syn_title}]]"

    # If the link already exists somewhere, no-op
    if re.search(r"\[\[\s*" + re.escape(syn_title) + r"\s*\]\]", text, re.IGNORECASE):
        return f"[[{g.title_of(src_slug)}]] already links to [[{syn_title}]] — skipped"

    # Find existing Connections section; append bullet at end of that section.
    # If no Connections section, create one at end of file.
    conn_match = re.search(r"^##\s+Connections\s*$", text, re.MULTILINE)
    if conn_match:
        # Find the next H2 (or end of file) to know section bounds
        start = conn_match.end()
        rest = text[start:]
        next_h2 = re.search(r"^##\s+", rest, re.MULTILINE)
        if next_h2:
            insert_at = start + next_h2.start()
            # Insert bullet before next H2 (and ensure trailing newline)
            preceding = text[:insert_at]
            if not preceding.endswith("\n"):
                preceding += "\n"
            new_text = preceding + bullet + "\n\n" + text[insert_at:]
        else:
            # Append at very end
            tail = "\n" if text.endswith("\n") else "\n\n"
            new_text = text + tail + bullet + "\n"
    else:
        # Create a Connections section at end of file
        tail = "\n" if text.endswith("\n") else "\n\n"
        new_text = text + tail + "## Connections\n\n" + bullet + "\n"
    src_path.write_text(new_text, encoding="utf-8")
    return f"added back-link bullet in [[{g.title_of(src_slug)}]] → [[{syn_title}]]"


# ──────────────────────────────────────────────────────────────────────────────
# Report rendering
# ──────────────────────────────────────────────────────────────────────────────

SEVERITY_ORDER = ["critical", "high", "medium", "low"]


def render_report(g: Graph, all_findings: dict[str, list[Finding]],
                  applied_actions: list[str], focused_check: str) -> str:
    """Render the audit report as Markdown."""
    lines: list[str] = []
    lines.append(f"# Audit Report — `{g.wiki_dir}`\n")

    # Graph health (always)
    pages = list(g.path_map.keys())
    edges = sum(len(s) for s in g.forward.values())
    avg_deg = (sum(g.degree(s) for s in pages) / len(pages)) if pages else 0.0

    # Components
    visited: set[str] = set()
    comp_sizes: list[int] = []
    for slug in pages:
        if slug in visited:
            continue
        stack = [slug]
        size = 0
        while stack:
            s = stack.pop()
            if s in visited:
                continue
            visited.add(s)
            size += 1
            for n in g.neighbors(s):
                if n not in visited:
                    stack.append(n)
        comp_sizes.append(size)
    comp_sizes.sort(reverse=True)
    giant = comp_sizes[0] if comp_sizes else 0
    islands = sum(1 for s in comp_sizes[1:] if 2 <= s <= 10)

    orphan_count = sum(1 for s in pages if not g.reverse.get(s))
    dangling_count = sum(
        1 for slug, targets in g.all_link_targets.items() for t in targets if t not in g.path_map
    )
    synthesis_pages = [
        s for s in pages
        if g.fm.get(s, {}).get("type") == "synthesis"
        or g.folder_of(s) == "synthesis"
        or g.fm.get(s, {}).get("synthesis-type")
    ]
    synthesis_findings = all_findings.get("synthesis", [])
    syn_unhealthy = {f.slug for f in synthesis_findings} | {
        g.fm.get(s, {}).get("synthesis_slug", "") for s in synthesis_findings
    }
    # Actually count synthesis pages with at least one finding involving them
    synth_with_issues = set()
    for f in synthesis_findings:
        synth_with_issues.add(f.slug)
        if f.apply_payload and "synthesis_slug" in f.apply_payload:
            synth_with_issues.add(f.apply_payload["synthesis_slug"])
    syn_total = len(synthesis_pages)
    syn_with_issues_count = len([s for s in synthesis_pages if s in synth_with_issues])
    syn_healthy = syn_total - syn_with_issues_count

    lines.append("## Graph Health\n")
    lines.append(f"- Pages: {len(pages):,} | Edges: {edges:,} | Avg degree: {avg_deg:.1f}")
    lines.append(f"- Largest component: {giant:,} ({(giant/len(pages)*100 if pages else 0):.1f}%)")
    lines.append(f"- Orphans: {orphan_count} | Islands (size 2-10): {islands} | Dangling refs: {dangling_count}")
    lines.append(f"- Synthesis pages: {syn_total} ({syn_healthy} healthy, {syn_with_issues_count} with broken `derived-from` or missing back-links)")
    lines.append("")

    # Findings by severity (across all checks that ran)
    by_sev: dict[str, list[Finding]] = defaultdict(list)
    for check_name, findings in all_findings.items():
        for f in findings:
            by_sev[f.severity].append(f)

    for sev in SEVERITY_ORDER:
        items = by_sev.get(sev, [])
        lines.append(f"## {sev.title()} ({len(items)})\n")
        if not items:
            lines.append("_none_\n")
            continue
        # Group by issue_type for readability, cap each group
        by_type: dict[str, list[Finding]] = defaultdict(list)
        for f in items:
            by_type[f.issue_type].append(f)
        for itype, group in sorted(by_type.items()):
            lines.append(f"### `{itype}` ({len(group)})\n")
            cap = 25
            for f in group[:cap]:
                tag = " [auto-fixable]" if f.auto_fixable else ""
                lines.append(f"- [[{g.title_of(f.slug)}]] ({f.folder}){tag}")
                lines.append(f"  - Evidence: {f.evidence}")
                lines.append(f"  - Action: {f.suggested_action}")
            if len(group) > cap:
                lines.append(f"  …and {len(group) - cap} more.")
            lines.append("")

    # Auto-fixed
    if applied_actions:
        lines.append("## Auto-fixed (with --apply)\n")
        for a in applied_actions:
            lines.append(f"- {a}")
        lines.append("")
    else:
        lines.append("## Auto-fixed\n")
        lines.append("_No fixes applied (dry-run by default; pass `--apply` to enable)._")
        lines.append("")

    # Footer summary
    fixable = sum(1 for fs in all_findings.values() for f in fs if f.auto_fixable)
    total = sum(len(fs) for fs in all_findings.values())
    lines.append("## Summary\n")
    lines.append(f"- Total findings: {total}")
    lines.append(f"- Auto-fixable: {fixable}")
    lines.append(f"- Run with `--apply` to apply auto-fixes; everything else needs your call.")
    lines.append("")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Dispatch
# ──────────────────────────────────────────────────────────────────────────────

DETECTORS = {
    "constitution": detect_constitution,
    "dangling": detect_dangling,
    "orphans": detect_orphans,
    "islands": detect_islands,
    "duplicates": detect_duplicates,
    "collisions": detect_slug_collisions,
    "synthesis": detect_synthesis,
    "stubs": detect_stubs,
    "bridges": detect_bridges,
    "hubs": detect_hubs,
}


def main():
    parser = argparse.ArgumentParser(description="Comprehensive KB audit (constitution + structural)")
    parser.add_argument("wiki_dir", type=Path)
    parser.add_argument("check", nargs="?", default="all",
                        choices=["all"] + list(DETECTORS.keys()))
    parser.add_argument("--apply", action="store_true",
                        help="Apply safe auto-fixes (reciprocal back-links, single-candidate dangling rewrites). Default is dry-run.")
    parser.add_argument("--json", action="store_true",
                        help="Emit findings as JSON (suppresses Markdown report).")
    args = parser.parse_args()

    wiki_dir = args.wiki_dir.resolve()
    if not wiki_dir.is_dir():
        print(f"Error: {wiki_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    print(f"Building graph from {wiki_dir}...", file=sys.stderr)
    g = Graph(wiki_dir)
    print(f"  pages: {len(g.path_map)}", file=sys.stderr)
    # Note: label_propagation is no longer required for bridges/hubs (they use
    # folder_fan, which is more stable on this graph). It's kept on Graph in case
    # future detectors need it.

    # Determine which detectors to run
    if args.check == "all":
        run_names = list(DETECTORS.keys())
    else:
        run_names = [args.check]

    all_findings: dict[str, list[Finding]] = {}
    for name in run_names:
        print(f"Running detector: {name}", file=sys.stderr)
        fn = DETECTORS[name]
        # detect_dangling and detect_synthesis accept apply but it's only used to indicate intent;
        # actual application happens after collection.
        if name in ("dangling", "synthesis"):
            findings = fn(g, apply=args.apply)
        else:
            findings = fn(g)
        all_findings[name] = findings

    # Apply auto-fixes
    applied_actions: list[str] = []
    if args.apply:
        for findings in all_findings.values():
            for f in findings:
                if not f.auto_fixable or not f.apply_payload:
                    continue
                if f.issue_type == "dangling-link":
                    msg = apply_dangling_rewrite(g, f.apply_payload)
                elif f.issue_type == "synthesis.missing-backlink":
                    msg = apply_synthesis_backlink(g, f.apply_payload)
                else:
                    continue
                applied_actions.append(msg)

    if args.json:
        out = {
            "graph": {
                "pages": len(g.path_map),
                "edges": sum(len(s) for s in g.forward.values()),
            },
            "findings": {name: [f.to_dict() for f in fs] for name, fs in all_findings.items()},
            "applied": applied_actions,
        }
        print(json.dumps(out, indent=2))
    else:
        print(render_report(g, all_findings, applied_actions, args.check))


if __name__ == "__main__":
    main()
