# SW4 simulation domain shape: tuning guide

When running large SW4 simulations, the *shape* of the simulation
domain (nx × ny × nz cell counts) interacts with how SW4 decomposes
work across MPI ranks, which in turn interacts with how each rank's
CPU and memory hierarchy chew through the data. On a wide-SIMD binary
(AVX-512, i.e. `-march=znver4`) this shape effect is worth roughly
**10–40 %** of per-core throughput on a million-core-hour campaign.
On the current SSE2-only NeSI / RCH binaries the effect is too small
to bother chasing — but those binaries should be rebuilt anyway, see
`building-sw4-on-nesi-and-rch.md`.

This doc layers from coarse rules of thumb to the underlying mechanics
so you can stop at whatever level of detail is useful.

## The basic principle

SW4's hot kernels are 3-D finite-difference stencils. They iterate
over the per-rank brick of cells in nested loops, with one of the
three loops as the innermost. Within that innermost loop, modern CPUs
use SIMD to compute several cells per instruction (2 with SSE2, 4
with AVX2, 8 with AVX-512), and hardware prefetchers stream cache
lines ahead of the loop. Both pieces of machinery have **fixed
startup costs** that are amortised over the inner loop's trip count.

Two consequences:

1. The **innermost loop should be long** so the SIMD pipeline and
   prefetcher reach steady state.
2. The **per-rank working set should fit in cache** (or at least be
   amenable to streaming from DRAM), or the kernel becomes
   memory-bandwidth-bound and SIMD width stops mattering.

Domain shape controls both. The rest of this doc is "how to pick a
shape that satisfies both."

## Coarse rules of thumb (the 80 % layer)

Four habits get you most of the way without any math:

1. **Prefer cubic-ish per-rank bricks** over slab-like ones. Halo
   communication scales with surface area; cubic minimises that.
2. **Avoid extreme aspect ratios in the global domain.** A
   100 × 2000 × 2000 grid forces lopsided per-rank bricks no matter
   how you decompose it.
3. **Pick rank counts with near-square 2D factorisations.**
   144 = 12 × 12 is much friendlier than 126 = 9 × 14. At 256 ranks,
   prefer 16 × 16 over 8 × 32. At 1024, prefer 32 × 32.
4. **Pad the global domain so the splits divide evenly.** If you're
   running 144 ranks and your physics suggests 1000 × 1000 × 500,
   bump it to 1008 × 1008 × 504. That's <1 % more cells but
   eliminates uneven per-rank bricks and ragged tail loops.

If you're picking domain shapes for a big campaign, doing just these
four things is the high-leverage move.

## The underlying mechanics

### MPI decomposition: where the per-rank brick comes from

SW4 splits the global grid across MPI ranks using a 2D strategy: it
keeps one dim whole (the smallest, to avoid wasting cells on halo
exchange across thin slabs) and slices the other two across ranks in
a roughly square 2D factorisation of the rank count.

For 126 ranks (9 × 14):

| Global grid       | Kept whole | Sliced                          | Per-rank brick      |
|---                |---         |---                              |---                  |
| 1000 × 1000 × 500 | 500        | 1000 ÷ 9 ≈ 111, 1000 ÷ 14 ≈ 71  | 71 × 111 × 500      |
| 128 × 1984 × 1984 | 128        | 1984 ÷ 9 ≈ 220, 1984 ÷ 14 ≈ 140 | 128 × 140 × 220     |

The per-rank brick is what each CPU core actually iterates over. Its
shape is a *function of the global grid and the rank count*; you
don't pick it directly, but you can reach the brick you want by
adjusting either input.

### Three competing pressures

The brick shape gets tugged in three directions:

| Pressure                       | Wants brick to be...     | Why |
|---                             |---                       |---  |
| Halo communication             | Cubic                    | Surface area is minimised when a = b = c. Halo cells go over the network every step. |
| SIMD / prefetcher amortisation | Long in the innermost dim | Inner-loop trip count must be ≫ SIMD width × pipeline depth to reach steady state. |
| Cache fit                      | Constrained on the *non*-innermost dims | The stencil touches several adjacent planes simultaneously; the working set must fit in cache. |

Pressure 2 pulls toward elongation; pressure 1 pulls toward cubic;
pressure 3 sets a side-constraint. The optimum is typically **slightly
elongated in the innermost dim, roughly square in the other two** —
which is what the weak-test brick (71 × 111 × 500) approximates.

