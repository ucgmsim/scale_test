# SW4 scaling test — rationale for the chosen numbers

This note explains how the numbers in `cylc/cylc-src/flow/strong_scaling.csv`,
`weak_scaling.csv`, and `events/input_strong.in` were derived. Anything not
spelled out here was either inherited from Jake Faulkner's template (commit
`6243641`) or is mechanical.

## Goals

Two things:

1. **Confirm SW4 scales** on our HPCs — weak curve roughly flat, strong
   curve approaches ideal T(1)/N at least in the low-to-mid range.
2. **Calibrate future production SW4 runs** — get a reliable
   cell-steps/core/second figure so production wall-clocks can be
   estimated rather than guessed.

The test is designed to run on **multiple HPCs** (NeSI Mahuika genoa and
milan, Cascade, RCH) with results directly comparable across machines.

## Cross-HPC constraint: fixed 126 tasks per node

To keep results comparable across HPCs, every job uses **the same number of
tasks per node everywhere**. That number has to be the lowest common
denominator across the machines we target:

| Machine | Cores/node | Note |
|---|---|---|
| NeSI milan | 128 | Can host 126/node (2 cores idle) |
| NeSI genoa | 336 | Can host 126/node (210 cores idle) |
| Cascade (standard pool) | 384 | Can host 126/node (258 cores idle) |
| RCH `hcpu` (n01-n04) | 144 | Can host 126/node (18 cores idle) |
| RCH `hcpu,mem` (n09-n12, n16-n17) | 144 | Can host 126/node (18 cores idle) |
| RCH `hcpu,mem` (n18-n19) | 192 | Can host 126/node (66 cores idle) |
| RCH `mem` (n05-n08) | 72 | **Cannot** host 126/node — excluded |
| RCH `gpu` (n13-n15) | 36 | **Cannot** host 126/node — excluded |
| RCH `cloud` (c01-c10) | 64 | **Cannot** host 126/node — excluded |

So we pin `--ntasks-per-node=126` everywhere. On genoa / Cascade / RCH this
leaves the majority of each node's cores idle, which is wasteful but
unavoidable for comparability. On RCH we additionally use
`--constraint=hcpu` to steer Slurm away from the 72-core `mem` nodes,
36-core `gpu` nodes, and 64-core `cloud` nodes — all of which are tagged
with the `hcpu` feature absent.

### Practical node ceiling

The practical job-pickup limit on NeSI Mahuika is **4 nodes**. We use that
as the hard ceiling across all machines even when other HPCs could schedule
larger, so the node counts match everywhere. Core-count list becomes:

**126, 252, 378, 504** (i.e. 1, 2, 3, 4 nodes × 126).

Four data points across a 4× range — narrower than one normally wants, but
fixed by the cross-HPC node-count ceiling.

## Memory per task: ~4 M cells/core, `--mem-per-cpu=2500M`

Memory per task available at 126/node on each machine:

| Machine | Mem/node | Mem/task at 126/node |
|---|---|---|
| NeSI milan | ~491 GB | ~3.90 GB |
| **NeSI genoa** | **~358 GB** | **~2.84 GB (bottleneck)** |
| Cascade standard | 755 GB | ~5.99 GB |
| Cascade high-mem | 1511 GB | ~11.99 GB |
| RCH `hcpu` (n01-n04) | 604 GB (MemTotal) | ~4.79 GB |
| RCH `hcpu,mem` (n09-n12, n16-n19) | 906 GB | ~7.19 GB |

Genoa is the memory bottleneck at ~2.84 GB/task. We set
`--mem-per-cpu=2500M` (= 2.44 GiB per task = 307 GiB/node at 126 tasks);
still fits genoa (~333 GiB usable/node) with ~26 GiB headroom, and is a
trivial fraction of every other machine's per-node memory.

### Calibrated memory model (from first two runs)

The first run tried 12 M cells/core → OOM across the board. The second
tried 8 M cells/core → also OOM across the board, though strong runs at
lower cells/core (≤4 M) succeeded. Fitting `MaxRSS = A + B × cells_per_rank`
to the three successful runs' `sacct` data:

| Run | cells/core | MaxRSS |
|---|---|---|
| strong_test252 | 4.00 M | 2.17 GiB |
| strong_test378 | 2.67 M | 1.57 GiB |
| strong_test504 | 2.00 M | 1.22 GiB |

gives a clean linear fit (residuals <2%):

