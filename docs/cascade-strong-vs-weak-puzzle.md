# Why is cascade's weak throughput so much higher than its strong throughput?

Companion note to `cross-hpc-throughput.md`. Captured because the gap
is peculiar to cascade.

**Resolved (2026-04-30)**: the cause is the SIMD width of the SW4
binary, not the cascade hardware. Cascade's Spack-built SW4 has
AVX-512 (`-march=znver4`); NeSI's SW4 has *no* SIMD wider than SSE2
(no `-march` flag — GCC defaults to generic `x86-64`). The wide-SIMD
binary is the only one in the dataset that can feel the
inner-loop-length difference between the strong and weak grids.
See "Resolution" below.

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

**Reproducibility**: the gap appears in *both* cascade campaigns (no
NaN check and NaN check on), which are independent scheduler runs on
different days. Strong-126 = 2.56 vs. weak-126 = 3.58 in the no-NaN
campaign; 2.49 vs. 3.61 with NaN-on. So this is not a one-off
allocation artefact — it survives the natural day-to-day variance the
NeSI numbers also show.

Subdomain shapes at 126 cores under SW4's typical 2D decomposition
(innermost contiguous dim kept whole, other two split):

- Strong (`128 × 1984 × 1984`) → per-rank ≈ `128 × 140 × 220` —
  slab-like, 128-element first dimension.
- Weak (`1000 × 1000 × 500`) → per-rank ≈ `70 × 110 × 500` — closer
  to cubic, longer contiguous dim.

## Resolution

**NeSI genoa SW4** — `/nesi/project/nesi00213/tools/sw4`, CMake-built
with GCC 12.3.0. `CMakeCache.txt` shows
`CMAKE_BUILD_TYPE=Release` (so `-O3 -DNDEBUG`), but
`CMAKE_CXX_FLAGS`, `CMAKE_C_FLAGS`, and `CMAKE_Fortran_FLAGS` are
all **empty**. No `-march` anywhere; GCC defaults to `-march=x86-64`,
which gates AVX/AVX2/AVX-512. Disassembly confirms:

```
$ objdump -d /nesi/project/nesi00213/tools/sw4 | grep -c '%zmm'
0
$ objdump -d /nesi/project/nesi00213/tools/sw4 | grep -c '%ymm'
0
```

Zero `%zmm` and zero `%ymm` register references — the binary
contains *no* AVX-class instructions at all, just SSE2 (`%xmm`).
Same generic SSE2 binary runs on both milan (Zen3) and genoa (Zen4).

**Cascade SW4** — Spack-built with `target=zen4`, so Spack injects
`-march=znver4` automatically → AVX-512.

**RCH SW4** — `/scratch/projects/rch-quakecore/sw4/optimize_mp/sw4`,
checked the same way as NeSI's binary:

```
$ objdump -d /scratch/projects/rch-quakecore/sw4/optimize_mp/sw4 | grep -c '%zmm'
0
$ objdump -d /scratch/projects/rch-quakecore/sw4/optimize_mp/sw4 | grep -c '%ymm'
0
```

Same SSE2-only signature. RCH is an independently administered HPC
(UoC, Zen3 hardware), so this is a third independent reproduction of
the missing-`-march` build pattern — strengthening the conclusion
that the SIMD-width gap is a build-flag effect rather than anything
NeSI-specific. RCH's hardware caps out at AVX2 (no AVX-512 on Zen3),
so the right rebuild target there is `-march=znver3`; see
`rch-sw4-rebuild-recommendation.md`.

The binaries differ by 4× in theoretical SIMD width (zmm: 8 doubles
vs. xmm: 2 doubles). That single fact resolves all three
cascade-vs-genoa anomalies:

1. **Cascade weak throughput ~46 % higher than genoa weak**: the
   weak grid's longer contiguous innermost dim (z = 500 vs. strong's
   z = 220) gives AVX-512 enough iterations per kernel call to pull
   ahead. SSE2 is too narrow to feel the difference between the two
   shapes — both saturate memory bandwidth equally.
2. **Cascade NaN-check overhead ~2 % vs. genoa's ~9 %**: the NaN
   scan is a trivial streaming pass; near-free in AVX-512, not in
   SSE2.
3. **Cascade strong-vs-weak gap (the original puzzle)**: only the
   AVX-512 binary is wide enough to feel the inner-loop-length
   difference between the two grid shapes.

H1 below is therefore **confirmed** as the explanation, modulo a
runtime experiment (rebuild NeSI's SW4 with `-march=znver4` and
re-measure — see `nesi-sw4-rebuild-recommendation.md`).

## What we've checked

**Cascade's SW4 build** (from `spack find -v` /  `spack spec -I` against
the binary's Spack hash `stl6gkqcnilzulk4jjaaimgndua6lceh`):

