"""Permeability by lattice-Boltzmann Stokes flow on a periodic RVE.

D3Q19 lattice, two-relaxation-time (TRT) collision with the "magic" parameter
Lambda = 3/16, for which half-way bounce-back puts no-slip walls exactly
half-way between fluid and solid nodes and the permeability does not depend
on the chosen viscosity (Ginzburg & d'Humieres 2003; Pan, Luo & Miller,
Comput. Fluids 2006). Flow is driven by a small body force g along one axis
with periodic boundaries; at steady state Darcy's law gives

    k = nu * <u> / g        (<u> = superficial velocity, lattice units)

and k [mm^2] = k_lattice * h^2. Only fluid nodes are stored; streaming with
bounce-back is a single precomputed gather per step, which runs on CUDA when
available.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

C = np.array(
    [
        [0, 0, 0],
        [1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1],
        [1, 1, 0], [-1, -1, 0], [1, -1, 0], [-1, 1, 0],
        [1, 0, 1], [-1, 0, -1], [1, 0, -1], [-1, 0, 1],
        [0, 1, 1], [0, -1, -1], [0, 1, -1], [0, -1, 1],
    ],
    dtype=np.int64,
)
W = np.array([1 / 3] + [1 / 18] * 6 + [1 / 36] * 12, dtype=np.float64)
OPP = np.array([0, 2, 1, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15, 18, 17])


@dataclass
class PermeabilityResult:
    axis: str
    permeability_mm2: float
    permeability_m2: float
    permeability_darcy: float
    porosity: float
    mean_pore_velocity_lu: float
    steps: int
    converged: bool
    device: str
    hydraulic_tortuosity: float | None = None
    method: str = "lattice Boltzmann D3Q19-TRT (Lambda=3/16), half-way bounce-back, body force, periodic"

    def to_dict(self) -> dict:
        return asdict(self)


def _device(requested: str | None):
    import torch

    if requested:
        return torch.device(requested)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def permeability(
    solid: np.ndarray,
    voxel_mm: float,
    axis: int = 2,
    *,
    tau_plus: float = 1.5,
    magic: float = 3.0 / 16.0,
    force: float = 1e-5,
    tol: float = 1e-4,
    max_steps: int = 30000,
    check_every: int = 250,
    max_seconds: float | None = None,
    device: str | None = None,
) -> PermeabilityResult:
    import time

    import torch

    started = time.perf_counter()
    dev = _device(device)
    solid = np.asarray(solid, dtype=bool)
    shape = solid.shape
    fluid = ~solid
    n_total = solid.size
    fluid_idx = np.flatnonzero(fluid)
    nf = fluid_idx.size
    names = ("x", "y", "z")
    if nf == 0:
        return PermeabilityResult(names[axis], 0.0, 0.0, 0.0, 0.0, 0.0, 0, True, str(dev))

    # Map grid -> compact fluid index (-1 for solid).
    compact = np.full(n_total, -1, dtype=np.int64)
    compact[fluid_idx] = np.arange(nf)
    coords = np.stack(np.unravel_index(fluid_idx, shape), axis=1)
    gather = np.empty((19, nf), dtype=np.int64)
    for i in range(19):
        src = (coords - C[i]) % np.asarray(shape)  # population i arrives from x - c_i
        src_flat = np.ravel_multi_index(src.T, shape)
        nbr = compact[src_flat]
        # From a solid node: bounce-back of the population that left x towards it.
        gather[i] = np.where(nbr >= 0, i * nf + nbr, OPP[i] * nf + np.arange(nf))
    gather_t = torch.from_numpy(gather.reshape(-1)).to(dev)
    del gather, compact

    dtype = torch.float32 if dev.type == "cuda" else torch.float64
    c = torch.tensor(C, dtype=dtype, device=dev)
    w = torch.tensor(W, dtype=dtype, device=dev)[:, None]
    opp = torch.tensor(OPP, device=dev)
    tau_minus = magic / (tau_plus - 0.5) + 0.5
    nu = (tau_plus - 0.5) / 3.0
    g = torch.zeros(3, dtype=dtype, device=dev)
    g[axis] = force
    # Guo forcing, antisymmetric (linear) part; the symmetric O(u) part is negligible in Stokes flow.
    source = (1.0 - 0.5 / tau_minus) * 3.0 * w * (c @ g)[:, None]

    f = w.expand(19, nf).clone()
    previous = None
    converged = False
    steps = 0
    u_mean = 0.0
    for steps in range(1, max_steps + 1):
        rho = f.sum(0)
        mom = c.T @ f
        u = mom / rho + 0.5 * g[:, None]
        cu = c @ u
        usq = (u * u).sum(0)
        feq = w * rho * (1.0 + 3.0 * cu + 4.5 * cu * cu - 1.5 * usq)
        f_opp = f[opp]
        feq_opp = feq[opp]
        fp, fm = 0.5 * (f + f_opp), 0.5 * (f - f_opp)
        ep, em = 0.5 * (feq + feq_opp), 0.5 * (feq - feq_opp)
        post = f - (fp - ep) / tau_plus - (fm - em) / tau_minus + source
        f = post.reshape(-1)[gather_t].reshape(19, nf)
        if steps % check_every == 0:
            u_mean = float(u[axis].sum()) / n_total  # superficial velocity
            if not np.isfinite(u_mean):
                break
            if previous is not None and abs(u_mean - previous) <= tol * abs(u_mean):
                converged = True
                break
            previous = u_mean
            if max_seconds is not None and time.perf_counter() - started > max_seconds:
                break  # reported as not converged
    rho = f.sum(0)
    u = (c.T @ f) / rho + 0.5 * g[:, None]
    u_mean = float(u[axis].sum()) / n_total
    speed = torch.sqrt((u * u).sum(0))
    hydraulic = float(speed.sum() / u[axis].abs().sum()) if float(u[axis].abs().sum()) > 0 else None
    k_lu = nu * u_mean / force
    k_mm2 = k_lu * voxel_mm**2
    phi = nf / n_total
    return PermeabilityResult(
        axis=names[axis],
        permeability_mm2=float(k_mm2),
        permeability_m2=float(k_mm2 * 1e-6),
        permeability_darcy=float(k_mm2 * 1e-6 / 9.869233e-13),
        porosity=float(phi),
        mean_pore_velocity_lu=float(u_mean / phi),
        steps=steps,
        converged=converged,
        device=str(dev),
        hydraulic_tortuosity=hydraulic,
    )
