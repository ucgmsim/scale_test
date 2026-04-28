# SW4 cross-HPC throughput

Per-core SW4 throughput across the HPCs we've measured so far, all run
with the same Cylc workflow at 126 tasks/node, ~4 M cells/core (weak)
and a fixed 128 × 1984 × 1984 grid (strong).

![Strong and weak scaling, four HPC × NaN-check combinations](cross-hpc-throughput.png)

## Headline numbers

Mean per-core throughput in **k cell-steps / core / s**, across the four
weak / four strong runs in each campaign. "Range" is min–max across
those four data points.

| HPC × config | Strong (mean / range) | Weak (mean / range) |
|---|---|---|
| genoa, no NaN check  | **688** / 636–726 | **679** / 661–715 |
| milan, no NaN check  | 406 / 326–493     | 429 / 380–452     |
| milan, NaN check on  | 296 / 190–439     | 372 / 299–451     |
| rch (hcpu), no NaN   | 335 / 306–378     | 334 / 308–355     |

Genoa is ~2× faster per core than milan or RCH, and it's also the
*tightest* — measurements vary by ~13 % across configurations. RCH
runs at roughly half genoa's throughput; its weak campaign is fairly
flat (~14 % spread) but the strong sweep is wider (~21 %), with a
mid-sweep dip at 252 cores that recurs in the weak data too.
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
| genoa, no NaN  | 722 | 636 | **88 %** |
| rch,   no NaN  | 378 | 306 | **81 %** |
| milan, no NaN  | 479 | 327 | 68 % (dominated by hardware noise) |

Genoa scales very well to 4 nodes. RCH's 81 % is solid; the four
points span 306–378 with a mid-sweep dip at 252 cores rather than a
monotonic decline. The milan number is consistent with what its
weak-scaling curve also shows: the partition is too heterogeneous
for a single efficiency number to be meaningful at this sample size.

## Weak scaling stability

For a memory-bandwidth-bound stencil code, ideal weak scaling means
the per-core throughput is **flat** as we add nodes (because each rank
gets the same work and the same bandwidth share). 504-core / 126-core
ratio:

| HPC × config | 126 weak | 504 weak | Stability |
|---|---|---|---|
| genoa | 679 | 661 | **97 %** — flat |
| rch   | 355 | 308 | 87 %        |
| milan, no NaN | 452 | 380 | 84 % |
| milan, NaN on | 387 | 350 | 91 % |

Genoa is excellent here. RCH is reasonable — flatter than milan, but
the 504-core point pulls the stability number well below genoa's.
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

`developer checkfornan=on` was tested only on milan, so the same
heterogeneity above clouds the result. The cleanest comparisons are
the points where with- and without-NaN per-core throughput is
similar in absolute terms (so both runs probably hit comparable
nodes):

| Test | Without NaN | With NaN | Overhead |
|---|---|---|---|
| strong-126 | 479 | 438 |  9 % |
| strong-504 | 327 | 294 | 10 % |
| weak-126   | 452 | 387 | 14 % |
| weak-504   | 380 | 350 |  8 % |

Estimate: **~10–15 % per-step overhead** for `developer
checkfornan=on` on milan. The wider points (strong-378 going from
493 → 190, etc.) are dominated by which nodes Slurm picked, not by
the NaN-check cost.

## Bandwidth hypothesis (carried over from milan vs. genoa)

The original genoa-vs-milan comparison set up a memory-bandwidth
explanation that holds up against the new RCH data.

SW4 is a 3-D finite-difference stencil code — its inner loops stream
large arrays from DRAM and become memory-bandwidth-bound once working
sets spill out of cache. Per-core throughput is therefore set by
**available DRAM bandwidth per rank**, not by raw FLOPS.

Bandwidth-per-rank at 126 ranks/node on each partition:

| Partition | Cores/node | DRAM | Channels/socket | Ranks/socket | Per-channel ranks |
|---|---|---|---|---|---|
| genoa (Zen4, 2× 168) | 336 | DDR5-4800 | 12 | 63 | ~5 |
| milan (Zen3, 2× 64)  | 128 | DDR4-3200 |  8 | 63 | ~8 |
| rch hcpu (Zen3-ish*) | 144–192 | DDR4 (likely DDR4-3200) | 8 | 63 | ~8 |

*RCH hcpu nodes use EasyBuild modules tuned for `amd/zen3`, so
they're Zen3-class with DDR4. The full per-class rundown is in
`scaling-test-rationale.md`.

Two effects compound on the older partitions:

1. **Channel utilisation**: ~5 ranks/channel on genoa vs. ~8 on
   milan/RCH. Ranks queue harder for the memory controller as you
   pack more of them per channel.
2. **Raw bandwidth per channel**: DDR5-4800 ≈ 38 GB/s vs. DDR4-3200
   ≈ 25 GB/s. Per-socket peak is ~460 GB/s (genoa) vs. ~205 GB/s
   (milan/RCH) — a ~2.3× gap *before* contention.

Both compound to a ~2× per-rank throughput gap, which is what we
see (genoa ~680 vs. milan/RCH ~330–430). Milan and RCH coming out
broadly similar at the per-core level is consistent with similar
DDR4 generations and similar over-subscription.

## Implications for users

- **Throughput-bound jobs**: prefer **genoa**. Roughly 2× more
  wall-clock per core-hour than milan or RCH.
- **Predictable wall-clock budgets**: **RCH (hcpu)** is the
  steadiest. Even though it's not the fastest, the lack of
  per-job noise makes it the best surface for budget estimation.
- **Avoid milan if alternatives exist**: not because it's slow on
  average — milan is *similar* to RCH at the mean — but because
  its variance is bad enough that you can't predict an individual
  run's wall-clock to better than ~50 %.
- **NaN checking** costs ~10–15 %. Reasonable for troubleshooting
  bad inputs, not worth leaving on for production.

## What this still does not tell us

- **Cascade**: the only target HPC we haven't measured. Cascade
  uses PBS rather than Slurm, so the workflow needs a new platform
  block + script template before it can be run there.
- **Different ranks/node layouts on milan**: 64/node (relieving
  channel pressure) might recover much of the genoa/milan gap. We
  haven't tested it because the whole point of 126/node is
  cross-HPC comparability.
- **NaN checks on genoa or RCH**: the ~10–15 % milan estimate is
  effectively a single-machine number. It could be different on a
  less bandwidth-constrained machine if the NaN scan touches
  different parts of the working set.

## Source data

Archives at `/home/arr65/data/sw4_scaling_tests/`. Each contains a
Cylc run dir; throughput numbers come straight from the
`log/db.task_jobs` table (`time_run_exit - time_run`) divided into
the cell × step counts from
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