```
sw4@3.0~debug+fftw+hdf5+openmp+proj~zfp build_system=makefile
  %cxx,fortran=gcc@11.4.1
  ^intel-oneapi-mpi@2021.16.1
  target=zen4
```

Key surprise: SW4 itself is built with **GCC 11.4.1**, not Intel ICX.
The `mpiicpx` path shown in the SW4 banner is just the MPI
compiler-wrapper script Spack used to drive g++; the underlying
compiler is GCC. The Intel oneAPI dependency only contributes the
MPI library.

NeSI's genoa SW4 reports `Compiler: /opt/.../GCCcore/12.3.0/bin/c++`
in its banner — also GCC, just a slightly newer minor version. So
**both builds are GCC**; the Intel-vs-GCC vectoriser story is dead.

What's still meaningfully different between the two builds:

- **Architecture target**: cascade's spec records `target=zen4`, so
  Spack passes `-march=znver4` (AVX-512 + Zen4 tuning) automatically.
  NeSI's build flags are not yet known — they may be a generic
  baseline (NeSI binaries typically have to run across milan and
  genoa partitions).
- **OpenMP**: cascade is `+openmp` (`-fopenmp` at compile time, even
  though `OMP_NUM_THREADS=1` at runtime — pragma'd loops can vectorise
  differently with `-fopenmp` enabled).
- **Variants**: cascade has `+fftw +hdf5 +proj` enabled; genoa's
  banner reports `3rd party include dir: NA` (no PROJ), so its
  variant set is narrower.

## Hypotheses

Ordered by what survives the build-spec evidence above. None verified.

### H1 — Subdomain shape × Zen4-tuned binary (most likely)

If cascade's binary uses `-march=znver4` (AVX-512 + Zen4-specific
tuning) and NeSI's genoa SW4 was compiled for a generic baseline,
cascade is the only build in the dataset actually exploiting AVX-512
in inner loops.

If so:

- Longer, more uniform inner loops let AVX-512 + FMA pull more work
  per memory transaction. The weak grid's per-rank ≈ `70 × 110 × 500`
  gives a longer contiguous innermost-dim run than the strong grid's
  ≈ `128 × 140 × 220`.
- Genoa's binary, running narrower SIMD, is bottlenecked by something
  else (likely DRAM bandwidth) regardless of grid shape — so its
  strong and weak per-core throughputs are similar.

This is the same axis that already separates cascade from genoa on
two other measurements (cf. `cross-hpc-throughput.md` § Bandwidth
hypothesis): cascade's ~45 % weak-scaling lead and ~7× lower
NaN-check overhead would both drop out of "cascade has a Zen4-tuned
AVX-512 build, NeSI doesn't".

### H2 — Cache fit / memory access pattern

The strong subdomain's innermost-contiguous working set may not fit
the same way the weak one does on Zen4's 1 MB-per-core L2. DDR5
hardware prefetch interaction with the access pattern could differ
between shapes.

This collapses into H1 if the prefetch-friendly behaviour is only
realised by the AVX-512 codegen path — i.e., genoa's narrower-SIMD
binary never lights up the same prefetch streams regardless of shape.

### H3 — MPI decomposition imbalance (unlikely to be dominant)

128 does not divide as cleanly as 1000 across 126 ranks, so SW4 may
choose a more lopsided 2D decomp for the strong grid. But this would
hurt every HPC, not just cascade — and the data shows the other
three HPCs barely register a strong-vs-weak gap. So this is at most
a minor contributor.

## What would settle it

1. ~~Inspect cascade's SW4 build flags.~~ **Done** — Spack
   `target=zen4` → AVX-512.

2. ~~Inspect NeSI's SW4 build flags.~~ **Done** — empty `CMAKE_*_FLAGS`,
   no `-march`, SSE2-only binary.

3. **Confirm by rebuild** (the only step left): rebuild NeSI's SW4 with
   `-march=znver4` and re-run a single-node weak-126 + strong-126 pair
   on the genoa partition. If the strong/weak gap on genoa starts
   tracking cascade's pattern, H1 is fully confirmed end-to-end. The
   rebuild instructions are in `nesi-sw4-rebuild-recommendation.md`.

4. (Optional, if curiosity persists) **Single-node, same cell count,
   different shape** on cascade — slab vs. cubic ~500 M cells at 126
   ranks. Should reproduce the strong/weak gap on the same binary,
   isolating shape sensitivity from anything else.

## Pointers

- Plot data and units: `cross-hpc-throughput.png`,
  `cross-hpc-throughput.md` (Headline numbers, Strong-scaling
  efficiency, Weak-scaling stability sections).
- Throughput formula: `scripts/compare_scaling.py:59–79`.
- Grid sizes: `WEAK_GRIDS` and `STRONG_GRID` constants in
  `compare_scaling.py:39–42`, mirrored in
  `cylc/cylc-src/flow/{weak,strong}_scaling.csv` and
  `cylc/cylc-src/flow/events/input_strong.in`.