```
memory_per_task ≈ ~270 MiB + ~510 B × cells_per_task
```

This is notably higher than the textbook estimate (120 B/cell unattenuated
+ 72 B/cell for 3-SLS attenuation ≈ 192 B/cell). The ~510 B/cell figure
includes finite-difference time-step buffers, ghost/halo cells, and
intermediate work arrays — typical for a 3-D FD code. The ~270 MiB
per-rank overhead covers OpenMPI + UCX buffers and SW4 runtime state.

### Why 4 M cells/core

Predicted OOM threshold from the calibrated model:
`(2560 MiB − 270) / 510 B ≈ 4.7 M cells/core`. Sitting at 4 M leaves
~11% headroom against the 2500M budget (predicted MaxRSS 2.17 GiB,
measured 2.17 GiB at strong_test252) — thin but observationally
validated.

### Rule of thumb: SW4-with-attenuation memory footprint

For sizing future SW4 jobs with 3-SLS `attenuation` enabled (the SW4
default):

```
memory_per_task ≈ 510 B × (nx·ny·nz / n_tasks)  +  ~270 MiB overhead
```

Derived from `MaxRSS` of the three successful `strong_test*` runs at
2-4 M cells/core on genoa, fit to a two-parameter linear model. Caveats:
non-attenuated runs drop to ~120 B/cell for the main state (overhead
term probably similar). PML/supergrid layers, topography, or richer
material models would add more. Coefficients might differ on a different
HPC (different OpenMPI/UCX version, different NUMA topology).

### Alternatives considered (and why rejected)

- **~12 M cells/core at `--mem-per-cpu=2500M`**: first-run pick. Every
  weak_test126/strong_test126 OOM-killed. Rejected.
- **~8 M cells/core at `--mem-per-cpu=2500M`**: second-run pick. Every
  weak task and strong_test126 OOM-killed; strong runs at ≥252 cores
  (≤4 M cells/core) succeeded. Rejected.
- **~15-20 M cells/core at `--mem-per-cpu=3G`**: 126 × 3G = 378 GiB/node
  requested vs ~333 GiB usable on genoa — overflows. Rejected.
- **Bumping `--mem-per-cpu` 2500M → 2700-2800M to keep 8 M cells/core**:
  2800M × 126 = 352.8 GiB/node requested — exceeds genoa's ~333 GiB
  usable. Rejected on cross-HPC portability grounds.

## Core counts: 126, 252, 378, 504

Fixed by the 126-tasks-per-node and 4-node-ceiling constraints. Power-of-2
ideas are off the table — we just use multiples of 126.

## Strong-scaling grid: anchored to the weak cores=126 row

### The principle (inherited from Jake)

Jake picked his strong-scaling grid so its total cell count matched one of
the weak-scaling rows. This means:

- The strong runtime at its anchor core count ≈ the weak runtime at that
  core count, so the two panels of the scaling plot are directly comparable
  at that shared point.
- The grid size is already known to be feasible at that core count,
  because the weak test sizes it to fit.

Jake also reshaped the strong grid: instead of using the weak row's
`nx = ny, nz = 500` verbatim, he set `nx` to a small power of 2 and made
`ny = nz`. This moves the "square" dimension into the y-z plane and gives
SW4's 3-D decomposition more flexibility.

### Why anchor at cores=126 (not the middle)

With only 4 core-counts in the sweep, anchoring at the "middle" (between
252 and 378) means the strong test can only run at core counts ≥ anchor —
losing 126 and possibly 252 from the strong sweep (they'd need more memory
per task than we have). That leaves 2-3 strong points, too few for a
meaningful curve.

Anchoring at cores=126 keeps all 4 core counts usable in the strong sweep
(126, 252, 378, 504). The cost is that Jake's "match the middle weak row"
preference isn't honoured — but preserving 4 strong points matters more
than that aesthetic.

### Grid numbers

The weak cores=126 row is `1000 × 1000 × 500` = 500 M cells. Applying
Jake's reshape with nx=128:

```
128 × ny² ≈ 500 M
ny ≈ √(500 M / 128) ≈ 1976
```

Rounded to **nx=128, ny=1984, nz=1984** (total 503.8 M cells). At
cores=126 that's ~4.00 M cells/core; predicted MaxRSS ~2.17 GiB,
~11% under the 2500M budget.

## Walltime: `--time=03:00:00`

