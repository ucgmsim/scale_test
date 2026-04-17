# SW4 scaling test — rationale for the chosen numbers

This note explains how the numbers in `cylc/cylc-src/flow/strong_scaling.csv`,
`weak_scaling.csv`, and `events/input_strong.in` were derived on the
`full-sw4-scale-tests` branch. Anything not spelled out here was either
inherited from Jake Faulkner's template (commit `6243641`) or is mechanical
(node counts from ⌈cores / 336⌉, etc.).

## Goals

Two things:

1. **Confirm SW4 scales** on NeSI Mahuika — i.e. the weak curve is roughly
   flat and the strong curve approaches ideal T(1)/N, at least in the low-
   to mid-core-count range.
2. **Calibrate future production SW4 runs** — get a reliable
   cell-steps/core/second figure at a representative cells/core budget, so
   production wall-clocks can be estimated up-front rather than guessed.

Goal #2 dictates that the scaling test should run on the same partition and
at the same memory packing as production will. Anything else gives numbers
that don't transfer.

## Partition: genoa

Mahuika options were **genoa** (56 nodes × 336 cores, AMD EPYC 9654, DDR5,
~367 GB/node ≈ 1.09 GB/core) vs **milan** (63 nodes × 128 physical cores,
Zen 3, DDR4, ~491 GB/node ≈ 3.8 GB/core). We chose genoa because:

- DDR5 gives ~1.5× the memory bandwidth per socket of milan's DDR4. SW4 is a
  stencil code and therefore memory-bandwidth-bound, so this matters a lot.
- No SMT on genoa. Milan reports 256 CPUs/node but only 128 are physical;
  oversubscribing physical cores typically hurts SW4, and avoiding that
  requires remembering to set `--hint=nomultithread`. Genoa is foot-gun-free.
- More cores/node (336 vs 128 physical) means fewer nodes for the same core
  count → less inter-node MPI traffic at the top of the sweep.
- Future SW4 production runs will almost certainly target genoa for the same
  reasons. A milan scaling test wouldn't characterise the platform we
  actually care about.

Milan's only real advantage is more memory per core, and we don't need it at
our cells/core target (see below).

## Memory packing: `--mem-per-cpu=1G`, ~7.2 M cells/core

Genoa has ~1.09 GB/core when packed to the full 336 cores/node. At
`--mem-per-cpu=1G`, Slurm will fit all 336 cores on a node without forcing
under-packing, and SW4 gets ~1024 MB of addressable memory per rank.

SW4's steady-state memory is roughly 128 B/cell (31 floats of state plus
some edge buffers). So 1024 MB / 128 B ≈ 8.0 M cells/core upper bound. We
target **7.2 M cells/core** (~922 MB/core, ~100 MB headroom for MPI buffers,
attenuation state, and stdout).

### Why not more generous?

The two alternatives we considered were both worse for the "calibrate
production" goal:

- **Bump `--mem-per-cpu=2G` to match Jake's 12 M cells/core.** This caps
  genoa at ~183 cores/node (~45% of every node idle). Production runs won't
  waste cores like that, so the scaling test would measure the wrong
  memory-bandwidth regime — unrepresentative.
- **Shrink to ~5 M cells/core for safety headroom.** Fits comfortably but
  measures SW4 at a different cache/bandwidth operating point than
  production will use. Less bad than the above, but still not quite the
  right calibration signal.

The chosen 7.2 M cells/core is an optimistic-but-verifiable point. If the
first job OOMs or runs slower than expected, the fix is a cheap one-line
edit (drop to 5 M cells/core or bump `--mem-per-cpu=1500M`) and rerun.

## Core counts: powers of 2, 64 → 2048

Jake's CSV used 64, 128, 256, 512, 750, 1000, 1250, 1500. We replaced the
awkward top-end values (750, 1250, 1500) with powers of 2 for two reasons:

- **Clean MPI decomposition.** SW4 does 2-D Cartesian decomposition of the
  horizontal plane. Powers of 2 factor cleanly into roughly-square rank
  grids (e.g. 1024 = 32 × 32); 1250 factors as 2 × 5⁴, which gives
  2 × 625, 5 × 250, 25 × 50, etc. — all far from square.
- **Easier to interpret scaling curves.** Each point is exactly 2× the
  previous, so efficiency loss per doubling reads straight off the plot.

The top end of 2048 cores uses ~6 genoa nodes (2048 / 336 ≈ 6.1), well
inside the 56-node partition. The bottom end of 64 cores fits in a single
node (64 / 336 ≈ 19% of a node).

