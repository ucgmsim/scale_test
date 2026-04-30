# SW4 cross-HPC throughput

Per-core SW4 throughput across the HPCs we've measured so far, all run
with the same Cylc workflow at 126 tasks/node, ~4 M cells/core (weak)
and a fixed 128 × 1984 × 1984 grid (strong).

![Strong and weak scaling, four HPCs (no NaN check)](cross-hpc-throughput.png)

The plot above shows the four no-NaN campaigns. The headline numbers
table below also includes the NaN-on campaigns, which are discussed in
the "NaN-check overhead" section.

## Headline numbers

Mean per-core throughput in **G cell updates / core-hour**, across the
four weak / four strong runs in each campaign. "Range" is min–max
across those four data points.

| HPC × config | Strong (mean / range) | Weak (mean / range) |
|---|---|---|
| cascade, no NaN check  | 2.32 / 2.02–2.55 | **3.54** / 3.51–3.58 |
| cascade, NaN check on  | 2.26 / 1.98–2.49 | 3.47 / 3.39–3.61     |
| genoa, no NaN check    | **2.48** / 2.29–2.61 | 2.45 / 2.38–2.58 |
| genoa, NaN check on    | 2.23 / 2.18–2.30 | 2.23 / 2.19–2.28     |
| milan, no NaN check    | 1.46 / 1.17–1.77 | 1.54 / 1.37–1.63     |
| milan, NaN check on    | 1.07 / 0.68–1.58 | 1.34 / 1.08–1.62     |
| rch (hcpu), no NaN     | 1.21 / 1.10–1.36 | 1.20 / 1.11–1.28     |

Cascade and genoa share the top of the table but in different ways.
Genoa wins on strong scaling (2.48 vs. 2.32) and is exceptionally
tight (13 % spread). Cascade wins decisively on weak scaling
(~3.54 vs. ~2.45, ~45 % faster per core) and is the flattest weak
curve we've measured — just 3.58 → 3.51 across 4× the node count.
Both clearly outclass milan and RCH (~2–3× per-core throughput).

RCH runs at roughly half genoa's throughput; its weak campaign is
fairly flat (~14 % spread) but the strong sweep is wider (~21 %), with
a mid-sweep dip at 252 cores that recurs in the weak data too.
Milan is in the same ballpark as RCH on average but with much wider
spread — the strong-scaling curve zigzags 1.72 → 1.17 → 1.77 → 1.18
between adjacent core counts, which can't be a real algorithmic
effect; it almost certainly reflects partition heterogeneity (see
"Milan internal variability" below).

## Strong scaling efficiency

Throughput-per-core preservation when going from 126 cores (1 node) to
504 cores (4 nodes) on the same fixed grid. Ideal is 100 %; lower
means scaling tax (communication and surface-area overhead).

| HPC × config | 126-core throughput | 504-core throughput | Efficiency |
|---|---|---|---|
| genoa,   no NaN | 2.60 | 2.29 | **88 %** |
| rch,     no NaN | 1.36 | 1.10 | **81 %** |
| cascade, no NaN | 2.56 | 2.02 | **79 %** |
| milan,   no NaN | 1.72 | 1.18 | 68 % (dominated by hardware noise) |

Genoa scales best to 4 nodes. Cascade's 79 % is interesting: per-core
throughput at 126 cores is essentially the same as genoa (2.56 vs. 2.60),
but cascade gives up more between 1 and 4 nodes — the strong sweep
goes 2.56 → 2.55 → 2.16 → 2.02, dropping noticeably from 252 cores
onwards. RCH's 81 % is solid, with the four points spanning 1.10–1.36
and a mid-sweep dip at 252 cores rather than a monotonic decline. The
milan number is consistent with what its weak-scaling curve also
shows: the partition is too heterogeneous for a single efficiency
number to be meaningful at this sample size.

## Weak scaling stability

For a memory-bandwidth-bound stencil code, ideal weak scaling means
the per-core throughput is **flat** as we add nodes (because each rank
gets the same work and the same bandwidth share). 504-core / 126-core
ratio:

| HPC × config | 126 weak | 504 weak | Stability |
|---|---|---|---|
| cascade, no NaN | 3.58 | 3.51 | **98 %** — flattest |
| cascade, NaN on | 3.61 | 3.39 | 94 % |
| genoa, no NaN | 2.44 | 2.38 | 97 % |
| genoa, NaN on | 2.19 | 2.21 | 101 % (essentially flat) |
| rch   | 1.28 | 1.11 | 87 % |
| milan, no NaN | 1.63 | 1.37 | 84 % |
| milan, NaN on | 1.39 | 1.26 | 91 % |

Cascade is the flat-out winner: 3.58 → 3.51 across the no-NaN sweep is
the steadiest curve in the dataset, and it's also the highest absolute
per-core throughput we've measured anywhere. Genoa is right behind in
stability terms. RCH is reasonable — flatter than milan, but the
504-core point pulls the stability number well below the leaders.
Milan degrades, but with the caveat that the underlying nodes weren't
the same set across the four runs.

## Milan internal variability

Both milan campaigns (with and without NaN checks) show the same
zigzagging pattern: alternating data points are fast / slow despite
identical SW4 configuration. The most extreme case is the
NaN-check-on strong-scaling 378-core run at 0.68 G cell updates / core-hour
— 2.6× slower than the 378-core run *without* NaN checks
(1.77 G cell updates / core-hour).
That can't be the NaN check itself: the same NaN-check setting at
126 cores cost only ~9 %.

The remaining explanation is that successive sbatch allocations on
NeSI's milan partition land on different physical nodes, and **those
nodes are not equivalent**. Possible drivers: silicon mix (Zen3
parts of varying quality), different DIMM populations, BIOS
revisions. Whatever the cause, the per-job variance dwarfs the
algorithmic differences we're trying to measure.

Genoa and RCH (with the `--constraint=hcpu` filter applied) don't
show this — their numbers are consistent across consecutive jobs.

## NaN-check overhead

`developer checkfornan=on` has been measured on three HPCs. The
result that drops out is **not** a clean function of memory
bandwidth — see below.

