# NeSI SW4 build is missing `-march`: recommend rebuild

The `/nesi/project/nesi00213/tools/sw4` binary is compiled with GCC's
default architecture target — i.e., generic `x86-64`, **SSE2-only**.
On the Zen4 (genoa) and Zen3 (milan) partitions this leaves per-core
throughput on the table. A one-flag rebuild should recover ~1.5×
on weak-scaling workloads on genoa, with smaller gains elsewhere
(see "Expected gains" below).

## Evidence

`/nesi/project/nesi00213/opt/sw4/build/CMakeCache.txt` (from the
Apr 15 2026 build by `baes`):

```
CMAKE_BUILD_TYPE      = Release            (= -O3 -DNDEBUG)
CMAKE_CXX_FLAGS       = (empty)
CMAKE_C_FLAGS         = (empty)
CMAKE_Fortran_FLAGS   = (empty)
CMAKE_CXX_COMPILER    = GCC 12.3.0
```

No `-march` set anywhere. GCC's default is `-march=x86-64`, which
gates everything wider than SSE2 (no AVX, no AVX2, no AVX-512).

Disassembly confirms — *zero* AVX-class instructions in the binary:

```
$ objdump -d /nesi/project/nesi00213/tools/sw4 | grep -c '%zmm'
0
$ objdump -d /nesi/project/nesi00213/tools/sw4 | grep -c '%ymm'
0
```

(SSE2 `%xmm` registers are still used; we just never go wider.)

## Why this matters

On ESNZ's cascade partition (Zen4, DDR5-4800, identical to
NeSI's genoa class), Spack-built SW4 with `target=zen4` (so
`-march=znver4` → AVX-512) shows the following per-core throughput
vs. the NeSI binary, single-node 126 ranks, same SW4 v3.0 source,
same hardware class:

| Test | NeSI genoa | ESNZ cascade | Notes |
|---|---|---|---|
| Strong scaling (126 cores) | 2.60 | 2.55 | similar |
| Weak scaling   (126 cores) | 2.45 | **3.58** | cascade ~46 % faster |
| NaN-check overhead         | ~9 % | ~2 % | cascade ~4× cheaper |

Units: G cell updates / core-hour.

Strong scaling looks similar at 1 node only because that grid's
inner-loop length is short enough to be memory-bandwidth-bound on
both binaries. The weak-scaling grid has a longer contiguous
innermost dimension, which the AVX-512 codegen can chew through
several times faster — hence cascade's ~46 % lead despite identical
hardware. The NaN scan is a trivial streaming pass and is near-free
in AVX-512 but not in SSE2, which lines up with the overhead numbers.

The simplest single-binary explanation that fits all three rows:
NeSI's SW4 has no SIMD wider than SSE2 enabled.

## Suggested rebuild

The build is already CMake-driven, so it's a one-flag change at
configure time. Pick whichever target fits the partition policy:

**Single binary, runs on milan + genoa** — `-march=znver3` (Zen3
baseline, AVX2). Likely modest gains on both partitions; see
"Expected gains" below:

```bash
cd /nesi/project/nesi00213/opt/sw4
rm -rf build && cmake -S . -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_FLAGS="-march=znver3" \
  -DCMAKE_C_FLAGS="-march=znver3" \
  -DCMAKE_Fortran_FLAGS="-march=znver3"
cmake --build build -j
```

**Genoa-only binary** — `-march=znver4` (AVX-512). Should match
cascade's weak-scaling throughput, ~1.46× faster than the current
genoa binary on weak workloads. Won't run on milan.

**Most portable** — `-march=x86-64-v3` (Haswell-class baseline,
AVX2). Runs on any modern x86-64 partition and is what most distros
now use for "modern x86_64". Slightly less Zen-specific tuning than
`-march=znver3` but close.

`-march=native` works too but bakes in the *login node's* arch,
which may not match every compute node — explicit Zen targets are
safer.

## Expected gains

The 4× SIMD-width ratio (zmm 8 doubles vs. xmm 2 doubles) is a
**theoretical ceiling**, not a forecast. SW4's stencil kernels are
memory-bandwidth-bound a lot of the time, so doubling SIMD width
past the bandwidth bottleneck doesn't translate to wall-clock.
The empirical end-to-end gap between the existing SSE2 binary and a
known AVX-512 binary on identical Zen4 hardware is:

