# Building SW4 on NeSI and RCH

Operational recipe for rebuilding the SW4 binaries on NeSI Mahuika
(both genoa and milan partitions) and on RCH (hcpu partition).
Originally written 2026-05-01 after the first rebuild attempt;
revised 2026-05-15 after a second round caught what the first
missed (the `fix-sfile-srf` branch needs PROJ; the smoke test
needs an actual input file; the rpath needs more libraries on RCH
than just OpenMPI / OpenBLAS / libstdc++). Captures the steps
that actually worked end-to-end.

For the *why* — what was wrong with the previous binaries, and the
empirical case for rebuilding — see:

- `cross-hpc-throughput.md` — cross-HPC dataset and the SIMD-width
  finding.
- `cascade-strong-vs-weak-puzzle.md` — full diagnostic chain.
- `cross-hpc-findings-explained.md` — non-technical summary.

## When you'd run this

The triggers for a rebuild:
- A new SW4 release or feature branch you want on these HPCs.
- A toolchain refresh (newer GCC/OpenMPI/OpenBLAS).
- Adding a new HPC to the supported set.
- Fixing a build flag that was wrong (the original case in 2026-04).

## Common pre-flight

Both rebuilds share these steps. Differences are called out per-HPC.

### Pick a source location

Use a fresh, dated directory parallel to (not inside) the existing SW4
source. This preserves the existing build as an untouched reference
in case anything goes wrong with the new one.

| HPC  | Source dir |
|---   |---         |
| NeSI | `/nesi/project/nesi00213/opt/sw4-rebuild-YYYY-MM` |
| RCH  | `/scratch/projects/rch-quakecore/sw4-rebuild-YYYY-MM` |

### Clone the desired branch

```bash
cd <source-dir>
git clone --branch <BRANCH> https://github.com/geodynamics/sw4.git .
git config --global --add safe.directory <source-dir>
git log --oneline -3   # confirm we're on the right branch
```

The `safe.directory` config is per-user and one-time per directory;
each team member who needs to run git inside the source tree adds the
same line. Required because the dir may be group-owned, with multiple
users touching it.

### Permissions

| HPC  | What to do |
|---   |---         |
| NeSI | After `mkdir`: `chgrp nesi00213 <dir> && chmod g+rwxs <dir>` to set group ownership and the setgid inheritance bit. |
| RCH  | Skip — RCH's filesystem ACLs handle group inheritance automatically. The `chgrp` will fail with "Operation not permitted" but the result is already correct via ACL. |

## NeSI build (two binaries)

Build genoa first, then milan, swapping the meta-module between them.

### Modules

```bash
module purge   # NeSI/zen3 stays loaded — it's sticky, that's expected
module swap NeSI/zen3 NeSI/zen4
module load GCC/12.3.0 CMake OpenMPI/4.1.5-GCC-12.3.0 \
            OpenBLAS/0.3.23-GCC-12.3.0 PROJ/9.3.0-GCC-12.3.0
module list

# CRITICAL: confirm OpenMPI wraps GCC, not NVHPC
mpicxx --show   # must print g++ ...
mpif90 --show   # must print gfortran ...
```

The default `OpenMPI` module on NeSI resolves to a CUDA + NVHPC variant
that wraps `nvc++` instead of `g++`. Always load the full versioned
name `OpenMPI/4.1.5-GCC-12.3.0` to avoid this trap. If `mpicxx --show`
reports `nvc++`, swap to the correct OpenMPI variant before building.

PROJ is required because the production `.in` files use
`proj=tmerc datum=WGS84 ...` and the `fix-sfile-srf` branch (and
presumably newer SW4 in general) refuses to run when the input
file requests a projection that the binary wasn't built to handle.
Older SW4 used to silently fall back to internal projection code,
which is what made the previous `baes` binary work without PROJ
support — the new branch tightens this check.

### Configure and build the genoa binary