Measured throughput across the three successful second-run strong tests
was **635-685 k cell-steps/core/s** on genoa (per-core figure drops
slightly with more cores — expected strong-scaling communication
overhead).

At 1000 time steps and 4 M cells/core, expected runtime per weak row:

| Throughput | Runtime |
|---|---|
| 685 k (best observed, 252-core) | 1.62 h |
| 635 k (worst observed, 504-core) | 1.75 h |
| 500 k (pessimistic) | 2.22 h |
| 300 k (very pessimistic) | 3.70 h |

**3 h** gives ~35% headroom over the 500 k pessimistic case, stays well
inside the Slurm backfill-friendly window, and is still above the very
pessimistic 3.70 h figure in all but the worst case. If throughput
disappoints further, fall back to knob #2 below (halve `time steps`)
rather than growing the walltime.

## Rough cost estimate

Using best-observed (685 k) and pessimistic (500 k) throughputs:

- **Weak**: Σ cores × runtime
  - 685 k: (126+252+378+504) × 1.62 h ≈ 2 040 core-h
  - 500 k: (126+252+378+504) × 2.22 h ≈ 2 800 core-h
- **Strong**: 4 × (total cells × steps / throughput_per_core)
  - 685 k: 4 × 204 core-h ≈ 820 core-h
  - 500 k: 4 × 280 core-h ≈ 1 120 core-h
- **Total**: ≈ 2 860 core-h best case, ≈ 3 920 core-h pessimistic. On
  genoa at 126/node (37.5% packed) that's ~23-31 node-hours per HPC.

## Per-HPC adaptation notes

The `flow.cylc` is now parameterised by a Jinja `HPC` variable — pick
the target at install time:

```
cylc vip flow --set HPC="mahuika-milan"   # default
cylc vip flow --set HPC="mahuika-genoa"
cylc vip flow --set HPC="rch"
```

Each HPC entry at the top of `flow.cylc` sets `--partition`, `--account`,
`--hint`, `--mem-per-cpu`, `--constraint` (RCH only), the module-load
block, and the SW4 binary path. Everything else (grid sizing, core
counts, walltime, graph) is shared.

Per-target details:

- **NeSI mahuika-milan / mahuika-genoa**: same module stack and account;
  `--partition` differs. `--hint=nomultithread` is needed on milan
  (SMT on) and a harmless no-op on genoa (SMT off at BIOS).
- **RCH**: `--partition=short` (6h cap, covers our 5h walltime);
  `--constraint=hcpu` to steer onto the 144+ core nodes and skip the
  72-core `mem` / 36-core `gpu` / 64-core `cloud` pools. Module stack
  is `prefix/2025 + foss/2024a`, matching the GCC/13.3.0 + OpenMPI/5.0.3
  toolchain the pre-built SW4 binary at
  `/scratch/projects/rch-quakecore/sw4/optimize_mp/sw4` was linked
  against.
- **Cascade**: uses PBS, not Slurm — a separate Cylc platform config and
  directive translation is required (qsub-style `mem=`, etc.). Not yet
  implemented; would be a fourth `{% elif HPC == 'cascade' %}` block in
  `flow.cylc` plus a new `cascade` entry in `cylc/global.cylc`.

The sizing choices in this doc (126 tasks/node, 4 M cells/core, 5h
walltime) carry over to every HPC unchanged.

## Knobs if things go wrong

Further diagnostics, cheapest-to-apply first (the first two runs' OOMs at
12 M and 8 M cells/core have been addressed by dropping to 4 M and
calibrating the memory model from `sacct MaxRSS`):

1. **Jobs still OOM at 4 M cells/core**: per-rank overhead is higher than
   the ~270 MiB we fitted, or per-cell is >~510 B. Drop cells/core to 3 M
   (edit the CSVs).
2. **Jobs hit the 5 h walltime limit**: throughput is well below our
   measured 500-685 k range. Drop `time steps=500` in `input_*.in`
   (halves runtime; still enough steps to see scaling).
3. **Submission rejected with "Requested node configuration is not
   available"**: probably a QOS or partition-specific task-per-node / total
   CPU cap. Check `sacctmgr show qos` and try adding `--qos=normal` to the
   directives. (We hit this once with a 256-ntasks-on-1-node request at
   `--mem-per-cpu=1G`; the 126/node layout may sidestep it, but flagging
   here in case.)

All three are one-line edits; rerun with `cylc vip flow`.