| Test | NeSI genoa (SSE2) | ESNZ cascade (AVX-512) | Speedup |
|---|---|---|---|
| Weak (single node, 126 cores)   | 2.45 | 3.58 | **1.46×** |
| Strong (single node, 126 cores) | 2.60 | 2.55 | ~1.0× (noise) |
| NaN-check overhead              | ~9 % | ~2 % | ~4× cheaper |

So on the rebuild:

- **`-march=znver4`** (genoa-only): expect roughly the cascade
  numbers above — ~1.5× on weak, near-flat on strong.
- **`-march=znver3` or `-march=x86-64-v3`** (AVX2, runs on milan
  too): half the SIMD width of AVX-512, no direct measurement, but
  expect somewhere in the ~1.2–1.4× range on weak workloads on
  both partitions. Genuine uncertainty.
- **NaN-check overhead** drops on any of the above — the scan is
  trivially streaming and benefits from any SIMD width above SSE2.

Strong-scaling workloads on the existing 128 × 1984 × 1984 grid see
little benefit because that grid's per-rank inner-loop length is
short enough that even AVX-512 saturates DRAM before its full SIMD
width pays off; both binaries bottleneck at the same place.

## Smaller secondary levers

If the `-march` rebuild lands and there's appetite to push further,
these are additional options ordered by effort vs. likely gain.
Numbers are rules of thumb for stencil codes, not measurements on
SW4 specifically.

- **`-mprefer-vector-width=512`** (only with `-march=znver4`).
  GCC defaults to 256-bit even on Zen4 because of historical
  frequency-throttling concerns inherited from Intel server parts;
  Zen4 doesn't have that issue. Explicit opt-in to 512-bit can add
  ~5–15 %. Cheap to try, trivial to back out.

- **Targeted numerics-relaxation flags**:
  `-fno-math-errno -fno-trapping-math` are essentially free
  (~1–3 %, no observable behaviour change for SW4). `-fno-signed-zeros`
  is similar but marginally riskier. **Avoid `-ffast-math`** —
  it implies `-ffinite-math-only`, which tells the compiler it can
  assume no NaN/Inf inputs. That breaks SW4's `checkfornan` feature
  by definition, and the compiler may also fold away the scan
  itself. Modest gain not worth that hazard.

- **`-flto`** (link-time optimisation): cross-translation-unit
  inlining and constant propagation. Typical ~3–7 % on this kind of
  code, no runtime correctness risk. Increases link time
  noticeably; sometimes interacts awkwardly with debuggers.

- **Profile-guided optimisation (PGO)**: two-stage build (compile
  with `-fprofile-generate`, run a representative workload, recompile
  with `-fprofile-use`). Often ~5–15 % on stencil/loop-heavy code.
  Significantly more work — needs a representative training input
  and a build harness that does the two-stage flow.

- **Newer GCC** (13.x / 14.x): meaningful Zen4 autovec improvements
  over 12.3, especially around `gather`/`scatter` and AVX-512 mask
  generation. Modest gain (~5 %), requires updating the toolchain
  module — coordinate with NeSI module maintainers.

## Out of scope: runtime tuning

These don't belong in a build-flags doc, but the maintainer is the
right person to know about them so the full performance picture is
clear:

- **Ranks per node**: the scaling tests pin 126 ranks/node for
  cross-HPC comparability (NeSI genoa has 336 cores/node, milan has
  128). Production users on genoa probably want to use all 336
  cores per node. SW4's per-rank cost depends on grid shape, so the
  "right" rank count is workload-specific — but 126/node is a
  comparability artefact, not an optimum.
- **NUMA / core binding**: under OpenMPI on these partitions, an
  explicit `--map-by numa --bind-to core` (or equivalent
  `srun --cpu-bind=cores`) can be worth a few percent vs. defaults,
  especially when ranks/node doesn't divide evenly across sockets.

## References

Full analysis lives in this repo:

- `docs/cross-hpc-throughput.md` — cross-HPC throughput data and
  the bandwidth/build-flags discussion.
- `docs/cascade-strong-vs-weak-puzzle.md` — how this rebuild
  recommendation was arrived at, with the full diagnostic chain.