```bash
cd <source-dir>

rm -rf build-genoa && cmake -S . -B build-genoa -DCMAKE_BUILD_TYPE=Release -DUSE_PROJ=ON -DCMAKE_CXX_FLAGS=-march=znver4 -DCMAKE_C_FLAGS=-march=znver4 -DCMAKE_Fortran_FLAGS=-march=znver4

cmake --build build-genoa -j 4
```

`-j 4` is polite for a shared login node. For a faster build use
`srun --account=nesi00213 --partition=genoa --time=00:30:00 --cpus-per-task=8 --pty bash`
and use `-j 8` on the compute node.

The cmake command is intentionally **on a single line**. Backslash
line-continuations are fragile under copy/paste — if the
backslash-newline gets eaten (some terminal/clipboard combinations
do this), two lines join without a space and quoted strings
concatenate with the next token, producing garbled flags like
`-march=znver4-DUSE_PROJ=ON`. Single-line is bulletproof.

### Switch and configure the milan binary

```bash
module swap NeSI/zen4 NeSI/zen3   # all toolchain modules survive the swap

rm -rf build-milan && cmake -S . -B build-milan -DCMAKE_BUILD_TYPE=Release -DUSE_PROJ=ON -DCMAKE_CXX_FLAGS=-march=znver3 -DCMAKE_C_FLAGS=-march=znver3 -DCMAKE_Fortran_FLAGS=-march=znver3

cmake --build build-milan -j 4
```

**Never use `-march=znver4` for milan** — milan is Zen3 hardware with
no AVX-512. A znver4 binary will SIGILL on the first AVX-512 op.

### Verify

```bash
# AVX-512 sanity (genoa) — both must be > 0
objdump -d build-genoa/bin/sw4 | grep -c '%zmm'
objdump -d build-genoa/bin/sw4 | grep -c '%ymm'

# AVX-2 sanity (milan) — %zmm MUST be 0
objdump -d build-milan/bin/sw4 | grep -c '%zmm'
objdump -d build-milan/bin/sw4 | grep -c '%ymm'
```

Reference numbers from the 2026-05 build: genoa ~12 K `%zmm` + ~16 K
`%ymm`, milan 0 `%zmm` + ~17 K `%ymm`. Exact counts will drift across
GCC versions and source revisions; the `%zmm = 0` check on milan is
the critical one.

### Smoke test on real hardware