## Strong-scaling grid: anchored to the weak cores=128 row

### The principle (inherited from Jake)

Jake picked his strong-scaling grid so its total cell count matched one of
the weak-scaling rows. This means:

- The runtime of the strong test at its anchor core count is (roughly) the
  weak-scaling runtime at that core count — so the two panels of the
  scaling plot are directly comparable at that shared point.
- The grid size is already known to be feasible at that core count, because
  the weak test sizes it to fit.

Jake anchored to the middle row of his sweep (cores=512 out of 64-1500).
He also reshaped the grid: instead of using the weak row's `nx = ny, nz =
500` verbatim, he set `nx` to a small power of 2 (equal to the anchor core
count) and made `ny = nz` (so the "square" dimension moves into the
y-z plane). This gives SW4's 3-D decomposition more flexibility.

### Why anchor at cores=128 instead of the middle

With our 6-row sweep (64-2048), the geometric middle is between 256 and 512.
Anchoring at 512 would mean total cells ≈ 3.7 B, which at 7.2 M cells/core
requires ≥ 3.7 B / 8 M ≈ 460 cores to fit in memory. That drops cores=64,
128, 256 from the strong sweep — leaving only 3 points (512, 1024, 2048),
which isn't enough to see a scaling curve shape.

Anchoring at cores=128 keeps 5 of the 6 core counts usable in the strong
sweep (128, 256, 512, 1024, 2048) while still following Jake's "match one
weak row" principle. The cost is only losing the cores=64 point from the
strong sweep — a reasonable trade for keeping 5 good strong-scaling points.

### Grid numbers

The weak cores=128 row is `1360 × 1360 × 500` ≈ 925 M cells. Applying
Jake's reshape (nx = anchor cores, ny = nz) preserving total cells:

```
nx × ny² = 925 M
nx = 128  →  ny = √(925 M / 128) ≈ 2688
```

Strong grid: **nx=128, ny=2688, nz=2688**, total 924.8 M cells. The `ny`
value comes out to a clean integer because 925 M was itself chosen to give
7.225 M cells/core at 128 ranks — the same target we used for the whole
weak CSV.

## Walltime: `--time=05:00:00`

From the smoke-test calibration, SW4 on genoa delivers roughly
**800 k cell-steps/core/sec** at the (small) smoke-test grid sizes. At 7.2 M
cells/core × 1000 time steps, an ideal-scaling run takes:

```
7.2e6 × 1000 / 8e5 ≈ 9000 s ≈ 2.5 h
```

The strong-scaling run at its smallest core count (cores=128, 925 M cells)
is the same ~9000 s by construction, and halves at each doubling above.

5 hours gives ~2× headroom on the weak and strong-low-end runs. The
conservatism costs nothing — Slurm only charges elapsed time, not requested
time. The only downside is slightly longer queue waits for 5 h jobs vs
3 h ones under Slurm's backfill scheduler, which is a minutes-to-hours
penalty, not days.

## Rough cost estimate

Under ideal scaling (reality will be somewhat worse):

- **Weak**: Σ cores × 2.5 h = (64 + 128 + 256 + 512 + 1024 + 2048) × 2.5 h
  ≈ 10,080 core-hours.
- **Strong**: 5 runs × 925 M × 1000 / 800 k = 5 × ~321 core-hours
  ≈ 1,600 core-hours (each strong run has the same *total* core-seconds under
  ideal scaling).

Total: ≈ 12 k core-hours ideal, realistically 15-20 k core-hours with
scaling losses. On genoa that's ~45 node-hours — comfortably inside the
56-node partition.

## Knobs if things go wrong

First-run diagnostics, cheapest-to-apply first:

1. **Jobs OOM quickly** (first few time steps): SW4's actual memory/cell
   exceeded our 128 B estimate, likely because of attenuation state. Either
   drop cells/core to ~5 M (edit the CSVs) or bump `--mem-per-cpu=1500M`
   (edit `flow.cylc`; accept ~27% under-packing per node).
2. **Jobs hit the 5 h walltime limit**: actual throughput is below 800 k
   cell-steps/core/sec. Either bump `--time=08:00:00` or drop
   `time steps=500` in the `input_*.in` files (halves runtime, still enough
   steps for a meaningful scaling measurement).
3. **Only the largest-core-count jobs fail / pend indefinitely**: genoa
   partition is busy. Lower `limit = 5` under `[[queues]]` to stagger
   submissions, or remove the cores=2048 row temporarily.

All three are one-line edits; rerun with `cylc vip flow`.
