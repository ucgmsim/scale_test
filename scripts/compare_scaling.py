#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.12"
# dependencies = ["matplotlib"]
# ///
"""Overlay SW4 scaling-test throughput across multiple Cylc run archives.

Companion to `plot_scaling.py`, which plots a single run. This one takes
several labelled archives and produces a side-by-side strong / weak
panel with one line per HPC × configuration. Throughput is normalised
to cell updates per core-hour so absolute lines from different HPCs
are directly comparable.

Usage:
    ./compare_scaling.py LABEL=PATH [LABEL=PATH ...] -o overlay.png
    ./compare_scaling.py "genoa=/data/genoa.tar.gz" "rch=/data/rch.tar.gz"

PATH may be a .tar.gz of a Cylc run dir or an already-extracted dir.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import tarfile
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt


# Grid sizes per scaling kind. Strong is fixed; weak grows with cores.
# Kept inline to avoid a runtime dep on the workflow's CSV files.
WEAK_GRIDS = {126: (1000, 1000, 500), 252: (1420, 1420, 500),
              378: (1740, 1740, 500), 504: (2008, 2008, 500)}
STRONG_GRID = (128, 1984, 1984)
STEPS = 1000

TASK_RE = re.compile(r"sw4_(weak|strong)_scaling_(?:weak|strong)_test(\d+)")


def parse_iso(s: str) -> datetime:
    s = re.sub(r"([+-]\d{2}):(\d{2})$", r"\1\2", s)
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")


def find_db(root: Path) -> Path:
    candidates = sorted(root.rglob("log/db"))
    if not candidates:
        sys.exit(f"no log/db found under {root}")
    return candidates[-1]


def load_throughputs(db: Path) -> dict[str, dict[int, float]]:
    """Return {kind: {cores: G_cell_updates_per_core_hour}} for successful tasks."""
    conn = sqlite3.connect(db)
    rows = conn.execute(
        """SELECT name, time_run, time_run_exit
           FROM   task_jobs
           WHERE  time_run IS NOT NULL AND time_run_exit IS NOT NULL
             AND  run_status = 0"""
    ).fetchall()
    out: dict[str, dict[int, float]] = defaultdict(dict)
    for name, t_run, t_exit in rows:
        m = TASK_RE.fullmatch(name)
        if not m:
            continue
        kind, cores = m.group(1), int(m.group(2))
        if cores in out[kind]:
            continue  # already have a successful submit for this task
        elapsed_h = (parse_iso(t_exit) - parse_iso(t_run)).total_seconds() / 3600.0
        nx, ny, nz = STRONG_GRID if kind == "strong" else WEAK_GRIDS[cores]
        out[kind][cores] = (nx * ny * nz * STEPS) / (cores * elapsed_h) / 1e9
    return out


def parse_label_path(arg: str) -> tuple[str, Path]:
    if "=" not in arg:
        sys.exit(f"argument {arg!r} must be of the form LABEL=PATH")
    label, path = arg.split("=", 1)
    return label, Path(path)


def extract_if_archive(p: Path, tmp: str) -> Path:
    if p.is_dir():
        return p
    if p.is_file() and "".join(p.suffixes[-2:]) == ".tar.gz":
        sub = Path(tmp) / p.stem.removesuffix(".tar")
        sub.mkdir(exist_ok=True)
        with tarfile.open(p) as tf:
            tf.extractall(sub)
        return sub
    sys.exit(f"{p} is neither a .tar.gz nor a directory")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("inputs", nargs="+", help="LABEL=PATH (PATH = .tar.gz or dir)")
    ap.add_argument("-o", "--output", type=Path, default=Path("cross-hpc-throughput.png"))
    args = ap.parse_args()

    parsed = [parse_label_path(a) for a in args.inputs]

    with tempfile.TemporaryDirectory() as tmp:
        all_data: list[tuple[str, dict[str, dict[int, float]]]] = []
        for label, path in parsed:
            root = extract_if_archive(path, tmp)
            db = find_db(root)
            print(f"{label:<28} {db}")
            all_data.append((label, load_throughputs(db)))

    fig, ax = plt.subplots(figsize=(8, 5.5))
    cores_per_node = 126
    all_cores: set[int] = set()
    ax.set_xlabel("Nodes")
    ax.set_ylabel("Throughput (G cell updates / core-hour)")
    ax.grid(True, alpha=0.3)

    kind_styles = {"strong": "-", "weak": "--"}
    palette = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    for i, (label, data) in enumerate(all_data):
        color = palette[i % len(palette)]
        for kind, linestyle in kind_styles.items():
            d = data.get(kind, {})
            if not d:
                continue
            cores = sorted(d.keys())
            all_cores.update(cores)
            nodes = [c / cores_per_node for c in cores]
            ax.plot(nodes, [d[c] for c in cores],
                    marker="o", linestyle=linestyle, color=color,
                    label=f"{label} ({kind})", alpha=0.85)
    ax.legend(fontsize=9, loc="upper right")

    cores_sorted = sorted(all_cores)
    ax.set_xticks([c / cores_per_node for c in cores_sorted])
    ax.set_xticklabels([str(c // cores_per_node) for c in cores_sorted])

    secax = ax.secondary_xaxis(
        "top",
        functions=(lambda x: x * cores_per_node, lambda x: x / cores_per_node),
    )
    secax.set_xticks(cores_sorted)
    secax.set_xticklabels([str(c) for c in cores_sorted])
    secax.set_xlabel(f"Cores ({cores_per_node} cores/node)")

    fig.tight_layout()
    fig.savefig(args.output, dpi=130)
    print(f"\nwrote {args.output}")

    print(f"\n{'archive':<28} {'kind':<6} {'mean':>5}  range            n  (G cell updates / core-hour)")
    for label, data in all_data:
        for kind in ("strong", "weak"):
            d = data.get(kind, {})
            if not d:
                continue
            mean = sum(d.values()) / len(d)
            print(f"{label:<28} {kind:<6} {mean:>5.2f}  "
                  f"{min(d.values()):.2f}-{max(d.values()):.2f}  ({len(d)})")


if __name__ == "__main__":
    main()
