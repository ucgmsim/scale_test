# RCH SW4 build is missing `-march`: recommend rebuild

The `/scratch/projects/rch-quakecore/sw4/optimize_mp/sw4` binary on
RCH (UoC's hcpu partition, Zen3-class) has the same problem as NeSI's
SW4: no `-march` flag at build time, so GCC defaulted to generic
`x86-64` (SSE2-only). This is the second independent NZ HPC site
where the static analysis lands the same way; the fix is the same
shape but the right target is `znver3`, **not** `znver4`, because the
hardware does not support AVX-512.

## Evidence

Disassembly of the in-use binary shows zero AVX-class instructions:

```
$ objdump -d /scratch/projects/rch-quakecore/sw4/optimize_mp/sw4 | grep -c '%zmm'
0
$ objdump -d /scratch/projects/rch-quakecore/sw4/optimize_mp/sw4 | grep -c '%ymm'
0
```

Same SSE2-only signature as NeSI's binary. (SSE2 `%xmm` registers are
still used; the binary just never widens past 128-bit SIMD.)

We don't have a `CMakeCache.txt` or build-script trail for this
binary on hand, but the disassembly is sufficient: the compiled
program contains no AVX/AVX2/AVX-512 instructions, so whatever the
build was, it didn't enable any SIMD wider than SSE2.

## Why this matters

RCH hcpu nodes are Zen3 with DDR4 memory. Their hardware ceiling is
**AVX2** (256-bit, 4 doubles per SIMD op) — twice the width of the
current binary's SSE2 (128-bit, 2 doubles). AVX-512 is a Zen4
feature; Zen3 does not have it, so a `-march=znver4` build would
crash with `SIGILL` (illegal instruction) on the first AVX-512 op.

We don't have a direct empirical measurement of an AVX2-built SW4 on
identical Zen3 hardware to quote a clean speedup, but the same
build-flag pattern accounts for the SSE2 vs. AVX-512 gap measured
between NeSI genoa and ESNZ cascade (1.46× on weak workloads). The
RCH version of that gap should be smaller — half the SIMD-width step
(2× rather than 4×) — but in the same direction.

## Suggested rebuild

The change is one flag at configure time. Two reasonable targets:

**Zen3-tuned** — `-march=znver3` (AVX2 + Zen3-specific tuning):

```bash
# pseudocode, adapt to whatever build harness this binary uses
cmake -S . -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_FLAGS="-march=znver3" \
  -DCMAKE_C_FLAGS="-march=znver3" \
  -DCMAKE_Fortran_FLAGS="-march=znver3"
cmake --build build -j
```

**Most portable** — `-march=x86-64-v3` (Haswell-class baseline,
AVX2). Runs on any modern x86-64 CPU and is what most distros now use
as the "modern x86_64" baseline. Slightly less Zen3-specific tuning
than `znver3` but close.

**Do NOT use `-march=znver4` or `-march=native` from a Zen4 login
node** — the resulting binary will use AVX-512 instructions that
Zen3 hardware does not implement, and will crash on the first such
instruction on RCH compute nodes.

## Expected gains

Since AVX2 is half the width of AVX-512, the empirical 1.46× gap
between NeSI genoa (SSE2) and ESNZ cascade (AVX-512) on weak
workloads is an *upper bound* for what a `znver3` rebuild can recover
on RCH. SW4 is partially memory-bandwidth-bound on the DDR4
partitions, which compresses the visible gain further. Realistic
expectation:

- **Weak workloads**: ~1.2–1.4× speedup. Genuine uncertainty — the
  AVX2 codegen on Zen3 has not been measured directly for SW4 on this
  hardware. Will be smaller than the 1.46× we measured for AVX-512 on
  Zen4.
- **Strong workloads** (the existing 128 × 1984 × 1984 grid): little
  change expected. That grid's per-rank inner-loop length is short
  enough that even AVX-512 on cascade saturates DRAM bandwidth before
  its SIMD width pays off; the same applies, more sharply, to AVX2 on
  DDR4. Both pre- and post-rebuild binaries will bottleneck on memory
  at this grid shape.
- **NaN-check overhead** (currently untested on RCH but predicted to
  be ~10 % from the build-flag pattern alone): should drop noticeably
  with AVX2. The NaN scan is a streaming pass and benefits from any
  SIMD width above SSE2.

## Smaller secondary levers

The same options that apply to NeSI's rebuild apply here, with one
adjustment: `-mprefer-vector-width=512` is irrelevant on Zen3 (no
AVX-512). Otherwise: `-flto`, targeted numerics-relaxation flags
(`-fno-math-errno -fno-trapping-math`, but **avoid `-ffast-math`** —
it implies `-ffinite-math-only` which breaks SW4's `checkfornan`),
PGO, and a newer GCC toolchain are all on the table. See
`nesi-sw4-rebuild-recommendation.md` § "Smaller secondary levers" for
the rationale and rough magnitudes — they all carry over to RCH.

## References

- `docs/cross-hpc-throughput.md` — cross-HPC throughput data.
- `docs/cascade-strong-vs-weak-puzzle.md` — full diagnostic chain
  showing how the SSE2-only build was identified.
- `docs/nesi-sw4-rebuild-recommendation.md` — sister doc for NeSI's
  binary; structurally identical, recommends `znver4` instead of
  `znver3` because NeSI genoa is Zen4 hardware.
