# What we found, in plain English

A non-technical companion to `cross-hpc-throughput.md`,
`cascade-strong-vs-weak-puzzle.md`, and
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
differently**:

| Test | Whole grid | Per-core chunk |
|---|---|---|
| Strong | 128 × 1984 × 1984 | ~128 × 140 × 220 |
| Weak   | 1000 × 1000 × 500 | ~70 × 110 × 500   |

The CPU works through one "row" at a time along the longest
dimension before fetching the next supply.

- **Strong test**: longest dimension per core is **220 cells**. The
  chef chops a row of 220 onions, then has to wait for the next
  delivery. Short rows mean lots of waiting and little chopping.
- **Weak test**: longest dimension per core is **500 cells** —
  more than 2× longer. The chef can chop straight through 500
  onions before needing to refetch.

Now the four cases play out cleanly:

|                              | ESNZ CPU (8 knives) | NeSI CPU (2 knives) |
|---                           |---|---|
| **Strong** (220-cell rows)   | Waiting on memory anyway → ~2.5 | Waiting on memory anyway → ~2.5 |
| **Weak** (500-cell rows)     | Plenty of work cached, 8 knives blast through → **3.5** | Plenty of work cached, but the 2 knives can't keep up → ~2.5 |

So three cases look similar because they're all bottlenecked on
something other than knife count — either the deliveries are too
slow (the strong test, both CPUs) or the knives are too few (the
weak test, NeSI). Only the ESNZ weak test escapes both bottlenecks
at once, which is why it's the one outlier.

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

- `cross-hpc-throughput.md` — full cross-HPC data and analysis.
- `cascade-strong-vs-weak-puzzle.md` — diagnostic chain leading to
  the SIMD-width finding.
- `building-sw4-on-nesi-and-rch.md` — concrete rebuild instructions
  for both NeSI and RCH.
