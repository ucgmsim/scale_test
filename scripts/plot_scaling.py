#!/usr/bin/env python3
"""Plot strong and weak scaling curves from a Cylc SW4 scale-test run.

Accepts either a .tar.gz of a Cylc run directory (e.g. the tarball pulled
off Mahuika) or an already-extracted directory, reads per-task wall-clock
runtimes from the Cylc sqlite db at `log/db`, and writes a two-panel PNG
(strong scaling on the left, weak scaling on the right).

Usage:
    ./plot_scaling.py /path/to/cylc_flow_*.tar.gz
    ./plot_scaling.py /path/to/extracted/run1 -o out.png
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt


TASK_RE = re.compile(r"sw4_(weak|strong)_scaling_(?:weak|strong)_test(\d+)")


def parse_iso(s: str) -> datetime:
    # Cylc writes ISO-8601 with a ±HH:MM offset. datetime.strptime's %z only
    # accepts ±HHMM on Python < 3.11, so strip the colon before parsing.
    s = re.sub(r"([+-]\d{2}):(\d{2})$", r"\1\2", s)
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")


def find_db(root: Path) -> Path:
    candidates = sorted(root.rglob("log/db"))
    if not candidates:
        sys.exit(f"no log/db found under {root}")
    return candidates[-1]


def load_timings(db: Path) -> list[tuple[str, int, float]]:
    """Return [(scaling_kind, cores, elapsed_seconds), ...] for successful tasks."""
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT name, time_run, time_run_exit, run_status
        FROM   task_jobs
        WHERE  time_run IS NOT NULL
          AND  time_run_exit IS NOT NULL
        """
    ).fetchall()

    results: list[tuple[str, int, float]] = []
    for r in rows:
        m = TASK_RE.fullmatch(r["name"])
        if not m or r["run_status"] != 0:
            continue
        kind, cores = m.group(1), int(m.group(2))
        elapsed = (parse_iso(r["time_run_exit"]) - parse_iso(r["time_run"])).total_seconds()
        results.append((kind, cores, elapsed))
    return results


def plot_scaling(data: list[tuple[str, int, float]], out_path: Path) -> None:
    fig, (ax_strong, ax_weak) = plt.subplots(1, 2, figsize=(11, 4.5))

    panels = [
        (ax_strong, "strong", "Strong scaling (fixed grid)"),
        (ax_weak,   "weak",   "Weak scaling (cells/core ≈ constant)"),
    ]

    for ax, kind, title in panels:
        subset = sorted((c, t) for k, c, t in data if k == kind)
        ax.set_title(title)
        ax.set_xlabel("MPI ranks (cores)")
        ax.grid(True, alpha=0.3)

        if not subset:
            ax.set_ylabel(
                "Wall-clock runtime (h)" if kind == "strong"
                else "Runtime ratio (measured / ideal)"
            )
            ax.text(0.5, 0.5, f"no {kind} data", ha="center", va="center",
                    transform=ax.transAxes)
            continue

        cores, times = zip(*subset)
        base_c, base_t = cores[0], times[0]

        if kind == "strong":
            hours = [t / 3600.0 for t in times]
            ax.set_ylabel("Wall-clock runtime (h)")
            ax.plot(cores, hours, "o-", label="measured")
            if len(subset) >= 2:
                ideal_hours = [base_t * base_c / c / 3600.0 for c in cores]
                ax.plot(cores, ideal_hours, "k--", alpha=0.5,
                        label=r"ideal: $T(N) = T(N_0) \cdot N_0 / N$")
            ax.legend()
        else:  # weak
            ratios = [t / base_t for t in times]
            ax.set_ylabel("Runtime ratio (measured / ideal)")
            ax.plot(cores, ratios, "o-", label="measured / ideal")
            ax.axhline(1.0, ls="--", color="k", alpha=0.5,
                       label=r"ideal: $T(N) / T(N_0) = 1$")
            ax.legend()

        ax.set_xticks(cores)
        ax.set_xticklabels([str(c) for c in cores])

        # Secondary x-axis (top) in nodes, with 126 cores per node.
        secax = ax.secondary_xaxis(
            "top",
            functions=(lambda x: x / 126.0, lambda x: x * 126.0),
        )
        secax.set_xticks([c // 126 for c in cores])
        secax.set_xticklabels([str(c // 126) for c in cores])
        secax.set_xlabel("Nodes (126 cores/node)")

    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    print(f"wrote {out_path}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("input", type=Path, help=".tar.gz archive or directory of a Cylc run")
    p.add_argument("-o", "--output", type=Path, default=Path("scaling.png"))
    args = p.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        root = args.input
        if args.input.is_file() and "".join(args.input.suffixes[-2:]) == ".tar.gz":
            print(f"extracting {args.input} …")
            with tarfile.open(args.input) as tf:
                tf.extractall(tmp)
            root = Path(tmp)
        elif not args.input.is_dir():
            sys.exit(f"{args.input} is neither a .tar.gz nor a directory")

        db = find_db(root)
        print(f"reading timings from {db}")
        data = load_timings(db)
        if not data:
            sys.exit("no timing rows found")

        print(f"\n{'kind':<7} {'cores':>5} {'elapsed':>10}")
        for k, c, t in sorted(data):
            print(f"{k:<7} {c:>5} {t:>9.1f}s")
        print()

        plot_scaling(data, args.output)


if __name__ == "__main__":
    main()