### Quantitative thresholds

If you want to compute the optimum for your hardware and stencil
order, here are the rough numbers for SW4 with the default 8th-order
stencil on Zen3/Zen4:

**SIMD startup cost** — the inner loop needs to run for at least
several iterations of the SIMD width before pipeline + prefetcher are
at steady state. Approximate microbenchmark thresholds:

| SIMD width        | Min useful inner length | Diminishing-returns length |
|---                |---                      |---                         |
| SSE2 (2 doubles)  | ~8 cells                | ~64 cells                  |
| AVX2 (4 doubles)  | ~16 cells               | ~128 cells                 |
| AVX-512 (8 doubles) | ~32 cells             | ~256 cells                 |

Below "min useful" the SIMD machinery never reaches full throughput;
above "diminishing returns" you're saturated and longer doesn't help
(in fact past a couple of L2-fits' worth, longer can hurt — see Cache
fit below). SW4's per-rank bricks should aim to keep the innermost
dim above the diminishing-returns length for the SIMD width in play.

**Cache fit** — the stencil's working set per inner-loop pass is
approximately:

```
working_set_bytes ≈ stencil_extent × mid_dim × inner_dim × 8 bytes × n_arrays
```

For SW4's default 8th-order stencil, `stencil_extent ≈ 9`. Several
arrays (velocity components, stress components) are touched
simultaneously, so `n_arrays ≈ 5–10` depending on which kernel.

Cache sizes per core on Zen3/Zen4:

| Level                | Capacity         | Doubles            |
|---                   |---               |---                 |
| L1d                  | 32 KB            | ~4 K               |
| L2                   | 512 KB – 1 MB    | ~64 K – 128 K      |
| L3 (per-core slice)  | ~2–4 MB          | ~250 K – 500 K     |

Working set should ideally fit in L2; L3 is acceptable; once it spills
to DRAM you're bandwidth-limited and SIMD width stops mattering.

**Halo cost** — for a brick `a × b × c` with stencil halo width `w`
(= 4 cells on each face for an 8th-order stencil), halo cell count
per step is:

```
halo_cells ≈ 2w(ab + bc + ac)
```

The halo-to-volume ratio is:

```
halo_fraction ≈ 2w(1/a + 1/b + 1/c)
```

Minimised when a = b = c (AM-GM inequality). For fixed per-rank volume
V, the cubic case gives `halo_fraction = 6w / V^(1/3)`. Anything
elongated pays a halo tax — small at modest aspect ratios, growing as
you elongate further.

### A back-of-envelope optimum

For per-rank volume V, SIMD diminishing-returns inner length L*, and
stencil halo width w, a defensible starting point:

1. Set inner dim `c = max(L*, V^(1/3))`. If V^(1/3) already exceeds
   L*, use cubic; otherwise elongate to L* on the innermost dim.
2. Make the remaining two dims square: `a = b = √(V/c)`. This
   minimises halo on the four lateral faces given fixed c.

For our test point V ≈ 4 M cells/rank on AVX-512 (L* ≈ 256):

- V^(1/3) ≈ 159, less than L* = 256, so elongate.
- c = 256, a = b = √(4 × 10⁶ / 256) ≈ 125.
- **Predicted optimum brick: ~125 × 125 × 256.**

What we actually measured:

| Per-rank brick   | Innermost dim | Throughput (G cell updates / core-hour) |
|---               |---            |---                                      |
| 71 × 111 × 500   | 500           | **3.58** (cascade weak)                 |
| 128 × 140 × 220  | 220           | 2.55  (cascade strong)                  |

The good one is *more elongated* than the predicted optimum — past
the diminishing-returns length, paying some halo tax it didn't have
to. A 125 × 125 × 256 shape might do slightly better still. The bad
one has innermost dim 220, just below the 256 sweet spot for AVX-512,
which is consistent with its inability to escape the cluster.

(All thresholds in this section are order-of-magnitude. They come
from the cascade-vs-NeSI gap and microbenchmark intuition, not from a
direct sweep on SW4. Treat the closed-form as a starting point and
verify empirically.)

## Knobs you actually have

In practice you don't directly pick the per-rank brick. You pick:

1. **Global grid (nx, ny, nz)** — usually constrained by physics
   (fault region, depth of interest, grid spacing) but typically has
   some slack at the edges. Pad to align with rank-count factors.
2. **Number of ranks** — constrained by allocation budget and node
   count, but the *factorisation* of that count is yours. Prefer
   near-square 2D factors.
