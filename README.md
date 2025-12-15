# Scale testing repository

This repository builds a scale testing workflow to test new HPC infrastructure. This workflow tests the scaling of the cluster for EMOD3D in the following ways

1. Strong scaling. Here we fix a domain and duration and increase the number of cores given to the problem. Amdahl's law states our speedup follows the functional form $\frac{1}{s + p/N}$, where $s$ is the serial portion of execution, and $p$ the parallel portion of execution. This is an upper bound assuming perfect parallelisation, which never happens. Hence, we can measure deviation from this ideal scaling to get a sense of diminishing returns.
2. Weak scaling. Here we grow both the problem size and the number of cores proportionally. The idea is that, assuming perfect weak scaling, the problem should complete in the same amount of time as we scale both cores and problem size. Of course, this never happens because of MPI overhead, CPU cache misses and context switching, etc.

Strong and weak scaling are orthogonal to each other so we test both.

## The Sample Event

The chosen sample event is [the Mw=6.5 Seddon earthquake](https://www.geonet.org.nz/earthquake/2013p543824). Any event would suffice for this test because the serial portion attributed to the SRF is trivial compared to the overall simulation time.

## Weak Scaling Tests

For the weak scaling test we run 20 simulations with increasing domain size. From experience, wall-clock time scales perfectly linearly with the number of timesteps (i.e. runtime per 100 timesteps is roughly constant for a given simulation), hence we fix a small number of timesteps to make these tests cheap to run. Fixing `nt=1000` and varying `nx`, `ny`, `nz`, and core count to achieve a constant 1.5GB of simulation memory per core. Simulation memory is estimated using the formula $4(31\mathrm{nx}\mathrm{ny}\mathrm{nz} + 56  max(\mathrm{nx}\mathrm{ny}, \mathrm{ny}\mathrm{nz}, \mathrm{nx}\mathrm{nz}) + 6(\mathrm{nx} + \mathrm{nz}))$.

| Cores | nx   | ny   | nz  |
| ----- | ---- | ---- | --- |
| 16    | 621  | 621  | 500 |
| 32    | 878  | 878  | 500 |
| 64    | 1242 | 1242 | 500 |
| 128   | 1757 | 1757 | 500 |
| 256   | 2484 | 2484 | 500 |
| 512   | 3513 | 3513 | 500 |
| 750   | 4252 | 4252 | 500 |
| 1000  | 4910 | 4910 | 500 |
| 1250  | 5489 | 5489 | 500 |
| 1500  | 6013 | 6013 | 500 |

## Strong Scaling Tests

For the strong scaling test, we pick the median simulation size `nx = 2484`, `ny = 2484`, `nz = 500` and scale the number of cores from 64 up to 1500 in the increments 64, 128, 256, 512, 750, 1000, 1250, 1500.
