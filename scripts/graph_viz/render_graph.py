"""Render an Obsidian-style force-directed graph of the ufo-kb wiki.

Pipeline:
  1. Load graph.json (built by build_graph.py).
  2. Compute (or load cached) force-directed layout via networkx spring_layout.
  3. Draw layers: faint edges → backbone edges → long-tail nodes → hubs → halos → labels.

The cached layout lives at layout.npz, keyed by node+edge-count signature plus
the layout parameters that change geometry. Delete layout.npz to recompute.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from matplotlib import patheffects as pe
from matplotlib.collections import LineCollection

HERE = Path(__file__).parent
GRAPH_JSON = HERE / "graph.json"
LAYOUT_NPZ = HERE / "layout.npz"
DEFAULT_OUT = HERE.parent.parent / "docs" / "graph.png"

# Obsidian-ish palette: warm amber for people, cyan for concepts, magenta for
# synthesis, etc. Picked so hubs stand out without clashing on dark bg.
TYPE_COLORS: dict[str, str] = {
    "person":     "#f5a85a",   # amber
    "concept":    "#5cd1d6",   # cyan
    "synthesis":  "#e066d6",   # magenta — the curated cross-source pages
    "org":        "#ef6b6b",   # red
    "place":      "#7ed957",   # green
    "program":    "#d4d44c",   # yellow
    "incident":   "#ffb38a",   # peach
    "document":   "#9ab8e6",   # soft blue
    "tech":       "#c298ff",   # lavender
    "craft":      "#ff79c6",   # hot pink
    "symbol":     "#bbbbbb",   # neutral
    "transcript": "#5b6470",   # dim grey
    "dangling":   "#3a3f47",   # very dim
    "other":      "#888888",
}

LEGEND_ORDER = [
    ("person", "People"),
    ("concept", "Concepts"),
    ("org", "Organizations"),
    ("place", "Places"),
    ("program", "Programs"),
    ("incident", "Incidents"),
    ("document", "Documents"),
    ("tech", "Tech / Artifacts"),
    ("craft", "Craft & Entities"),
    ("synthesis", "Synthesis"),
    ("transcript", "Transcripts"),
]

BG = "#0d1117"          # near-black, Obsidian-ish
EDGE_COLOR = "#7aa3c7"  # cool blue, low alpha
BACKBONE_COLOR = "#a4c5e8"


def load_graph() -> tuple[nx.Graph, dict[str, dict]]:
    data = json.loads(GRAPH_JSON.read_text())
    g = nx.Graph()
    meta: dict[str, dict] = {}
    for n in data["nodes"]:
        slug = n["id"]
        meta[slug] = n
        g.add_node(slug)
    for a, b in data["edges"]:
        g.add_edge(a, b)
    return g, meta


def compute_layout(
    g: nx.Graph,
    *,
    iterations: int,
    k_mul: float,
    force: bool = False,
) -> dict[str, np.ndarray]:
    sig = f"{g.number_of_nodes()}-{g.number_of_edges()}-it{iterations}-k{k_mul}"
    if not force and LAYOUT_NPZ.exists():
        npz = np.load(LAYOUT_NPZ, allow_pickle=True)
        if str(npz["sig"]) == sig:
            keys = npz["keys"]
            xy = npz["xy"]
            print(f"[layout] cache hit ({sig})")
            return {str(k): xy[i] for i, k in enumerate(keys)}

    print(f"[layout] computing spring_layout iters={iterations} k_mul={k_mul} for {g.number_of_nodes()} nodes…")
    pos = nx.spring_layout(
        g,
        k=k_mul / math.sqrt(g.number_of_nodes()),
        iterations=iterations,
        seed=42,
        weight=None,
    )
    keys = list(pos.keys())
    xy = np.array([pos[k] for k in keys], dtype=np.float32)
    np.savez(LAYOUT_NPZ, sig=sig, keys=np.array(keys), xy=xy)
    print(f"[layout] cached → {LAYOUT_NPZ.name}")
    return pos


def degree_to_size(deg: int, max_deg: int) -> float:
    """Sqrt scaling so very high-degree hubs don't crowd the plot."""
    return 5.0 + 280.0 * math.sqrt(deg / max(1, max_deg))


ACRONYMS = {"cia", "fbi", "nsa", "darpa", "jfk", "ufo", "uap", "mk", "ic", "us", "usa"}

