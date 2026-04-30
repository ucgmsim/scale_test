#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.12"
# dependencies = ["matplotlib"]
# ///
"""Overlay SW4 wall-clock runtime vs. cores across multiple Cylc archives.

Sibling of `compare_scaling.py`. That script normalises to per-core
throughput (k cell-steps/core/s) so absolute wall-clock differences
between HPCs are removed. This one keeps wall-clock — useful when the
question is "if I run this on HPC X, how long do I wait?".

Usage:
    ./plot_runtime_vs_cores.py LABEL=PATH [LABEL=PATH ...] -o out.png
    ./plot_runtime_vs_cores.py --kind weak ...
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


TASK_RE = re.compile(r"sw4_(weak|strong)_scaling_(?:weak|strong)_test(\d+)")


def parse_iso(s: str) -> datetime:
    s = re.sub(r"([+-]\d{2}):(\d{2})$", r"\1\2", s)
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")


def find_db(root: Path) -> Path:
    candidates = sorted(root.rglob("log/db"))
    if not candidates:
        sys.exit(f"no log/db found under {root}")
    return candidates[-1]


def load_runtimes(db: Path) -> dict[str, dict[int, float]]:
    """Return {kind: {cores: elapsed_seconds}} for successful tasks."""
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
            continue
        out[kind][cores] = (parse_iso(t_exit) - parse_iso(t_run)).total_seconds()
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
    ap.add_argument("--kind", choices=("strong", "weak"), default="strong")
    ap.add_argument("-o", "--output", type=Path,
                    default=Path("strong-scaling-runtime.png"))
    args = ap.parse_args()

    parsed = [parse_label_path(a) for a in args.inputs]

    with tempfile.TemporaryDirectory() as tmp:
        all_data: list[tuple[str, dict[int, float]]] = []
        for label, path in parsed:
            root = extract_if_archive(path, tmp)
            db = find_db(root)
            data = load_runtimes(db).get(args.kind, {})
            print(f"{label:<28} {db}  ({len(data)} {args.kind} points)")
            all_data.append((label, data))

    fig, ax = plt.subplots(figsize=(7.5, 5))
    title_kind = "Strong scaling" if args.kind == "strong" else "Weak scaling"
    subtitle = ("fixed 128 × 1984 × 1984 grid" if args.kind == "strong"
                else "~4 M cells/core")
    ax.set_title(f"{title_kind} runtime — {subtitle}")
    ax.set_xlabel("MPI ranks (cores)")
    ax.set_ylabel("Wall-clock runtime (min)")
    ax.grid(True, alpha=0.3)

    all_cores: set[int] = set()
    for label, data in all_data:
        if not data:
            continue
        cores = sorted(data.keys())
        all_cores.update(cores)
        minutes = [data[c] / 60.0 for c in cores]
        ax.plot(cores, minutes, "o-", label=label, alpha=0.85)
    ax.legend()

    cores_sorted = sorted(all_cores)
    ax.set_xticks(cores_sorted)
    ax.set_xticklabels([str(c) for c in cores_sorted])

    secax = ax.secondary_xaxis(
        "top",
        functions=(lambda x: x / 126.0, lambda x: x * 126.0),
    )
    secax.set_xticks([c // 126 for c in cores_sorted])
    secax.set_xticklabels([str(c // 126) for c in cores_sorted])
    secax.set_xlabel("Nodes (126 cores/node)")

    fig.tight_layout()
    fig.savefig(args.output, dpi=130)
    print(f"\nwrote {args.output}")

    print(f"\n{'archive':<28} {'cores':>5} {'minutes':>8}")
    for label, data in all_data:
        for cores in sorted(data):
            print(f"{label:<28} {cores:>5} {data[cores]/60:>8.1f}")


if __name__ == "__main__":
    main()
