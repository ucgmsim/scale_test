# What we found, in plain English

A non-technical companion to `cross-hpc-throughput.md` and
`building-sw4-on-nesi-and-rch.md`. Same conclusions, fewer
acronyms — useful for explaining the findings to someone who
doesn't work on HPC scaling tests.

## The puzzle we set out to solve

Two New Zealand HPC sites (NeSI and ESNZ) have nearly identical
processors and memory. We ran the same earthquake simulation (SW4)
on both. On one of the test types, the ESNZ machine was about 1.5×
faster than the NeSI machine. Why?

## The CPU's super-power

Modern processors can do math on many numbers at once — like a
chef chopping eight onions in a single motion instead of chopping
them one at a time. This is the single biggest performance feature
CPUs have added in the last decade.

The two CPUs in this comparison are physically the same model.
Both can chop **8 numbers at a time**. So the hardware super-power
is identical.

## The catch

When you build a program from source code, you have to **tell** the
build tool that the CPU has this super-power. If you don't, the
build tool plays it safe and assumes the oldest, most boring
processor from 2003 — which can only do **2 numbers at a time**.

The ESNZ build was set up correctly. The NeSI build was not.

So the NeSI program runs on a modern CPU but uses one quarter of
its arithmetic capability — same code, same hardware, but quietly
chopping at a fraction of the speed.

## How we proved it

Two pieces of evidence:

1. **The build settings are recorded in a file** when the program
   is compiled. We pulled NeSI's settings file and the relevant
   line was simply blank — no instruction to use the wide
   super-power.
2. **The compiled program itself reveals what arithmetic style it
   uses.** We looked inside the NeSI program and counted the wide
   instructions: zero. It's chopping two at a time, everywhere.

## A twist: why some test results look the same anyway

Looking at the throughput numbers, three out of four cases cluster
around 2.5 (in our throughput units) and only one — the ESNZ
"weak test" — shoots up to 3.5. If the issue is just "wide knives
vs. narrow knives", why don't *all* the ESNZ results pull ahead?

Because there are **two bottlenecks**, not one:

1. How fast memory can deliver numbers to the CPU.
2. How fast the CPU can do the math once it has them.

Wide knives only help with #2. If you're already waiting on
deliveries from memory, more knives don't make the supplies arrive
faster.

## Why grid shape matters

We ran two test types. Each gives every core roughly the same
amount of work (~4 million cells per core), but **shaped
differently**. The CPU works through one "row" at a time along the
longest dimension of each core's chunk before fetching the next
supply — so **the length of that longest row is the variable that
decides whether the wide knives help or get under-used**.

### Strong test — global grid fixed, cores grow

The global grid is held constant; each core's chunk shrinks as we
add cores.

| Cores | Global grid       | Per-core chunk    | Per-core longest row |
|---    |---                |---                |---                   |
| 126   | 128 × 1984 × 1984 | 128 × 142 × 220   | 220 |
| 252   | 128 × 1984 × 1984 | 128 × 142 × 110   | 142 |
| 378   | 128 × 1984 × 1984 | 128 × 110 × 94    | 128 |
| 504   | 128 × 1984 × 1984 | 128 × 94  × 84    | 128 |

The longest row **shrinks** as cores grow (the global grid keeps
getting sliced finer). At 126 cores it's already only 220 cells.

### Weak test — global grid grows with cores

Each core's chunk stays roughly the same size; the global grid grows
to match.

| Cores | Global grid       | Per-core chunk    | Per-core longest row |
|---    |---                |---                |---                   |
| 126   | 1000 × 1000 × 500 | 71 × 111 × 500    | **500** |
| 252   | 1420 × 1420 × 500 | 79 × 101 × 500    | **500** |
| 378   | 1740 × 1740 × 500 | 83 × 97 × 500     | **500** |
| 504   | 2008 × 2008 × 500 | 84 × 96 × 500     | **500** |

The longest row **stays at 500 cells throughout**, because the
500-cell dimension was the smallest of the global grid and the
decomposition leaves it untouched.

### The point — weak's longest row is always longer

**In every single weak-scaling run, the per-core longest row is 500
cells. In every single strong-scaling run, it's 220 or less.** That
single difference — weak's longest row always being longer than
strong's — is what creates the throughput gap on the ESNZ machine.

For the wide-knife CPU (ESNZ, 8 knives):

- **Strong** (rows ≤ 220): not long enough to keep all 8 knives fed.
  The chef wastes time waiting for the next row to start. Throughput
  ≈ 2.5.
- **Weak** (rows = 500): comfortably long enough to keep all 8 knives
  busy non-stop. Throughput ≈ **3.5**.

For the narrow-knife CPU (NeSI, 2 knives):

- Both tests look similar (~2.5). Two knives are easy to keep fed
  even on short rows — the CPU isn't the bottleneck either way.

So three of the four cases look similar because they're not
CPU-bound at all. Only the ESNZ weak test combines wide knives
*with* long enough rows to actually use them — and that's the one
outlier.

## The fix and what it gets us

Recompile the NeSI version with one extra word in the build
command (`-march=znver4`). That's the entire change. Based on the
empirical comparison with the ESNZ build, we expect:

- NeSI's weak-test performance to catch up with ESNZ's — about a
  1.5× speedup on weak workloads.
- NeSI's strong-test performance to stay roughly the same; it was
  bottlenecked on memory, not knife count.
- An optional safety feature (NaN checking, which scans the data
  for bad numbers each step) to drop from ~9 % overhead to ~2 %.
  The wide knives also speed up that scan.

In practical terms: researchers running these simulations on NeSI
get their weak-scaling results faster, and the same compute budget
pays for more science.

## Where the technical detail lives

- `cross-hpc-throughput.md` — full cross-HPC data, analysis, and the
  diagnostic chain that landed on the SIMD-width finding (§ "The
  SIMD-width finding").
- `building-sw4-on-nesi-and-rch.md` — concrete rebuild instructions
  for both NeSI and RCH.
