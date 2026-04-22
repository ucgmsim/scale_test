# SW4 throughput: milan vs. genoa

Observation from the first cross-HPC scaling run: **SW4 runs ~2× slower
per core on NeSI Mahuika's milan partition than on genoa**, even though
both are run with identical grids, identical `--ntasks-per-node=126`,
and identical `--mem-per-cpu=2500M`.

This is a memory-bandwidth finding, not a memory-capacity one.

## Numbers

| Partition | Per-core throughput | Source |
|---|---|---|
| genoa | 635-685 k cell-steps/core/s | 3 successful strong runs, 2nd test campaign |
| milan | ~335 k cell-steps/core/s | weak_test252 TIMEOUT at step 901/1000 in 10 829 s |

Derivation for milan:
`(1420 × 1420 × 500 cells × 901 steps) / (252 cores × 10 829 s) ≈ 333 k`.

At 4 M cells/core × 1000 steps that implies:

- Genoa expected runtime: ~1.6 h ✓ (matches rationale-doc predictions)
- Milan expected runtime: ~3.3 h — overruns the original 3 h walltime

Which is exactly what we saw: `weak_test252` on milan TIMEOUT'd at
step 901 (~90% through), and other pending weak tasks were at the same
risk. Walltime bumped to 5 h in commit `5958fc4`.

## Memory capacity: fine

Milan memory was never the issue. `sacct` for `weak_test252`:

- MaxRSS ≈ 2017 MiB ≈ 1.97 GiB per rank
- Budget at `--mem-per-cpu=2500M` = 2.44 GiB per rank → ~20% headroom

The calibrated memory model from the genoa runs
(`~270 MiB + ~510 B × cells_per_task`, see
`scaling-test-rationale.md`) predicts ~2.17 GiB at 4 M cells/core.
Milan measured 1.97 GiB, slightly *below* the genoa fit. Allocator /
glibc differences probably account for the ~200 MiB delta. Point
being: milan is comfortably inside the memory budget.

## Hypothesis: memory bandwidth contention

SW4 is a 3-D finite-difference stencil code — its inner loops
stream large arrays from DRAM and are memory-bandwidth-bound once
working sets spill out of cache. So per-core throughput is set by
**available DRAM bandwidth per rank**, not by raw FLOPS.

Bandwidth-per-rank at 126 ranks/node on each partition:

| Partition | Cores/node | DRAM | Channels/socket | Ranks/socket | Socket utilization |
|---|---|---|---|---|---|
| genoa (Zen4) | 336 (2× 168) | DDR5-4800 | 12 | 63 | **38 %** |
| milan (Zen3) | 128 (2× 64)  | DDR4-3200 |  8 | 63 | **98 %** |

Two effects compound:

1. **Utilization**: genoa runs 63 ranks against 12 DDR5 channels —
   ~5 ranks per channel. Milan runs 63 ranks against 8 DDR4 channels —
   ~8 ranks per channel, and the socket is packed end-to-end. Ranks on
   milan queue harder for memory controller cycles.
2. **Raw bandwidth per channel**: DDR5-4800 delivers ~38 GB/s per
   channel vs. DDR4-3200's ~25 GB/s. Per-socket peak is roughly
   460 GB/s (genoa) vs. 200 GB/s (milan) — a ~2.3× gap before
   contention.

Multiplied together, the ~2× per-rank throughput ratio we observe is
consistent with a bandwidth-starved stencil code.

## Implications

- **Production SW4 on milan**: budget ~2× the wall-clock of an
  equivalent genoa run. The ~510 B/cell memory model still applies.
- **Packing less than 126 ranks/node on milan would help.** Running
  e.g. 64 ranks/node (one per physical core pair, or splitting the
  socket bandwidth across fewer consumers) should approach or exceed
  genoa's per-core throughput — at the cost of twice the node count
  for the same core count. Useful for urgent jobs, wasteful
  otherwise. Not tested here.
- **This scaling test's 126/node constraint is still the right call
  for cross-HPC comparability** — the whole *point* is to run the
  same layout everywhere and see how each machine behaves. The milan
  result just tells us milan is ~half as fast per core under that
  layout; it doesn't invalidate the comparison.

## What this does *not* tell us

- Nothing about Cascade or RCH throughput yet — haven't run there.
- Nothing about how milan would behave at a different ranks/node
  layout (e.g. 64/node) — only 126/node was tested.
- Nothing about SMT: `--hint=nomultithread` is set, so the 126 ranks
  are pinned to 126 physical cores (out of 128). SMT wasn't
  contributing to the slowdown.
