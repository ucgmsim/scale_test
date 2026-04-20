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
| RCH n01-n04 | 128 | Can host 126/node (2 cores idle) |
| RCH n09-n12, n16-n17 | 128 | Can host 126/node (2 cores idle) |
| RCH n05-n08 | 64 | **Cannot** host 126/node — excluded |

So we pin `--ntasks-per-node=126` everywhere. On genoa / Cascade this leaves
the majority of each node's cores idle, which is wasteful but unavoidable
for comparability.

### Practical node ceiling

The practical job-pickup limit on NeSI Mahuika is **4 nodes**. We use that
as the hard ceiling across all machines even when other HPCs could schedule
larger, so the node counts match everywhere. Core-count list becomes:

**126, 252, 378, 504** (i.e. 1, 2, 3, 4 nodes × 126).

Four data points across a 4× range — narrower than one normally wants, but
fixed by the cross-HPC node-count ceiling.

## Memory per task: ~12 M cells/core, `--mem-per-cpu=2500M`

Memory per task available at 126/node on each machine:

| Machine | Mem/node | Mem/task at 126/node |
|---|---|---|
| NeSI milan | ~491 GB | ~3.90 GB |
| **NeSI genoa** | **~358 GB** | **~2.84 GB (bottleneck)** |
| Cascade standard | 755 GB | ~5.99 GB |
| Cascade high-mem | 1511 GB | ~11.99 GB |
| RCH n01-n04 | 590 GB | ~4.68 GB |
| RCH n09-n12, n16-n17 | 885 GB | ~7.02 GB |

Genoa is the memory bottleneck at ~2.84 GB/task. We set
`--mem-per-cpu=2500M` (= 2.44 GiB per task = 307 GiB/node at 126 tasks);
still fits genoa (~333 GiB usable/node) with ~26 GiB headroom, and is a
trivial fraction of every other machine's per-node memory.

### Why 2500M rather than 2G

Unattenuated SW4 uses roughly 30 floats per cell (~120 B/cell). The input
file enables `attenuation` (SW4 default 3 SLS mechanisms), which adds
~6 memory variables per mechanism = ~18 × 4 B ≈ **72 B/cell extra**.
Realistic SW4-with-attenuation memory is therefore **~190-200 B/cell**,
not the 128 B/cell that a naive state-only count gives.

At 12 M cells/core × 200 B/cell = 2.24 GiB/task — overflows a 2 GiB
budget. At 2500M (2.44 GiB) budget, we have ~8% headroom at 200 B/cell
and ~31% headroom if the real figure is closer to 150 B/cell. First-run
will tell us where we actually sit.

### Alternatives considered

- **~7 M cells/core at `--mem-per-cpu=1G`**: matches what a fully-packed
  (every core active) production run would see. But since our 126/node
  layout leaves most node memory idle anyway, there's no point shrinking.
- **~15-20 M cells/core at `--mem-per-cpu=3G`**: uses more of the
  available memory. On genoa, 126 × 3 G = 378 GiB/node requested vs ~333
  GiB usable — overflows. Rejected.

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

The weak cores=126 row is `1740 × 1740 × 500` ≈ 1.514 B cells. Applying
Jake's reshape with nx=128:

```
128 × ny² ≈ 1.514 B
ny ≈ √(1.514 B / 128) ≈ 3439
```

Rounded to nice clean **nx=128, ny=3440, nz=3440** (total 1.515 B cells).
At cores=126 that's ~12.02 M cells/core ≈ 1.80 GB/task ✓.

## Walltime: `--time=12:00:00`

The smoke-test calibration gave ~800 k cell-steps/core/s, but at tiny
grids (~10⁵ cells/core, entirely cache-resident on Zen 4). At our new
12 M cells/core the working set is ~1.8 GiB per rank — vastly larger
than any core's L3 cache (~96 MiB on genoa). Throughput will be
memory-bandwidth-bound, with attenuation state adding extra traffic per
step. Realistic throughput is probably **400-600 k cell-steps/core/s**.

At 1000 time steps, expected runtime per weak row:

| Throughput | Runtime |
|---|---|
| 800 k (smoke, optimistic) | 4.2 h |
| 500 k (realistic guess) | 6.7 h |
| 300 k (pessimistic)     | 11.1 h |

**12 h** gives meaningful headroom even under the pessimistic throughput
scenario. Slurm only charges elapsed time, so over-requesting wall-clock
is essentially free apart from slightly longer queue waits under Slurm's
backfill scheduler.

## Rough cost estimate

Ideal scaling (reality will be worse). Throughput-sensitive, so we give
both optimistic (800 k cell-steps/core/s) and realistic (500 k) figures:

- **Weak**: Σ cores × runtime
  - 800 k: (126+252+378+504) × 4.2 h ≈ 5 300 core-h
  - 500 k: (126+252+378+504) × 6.7 h ≈ 8 400 core-h
- **Strong**: 4 × (total cells × steps / throughput)
  - 800 k: 4 × 526 core-h ≈ 2 100 core-h
  - 500 k: 4 × 842 core-h ≈ 3 400 core-h
- **Total**: ≈ 7 400 core-h optimistic, ≈ 11 800 core-h realistic. On
  genoa at 126/node (37.5% packed) that's ~58-94 node-hours per HPC.
  Comfortably inside partition capacity either way.

## Per-HPC adaptation notes

The `flow.cylc` currently hard-codes `--partition=genoa` — for runs on
other HPCs, these directives need per-HPC overrides:

- **NeSI milan**: change `--partition=genoa` → `--partition=milan`. May
  need `--hint=nomultithread` since milan has SMT.
- **Cascade**: uses PBS, not Slurm — a separate Cylc platform config and
  directive translation is required (qsub-style `mem=`, etc.).
- **RCH**: Slurm-based; will need RCH-specific partition / account names.

These are out of scope for this branch; the sizing choices in this doc
carry over to every HPC unchanged.

## Knobs if things go wrong

First-run diagnostics, cheapest-to-apply first:

1. **Jobs OOM quickly** (first few time steps): SW4's per-cell memory
   exceeded even the ~200 B/cell allowance. Drop cells/core to 8-9 M
   (edit the CSVs) — don't bump `--mem-per-cpu` further, as 2500M is
   already close to genoa's per-node ceiling at 126/node.
2. **Jobs hit the 12 h walltime limit**: throughput is below our
   pessimistic 300 k cell-steps/core/s estimate. Drop `time steps=500`
   in `input_*.in` (halves runtime; still enough steps to see scaling).
3. **Submission rejected with "Requested node configuration is not
   available"**: probably a QOS or partition-specific task-per-node / total
   CPU cap. Check `sacctmgr show qos` and try adding `--qos=normal` to the
   directives. (We hit this once with a 256-ntasks-on-1-node request at
   `--mem-per-cpu=1G`; the 126/node layout may sidestep it, but flagging
   here in case.)

All three are one-line edits; rerun with `cylc vip flow`.
