# SW4 cross-HPC throughput

Per-core SW4 throughput across the HPCs we've measured so far, all run
with the same Cylc workflow at 126 tasks/node, ~4 M cells/core (weak)
and a fixed 128 × 1984 × 1984 grid (strong).

![Strong and weak scaling, seven HPC × NaN-check combinations](cross-hpc-throughput.png)

## Headline numbers

Mean per-core throughput in **k cell-steps / core / s**, across the four
weak / four strong runs in each campaign. "Range" is min–max across
those four data points.

| HPC × config | Strong (mean / range) | Weak (mean / range) |
|---|---|---|
| cascade, no NaN check  | 645 / 561–710     | **983** / 975–994 |
| cascade, NaN check on  | 627 / 549–693     | 964 / 942–1002    |
| genoa, no NaN check  | **688** / 636–726 | 679 / 661–715     |
| genoa, NaN check on  | 620 / 607–638     | 620 / 607–634     |
| milan, no NaN check  | 406 / 326–493     | 429 / 380–452     |
| milan, NaN check on  | 296 / 190–439     | 372 / 299–451     |
| rch (hcpu), no NaN   | 335 / 306–378     | 334 / 308–355     |

Cascade and genoa share the top of the table but in different ways.
Genoa wins on strong scaling (688 vs. 645) and is exceptionally tight
(13 % spread). Cascade wins decisively on weak scaling (~983 vs. ~679,
~45 % faster per core) and is the flattest weak curve we've measured —
just 994 → 975 across 4× the node count. Both clearly outclass milan
and RCH (~2–3× per-core throughput).

RCH runs at roughly half genoa's throughput; its weak campaign is
fairly flat (~14 % spread) but the strong sweep is wider (~21 %), with
a mid-sweep dip at 252 cores that recurs in the weak data too.
Milan is in the same ballpark as RCH on average but with much wider
spread — the strong-scaling curve zigzags 479 → 326 → 493 → 327
between adjacent core counts, which can't be a real algorithmic
effect; it almost certainly reflects partition heterogeneity (see
"Milan internal variability" below).

## Strong scaling efficiency

Throughput-per-core preservation when going from 126 cores (1 node) to
504 cores (4 nodes) on the same fixed grid. Ideal is 100 %; lower
means scaling tax (communication and surface-area overhead).

| HPC × config | 126-core throughput | 504-core throughput | Efficiency |
|---|---|---|---|
| genoa,   no NaN | 722 | 636 | **88 %** |
| rch,     no NaN | 378 | 306 | **81 %** |
| cascade, no NaN | 710 | 561 | **79 %** |
| milan,   no NaN | 479 | 327 | 68 % (dominated by hardware noise) |

Genoa scales best to 4 nodes. Cascade's 79 % is interesting: per-core
throughput at 126 cores is essentially the same as genoa (710 vs. 722),
but cascade gives up more between 1 and 4 nodes — the strong sweep
goes 710 → 708 → 600 → 561, dropping noticeably from 252 cores
onwards. RCH's 81 % is solid, with the four points spanning 306–378
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
| cascade, no NaN | 994 | 975 | **98 %** — flattest |
| cascade, NaN on | 1002 | 942 | 94 % |
| genoa, no NaN | 679 | 661 | 97 % |
| genoa, NaN on | 607 | 614 | 101 % (essentially flat) |
| rch   | 355 | 308 | 87 % |
| milan, no NaN | 452 | 380 | 84 % |
| milan, NaN on | 387 | 350 | 91 % |

Cascade is the flat-out winner: 994 → 975 across the no-NaN sweep is
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
NaN-check-on strong-scaling 378-core run at 190 kCS/core/s — 2.6×
slower than the 378-core run *without* NaN checks (493 kCS/core/s).
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
| strong-126 | 479 | 438 |  9 % |
| strong-504 | 327 | 294 | 10 % |
| weak-126   | 452 | 387 | 14 % |
| weak-504   | 380 | 350 |  8 % |

→ **~10–15 % per-step overhead**. The wider points (strong-378
going from 493 → 190, etc.) are dominated by which nodes Slurm
picked, not by the NaN-check cost.

**Genoa** (NeSI, Zen4, DDR5-4800, 12 channels/socket):

| Test | Without NaN | With NaN | Overhead |
|---|---|---|---|
| strong-126 | 722 | 614 | 15 % |
| strong-252 | 726 | 638 | 12 % |
| strong-378 | 670 | 620 |  7 % |
| strong-504 | 636 | 607 |  5 % |
| weak-126   | 679 | 607 | 11 % |
| weak-252   | 715 | 634 | 11 % |
| weak-378   | 662 | 627 |  5 % |
| weak-504   | 660 | 614 |  7 % |

→ **~5–15 % per-step overhead**, mean ~9 %. Larger overhead at
small core counts and tapering off as nodes are added — possibly
real, possibly noise from a 4-point sweep.

**Cascade** (UoC RCC, Zen4 Genoa, DDR5-4800, 12 channels/socket):

| Test | Without NaN | With NaN | Overhead |
|---|---|---|---|
| strong-126 | 710 | 693 | 2 % |
| strong-504 | 561 | 549 | 2 % |
| weak-126   | 994 | 1002 | −1 % (within noise) |
| weak-504   | 975 | 942 |  3 % |