def label_text(slug: str, type_: str) -> str:
    if type_ == "transcript":
        return slug
    # title-case but keep "mk-ultra" hyphenated, keep acronyms upper
    parts = slug.split("-")
    out = []
    for w in parts:
        out.append(w.upper() if w in ACRONYMS else w.capitalize())
    # Re-hyphenate when the first token is a known acronym (e.g. MK-Ultra).
    if parts and parts[0] in ACRONYMS and len(parts) > 1:
        return out[0] + "-" + " ".join(out[1:])
    return " ".join(out)


def avoid_label_overlaps(positions: list[tuple[float, float]],
                         heights: list[float],
                         widths: list[float],
                         iters: int = 60) -> list[tuple[float, float]]:
    """Tiny push-apart on label centers. Treats labels as boxes."""
    pos = np.array(positions, dtype=np.float64)
    w = np.array(widths)
    h = np.array(heights)
    for _ in range(iters):
        moved = False
        for i in range(len(pos)):
            for j in range(i + 1, len(pos)):
                dx = pos[j, 0] - pos[i, 0]
                dy = pos[j, 1] - pos[i, 1]
                # axis-aligned overlap test on label boxes
                ow = (w[i] + w[j]) / 2 - abs(dx)
                oh = (h[i] + h[j]) / 2 - abs(dy)
                if ow > 0 and oh > 0:
                    moved = True
                    # push along the smaller-overlap axis (prefer vertical)
                    if oh < ow:
                        push = oh / 2 + 1e-4
                        sign = 1 if dy >= 0 else -1
                        pos[j, 1] += sign * push
                        pos[i, 1] -= sign * push
                    else:
                        push = ow / 2 + 1e-4
                        sign = 1 if dx >= 0 else -1
                        pos[j, 0] += sign * push
                        pos[i, 0] -= sign * push
        if not moved:
            break
    return [tuple(p) for p in pos]


