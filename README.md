# SW4 cross-HPC scale test

A Cylc-driven scaling test for the [SW4](https://github.com/geodynamics/sw4)
earthquake simulation code, designed to run identically across multiple
HPCs (NeSI Mahuika genoa/milan, RCH, ESNZ Cascade) so that per-core
throughput is directly comparable. Strong and weak sweeps at 126
ranks/node, ~4 M cells/core. Captures per-task wall-clock timings in
the cylc sqlite DB; an analysis pipeline turns those into
`G cell-updates / core-hour` plots.

For background on what cross-HPC comparisons have shown so far — and
why the SW4 binaries on NeSI and RCH were rebuilt in 2026-05 — see
the `docs/` index at the bottom of this README.

## Quick start

```bash
# on a supported HPC, in a cylc-aware shell:
cd <wherever this repo is cloned on the HPC>
tmux new -s sw4-scale          # protect the cylc scheduler from logout
cylc vip flow --set 'HPC="<hpc-name>"'
# Ctrl-b d to detach
```

`<hpc-name>` is one of the values in the table below. Quoting matters
— `cylc vip --set HPC=...` evaluates the RHS as a Python literal, so
bare identifiers like `cascade` get rejected. Inner double quotes are
correct in all cases.

## Supported HPCs

| `HPC=` value         | Partition / queue | Notes |
|---                   |---                |---    |
| `mahuika-milan`      | NeSI Mahuika `milan`  | Zen3, DDR4-3200. Default if `HPC` is omitted. |
| `mahuika-genoa`      | NeSI Mahuika `genoa`  | Zen4, DDR5-4800. |
| `mahuika-genoa-avx2` | NeSI Mahuika `genoa`  | **Experimental.** Identical to `mahuika-genoa` but runs the `sw4-milan` (AVX-2) binary on Zen4 hardware to measure the SIMD-width gap. |
| `rch`                | UoC RCH `short` (`--constraint=hcpu`) | Zen3-class. |
| `cascade`            | ESNZ Cascade `shortq` (PBS) | Zen4 Genoa. Separate site, uses PBS rather than Slurm. |

Each HPC's specific account, partition, memory budget, SW4 binary
path, and pre-script module loads are set inside `flow.cylc` — search
for the relevant `{% elif HPC == '...' %}` block.

## What the workflow runs

Two parallel sweeps, each at four sizes (one per node count 1–4):

**Strong scaling** — fixed 128 × 1984 × 1984 grid, increasing rank
count from 126 to 504. Tests how well work parallelises on the same
problem.

**Weak scaling** — per-rank work held roughly constant (~4 M cells)
by growing the grid alongside the rank count:

| Nodes | Cores | nx   | ny   | nz  |
|---    |---    |---   |---   |---  |
| 1     | 126   | 1000 | 1000 | 500 |
| 2     | 252   | 1420 | 1420 | 500 |
| 3     | 378   | 1740 | 1740 | 500 |
| 4     | 504   | 2008 | 2008 | 500 |

All runs use a single MPI rank per core, **126 ranks/node**. That's
the lowest common denominator that fits on every HPC's smallest node
class — picked for comparability rather than per-HPC optimum.
Production users would typically use all cores per node; see
`docs/building-sw4-on-nesi-and-rch.md` § "Out of scope: runtime
tuning".

The simulated event is a small synthetic source in a uniform medium,
1000 time steps. Grid commands use `proj=tmerc` for coordinate
transformation, which requires SW4 to be built with PROJ support
(see `docs/building-sw4-on-nesi-and-rch.md`).

## Reading the results

Per-task wall-clock timings land in `<run-dir>/log/db` (a cylc-managed
sqlite DB). The Python scripts under `scripts/` convert those into
throughput plots in **G cell-updates per core-hour**, the same unit
across all HPCs.

```bash
# single-run plot
./scripts/plot_scaling.py <path-or-tarball-of-cylc-run-dir> -o run.png

# cross-HPC comparison plot (overlay multiple campaigns)
./scripts/compare_scaling.py \
  "genoa=/path/to/genoa.tar.gz" \
  "milan=/path/to/milan.tar.gz" \
  "rch=/path/to/rch.tar.gz" \
  "cascade=/path/to/cascade.tar.gz" \
  -o cross-hpc-throughput.png
```

Each accepts either an extracted cylc run directory or a `.tar.gz`
of one. Both are `uv run` self-contained scripts — just executable.

## Documentation

The `docs/` directory holds the analysis and operational
documentation built up around this workflow. Recommended reading
order depends on what you're trying to do:

**Just want to understand what we've found:**
- `docs/cross-hpc-findings-explained.md` — plain-English summary,
  no jargon. Start here if you're not in HPC every day.
- `docs/cross-hpc-throughput.md` — the technical version with full
  data and analysis.

**Want to dig into specific findings:**
- `docs/cascade-strong-vs-weak-puzzle.md` — diagnostic chain that
  traced cascade's anomalous weak-throughput edge back to a build-flag
  effect (the SIMD-width finding).
- `docs/sw4-domain-shape-tuning.md` — how the per-rank grid shape
  affects throughput on wide-SIMD binaries. Coarse rules of thumb
  through closed-form back-of-envelope formulas.

**Want to rebuild or extend the workflow:**
- `docs/building-sw4-on-nesi-and-rch.md` — operational recipes for
  rebuilding the SW4 binaries on NeSI and RCH. Documents all the
  paste-gotchas, missing-libs, and ISA-dispatch oddities that
  surfaced during the 2026-05 rebuild.
- `docs/scaling-test-rationale.md` — how the grid sizes, core
  counts, and other numbers in the workflow CSVs were derived.

## Repo layout

```
.
├── cylc/cylc-src/flow/          ← cylc workflow source
│   ├── flow.cylc                ← per-HPC config + task graph
│   ├── weak_scaling.csv         ← weak-sweep core counts and grid sizes
│   ├── strong_scaling.csv       ← strong-sweep core counts
│   └── events/
│       ├── input_strong.in      ← SW4 input for the strong sweep
│       └── input_weak.in        ← SW4 input template for the weak sweep
├── scripts/                     ← analysis pipeline (uv-run self-contained)
│   ├── plot_scaling.py          ← single-run plot
│   ├── compare_scaling.py       ← cross-HPC overlay plot
│   └── plot_runtime_vs_cores.py ← strong-scaling runtime view
└── docs/                        ← analysis + operational documentation
    ├── (analysis docs listed above)
    └── sw4-build-smoke.in       ← canonical smoke input for verifying a new SW4 build
```

## Status

As of 2026-05-15, post-rebuild scaling campaigns are queued on all
three NeSI/RCH HPCs to confirm the empirical SIMD-width fix. Cascade
data was collected pre-rebuild and is the reference for what
wide-SIMD throughput looks like on Zen4 hardware. See
`docs/cross-hpc-throughput.md` for the current dataset and
`docs/building-sw4-on-nesi-and-rch.md` § "Pending follow-ups" for
queued experiments.
