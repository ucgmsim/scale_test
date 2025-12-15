#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.14"
# dependencies = ["numpy", "pandas", "scipy"]
# ///

import pandas as pd
from collections.abc import Iterable


GB = 1e09


def simulation_memory(nx: int, ny: int, nz: int) -> int:
    edge = max(nx * ny, ny * nz, nx * nz)
    return 4 * (31 * nx * ny * nz + 56 * edge + 6 * (nx + nz))


def simulation_parameters(
    cores: int, memory_per_core: int, nz: int, max_extent: int = 10000
) -> tuple[int, int, int]:
    memory = cores * memory_per_core
    x_lb = 1
    x_ub = max_extent
    while x_ub > x_lb + 1:
        x = (x_ub + x_lb) // 2
        cur_memory = simulation_memory(x, x, nz)
        if cur_memory == memory:
            return x, x, nz
        elif cur_memory > memory:
            x_ub = x
        else:
            x_lb = x
    return min(
        [(x_lb, x_lb, nz), (x_ub, x_ub, nz)],
        key=lambda x: abs(simulation_memory(*x) - memory),
    )


def weak_scaling_parameters(
    cores: Iterable[int], memory_per_core: int, nz: int = 300
) -> pd.DataFrame:
    results = []
    for core_count in cores:
        results.append(simulation_parameters(core_count, memory_per_core, nz))
    return pd.DataFrame(results, columns=["nx", "ny", "nz"])
