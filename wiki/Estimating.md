# Estimating wall-time and core-hours for SW4 simulations

The size of an SW4 simulation is given by the total number of cell-updates, $N$

The number of cell updates, $N$, in an SW4 simulation is given by 

$N = n_x \times n_y \times n_z \times n_t$ where $n_x$, $n_y$, $n_z$ are the 
number of grid cells in the $x$, $y$, and $z$ dimensions, respectively, and $n_t$
is the total number of time steps in the simulation.


The compute, $C$, required for a simulation of $N$ cell-updates is given by
$$ C = \frac{N}{(T \times 10^9)} $$

where $C$ is in core-hours, and $T$ is throughput in Giga cell-updates / core-hour.

Assuming ideal scaling, the required wall-clock time, $t_w$, in hours, is given by 
$$ t_w = \frac{C}{N_c} $$

where $N_c$ is the rank count (or number of cores).

Measured throughputs, scaling efficiencies, and NaN check overheads for several HPCs are shown in the following table:

| HPC                | Throughput, $T$ <br> (Giga cell-updates / core-hour) | Scaling <br> efficiency  (%) | NaN check <br> overhead (%) |
|---                 |---                                                   |---                           | ---                         |
| Cascade            | 3.5                                                  | 98                           | 2                           |
| Mahuika Genoa      | 2.4                                                  | 97                           | 2                           |              
| Mahuika Milan      | 1.5                                                  | 84                           | 5                           |
| RCH                | 1.2                                                  | 87                           | 5                           |

These throughputs were derived using 126 ranks/node as this configuration was possible on all tested HPCs, but some support more ranks/node. They are also not inclusive of the optional NaN check overhead. Furthermore, they are for a roughly cube-shaped simulation domain, so if one domain dimension is much smaller than the others, throughput is reduced by ~30 % on Cascade, Genoa, and RCH (see [Grid shape effect](#grid-shape-effect) for details). 


## Memory

Testing shows that SW4's per-rank memory footprint can be modelled as:

```
memory_per_task_MiB ≈ 270 + 0.000510 × cells_per_rank
                    ≈ 270 + 0.51 × (cells_per_rank / 1000)
```

## Grid shape effect

The per-HPC numbers above assume a **roughly cubic per-rank brick**.
A grid like 1000 × 1000 × 500 — large horizontal extent, moderate
depth — produces that. SW4's MPI decomposition preserves the
smallest global dim whole and splits the other two across ranks,
so the per-rank brick ends up shape-matched to the global one.

If your global grid is **slab-shaped** (one dim much smaller than
the others, e.g. 128 × 1984 × 1984 for a shallow shelf or a very
thin sediment basin), the per-rank brick has a shorter inner loop
and wide-SIMD machinery under-uses its lanes. Per-core throughput
is lower than the table by:

| Binary's SIMD width | Shape effect on slab grids (vs. cubic numbers) |
|---                  |---                                             |
| AVX-512 (cascade, NeSI/RCH post-rebuild)             | **~30 % lower** (up to ~40 % for very slab-y shapes) |
| AVX-2 (NeSI/RCH post-rebuild w/o AVX-512)            | ~15–25 % lower |
| SSE2 (NeSI/RCH pre-rebuild)                          | < 10 % (within noise) |

Quick rule for whether your grid is "slab-shaped" for this purpose:
if `nz / max(nx, ny) ≲ 0.1` (or any other axis is similarly small),
apply the slab derating.

For production-tuning beyond this rough cut — including the
closed-form back-of-envelope optimum for picking grid dimensions —
see [`docs/sw4-domain-shape-tuning.md`](https://github.com/ucgmsim/scale_test/blob/main/docs/sw4-domain-shape-tuning.md)
in the main repo.


