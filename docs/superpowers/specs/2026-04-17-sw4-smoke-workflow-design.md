# SW4 Cylc Scale-Test Smoke Workflow — Design

**Date:** 2026-04-17
**Branch:** `mini-sw4-scale-tests`
**Status:** Approved for implementation

## 1. Motivation and Goal

The `scale_test` repo runs SW4 weak- and strong-scaling studies on NeSI Mahuika via Cylc. The real tests request 64–1500 cores, which wait a long time in the Slurm queue — slow feedback on whether the Cylc workflow itself is correct.

**Goal:** produce a complete, NeSI-Mahuika-ready `flow.cylc` (plus matching CSVs and `.in` files) that exercises both weak and strong SW4 scaling end-to-end, using grid sizes and core counts small enough that jobs are picked up from the Slurm queue immediately and finish in seconds. Successful smoke runs populate the Cylc sqlite `db` exactly as the real tests will, so workflow mechanics are validated before scaling up.

**Non-goals:** measuring real scaling behavior, tuning simulation physics, or preserving legacy paths. Runtime numbers from the smoke runs are not meaningful.

## 2. Constraints

- **Simulation parameters that may change:** only `nx`, `ny`, `nz` in the `.in` files. Everything else (grid spacing `h`, source location, timesteps, material properties, etc.) stays identical to the current files.
- **Grid spacing `h=100` m, source at `(x, y, z) = (6250, 6250, 5000)` m.** For the source to lie inside the domain, `(nx-1)*h ≥ 6250` ⇒ `nx ≥ 64`; same for `ny`; and `(nz-1)*h ≥ 5000` ⇒ `nz ≥ 51`.
- **Deploy location:** `/nesi/project/nesi00213/sw4_scale_tests/scale_test/` (git remote name is `scale_test`).
- **Platform:** NeSI Mahuika (Slurm), `--account=nesi00213`, SW4 binary at `/nesi/project/nesi00213/tools/sw4`.
- **`CYLC_CONF_PATH`** points at `cylc/` so Cylc finds the workflow at `cylc/cylc-src/flow/flow.cylc` directly inside the cloned repo.

## 3. Approach

**Hybrid restructure.** Keep `flow.cylc`'s existing scaffolding (parameterized weak-test and strong-test families driven by the two CSVs, one task per core count) and overlay the NeSI-specific configuration from `small_strong_flow.cylc` (platform, account, SW4 path, Mahuika module list). Remove dead code carried over from a different use case. Delete `small_strong_flow.cylc` once `flow.cylc` subsumes it.

## 4. File-by-file changes

### 4.1 `cylc/cylc-src/flow/flow.cylc`

New structure (Jinja2 + Cylc):

```
[meta]
    title        — "SW4 Scale Test (smoke)"
    description  — purpose, deploy location, run command, Cylc-only dependency
                   (Apptainer reference removed; it is not used on Mahuika)

{% set weak_test   = load_data('weak_scaling.csv') %}
{% set strong_test = load_data('strong_scaling.csv') %}

[task parameters]
    weak_test   = <comma-joined cores from weak_scaling.csv>
    strong_test = <comma-joined cores from strong_scaling.csv>

[scheduling]
    [[graph]]
        R1 = "sw4_weak_scaling<weak_test>
              sw4_strong_scaling<strong_test>"
    [[queues]]
        [[[all]]] limit=5 ; members=root

[runtime]
    [[root]]
        platform = mahuika
        [[[directives]]]
            --account = nesi00213

    [[SW4]]                                     # NEW shared family
        pre-script = """
            module purge
            module load <full NeSI Mahuika module list copied verbatim
                         from small_strong_flow.cylc — 42 modules>
        """
        [[[directives]]]
            --mem-per-cpu = 512M
        [[[environment]]]
            SW4       = "/nesi/project/nesi00213/tools/sw4"
            INPUT_DIR = "${CYLC_WORKFLOW_RUN_DIR}/events"

    # Jinja2 for-loop generates one family per core count
    {% for simulation in weak_test %}
    [[SW4_WEAK<weak_test={{simulation['cores']}}>]]
        inherit = SW4
        [[[directives]]]
            --ntasks = {{simulation['cores']}}
            --nodes  = {{simulation['nodes']}}
            --time   = 00:15:00
        [[[environment]]]
            NX = "{{simulation['nx']}}"
            NY = "{{simulation['ny']}}"
            NZ = "{{simulation['nz']}}"
    {% endfor %}

    {% for simulation in strong_test %}
    [[SW4_STRONG<strong_test={{simulation['cores']}}>]]
        inherit = SW4
        [[[directives]]]
            --ntasks = {{simulation['cores']}}
            --nodes  = {{simulation['nodes']}}
            --time   = 00:15:00
    {% endfor %}

    [[sw4_weak_scaling<weak_test>]]
        inherit = SW4_WEAK<weak_test>
        script  = """
            sed -e "s;NX;${NX};g" \
                -e "s;NY;${NY};g" \
                -e "s;NZ;${NZ};g" \
                ${INPUT_DIR}/input_weak.in > ${PWD}/input.in
            mpirun $SW4 ${PWD}/input.in
        """

    [[sw4_strong_scaling<strong_test>]]
        inherit = SW4_STRONG<strong_test>
        script  = """
            mpirun $SW4 ${INPUT_DIR}/input_strong.in
        """
```

**Fixes vs. the current `flow.cylc`:**

