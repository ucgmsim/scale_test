# Building SW4 on NeSI and RCH

Operational recipe for rebuilding the SW4 binaries on NeSI Mahuika
(both genoa and milan partitions) and on RCH (hcpu partition). Wrote
2026-05-01 after the post-rebuild campaign, capturing the actual
steps that worked rather than the prescriptive "should be one flag"
of the original recommendation docs (which are now retired).

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
module load GCC/12.3.0 CMake OpenMPI/4.1.5-GCC-12.3.0 OpenBLAS/0.3.23-GCC-12.3.0
module list

# CRITICAL: confirm OpenMPI wraps GCC, not NVHPC
mpicxx --show   # must print g++ ...
mpif90 --show   # must print gfortran ...
```

The default `OpenMPI` module on NeSI resolves to a CUDA + NVHPC variant
that wraps `nvc++` instead of `g++`. Always load the full versioned
name `OpenMPI/4.1.5-GCC-12.3.0` to avoid this trap. If `mpicxx --show`
reports `nvc++`, swap to the correct OpenMPI variant before building.

### Configure and build the genoa binary

```bash
cd <source-dir>

cmake -S . -B build-genoa \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_FLAGS="-march=znver4" \
  -DCMAKE_C_FLAGS="-march=znver4" \
  -DCMAKE_Fortran_FLAGS="-march=znver4"

cmake --build build-genoa -j 4
```

`-j 4` is polite for a shared login node. For a faster build use
`srun --partition=genoa --time=00:30:00 --cpus-per-task=8 --pty bash`
and use `-j 8` on the compute node.

### Switch and configure the milan binary

```bash
module swap NeSI/zen4 NeSI/zen3   # all toolchain modules survive the swap

cmake -S . -B build-milan \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_FLAGS="-march=znver3" \
  -DCMAKE_C_FLAGS="-march=znver3" \
  -DCMAKE_Fortran_FLAGS="-march=znver3"

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

```bash
srun --partition=genoa --time=00:05:00 --ntasks=1 \
  <source-dir>/build-genoa/bin/sw4 -h

srun --partition=milan --time=00:05:00 --ntasks=1 \
  <source-dir>/build-milan/bin/sw4 -h
```

Expected: an SW4 banner + "ERROR OPENING INPUT FILE: -h". The error
is benign — SW4 doesn't take `-h`, treats it as a filename, fails to
open, exits cleanly. Critical: **no SIGILL, no `Illegal instruction`,
no library-load errors**.

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
outside cylc, they need to `module load` the same toolchain first or
they'll hit `libmpi.so.40: not found`.

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
            OpenMPI/5.0.3-GCC-13.3.0 OpenBLAS/0.3.27-GCC-13.3.0
module list

# verify wrappers
mpicxx --show   # must print g++ ...
mpif90 --show   # must print gfortran ...
```

The 13.3 toolchain matches what RCH's existing SW4 binary was built
against. Picking the same toolchain keeps the pre/post comparison
clean (only `-march` differs). NeSI uses 12.3 because the existing
NeSI binary was built with 12.3 — same logic, different version per
HPC convention.

### Configure with rpath flags

```bash
cd <source-dir>

# the three directories the binary needs at runtime
RPATH="$EBROOTOPENMPI/lib:$EBROOTOPENBLAS/lib:$EBROOTGCCCORE/lib64"

cmake -S . -B build-rch \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_FLAGS="-march=znver3" \
  -DCMAKE_C_FLAGS="-march=znver3" \
  -DCMAKE_Fortran_FLAGS="-march=znver3" \
  -DCMAKE_EXE_LINKER_FLAGS="-Wl,-rpath,$RPATH"

cmake --build build-rch -j 1
```

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

### The three rpath directories

The binary needs all three at runtime:
- `$EBROOTOPENMPI/lib` — `libmpi.so.40`
- `$EBROOTOPENBLAS/lib` — `libopenblas.so.0`
- `$EBROOTGCCCORE/lib64` — `libstdc++.so.6` (for `GLIBCXX_3.4.32`,
  required because GCC 13 emits newer C++ ABI symbols than the system
  `libstdc++` from GCC 11) and `libgfortran.so.5`.

If any of those paths are missing from the rpath, the binary will
fail at runtime with `libX.so.N: cannot open shared object file`.

### Verify

```bash
# rpath baked in
readelf -d build-rch/bin/sw4 | grep -E 'RPATH|RUNPATH'
# should show all three directories

# all libraries resolve
ldd build-rch/bin/sw4 | grep -E 'mpi|blas|stdc|gfortran|not found'
# should show all four resolved, no "not found"

# AVX-2 sanity
objdump -d build-rch/bin/sw4 | grep -c '%zmm'   # MUST be 0
objdump -d build-rch/bin/sw4 | grep -c '%ymm'   # should be > 0
```

### Smoke test

The binary should now be self-contained — no module loads needed at
runtime:

```bash
srun --account=rch-quakecore --partition=short --time=00:05:00 \
     --ntasks=1 --constraint=hcpu --exclude=n03 \
     <source-dir>/build-rch/bin/sw4 -h
```

(`--exclude=n03`: that node has a known cylc incompatibility; not
strictly required for a one-shot srun, but harmless for symmetry with
the cylc workflow.)

Same expected output as NeSI: SW4 banner + "ERROR OPENING INPUT FILE:
-h", no library-load errors.

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
  add ~5–15 %. Cheap to try, trivial to back out.

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

## Common pitfalls

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
- **Building `znver4` for milan or RCH**: SIGILL on the first AVX-512
  instruction. Always match the `-march` to the **lowest** capability
  partition the binary will run on.
- **`-march=native` from a login node**: bakes in the login node's
  arch, which may differ from the compute nodes (especially on RCH
  where login is Zen3 but compute may include other classes). Always
  use explicit `znver{3,4}` targets.
