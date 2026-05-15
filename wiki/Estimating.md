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

Testing shows that SW4's memory footprint per rank, $M_r$, can be modelled in MiB as:

$M_r \approx 270 + n_r \times 5.1 \times 10 ^{-4}$ 

where $n_r$ is the number of cells per rank.

## Grid shape effect

The provided throughputs were drived from a **roughly cubic per-rank brick**
produced by a domain grid like 1000 × 1000 × 500 because SW4's MPI decomposition preserves the smallest global dimension whole and splits the other two across ranks.

If the global grid is **slab-shaped** with one dimension much smaller than
the other two, the wide-SIMD capacity of Cascade, RCH, and Milan will be under-utilized, reducing throughputs by up to ~30%.

For production-tuning beyond this rough cut — including the
closed-form back-of-envelope optimum for picking grid dimensions —
see [`docs/sw4-domain-shape-tuning.md`](https://github.com/ucgmsim/scale_test/blob/main/docs/sw4-domain-shape-tuning.md)
in the main repo.