| Item                                      | Before                                              | After                                  |
|-------------------------------------------|-----------------------------------------------------|----------------------------------------|
| `platform`                                | `barcelona`                                         | `mahuika`                              |
| Root directives                           | `--qos=gp_resa`, `--account=cant1`                  | `--account=nesi00213`                  |
| SW4 binary                                | `"SET_SW4_HERE"` (duplicated in each family)        | `"/nesi/project/nesi00213/tools/sw4"` (centralised in `[[SW4]]`) |
| Module loads                              | none                                                | full Mahuika list in `[[SW4]]` pre-script |
| Mem request                               | none                                                | `--mem-per-cpu=512M`                   |
| Walltime                                  | `01:00:00`                                          | `00:15:00`                             |
| Weak-scaling mpirun                       | `mpirun $SW4_WEAK …` (undefined)                    | `mpirun $SW4 …`                        |
| Weak-scaling input path                   | `$CYLC_WORKFLOW_SHARE_DIR/input_weak.in`            | `${INPUT_DIR}/input_weak.in`           |
| Strong-scaling input path                 | `$CYLC_WORKFLOW_SHARE_DIR/input_strong.in`          | `${INPUT_DIR}/input_strong.in`         |
| `CONTAINER = …/runner.sif`                | present (Apptainer)                                 | removed                                |
| `[[SW4]]` empty stub                      | present                                             | replaced with populated shared family  |
| `[[copy]]` task (copies events → share)   | present but not in graph                            | removed                                |
| `[[VM<weak_test=…>]]` family              | present, unused in graph                            | removed                                |

`INPUT_DIR` resolves to `$CYLC_WORKFLOW_RUN_DIR/events/`, which is populated automatically by `cylc install` (since `events/` lives alongside `flow.cylc` under `cylc-src/flow/`). No copy task is required.

### 4.2 `cylc/cylc-src/flow/strong_scaling.csv`

Overwrite with smoke values (columns unchanged):

```
nodes,cores
1,1
1,2
1,4
1,8
```

### 4.3 `cylc/cylc-src/flow/weak_scaling.csv`

Overwrite with smoke values. `nx` and `ny` scale as √cores so cells-per-core stays ≈ 600 k; `nz` fixed at 60; all on one node.

```
nodes,cores,nx,ny,nz
1,1,100,100,60
1,2,141,141,60
1,4,200,200,60
1,8,283,283,60
```

Cells / memory check using `simulation_memory(nx,ny,nz) = 4·(31·nx·ny·nz + 56·max(edge areas) + 6·(nx+nz))` from `scripts/simulation_parameters.py`:

| cores | cells     | cells/core | total mem |
|-------|-----------|------------|-----------|
| 1     |   600 000 |  600 000   |  ≈ 77 MB  |
| 2     | 1 193 460 |  596 730   | ≈ 152 MB  |
| 4     | 2 400 000 |  600 000   | ≈ 307 MB  |
| 8     | 4 805 340 |  600 668   | ≈ 614 MB  |

All rows satisfy `nx, ny ≥ 64` and `nz ≥ 51` (source-containment requirement with `h=100`). `--mem-per-cpu=512M` gives comfortable headroom at every row.

### 4.4 `cylc/cylc-src/flow/events/input_strong.in`

Only the `grid` line's `nx`, `ny`, `nz` change:

```
grid nx=100 ny=100 nz=60 h=100.0 lon=172.0 lat=-43.0 az=0.1 proj=tmerc datum=WGS84 lat_p=-43.0 lon_p=173 scale=0.9996
```

All other lines (`block`, `time steps`, `attenuation`, `prefilter`, `source`) stay exactly as they are.

### 4.5 `cylc/cylc-src/flow/events/input_weak.in`

**No change.** The file already has `nx=NX ny=NY nz=NZ` placeholders that the weak-scaling task script substitutes via `sed` from the per-row CSV values.

### 4.6 `cylc/global.cylc`

One-character fix — the symlink target currently has a plural `scale_tests` that does not match the repo's cloned name:

```
# BEFORE
run = /nesi/project/nesi00213/sw4_scale_tests/scale_tests/cylc
# AFTER
run = /nesi/project/nesi00213/sw4_scale_tests/scale_test/cylc
```

Everything else in `global.cylc` stays as is.

### 4.7 `cylc/cylc-src/flow/small_strong_flow.cylc`

**Delete.** `flow.cylc` now carries the correct Mahuika configuration and covers the smoke-test role that `small_strong_flow.cylc` was standing in for.

## 5. Unchanged files (for clarity)

- `cylc/cylc-src/flow/lib/python/load_data.py` — unchanged.
- `scripts/simulation_parameters.py` and `scripts/weak_scaling_parameters.csv` — unchanged; used only to generate full-scale CSV values, not needed for the smoke run.
- `slurm/*.sl` — unchanged; legacy standalone Slurm scripts, out of scope.
- `README.md` — unchanged for now; describes the full-scale tests, not this smoke variant. (The smoke branch is a temporary validation step.)

## 6. Verification plan

1. **Local review.** Visual diff of `flow.cylc`, the two CSVs, `input_strong.in`, and `global.cylc`.
2. **On Mahuika:** `cylc validate flow` from the source dir — catches Jinja and Cylc syntax errors without submitting.
3. `cylc vip flow` to install and run. Monitor with `cylc tui`.
4. **Expected:** all 8 tasks (4 weak + 4 strong) queue immediately, run in seconds, exit 0.
5. **Success criterion:** the Cylc sqlite db at `<run-dir>/log/db` contains finish timings for all 8 tasks.
6. **On failure:** inspect `<run-dir>/log/job/<task>/NN/job.err` and `job.out` for the failing task.

## 7. Out of scope

- Tuning real weak/strong scaling runs (will be done after the smoke workflow passes).
- Containerising (Apptainer) — removed entirely; not used on Mahuika.
- Updating `README.md` — the smoke branch is a validation step; full-scale docs stay unchanged.
- Any changes to `.in` files beyond `nx`/`ny`/`nz` on the `grid` line.