Use the canonical smoke input file `docs/sw4-build-smoke.in` in this
repo — a 7 × 7 × 7 km grid with a `proj=tmerc` projection and a
single time step. Two things have to be true at once: the input
exercises PROJ (the failure mode we're guarding against), and the
grid is large enough to contain SW4's default 3 km supergrid absorbing
boundary on each non-free-surface face.

```bash
# scp the smoke input up (do this once)
scp docs/sw4-build-smoke.in <nesi>:/nesi/project/nesi00213/sw4_scale_tests/smoke.in

# on NeSI — note --account=nesi00213 is mandatory now
srun --account=nesi00213 --partition=genoa --time=00:05:00 --ntasks=1 \
  <source-dir>/build-genoa/bin/sw4 \
  /nesi/project/nesi00213/sw4_scale_tests/smoke.in

srun --account=nesi00213 --partition=milan --time=00:05:00 --ntasks=1 \
  <source-dir>/build-milan/bin/sw4 \
  /nesi/project/nesi00213/sw4_scale_tests/smoke.in
```

Expected: SW4 banner with `3rd party include dir: <PROJ path>`
(rather than the old `NA`), grid setup messages, a single time step,
clean exit. Critical: **no SIGILL, no `Illegal instruction`,
no library-load errors, no `Fatal input error` about PROJ or
supergrid taper width**.

Argument-only smoke tests (e.g. running with `-h`) are not sufficient
— they exit before SW4 reaches input-file parsing, so they don't
exercise the PROJ-required check. That's how the 2026-05-01 first-pass
rebuild slipped a PROJ-less binary into production-but-failing
campaigns. Always use an actual `.in` file for smoke testing.

### Install

```bash
cp build-genoa/bin/sw4 /nesi/project/nesi00213/tools/sw4-genoa
cp build-milan/bin/sw4 /nesi/project/nesi00213/tools/sw4-milan
chgrp nesi00213    /nesi/project/nesi00213/tools/sw4-{genoa,milan}
chmod g+rx         /nesi/project/nesi00213/tools/sw4-{genoa,milan}
```

The existing `/nesi/project/nesi00213/tools/sw4` stays untouched —
still the safe fallback during validation.

### NeSI does not need rpath

NeSI's modules set `LD_LIBRARY_PATH` (legacy EasyBuild behaviour), and
the cylc workflow's pre-script loads modules at job time, which
propagates `LD_LIBRARY_PATH` through `srun`. So the binaries work at
runtime without needing rpath baked in. Matches the convention of the
existing `baes`-built binary, which also has no rpath.

If a developer wants to run `sw4-genoa` or `sw4-milan` standalone
outside cylc, they need to `module load` the same toolchain first
(including `PROJ/9.3.0-GCC-12.3.0` — PROJ is needed at runtime
as well as build time) or they'll hit `libmpi.so.40: not found`
or `libproj.so.X: not found`. The cylc workflow's existing
`[[SW4]]` pre-script already loads PROJ, so the production pathway
is fine — this is just a standalone-use heads-up.

## RCH build (one binary, with rpath workaround)

RCH is Zen3 only — one architecture, one binary. But RCH's modules
don't set `LD_LIBRARY_PATH` at runtime (modern EasyBuild behaviour),
so the rpath workaround is mandatory. Without it, the binary fails at
runtime even with modules loaded.

### Modules

```bash
module purge
module load prefix/2025      # gates the EasyBuild module tree on RCH
module load GCC/13.3.0 CMake/3.29.3-GCCcore-13.3.0 \
            OpenMPI/5.0.3-GCC-13.3.0 OpenBLAS/0.3.27-GCC-13.3.0 \
            PROJ/9.4.1-GCCcore-13.3.0 LibTIFF/4.6.0-GCCcore-13.3.0
module list

# verify wrappers
mpicxx --show   # must print g++ ...
mpif90 --show   # must print gfortran ...

# confirm the EBROOT* vars we'll feed into RPATH all expanded
for v in EBROOTOPENMPI EBROOTOPENBLAS EBROOTGCCCORE EBROOTPROJ EBROOTSQLITE EBROOTLIBTIFF; do
  echo "$v=${!v}"
done
```

The 13.3 toolchain matches what RCH's existing SW4 binary was built
against. Picking the same toolchain keeps the pre/post comparison
clean (only `-march` differs). NeSI uses 12.3 because the existing
NeSI binary was built with 12.3 — same logic, different version per
HPC convention.

**Transitive PROJ deps**: PROJ pulls in SQLite (which loads
automatically when you load PROJ — check `$EBROOTSQLITE`) and
LibTIFF (which does **not** auto-load — must be loaded explicitly,
hence its presence in the module load line above). PROJ may pull
in more deps in newer versions — whack-a-mole the `ldd ... | grep
'not found'` output after building until everything resolves.

### Configure with rpath flags

```bash
cd <source-dir>

# all six directories the binary needs at runtime
RPATH="$EBROOTOPENMPI/lib:$EBROOTOPENBLAS/lib:$EBROOTGCCCORE/lib64:$EBROOTPROJ/lib:$EBROOTPROJ/lib64:$EBROOTSQLITE/lib:$EBROOTLIBTIFF/lib"
echo "RPATH=$RPATH"   # sanity-check no empty components

rm -rf build-rch && cmake -S . -B build-rch -DCMAKE_BUILD_TYPE=Release -DUSE_PROJ=ON -DCMAKE_CXX_FLAGS=-march=znver3 -DCMAKE_C_FLAGS=-march=znver3 -DCMAKE_Fortran_FLAGS=-march=znver3 -DCMAKE_EXE_LINKER_FLAGS="-Wl,-rpath,$RPATH"

cmake --build build-rch -j 1
```

Cmake command is single-line for the same reason as the NeSI build
— avoids the bash paste line-continuation gotcha that concatenates
quoted strings with the next token.

**Never use `-march=znver4` on RCH** — Zen3 hardware has no AVX-512;
any znver4 build will SIGILL on the first AVX-512 instruction.

`-j 1` because RCH's login node is feeble. For faster builds, request
an interactive compute session: `srun --account=rch-quakecore
--partition=short --time=00:30:00 --cpus-per-task=8 --constraint=hcpu
--pty bash`.

### Why `CMAKE_EXE_LINKER_FLAGS` instead of CMake's rpath variables

`CMAKE_INSTALL_RPATH_USE_LINK_PATH=ON` and
`CMAKE_BUILD_WITH_INSTALL_RPATH=ON` are the "polite" CMake variables
that should set rpath automatically. Empirically on RCH they didn't
take effect — something in SW4's CMakeLists.txt or the build chain
overrode them. The `CMAKE_EXE_LINKER_FLAGS="-Wl,-rpath,..."` approach
appends the rpath directly to the linker command line, bypassing
CMake's rpath logic entirely. It's a sledgehammer but it works.

### The rpath directories

The binary needs all of these at runtime; each addresses a specific
library it can't find via system defaults:

| Path | What it provides |
|---|---|
| `$EBROOTOPENMPI/lib`   | `libmpi.so.40` |
| `$EBROOTOPENBLAS/lib`  | `libopenblas.so.0` |
| `$EBROOTGCCCORE/lib64` | `libstdc++.so.6` (newer `GLIBCXX_3.4.32` than the system GCC 11 provides) and `libgfortran.so.5` |
| `$EBROOTPROJ/lib`, `$EBROOTPROJ/lib64` | PROJ runtime (both subdirs needed — PROJ ships data files in `lib`, libs in `lib64`) |
| `$EBROOTSQLITE/lib`    | `libsqlite3.so.0` (PROJ's transitive dep for its on-disk projection database) |
| `$EBROOTLIBTIFF/lib`   | `libtiff.so.6` (PROJ uses it for GeoTIFF I/O) |

If any of these paths is missing from the rpath, the binary will
fail at runtime with `libX.so.N: cannot open shared object file`.
Run `ldd build-rch/bin/sw4 | grep 'not found'` after the build —
should be empty.

### Verify

```bash
# rpath baked in
readelf -d build-rch/bin/sw4 | grep -E 'RPATH|RUNPATH'
# should show all six directories (OpenMPI, OpenBLAS, GCCcore,
# PROJ/lib, PROJ/lib64, SQLite, LibTIFF)

# all libraries resolve
ldd build-rch/bin/sw4 | grep 'not found'
# should print nothing — if any library is "not found", load its
# module and add $EBROOTXXX/lib to the RPATH variable, then rebuild

# SIMD sanity
objdump -d build-rch/bin/sw4 | grep -c '%ymm'   # should be > 0 (AVX-2 in use)
objdump -d build-rch/bin/sw4 | grep -c '%zmm'   # see note below
```

**Heads-up on `%zmm` for the RCH binary**: empirically the 2026-05
build with PROJ enabled has **~700 `%zmm` references** in its text
section despite being compiled at `-march=znver3` (which has no
AVX-512). The reason is that PROJ ships with ISA-dispatched
implementations of some functions — one each for SSE2 / AVX-2 /
AVX-512 — and PROJ's static helpers pull all variants into our
binary. PROJ then runtime-detects the CPU at first call and picks
the AVX-2 path on Zen3. The AVX-512 code is *present but unreachable*
on Zen3. The smoke test below is the real proof that nothing
SIGILLs in practice.

Previous RCH build (without `USE_PROJ=ON`) had **0 `%zmm`** — that's
where the AVX-512 instructions came from when we added PROJ.

### Smoke test

The binary is self-contained (rpath baked in) — no module loads
needed at runtime:

```bash
# scp the smoke input up (do this once)
scp docs/sw4-build-smoke.in <rch>:/scratch/projects/rch-quakecore/sw4_scale_tests/smoke.in

# on RCH
srun --account=rch-quakecore --partition=short --time=00:05:00 \
     --ntasks=1 --constraint=hcpu --exclude=n03 \
     <source-dir>/build-rch/bin/sw4 \
     /scratch/projects/rch-quakecore/sw4_scale_tests/smoke.in
```

(`--exclude=n03`: that node has a known cylc incompatibility; not
strictly required for a one-shot srun, but harmless for symmetry with
the cylc workflow.)

Expected: SW4 banner with `3rd party include dir: <PROJ path>`,
grid setup messages, a single time step, clean exit. No SIGILL
(despite the `%zmm` references — see verify section above), no
library-load errors, no `Fatal input error`.

The smoke test exercises PROJ's coordinate-transform path during
grid setup; if PROJ's ISA dispatch were broken on Zen3, this would
SIGILL during initialisation. Successful smoke = confirmation that
the `%zmm` references are unreachable on this hardware.

### Install

```bash
cp build-rch/bin/sw4 /scratch/projects/rch-quakecore/sw4/sw4-znver3
chmod g+rx /scratch/projects/rch-quakecore/sw4/sw4-znver3
```

Skip `chgrp` on RCH — ACL inheritance handles it. The existing
`/scratch/projects/rch-quakecore/sw4/optimize_mp/sw4` stays untouched
as the fallback.

## Updating the cylc workflow

After install, point the cylc workflow at the new binary by editing
`cylc/cylc-src/flow/flow.cylc`. Update `SW4_BIN` for each affected
HPC block (lines vary as the file evolves; search for the existing
`SW4_BIN =` lines):

| HPC block in flow.cylc | SW4_BIN should point at |
|---                      |---                       |
| `mahuika-genoa`         | `/nesi/project/nesi00213/tools/sw4-genoa` |
| `mahuika-milan`         | `/nesi/project/nesi00213/tools/sw4-milan` |
| `rch`                   | `/scratch/projects/rch-quakecore/sw4/sw4-znver3` |

Commit + push. On the target HPC, `git pull` in the workflow checkout
and launch the campaign:

```bash
cd <workflow-checkout>      # NeSI: /nesi/project/nesi00213/sw4_scale_tests/scale_test
                             # RCH:  /scratch/projects/rch-quakecore/sw4_scale_tests/scale_test
git pull
tmux new -s sw4-rebuild
cylc vip flow --set 'HPC="<mahuika-genoa|mahuika-milan|rch>"'
```

`tmux` protects the cylc scheduler from systemd-logind reaping at SSH
session end — important because the scheduler is the one updating
`log/db` with task timings. (Note: cylc *daemonises* the scheduler, but
the daemon's lifetime depends on whether systemd reaps it; tmux gives
it a longer-lived parent.)

## Future binary swap (optional)

The "install alongside, point cylc at it" pattern leaves the original
binary untouched. Once the post-rebuild scaling campaign confirms the
new binary is faster and correct, the canonical path can be swapped
to point at the new file:

```bash
# RCH example — same idea on NeSI with sw4-genoa / sw4-milan
mv /scratch/projects/rch-quakecore/sw4/optimize_mp/sw4 \
   /scratch/projects/rch-quakecore/sw4/optimize_mp/sw4-pre-march-2026-04
ln -s /scratch/projects/rch-quakecore/sw4/sw4-znver3 \
      /scratch/projects/rch-quakecore/sw4/optimize_mp/sw4
```

Symlink is preferred over `mv` for the canonical path because it's
trivially reversible. Coordinate with the original binary's owner
before doing this — date-stamped renames preserve the audit trail.

## Smaller secondary tuning levers

If the `-march` build is in place and there's appetite to push
further, these are additional options ordered by effort vs. likely
gain. Numbers are rules of thumb for stencil codes, **not** measured
on SW4 specifically.

- **`-mprefer-vector-width=512`** (only with `-march=znver4`).
  GCC defaults to 256-bit vector width even on Zen4 because of
  historical frequency-throttling concerns inherited from Intel server
  parts. Zen4 doesn't have that issue; explicit opt-in to 512-bit can
  add ~5–15 %. Cheap to try, trivial to back out. **Planned follow-up
  experiment**: see "Pending follow-ups" below.

- **Targeted numerics-relaxation flags**:
  `-fno-math-errno -fno-trapping-math` are essentially free
  (~1–3 %, no observable behaviour change for SW4). `-fno-signed-zeros`
  is similar but marginally riskier. **Avoid `-ffast-math`** —
  it implies `-ffinite-math-only`, which tells the compiler it can
  assume no NaN/Inf inputs. That breaks SW4's `checkfornan` feature
  by definition, and the compiler may also fold away the scan
  itself. Modest gain not worth the hazard.

- **`-flto`** (link-time optimisation): cross-translation-unit
  inlining and constant propagation. Typical ~3–7 % on this kind of
  code, no runtime correctness risk. Increases link time noticeably;
  occasionally interacts awkwardly with debuggers.

- **Profile-guided optimisation (PGO)**: two-stage build (compile
  with `-fprofile-generate`, run a representative workload, recompile
  with `-fprofile-use`). Often ~5–15 % on stencil/loop-heavy code.
  Significantly more work — needs a representative training input and
  a build harness that does the two-stage flow.

- **Newer GCC** (14.x +): meaningful Zen4 autovec improvements over
  12.3 / 13.3, especially around `gather`/`scatter` and AVX-512 mask
  generation. Modest gain (~5 %), requires updating the toolchain
  module — coordinate with the HPC's module maintainers.

## Out of scope: runtime tuning

These don't belong in a build doc but the maintainer is the right
person to know about them so the full performance picture is clear:

- **Ranks per node**: the scaling tests pin 126 ranks/node for
  cross-HPC comparability (NeSI genoa has 336 cores/node, milan 128;
  RCH hcpu has 144–192). Production users will typically want to use
  all available cores per node. The "right" rank count is
  workload-specific (depends on grid shape, see
  `sw4-domain-shape-tuning.md`) — but 126/node is a comparability
  artefact, not an optimum.
- **NUMA / core binding**: under OpenMPI, an explicit
  `--map-by numa --bind-to core` (or equivalent
  `srun --cpu-bind=cores`) can be worth a few percent vs. defaults,
  especially when ranks/node doesn't divide evenly across sockets.

## Pending follow-ups

### Genoa: add `-mprefer-vector-width=512` and measure marginal effect

After the post-rebuild scaling campaign confirms `sw4-genoa` at
`-march=znver4` delivers as predicted, build a parallel binary with
the additional flag and measure the marginal effect on top of plain
znver4. **Don't replace** the existing `sw4-genoa` — install
alongside as `sw4-genoa-vw512` so the comparison is clean and the
production binary stays untouched until we have data.

Recipe (genoa only — flag is a no-op on milan/RCH which are Zen3):

```bash
# from the existing source tree, with the same NeSI/zen4 +
# GCC 12.3.0 + OpenMPI 4.1.5 + OpenBLAS 0.3.23 toolchain loaded
cmake -S . -B build-genoa-vw512 \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_FLAGS="-march=znver4 -mprefer-vector-width=512" \
  -DCMAKE_C_FLAGS="-march=znver4 -mprefer-vector-width=512" \
  -DCMAKE_Fortran_FLAGS="-march=znver4 -mprefer-vector-width=512"
cmake --build build-genoa-vw512 -j 4
cp build-genoa-vw512/bin/sw4 /nesi/project/nesi00213/tools/sw4-genoa-vw512
chgrp nesi00213 /nesi/project/nesi00213/tools/sw4-genoa-vw512
chmod g+rx       /nesi/project/nesi00213/tools/sw4-genoa-vw512
```

Then a focused micro-campaign — single-node weak-126 + strong-126
should be enough to measure the marginal effect on top of plain
znver4. Could be done by adding a temporary `mahuika-genoa-vw512` HPC
variant in `flow.cylc` pointing at the new binary.

**Magnitude expectation**: 3–8 % on top of plain znver4 — rule of
thumb for stencil codes, lower end likely because SW4 is partly
memory-bandwidth-bound. Real possibility it's at the noise floor and
not worth keeping the second binary; that's what the experiment will
tell us.

**Decision criteria**: if the micro-campaign shows ≥ 5 % on weak-126
above plain znver4, promote `sw4-genoa-vw512` to be the canonical
`sw4-genoa` (rename old to `sw4-genoa-noprefer`, point cylc and
optionally the canonical `sw4` symlink at the new one). If < 5 %,
keep `sw4-genoa` as-is and either retain `sw4-genoa-vw512` for
science or remove it.

### Genoa: run the milan binary on genoa to measure the AVX-2 vs AVX-512 gap

Hypothesis: the milan binary (znver3 / AVX-2) on Zen4 hardware is
~17–25 % slower than the genoa binary (znver4 / AVX-512) on the same
hardware. Confirming this empirically tells us what we'd give up if
we ever consolidated to a single "works on both partitions" binary,
and is the cleanest possible isolation of the AVX-2 vs AVX-512 step
(same hardware, same source tree, same compiler version — only `-march`
differs between the two binaries).

The cylc workflow has a dedicated HPC variant for this — added
2026-05-15 as a sibling of `mahuika-genoa`:

```bash
# wait until the main mahuika-genoa rebuild campaign has succeeded
# and we've confirmed sw4-genoa delivers as predicted, then:
cylc vip flow --set 'HPC="mahuika-genoa-avx2"'
```

The variant is identical to `mahuika-genoa` apart from `SW4_BIN`
pointing at `/nesi/project/nesi00213/tools/sw4-milan` instead of
`sw4-genoa`. Same partition, account, mem-per-cpu, ranks, grid sizes
— so results slot directly into `compare_scaling.py` alongside the
other campaigns and plot on the same axes.

**Predicted outcome**:

| Binary on genoa | Predicted weak-126 throughput (G cell-updates / core-hour) |
|---|---|
| `sw4-genoa` (znver4, AVX-512)             | ~3.5 (main rebuild result) |
| `sw4-milan` on genoa (znver3, AVX-2)      | **~2.9–3.0** |
| Pre-rebuild SSE2 (existing baseline)      | 2.45 (measured) |

If milan-on-genoa lands at ~2.9, the AVX-2 vs AVX-512 + tuning gap
is ~17–20 %. That's the cost of running a single shared binary across
both partitions.

**Decision criteria**: this experiment is purely informational —
we're not picking a winner, we're measuring a trade-off. Result
goes into `cross-hpc-throughput.md` as a "what does a shared binary
cost on genoa" data point. The actual `mahuika-genoa` production
path stays on `sw4-genoa` regardless.

**Cleanup**: keep the `mahuika-genoa-avx2` block in `flow.cylc` for
reproducibility — it's small, well-commented, and unlikely to be run
by accident (the default `HPC` value is `mahuika-milan`, and you'd
have to explicitly pass `--set 'HPC="mahuika-genoa-avx2"'` to hit it).

## Common pitfalls

- **Forgetting `-DUSE_PROJ=ON`**: the binary builds and runs `-h`
  fine, but at scaling-test time every task fails with
  `Fatal input error: ERROR: need to configure SW4 with proj=yes
  to use projections from the PROJ library`. The production `.in`
  files all use `proj=tmerc datum=WGS84 ...`, and the `fix-sfile-srf`
  branch refuses to fall back to internal projection code when PROJ
  support is missing. (Older SW4 silently fell back, which is what
  made the previous `baes`-built NeSI binary work without PROJ.)
- **`-h` is not a real smoke test**: it exits before SW4 reaches
  input-file parsing, so it can't catch the missing-PROJ trap above.
  Always smoke-test with an actual `.in` file (see
  `docs/sw4-build-smoke.in`).
- **Smoke-test domain too small for the supergrid**: SW4's default
  supergrid absorbing boundary is 3 km wide on each non-free-surface
  face. A smoke domain smaller than that fails with
  `Fatal input error: The supergrid taper width must be smaller
  than the domain`. The canonical `sw4-build-smoke.in` uses a 7 km
  cube, which has comfortable margin.
- **NVHPC OpenMPI on NeSI**: the default `OpenMPI` module name resolves
  to a CUDA-flavoured variant that wraps `nvc++`. Always load by full
  name and verify with `mpicxx --show`.
- **Forgetting `prefix/2025` on RCH**: without it, `module load
  GCC/13.3.0` fails with "exists but cannot be loaded as requested".
  RCH's EasyBuild module tree is gated behind the `prefix/` meta-module.
- **Missing rpath on RCH**: the binary builds successfully but fails at
  runtime with `libmpi.so.40: not found`, even with modules loaded.
  The fix is the `CMAKE_EXE_LINKER_FLAGS="-Wl,-rpath,..."` approach
  documented above.
- **Missing PROJ transitive deps on RCH**: PROJ pulls in SQLite
  (auto-loads when you load PROJ — `$EBROOTSQLITE` will be set)
  *and* LibTIFF (does not auto-load — load it explicitly:
  `LibTIFF/4.6.0-GCCcore-13.3.0`). Both need to be in the rpath. PROJ
  may pull in more deps in future versions — whack-a-mole `ldd ... |
  grep 'not found'` after the build.
- **Bash paste eating line continuations**: multi-line `cmake`
  commands using `\` at the end of each line can fail catastrophically
  if the terminal/clipboard combination strips the backslash-newline
  pair. The two lines join without a space, and bash concatenates
  quoted strings with adjacent tokens, producing garbled compiler
  flags like `-march=znver4-DUSE_PROJ=ON`. The fix is to use a
  single-line `cmake` invocation (and drop the quotes when the value
  has no spaces). Recipes in this doc are written that way.
- **NeSI requires `--account=nesi00213`**: as of mid-2026, NeSI's
  Slurm policy rejects `srun` / `sbatch` without an explicit
  `--account`. Easy fix; just include it. (The cylc workflow's
  job-runner config already does.)
- **`%zmm` instructions in the RCH binary**: the RCH binary at
  `-march=znver3` (which is Zen3, no AVX-512 in hardware) contains
  hundreds of `%zmm` (AVX-512) references in its text section
  because PROJ static helpers ISA-dispatch and pull in all variants.
  PROJ runtime-detects the CPU and picks the AVX-2 path on Zen3 —
  the AVX-512 code is unreachable, not a SIGILL hazard. Confirmed by
  successful smoke test on real Zen3 hardware. Not a bug.
- **Building `znver4` for milan or RCH**: SIGILL on the first AVX-512
  instruction in our own code. Always match the `-march` to the
  **lowest** capability partition the binary will run on.
- **`-march=native` from a login node**: bakes in the login node's
  arch, which may differ from the compute nodes (especially on RCH
  where login is Zen3 but compute may include other classes). Always
  use explicit `znver{3,4}` targets.
