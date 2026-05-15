# Estimating wall-time and core-hours

To plan an SW4 simulation, you need two estimates:

- **Wall-clock time** — how long you'll wait for the job to finish.
- **Core-hours** — how much of your HPC allocation it will consume.

Both follow from one number per HPC: **per-core throughput** in
*Giga (G) cell-updates per core-hour*. Look the number up below, plug it
into the formula, and you've got an estimate good to ±20 % (often
better) on the HPCs we've measured.

See the [Home page](Home.md) for the list of HPCs and high-level
guidance on which to pick.

## The formula

The work done by an SW4 simulation is well-approximated by the
total **cell-updates** — every cell in every time step counts as
one update:

```
total_cell_updates = nx × ny × nz × time_steps
```

Given a per-core throughput `T` (in G cell-updates / core-hour) and
a rank count `cores`:

```
core_hours  = total_cell_updates / (T × 10⁹)
wall_hours  = core_hours / cores                    # ideal scaling
```

Both formulas assume ideal scaling (no overhead from inter-node
communication). Real workloads see scaling efficiency below 100 %
— see the [Scaling efficiency](#scaling-efficiency) section
below for how much to derate by.

## Per-HPC throughput

Values are per-core throughput at 126 ranks/node, no NaN checking,
in *G cell-updates per core-hour*. The numbers assume a
**roughly cubic per-rank brick** — what you get on a typical
production earthquake simulation with large horizontal extent and
moderate depth.

> **Heads-up for slab-shaped grids.** If one global dim of your
> simulation is much smaller than the others (typically `nz ≤ ~150`
> cells, e.g. a very shallow regional model), per-core throughput is
> lower than the table below: ~30 % on AVX-512 binaries (cascade
> and NeSI/RCH after rebuild), 15–25 % on AVX-2, negligible on SSE2.
> See [Grid shape effect](#grid-shape-effect) below for the
> mechanism and per-binary numbers.

### Today's measured numbers

These are what the scale-test campaigns have actually returned:

| HPC                | Per-core throughput | Notes                                    |
|---                 |---                  |---                                       |
| Cascade            | **3.54**            | Zen4 + AVX-512 + DDR5-4800               |
| Mahuika genoa      | 2.45                | Zen4 + DDR5-4800, **SSE2-only binary**   |
| Mahuika milan      | 1.54                | Zen3 + DDR4-3200, SSE2-only binary       |
| RCH hcpu           | 1.20                | Zen3 + DDR4, SSE2-only binary            |

### Projected post-rebuild numbers

The NeSI and RCH binaries have been rebuilt with `-march=znver{3,4}`
to enable AVX-2/AVX-512. The post-rebuild scaling-test campaign is
queued; until results come back, predicted numbers are:

| HPC                | Predicted weak | Confidence                          |
|---                 |---             |---                                  |
| Mahuika genoa      | ~3.5           | High — should match cascade closely |
| Mahuika milan      | ~2.0           | Medium                              |
| RCH n              | ~1.5           | Medium                              |

This page will be updated with the empirical numbers once the
campaign completes.

## Worked examples

### Example 1: a regional simulation on cascade

A 2000 × 2000 × 500 grid (100 × 100 × 25 km at 50 m spacing) for
50 000 time steps, planned for cascade:

```
total_cell_updates = 2000 × 2000 × 500 × 50000 = 1.0 × 10¹⁴ cell-updates
core_hours         = 1.0 × 10¹⁴ / (3.54 × 10⁹) ≈ 28 000 core-hours
```

At 384 cores per node, a 4-node allocation (1536 cores):

```
wall_hours = 28 000 / 1536 ≈ 18 hours
```

So about **18 hours of wall-clock time** and **28 000 core-hours**
of budget burn. (Apply weak-scaling efficiency derating — see below
— for a more conservative estimate: 28 000 / 0.98 ≈ 28 600
core-hours, wall ~18.6 hours.)

Memory check at 1536 cores: `cells_per_rank ≈ 1.3 M`, `mem_per_task
≈ 270 + 0.510 × 1300 ≈ 933 MiB` — fits comfortably under
`--mem-per-cpu=2500M`.

### Example 2: the same job on NeSI milan

Same grid, same time steps, but on milan today (SSE2-only binary):

```
core_hours = 1.0 × 10¹⁴ / (1.54 × 10⁹) ≈ 65 000 core-hours
```

At 128 cores per node, a 4-node allocation (512 cores), with the
84 % weak-scaling efficiency derating already factored in:

```
adjusted_core_hours = 65 000 / 0.84 ≈ 77 000 core-hours
wall_hours          = 77 000 / 512  ≈ 150 hours ≈ 6.3 days
```

So **2.3× the core-hours** of cascade and **8× the wall-clock time**
(milan has fewer cores per node, so the same 4 nodes is only 512
cores vs. cascade's 1536). After the rebuild lands, expect ~30 %
better on milan, but it remains substantially slower than the Zen4
HPCs for stencil work.

### Example 3: a short test run on genoa

A 500 × 500 × 200 grid for 1000 time steps — typical "does it run"
shakedown:

```
total_cell_updates = 500 × 500 × 200 × 1000 = 5.0 × 10¹⁰ cell-updates
core_hours         = 5.0 × 10¹⁰ / (2.45 × 10⁹) ≈ 20 core-hours
wall_hours         = 20 / 126 ≈ 0.16 hours ≈ 10 minutes
```

So a **10-minute test run** for 20 core-hours on a single node.
Useful as a calibration before submitting the full job.

## Scaling efficiency

The numbers above are per-core throughput at a single node (126
ranks). When you scale out, per-core throughput drops because of
inter-node communication. For a workload where the problem grows
with the number of cores (the typical case for large production
runs), the 4-node empirical efficiency is:

| HPC                 | 1 → 4 node efficiency |
|---                  |---                    |
| Cascade             | 98 %                  |
| NeSI Mahuika genoa  | 97 %                  |
| NeSI Mahuika milan  | 84 %                  |
| RCH hcpu            | 87 %                  |

To incorporate, divide your `core_hours` estimate by the relevant
efficiency:

```
adjusted_core_hours = core_hours / efficiency
```

For most planning purposes, **assume ~95 %** on Zen4/DDR5 HPCs
(cascade, genoa) and **~85 %** on Zen3/DDR4 HPCs (milan, RCH). For
fixed-size workloads spread across many cores (a less common pattern
where the per-core work shrinks as cores grow), per-core efficiency
is lower — see the corresponding numbers in
[`docs/cross-hpc-throughput.md`](https://github.com/ucgmsim/scale_test/blob/main/docs/cross-hpc-throughput.md).

## Grid shape effect

The per-HPC numbers above assume a **roughly cubic per-rank brick**.
A grid like 1000 × 1000 × 500 — large horizontal extent, moderate
depth — produces that. SW4's MPI decomposition preserves the
smallest global dim whole and splits the other two across ranks,
so the per-rank brick ends up shape-matched to the global one.

If your global grid is **slab-shaped** (one dim much smaller than
the others, e.g. 128 × 1984 × 1984 for a shallow shelf or a very
thin sediment basin), the per-rank brick has a shorter inner loop
and wide-SIMD machinery under-uses its lanes. Per-core throughput
is lower than the table by:

| Binary's SIMD width | Shape effect on slab grids (vs. cubic numbers) |
|---                  |---                                             |
| AVX-512 (cascade, NeSI/RCH post-rebuild)             | **~30 % lower** (up to ~40 % for very slab-y shapes) |
| AVX-2 (NeSI/RCH post-rebuild w/o AVX-512)            | ~15–25 % lower |
| SSE2 (NeSI/RCH pre-rebuild)                          | < 10 % (within noise) |

Quick rule for whether your grid is "slab-shaped" for this purpose:
if `nz / max(nx, ny) ≲ 0.1` (or any other axis is similarly small),
apply the slab derating.

For production-tuning beyond this rough cut — including the
closed-form back-of-envelope optimum for picking grid dimensions —
see [`docs/sw4-domain-shape-tuning.md`](https://github.com/ucgmsim/scale_test/blob/main/docs/sw4-domain-shape-tuning.md)
in the main repo.

## Memory

SW4's per-rank memory footprint is well-modelled by:

```
memory_per_task_MiB ≈ 270 + 0.000510 × cells_per_rank
                    ≈ 270 + 0.51 × (cells_per_rank / 1000)
```

(Derived empirically from OOM-calibration runs at 8 M / 12 M
cells/core. Applies to the standard SW4-with-attenuation
configuration; PML / supergrid / topography would add more.)

At the **~4 M cells/core** sizing used in the scaling tests, that's
~2.3 GiB per rank — sized to fit comfortably in `--mem-per-cpu=2500M`
on NeSI genoa with margin.

If you're sizing a new run, the inverse formula is:

```
max_cells_per_rank ≈ (mem_per_cpu_MiB − 270) / 0.000510
```

At `mem_per_cpu=2500M`: ~4.4 M cells/core; sit at 4 M for headroom.

## Caveats

- **The numbers are per-core throughput at 126 ranks/node.** That's
  the cross-HPC comparability point, not the per-HPC optimum.
  Production users on genoa typically want all 336 cores/node; the
  per-core throughput at higher node fill is workload-dependent.
- **NaN checking adds overhead.** On AVX-512 binaries (cascade,
  rebuilt genoa) the overhead is ~2 %. On SSE2 binaries it's ~9–12 %.
  Account for it if you'll be enabling `developer checkfornan=on`.
- **MPI/launch overhead is ignored.** Each SW4 invocation has a
  startup cost of seconds-to-minutes that isn't captured in the
  cell-update math. For jobs of more than a few minutes wall-time,
  ignorable; for very short jobs, add a fixed budget.
- **The throughput numbers were measured on a synthetic workload**
  (uniform velocity model, simple point source, 1000 time steps,
  uniform 100 m grid). Real production workloads with topography,
  attenuation, or non-trivial source descriptions may run slower —
  budget ~10–20 % extra for these effects.
- **Milan has high per-job variance**: an individual milan run can
  land at 60–150 % of the table value depending on which physical
  node Slurm picks. Plan for the worst case if you need wall-time
  guarantees.

## Choosing an HPC

By workload type:

| Goal                                       | Best choice                          | Why                                                |
|---                                         |---                                   |---                                                 |
| Maximum throughput per core-hour           | **Cascade** (or genoa-after-rebuild) | AVX-512 + DDR5 + flat 98 % scaling out to 4 nodes  |
| Predictable wall-clock budget              | **Cascade**                          | Tightest spread (~98 % stability, no zigzag)       |
| Fallback when DDR5 HPCs unavailable        | **RCH hcpu**                         | Steady DDR4 performance, consistent across jobs    |
| Last resort                                | NeSI milan                           | Works, but variance is bad enough to plan around   |

By queue availability: at any given moment one of the above may be
oversubscribed; the table above is a "given equal queue waits" guide.
For long-running production work it's often worth submitting to two
HPCs in parallel and using whichever gets allocated first.