def render(
    *,
    out: Path,
    label_top_n: int = 25,
    backbone_top_n: int = 50,
    figure_size: tuple[float, float] = (24, 24),
    dpi: int = 200,
    edge_alpha: float = 0.04,
    edge_lw: float = 0.16,
    backbone_alpha: float = 0.32,
    backbone_lw: float = 0.45,
    layout_iters: int = 150,
    layout_k_mul: float = 1.4,
    title: str | None = None,
    show_legend: bool = True,
) -> None:
    g, meta = load_graph()
    pos = compute_layout(g, iterations=layout_iters, k_mul=layout_k_mul)

    max_deg = max((meta[n]["degree"] for n in g.nodes), default=1)

    # Identify hubs (top-N by degree) — used for halo, labels, and "backbone" edge highlighting.
    hubs_ranked = sorted(g.nodes, key=lambda n: -meta[n]["degree"])
    top_hubs = hubs_ranked[:label_top_n]
    backbone_hubs = set(hubs_ranked[:backbone_top_n])

    fig, ax = plt.subplots(figsize=figure_size, facecolor=BG)
    ax.set_facecolor(BG)
    ax.set_axis_off()

    # ---- Edges: split into "faint" and "backbone" passes ----
    faint_segs: list = []
    backbone_segs: list = []
    for a, b in g.edges:
        seg = (pos[a], pos[b])
        if a in backbone_hubs or b in backbone_hubs:
            backbone_segs.append(seg)
        else:
            faint_segs.append(seg)
    if faint_segs:
        ax.add_collection(LineCollection(
            faint_segs, colors=EDGE_COLOR, linewidths=edge_lw,
            alpha=edge_alpha, antialiased=True, zorder=1,
        ))
    if backbone_segs:
        ax.add_collection(LineCollection(
            backbone_segs, colors=BACKBONE_COLOR, linewidths=backbone_lw,
            alpha=backbone_alpha, antialiased=True, zorder=2,
        ))

    # ---- Nodes, drawn smallest → largest so hubs land on top ----
    nodes_sorted = sorted(g.nodes, key=lambda n: meta[n]["degree"])
    xs = np.array([pos[n][0] for n in nodes_sorted])
    ys = np.array([pos[n][1] for n in nodes_sorted])
    sizes = np.array([degree_to_size(meta[n]["degree"], max_deg) for n in nodes_sorted])
    colors = [TYPE_COLORS.get(meta[n]["type"], TYPE_COLORS["other"]) for n in nodes_sorted]
    alphas = [
        0.30 if meta[n]["type"] in ("transcript", "dangling")
        else 0.50 if meta[n]["degree"] < 3
        else 0.95
        for n in nodes_sorted
    ]
    ax.scatter(xs, ys, s=sizes, c=colors, alpha=alphas,
               linewidths=0, zorder=3)

    # ---- Soft halos for top hubs ----
    hub_xs = np.array([pos[n][0] for n in top_hubs])
    hub_ys = np.array([pos[n][1] for n in top_hubs])
    hub_sizes = np.array([degree_to_size(meta[n]["degree"], max_deg) for n in top_hubs])
    hub_colors = [TYPE_COLORS.get(meta[n]["type"], TYPE_COLORS["other"]) for n in top_hubs]
    # five-pass halo for richer glow
    for halo_mult, halo_alpha in [(14.0, 0.025), (9.0, 0.045), (5.5, 0.075), (3.2, 0.13), (2.0, 0.22)]:
        ax.scatter(hub_xs, hub_ys, s=hub_sizes * halo_mult, c=hub_colors,
                   alpha=halo_alpha, linewidths=0, zorder=2)
    ax.scatter(hub_xs, hub_ys, s=hub_sizes, c=hub_colors,
               alpha=1.0, linewidths=0.8, edgecolors="#ffffff", zorder=4)

    # Extra "gravity well" glow for the top 5 mega-hubs.
    mega = hubs_ranked[:5]
    mega_xs = np.array([pos[n][0] for n in mega])
    mega_ys = np.array([pos[n][1] for n in mega])
    mega_sizes = np.array([degree_to_size(meta[n]["degree"], max_deg) for n in mega])
    mega_colors = [TYPE_COLORS.get(meta[n]["type"], TYPE_COLORS["other"]) for n in mega]
    for halo_mult, halo_alpha in [(28.0, 0.018), (18.0, 0.032)]:
        ax.scatter(mega_xs, mega_ys, s=mega_sizes * halo_mult, c=mega_colors,
                   alpha=halo_alpha, linewidths=0, zorder=2)

    # ---- Labels for top hubs ----
    # Strategy: pin each hub's label at angular position θ (its angle from
    # centroid) on a ring at radius (R_layout + margin). Sort by angle and
    # spread any angular collisions. This always produces a clean halo of
    # labels around the graph, no matter how dense the center is.
    label_strs = [label_text(n, meta[n]["type"]) for n in top_hubs]
    extent_x = xs.max() - xs.min()
    extent_y = ys.max() - ys.min()

    cx = (xs.min() + xs.max()) / 2
    cy = (ys.min() + ys.max()) / 2

    R = max(extent_x, extent_y) / 2
    label_ring = R * 1.18  # ring radius for label placement

    # Approx rendered label widths in data coordinates (for angular packing).
    # Slightly over-estimate to keep labels comfortably apart.
    label_widths = [max(0.05 * extent_x, 0.011 * extent_x * len(s)) for s in label_strs]

    # Width-aware angular packing. Each label claims arc-length proportional
    # to its rendered width; we then spread labels so their arcs don't overlap.
    raw = []
    for i, n in enumerate(top_hubs):
        nx_, ny_ = pos[n]
        dx = nx_ - cx
        dy = ny_ - cy
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            theta = 0.0
        else:
            theta = math.atan2(dy, dx)
        raw.append((theta, i))
    raw.sort()

    sorted_idx = [i for _, i in raw]
    sorted_theta = [t for t, _ in raw]

    # arc_len = label_width / radius  (small-angle approx)
    # add a small angular gap between labels for breathing room
    gap = 0.038
    arcs = [label_widths[i] / label_ring + gap for i in sorted_idx]

    # Iteratively push neighbours apart in angular space.
    spread = list(sorted_theta)
    for _ in range(400):
        moved = False
        for k in range(len(spread)):
            j = (k + 1) % len(spread)
            d = spread[j] - spread[k]
            if j == 0:
                d += 2 * math.pi
            need = (arcs[k] + arcs[j]) / 2
            if d < need - 1e-5:
                push = (need - d) / 2
                spread[k] -= push
                spread[j] += push
                moved = True
        if not moved:
            break

    placed = [None] * len(top_hubs)
    for orig_idx, new_theta in zip(sorted_idx, spread):
        lx = cx + label_ring * math.cos(new_theta)
        ly = cy + label_ring * math.sin(new_theta)
        placed[orig_idx] = (lx, ly)

    # Draw a faint leader line from each hub to its label on the ring.
    leader_segs = []
    for n, (lx, ly) in zip(top_hubs, placed):
        nx_, ny_ = pos[n]
        leader_segs.append(((nx_, ny_), (lx, ly)))
    if leader_segs:
        ax.add_collection(LineCollection(
            leader_segs,
            colors="#9aa6b4",
            linewidths=0.4,
            alpha=0.28,
            antialiased=True,
            zorder=5,
        ))

    for n, txt, (lx, ly) in zip(top_hubs, label_strs, placed):
        ax.text(
            lx, ly, txt,
            color="#ffffff",
            fontsize=9.0,
            fontweight="bold",
            ha="center",
            va="center",
            zorder=6,
            path_effects=[
                pe.Stroke(linewidth=2.8, foreground=BG, alpha=0.92),
                pe.Normal(),
            ],
        )

    # ---- Title ----
    if title:
        ax.text(
            0.5, 0.985, title,
            transform=ax.transAxes,
            color="#e6e6e6", fontsize=22, fontweight="bold",
            ha="center", va="top", zorder=7,
            path_effects=[pe.Stroke(linewidth=3, foreground=BG, alpha=0.8), pe.Normal()],
        )

    # ---- Legend (top-right corner, in axes fraction coords) ----
    if show_legend:
        x0, y0 = 0.012, 0.985
        line_h = 0.024
        ax.text(x0, y0, "Type",
                transform=ax.transAxes, color="#cccccc", fontsize=10,
                fontweight="bold", ha="left", va="top", zorder=7)
        for i, (t, label) in enumerate(LEGEND_ORDER):
            ay = y0 - line_h * (i + 1)
            ax.scatter([x0 + 0.010], [ay + 0.005],
                       transform=ax.transAxes,
                       s=46, c=TYPE_COLORS[t], alpha=0.95,
                       linewidths=0, zorder=7)
            ax.text(x0 + 0.022, ay + 0.005, label,
                    transform=ax.transAxes, color="#bfc7d2", fontsize=9,
                    ha="left", va="center", zorder=7)

        # footer with counts
        ax.text(
            0.5, 0.012,
            f"{g.number_of_nodes():,} pages · {g.number_of_edges():,} connections · top {label_top_n} hubs labeled",
            transform=ax.transAxes,
            color="#7a8390", fontsize=10,
            ha="center", va="bottom", zorder=7,
        )

    ax.set_aspect("equal")
    # Asymmetric pad: extra space at bottom so the footer text doesn't collide
    # with the bottom-most ring label.
    pad_x = 0.24 * extent_x
    pad_y_top = 0.22 * extent_y
    pad_y_bot = 0.34 * extent_y
    ax.set_xlim(xs.min() - pad_x, xs.max() + pad_x)
    ax.set_ylim(ys.min() - pad_y_bot, ys.max() + pad_y_top)

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=dpi, facecolor=BG, bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    print(f"[render] wrote {out}  ({figure_size[0]:.0f}×{figure_size[1]:.0f}in @ {dpi}dpi)")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--label-top", type=int, default=25)
    p.add_argument("--backbone-top", type=int, default=50)
    p.add_argument("--size", type=float, default=24.0)
    p.add_argument("--dpi", type=int, default=200)
    p.add_argument("--edge-alpha", type=float, default=0.04)
    p.add_argument("--edge-lw", type=float, default=0.16)
    p.add_argument("--backbone-alpha", type=float, default=0.32)
    p.add_argument("--backbone-lw", type=float, default=0.45)
    p.add_argument("--iters", type=int, default=150)
    p.add_argument("--k-mul", type=float, default=1.4)
    p.add_argument("--title", type=str, default=None)
    p.add_argument("--no-legend", action="store_true")
    args = p.parse_args()
    render(
        out=args.out,
        label_top_n=args.label_top,
        backbone_top_n=args.backbone_top,
        figure_size=(args.size, args.size),
        dpi=args.dpi,
        edge_alpha=args.edge_alpha,
        edge_lw=args.edge_lw,
        backbone_alpha=args.backbone_alpha,
        backbone_lw=args.backbone_lw,
        layout_iters=args.iters,
        layout_k_mul=args.k_mul,
        title=args.title,
        show_legend=not args.no_legend,
    )


if __name__ == "__main__":
    main()