3. **Ranks per node** — tradeoff: more ranks/node means smaller
   per-rank brick (more aspect-ratio freedom) but more
   memory-bandwidth contention per rank. The cross-HPC tests use
   126/node for comparability; production runs typically pack all
   cores per node, which is a different operating point.
4. **Stencil order** (if SW4 lets you choose at runtime) — higher
   order means wider halo and more shape sensitivity. The default
   8th-order is what most production runs use.

You **don't** typically pick the MPI decomposition algorithm directly
— SW4 chooses 2D-with-smallest-dim-whole automatically. If you need
a 3D decomposition or a different "kept whole" axis, that's a
code-level change.

## Empirical magnitudes by SIMD width

The shape effect is wholly mediated by SIMD width:

| SIMD width        | Strong vs. weak per-core throughput swing |
|---                |---                                        |
| SSE2  (NeSI genoa, same hardware class as cascade) | ~6 % (within noise; sign can flip) |
| AVX2  (predicted; not directly measured)           | ~15–25 % |
| AVX-512 (cascade, measured)                        | ~40 %    |

Same per-rank cell count, same hardware (Zen4), same SW4 version —
the only thing that changes is whether the binary can use wide SIMD.
The shape lever scales almost linearly with SIMD width because the
mechanism is "wide SIMD needs long inner loops to amortise."

Practical implication: **on SSE2, don't bother shape-tuning** — you
won't see it. **On AVX2, it's worth a check.** **On AVX-512, do the
30-minute sweep below before any big campaign.**

## How to verify before a big campaign

Don't trust this doc — the thresholds are approximations. Before a
million-core-hour run:

1. Pick 3–5 candidate shapes around the closed-form optimum. For
   4 M cells/rank on AVX-512: cubic ~159³, elongated 125 × 125 × 256,
   more elongated 100 × 100 × 400, very elongated 71 × 111 × 500,
   and your physics-driven default.
2. Run each at single-node scale (126 or 144 ranks) for a short fixed
   number of timesteps — a few minutes' wall time per shape.
3. Compute throughput in G cell updates / core-hour. Pick the winner.
4. Use the winner's shape (and its rank-count factorisation) as the
   template for production.

A 30-minute single-node sweep can save several percent on a multi-day
production run — easily worth it once you're past ~50 K core-hours.

## A worked example

Suppose you're planning a 2 M-core-hour SW4 campaign on cascade with
a physical domain of roughly 50 × 50 × 25 km and 100 m grid spacing,
giving ~500 × 500 × 250 cells globally. You're targeting 144 ranks
per allocation (12 × 12 = 144 — better than 126's 9 × 14).

- Per-rank cell count: 500 × 500 × 250 ÷ 144 ≈ 434 K. Smaller than
  our 4 M test point, so cache pressure is less; SIMD-amortisation
  threshold is the dominant constraint.
- V^(1/3) ≈ 76, well below the AVX-512 L* of 256. Definitely elongate.
- Closed form: c = 256, a = b ≈ √(434K / 256) ≈ 41.
- SW4 will keep the smallest global dim (250) whole. After the 12 × 12
  split: 500 ÷ 12 ≈ 42, 500 ÷ 12 ≈ 42. Per-rank brick = 42 × 42 × 250.
- Innermost dim 250 ≈ matches L* = 256. Other two dims at 42 ≈ matches
  the closed-form's 41. **Already near-optimal as specified.**
- Pad 500 → 504 (= 12 × 42 exactly) to remove the rounding tax.

If instead you'd picked 126 ranks (9 × 14): per-rank brick =
35 × 55 × 250. The 14-way split is bad — 35 cells is a thin lateral
face, growing the halo fraction. The rank-count choice is doing more
work for you here than the global-grid choice would.

## References

- `cross-hpc-throughput.md` — full cross-HPC dataset, the SIMD-width
  finding, and the diagnostic chain showing where the strong-vs-weak
  gap comes from (§ "The SIMD-width finding").
- `cross-hpc-findings-explained.md` — non-technical version of the
  same story.
- `building-sw4-on-nesi-and-rch.md` — rebuild instructions to enable
  wide-SIMD on both HPCs; prerequisite for the shape lever to matter
  there.
- SW4 source: the inner stencil loops live in the
  `rhs4*.f` Fortran kernels — look there if you need to verify which
  dim is the innermost contiguous loop on your build.
