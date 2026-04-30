# Why is cascade's weak throughput so much higher than its strong throughput?

Companion note to `cross-hpc-throughput.md`. Captured because the gap is
peculiar to cascade and worth investigating later.

## The puzzle

At single-node (126 cores), per-core work is identical between strong
and weak: each rank gets ~4 M cells × 1000 time steps. Yet on cascade
the per-core throughput differs sharply:

| HPC | Strong @ 126 | Weak @ 126 | Strong / Weak |
|---|---|---|---|
| genoa   | 2.60 | 2.45 | 1.06 (≈ flat) |
| milan   | 1.72 | 1.62 | 1.06 (≈ flat) |
| rch     | 1.36 | 1.27 | 1.07 (≈ flat) |
| cascade | 2.55 | **3.58** | **0.71** (weak ~40 % higher) |

Units: G cell updates / core-hour.

The gap is already present at 1 node, before any inter-node
communication, so it is not a strong-scaling efficiency artefact. It
appears to be cascade-specific and shows up as soon as the grid shape
changes.

Subdomain shapes at 126 cores under SW4's typical 2D decomposition
(innermost contiguous dim kept whole, other two split):

- Strong (`128 × 1984 × 1984`) → per-rank ≈ `128 × 140 × 220` —
  slab-like, 128-element first dimension.
- Weak (`1000 × 1000 × 500`) → per-rank ≈ `70 × 110 × 500` — closer
  to cubic, longer contiguous dim.

## Hypotheses

Ordered roughly by perceived plausibility. None verified.

### H1 — Subdomain shape × Intel-build vectoriser (most likely)

If cascade's SW4 was built with Intel oneAPI + Spack at `-O3 -xHost`,
it has AVX-512 + FMA enabled on Genoa-class hardware. NeSI's genoa
build is GCC + Cray-MPICH and may use narrower SIMD or less
aggressive prefetch.

If so:

- The Intel build extracts more from longer, more uniform inner loops.
- The weak grid's subdomain shape gives a longer effective vector
  length per inner-loop body than the strong grid's 128-element
  x-extent allows.
- Genoa's GCC build doesn't see this difference because it isn't
  exploiting the wider SIMD as hard either way — so genoa's strong
  and weak throughputs are similar.

This is the same axis that already explains two other cascade-only
anomalies (cf. `cross-hpc-throughput.md` § Bandwidth hypothesis):

1. Cascade's weak throughput beats genoa's by ~45 % despite identical
   nominal hardware.
2. Cascade's NaN-check overhead is ~7× lower than genoa's
   (~2 % vs. ~9 %).

Three independent measurements pointing at the cascade software
stack is suggestive.

### H2 — Cache fit / memory access pattern

The strong subdomain's innermost-contiguous working set is ~4× larger
than the weak subdomain's (z = 1984 vs. z = 500, if z is innermost).
On Zen4, each core has 1 MB L2; the weak subdomain may fit in L2
where the strong does not. DDR5 prefetch on cascade may hide the
difference well for one shape and badly for the other.

Genoa has the same cache hierarchy, so cache fit alone does not
explain a cascade-specific gap — unless Intel's prefetch hints
(which the GCC build does not emit) are what is making the
difference. So this hypothesis collapses back into H1 if pursued.

### H3 — MPI decomposition imbalance (unlikely to be dominant)

128 does not divide as cleanly as 1000 across 126 ranks, so SW4 may
choose a more lopsided 2D decomp for the strong grid. But this would
hurt every HPC, not just cascade — and the data shows the other
three HPCs barely register a strong-vs-weak gap. So this is at most
a minor contributor.

## What would settle it

Cheap-to-very-cheap experiments, in order of effort:

1. **Inspect cascade's SW4 build flags.** Spack records this in the
   install manifest:

   ```
   spack find -v sw4
   spack spec -I sw4
   ```

   Confirms or kills H1 cheaply. Look for `-xHost`,
   `-march=znver4` / `-mavx512f`, `-O3`, FMA enablement, and the
   Intel ICX / ICC compiler ID.

2. **Single-node, same cell count, different shape** on cascade. Run
   the strong-shape grid (~504 M cells, slab) and a weak-shape grid
   (~500 M cells, cubic) at 126 cores and compare per-core
   throughput. If the gap stays, it is shape-driven (cache, SIMD
   length); if it closes, the original measurement was confounded
   with something else.

3. **Less-skewed strong grid on cascade**, e.g. `512 × 992 × 992`
   (same cell count as the current strong grid, more uniform aspect
   ratio). If the gap to weak closes, the issue is the
   `128 × 1984 × 1984` aspect ratio specifically, not strong-vs-weak
   in general.

4. **GCC-built SW4 on cascade**, same Spack environment minus the
   Intel compiler. If GCC-on-cascade behaves like GCC-on-genoa
   (flat across strong and weak), H1 is essentially confirmed.

Step 1 is a single shell command and should be done first.

## Pointers

- Plot data and units: `cross-hpc-throughput.png`,
  `cross-hpc-throughput.md` (Headline numbers, Strong-scaling
  efficiency, Weak-scaling stability sections).
- Throughput formula: `scripts/compare_scaling.py:59–79`.
- Grid sizes: `WEAK_GRIDS` and `STRONG_GRID` constants in
  `compare_scaling.py:39–42`, mirrored in
  `cylc/cylc-src/flow/{weak,strong}_scaling.csv` and
  `cylc/cylc-src/flow/events/input_strong.in`.
