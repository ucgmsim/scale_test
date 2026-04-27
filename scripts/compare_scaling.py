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
to k cell-steps per core per second so absolute lines from different
HPCs are directly comparable.

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
    """Return {kind: {cores: kCS_per_core_per_s}} for successful tasks."""
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
        elapsed = (parse_iso(t_exit) - parse_iso(t_run)).total_seconds()
        nx, ny, nz = STRONG_GRID if kind == "strong" else WEAK_GRIDS[cores]
        out[kind][cores] = (nx * ny * nz * STEPS) / (cores * elapsed) / 1000.0
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

    fig, (ax_s, ax_w) = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    panels = [("strong", ax_s, "Strong scaling: fixed 128×1984×1984 grid"),
              ("weak",   ax_w, "Weak scaling: ~4M cells/core")]
    for kind, ax, title in panels:
        ax.set_title(title)
        ax.set_xlabel("Cores")
        ax.set_ylabel("Throughput (k cell-steps / core / s)")
        ax.grid(True, alpha=0.3)
        for label, data in all_data:
            d = data.get(kind, {})
            if not d:
                continue
            cores = sorted(d.keys())
            ax.plot(cores, [d[c] for c in cores], "o-", label=label, alpha=0.85)
        ax.legend(fontsize=9)

    fig.tight_layout()
    fig.savefig(args.output, dpi=130)
    print(f"\nwrote {args.output}")

    print(f"\n{'archive':<28} {'kind':<6} {'mean':>5}  range          n")
    for label, data in all_data:
        for kind in ("strong", "weak"):
            d = data.get(kind, {})
            if not d:
                continue
            mean = sum(d.values()) / len(d)
            print(f"{label:<28} {kind:<6} {mean:>5.0f}  "
                  f"{min(d.values()):.0f}-{max(d.values()):.0f}  ({len(d)})")


if __name__ == "__main__":
    main()