**Milan** (Zen3, DDR4-3200, ~half genoa's bandwidth):

| Test | Without NaN | With NaN | Overhead |
|---|---|---|---|
| strong-126 | 1.72 | 1.58 |  9 % |
| strong-504 | 1.18 | 1.06 | 10 % |
| weak-126   | 1.63 | 1.39 | 14 % |
| weak-504   | 1.37 | 1.26 |  8 % |

→ **~10–15 % per-step overhead**. The wider points (strong-378
going from 1.77 → 0.68, etc.) are dominated by which nodes Slurm
picked, not by the NaN-check cost.

**Genoa** (NeSI, Zen4, DDR5-4800, 12 channels/socket):

| Test | Without NaN | With NaN | Overhead |
|---|---|---|---|
| strong-126 | 2.60 | 2.21 | 15 % |
| strong-252 | 2.61 | 2.30 | 12 % |
| strong-378 | 2.41 | 2.23 |  7 % |
| strong-504 | 2.29 | 2.19 |  5 % |
| weak-126   | 2.44 | 2.19 | 11 % |
| weak-252   | 2.57 | 2.28 | 11 % |
| weak-378   | 2.38 | 2.26 |  5 % |
| weak-504   | 2.38 | 2.21 |  7 % |

→ **~5–15 % per-step overhead**, mean ~9 %. Larger overhead at
small core counts and tapering off as nodes are added — possibly
real, possibly noise from a 4-point sweep.

**Cascade** (ESNZ, Zen4 Genoa, DDR5-4800, 12 channels/socket):

| Test | Without NaN | With NaN | Overhead |
|---|---|---|---|
| strong-126 | 2.56 | 2.49 | 2 % |
| strong-504 | 2.02 | 1.98 | 2 % |
| weak-126   | 3.58 | 3.61 | −1 % (within noise) |
| weak-504   | 3.51 | 3.39 |  3 % |

→ **~0–3 % per-step overhead** — essentially in noise.

### What this means

The cascade vs. NeSI gap on NaN overhead is **resolved**: it's a
SIMD-width effect, not a memory-bandwidth or MPI-runtime effect.

- **Cascade SW4** is Spack-built with `target=zen4` → `-march=znver4`
  → AVX-512.
- **NeSI's SW4** (`/nesi/project/nesi00213/tools/sw4`) is CMake-built
  with empty `CMAKE_*_FLAGS` — no `-march`, so GCC defaults to
  generic `x86-64`. `objdump -d` confirms the binary has zero
  `%ymm` and zero `%zmm` register references — SSE2-only.

The NaN scan is a trivially streaming pass: AVX-512 chews through it
~4× wider than SSE2, so the per-step overhead drops from ~9 % to
~2 %. Same hardware, different binary.

Because milan also runs the NeSI binary, milan's ~10 % NaN overhead
fits the same SSE2-only story; nothing about milan's DDR4 or its
heterogeneous nodes is needed to explain it. RCH almost certainly
has the same SSE2-class build (we haven't measured NaN-on there),
so the prediction is ~10 % overhead.

The full diagnostic chain is in `cascade-strong-vs-weak-puzzle.md`,
and a rebuild recommendation for NeSI is in
`nesi-sw4-rebuild-recommendation.md`.

## Bandwidth hypothesis

The original genoa-vs-milan comparison set up a memory-bandwidth
explanation that the cascade data has now reinforced — and complicated.

SW4 is a 3-D finite-difference stencil code — its inner loops stream
large arrays from DRAM and become memory-bandwidth-bound once working
sets spill out of cache. Per-core throughput is therefore set by
**available DRAM bandwidth per rank**, not by raw FLOPS.

Bandwidth-per-rank at 126 ranks/node on each partition:

| Partition | Cores/node | DRAM | Channels/socket | Ranks/socket | Per-channel ranks |
|---|---|---|---|---|---|
| cascade (Zen4 Genoa, 2× 192)   | 384 | DDR5-4800 | 12 | 63 | ~5 |
| genoa   (NeSI, Zen4, 2× 168)   | 336 | DDR5-4800 | 12 | 63 | ~5 |
| milan   (Zen3, 2× 64)          | 128 | DDR4-3200 |  8 | 63 | ~8 |
| rch hcpu (Zen3-ish*)           | 144–192 | DDR4 (likely DDR4-3200) | 8 | 63 | ~8 |

*RCH hcpu nodes use EasyBuild modules tuned for `amd/zen3`, so
they're Zen3-class with DDR4. The full per-class rundown is in
`scaling-test-rationale.md`.

Two effects compound on the DDR4 partitions:

1. **Channel utilisation**: ~5 ranks/channel on the DDR5 boxes vs.
   ~8 on milan/RCH. Ranks queue harder for the memory controller as
   you pack more of them per channel.
2. **Raw bandwidth per channel**: DDR5-4800 ≈ 38 GB/s vs. DDR4-3200
   ≈ 25 GB/s. Per-socket peak is ~460 GB/s (DDR5) vs. ~205 GB/s
   (DDR4) — a ~2.3× gap *before* contention.

Both compound to a ~2× per-rank throughput gap, which is what we see
between the DDR5 and DDR4 machines (cascade/genoa ~2.3–3.5 vs.
milan/RCH ~1.2–1.5).

**Why cascade beats genoa on the same nominal hardware**: it's the
SIMD width of the SW4 binary, not the hardware. Cascade's Spack
build sets `target=zen4` → `-march=znver4` → AVX-512 (8 doubles per
SIMD op). NeSI's CMake build leaves `CMAKE_*_FLAGS` empty, so GCC
uses the generic `x86-64` default → SSE2 (2 doubles per SIMD op).
Disassembly of the NeSI binary shows zero `%ymm` / `%zmm` register
references; only `%xmm`.

That ~4× SIMD-width difference accounts for cascade's ~46 %
weak-scaling lead and ~4× cheaper NaN scan. On strong scaling the
gap is smaller (2.32 vs. 2.48) because that grid's per-rank
inner-loop length is short enough that even AVX-512 saturates DRAM
bandwidth before its full SIMD width pays off — the two binaries
end up bottlenecked at the same place.

Strong-scaling efficiency is also slightly worse on cascade
(79 % vs. 88 %), which is likely a separate inter-node-communication
effect — cascade's PBS/Intel-MPI fabric vs. NeSI's Slurm/OpenMPI
fabric. Worth checking if anyone wants to chase it, but it's a
second-order effect.

Full diagnostic chain in `cascade-strong-vs-weak-puzzle.md`; rebuild
recommendation for NeSI in `nesi-sw4-rebuild-recommendation.md`.

## Implications for users

- **Throughput-bound jobs at production scale (weak scaling)**:
  prefer **cascade**. ~45 % faster per core than genoa and
  ~2.3–2.9× faster than milan/RCH, and the curve is dead flat
  out to 4 nodes.
- **Throughput-bound jobs at fixed problem size (strong scaling)**:
  **genoa** edges cascade (2.48 vs. 2.32) and scales slightly better
  to 4 nodes (88 % vs. 79 % efficiency). Cascade is still a strong
  second.
- **Predictable wall-clock budgets**: cascade is now the steadiest
  fast option (98 % weak stability, no per-job zigzag). RCH (hcpu)
  remains the steadiest of the DDR4 boxes if cascade is unavailable.
- **Avoid milan if alternatives exist**: not because it's slow on
  average — milan is *similar* to RCH at the mean — but because
  its variance is bad enough that you can't predict an individual
  run's wall-clock to better than ~50 %.
- **NaN checking**: cheap on cascade only (~0–3 %). On NeSI's
  genoa and milan it costs ~9–12 % because the NeSI SW4 binary
  is SSE2-only (no `-march` flag at build time), so the NaN scan
  doesn't vectorise. RCH's binary is in the same class, so budget
  ~10 % overhead there too. A NeSI rebuild with `-march=znver{3,4}`
  would close this gap — see `nesi-sw4-rebuild-recommendation.md`.

## What this still does not tell us

- **Confirmation by rebuild**: we've shown by static analysis that
  the NeSI binary is SSE2-only and the cascade binary has AVX-512.
  We haven't yet rerun NeSI scaling with a `-march=znver{3,4}`
  rebuild to confirm the predicted speedup end-to-end.
- **Cascade's worse strong-scaling efficiency** (79 % vs. genoa's
  88 %): probably an inter-node-comm difference (Intel MPI / PBS
  fabric vs. NeSI's OpenMPI / Slurm), but not isolated.
- **Different ranks/node layouts on milan**: 64/node (relieving
  channel pressure) might recover much of the genoa/milan gap. We
  haven't tested it because the whole point of 126/node is
  cross-HPC comparability.
- **NaN checks on RCH**: still untested directly. RCH almost
  certainly runs the same SSE2-class build as NeSI, so ~10 %
  overhead is the prediction.

## Source data

Archives at `/home/arr65/data/sw4_scaling_tests/`:

- `without_nan_checks/{nesi_genoa,nesi_milan,rch,cascade}_scaling_test_without_nan_checks.tar.gz`
- `with_nan_checks/{nesi_genoa,nesi_milan,cascade}_scaling_test_with_nan_checks.tar.gz`

Each contains a Cylc run dir; throughput numbers come straight from
the `log/db.task_jobs` table (`time_run_exit - time_run`) divided
into the cell × step counts from
`cylc/cylc-src/flow/{weak,strong}_scaling.csv` and the strong-test
input file. The plot is generated by `scripts/compare_scaling.py`.

**Note on the RCH 504 timings**: the cylc scheduler on the RCH login
node died before the 504-core jobs left the queue, so it never
recorded their completion in `log/db`. The two jobs (Slurm 164927
strong, 165473 weak) ran successfully on 2026-04-27. Their
`time_run` / `time_run_exit` were back-filled into the archived db
by hand via a sqlite `UPDATE` from sacct's Start/End, so
`compare_scaling.py` reads all four points directly. To avoid the
back-fill on future RCH runs, launch the scheduler under
`tmux` / `screen` so it survives a login-session timeout.