→ **~0–3 % per-step overhead** — essentially in noise.

### What this means

The earlier draft of this doc proposed a clean "memory-bandwidth"
explanation: bandwidth-starved milan pays ~10 %, bandwidth-rich
cascade pays ~0 %. That hypothesis is now **broken** by the genoa
data. Genoa has the same DDR5-4800 + 12-channel hardware as cascade
(see bandwidth table below) and should sit next to cascade if the
explanation were memory-bandwidth alone — but its NaN overhead is
~9 %, much closer to milan than to cascade.

So cascade is the outlier, not the rule. Possible drivers, none
yet verified:

- **Compiler / vectorisation**: cascade is built with Intel oneAPI
  2021.16 + Spack; NeSI's genoa and milan use GCC + Cray-MPICH.
  ICX/ICC may be auto-vectorising the NaN scan into a streaming
  prefetch that overlaps with the stencil compute, where GCC emits
  a serial scan that contends.
- **Build flags**: cascade's SW4 may have been compiled with
  different optimisation flags (`-O3 -xHost`, FMA / AVX-512
  enablement) that change how the scan loop is laid out.
- **MPI runtime**: Intel MPI vs. Cray-MPICH may have different
  prefetch / non-temporal-store behaviour around the buffers SW4
  is scanning.

This is exactly the same axis that already separates cascade from
genoa on weak-scaling throughput (cascade ~983 vs. genoa ~679, see
bandwidth section). Two independent measurements both pointing at
the cascade software stack as the explanation strengthens the case
that something — most likely compiler-level — is meaningfully
better on the cascade build than on the NeSI builds.

We still don't have NaN-on data on RCH; given RCH (DDR4, GCC) is
configurationally closest to milan, the most likely outcome there
is ~10 % overhead like milan and genoa.

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
between the DDR5 and DDR4 machines (cascade/genoa ~650–980 vs.
milan/RCH ~330–430).

**What's puzzling**: cascade and NeSI's genoa are nominally the same
class (Zen4, DDR5-4800, 12 channels), but cascade is ~45 % faster on
weak scaling (983 vs. 679) **and** has dramatically lower NaN-check
overhead (~2 % vs. ~9 %). On strong scaling without NaN checks
they're closer (645 vs. 688), but the gap on the other two axes is
hard to explain with hardware alone.

Both anomalies point in the same direction: the cascade build / runtime
is doing something the NeSI builds aren't. Candidates — none confirmed:

- **Compiler stack**: Intel oneAPI 2021.16 + Spack on cascade vs.
  NeSI's GCC + Cray-MPICH on genoa. ICX/ICC's stencil
  vectorisation, FMA / AVX-512 lowering, and prefetch heuristics
  are different from GCC's.
- **Build flags**: cascade's SW4 may use `-O3 -xHost` / aggressive
  inlining where the NeSI build is more conservative.
- **MPI runtime**: Intel MPI vs. Cray-MPICH have different
  intra-node shared-memory paths and different non-temporal-store
  policies.
- **DIMM populations or BIOS-level memory tuning** — these can
  swing realised DDR5 bandwidth meaningfully even at the same
  nominal data rate.
- **Cascade nodes are 2× 192 cores (384 total) vs. genoa's 2× 168
  (336)**. We pin to 126 ranks/node on both, so bandwidth-per-rank
  should actually be slightly *higher* on cascade — but the pad of
  unused cores per socket may also reduce contention on shared
  caches and uncore.
- Quieter neighbours on cascade than on genoa during the test
  window — possible but doesn't easily explain the systematic
  ~45 % weak-scaling gap.

The strong-scaling gap *narrows* between cascade and genoa
(efficiency 79 % vs. 88 %), suggesting inter-node communication on
cascade is relatively more expensive — partially offsetting
cascade's intra-node edge. Worth investigating if anyone wants to
chase this further.

## Implications for users

- **Throughput-bound jobs at production scale (weak scaling)**:
  prefer **cascade**. ~45 % faster per core than genoa and
  ~2.3–2.9× faster than milan/RCH, and the curve is dead flat
  out to 4 nodes.
- **Throughput-bound jobs at fixed problem size (strong scaling)**:
  **genoa** edges cascade (688 vs. 645) and scales slightly better
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
  genoa and milan it costs ~9–12 %, despite the genoa/cascade
  hardware being nominally identical — so the cost looks like a
  function of the build/runtime stack, not just the HPC. Worth
  leaving on during development on cascade; budget ~10 % overhead
  on the NeSI machines and likely on RCH too.

## What this still does not tell us

- **Why cascade beats genoa on weak scaling by ~45 %** *and* pays
  ~7× less NaN-check overhead, despite nominally identical Zen4 +
  DDR5 hardware. Both anomalies point at the cascade build /
  runtime stack (Intel oneAPI + Spack) vs. NeSI's GCC +
  Cray-MPICH, but we haven't isolated which of compiler,
  build-flags, MPI, or BIOS-level tuning is responsible.
- **Different ranks/node layouts on milan**: 64/node (relieving
  channel pressure) might recover much of the genoa/milan gap. We
  haven't tested it because the whole point of 126/node is
  cross-HPC comparability.
- **NaN checks on RCH**: still untested directly. RCH's
  configuration is closest to milan, so ~10 % overhead is the
  expected outcome, but it's a prediction, not a measurement.

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
