"""Effective elastic stiffness by FFT homogenisation on a periodic RVE.

Small-strain Galerkin FFT scheme solved with conjugate gradients (Zeman et
al., J. Comput. Phys. 2010; de Geus et al., CMAME 2017). The unknown is the
periodic displacement-gradient field F = E + grad(u); the operator
G(sigma(sym F)) projects the stress onto gradient fields,

    G(T)_ij = (T_im xi_m) xi_j / |xi|^2      (Fourier space),

so equilibrium is G(sigma) = 0. Solid and void are linear isotropic; the
void gets a small stiffness ratio (default 1e-3) so the operator stays
definite. Six unit macroscopic strains give the effective stiffness C*
(Voigt, engineering shear); the compliance S* = C*^-1 gives directional
Young's moduli E_i = 1/S_ii. Results are relative to the solid modulus.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

VOIGT = [(0, 0), (1, 1), (2, 2), (1, 2), (0, 2), (0, 1)]


@dataclass
class StiffnessResult:
    relative_density: float
    youngs_relative: list[float]  # E_x, E_y, E_z divided by the solid modulus
    shear_relative: list[float]  # G_yz, G_xz, G_xy divided by the solid modulus
    poisson: list[float]  # nu_yz, nu_xz, nu_xy
    zener_anisotropy: float | None
    iterations: list[int]
    converged: bool
    device: str
    solid_poisson: float
    void_stiffness_ratio: float
    stiffness_voigt_relative: list[list[float]] = field(default_factory=list)
    method: str = "Galerkin FFT homogenisation (small strain, conjugate gradients), periodic RVE"

    def to_dict(self) -> dict:
        return asdict(self)


def effective_stiffness(
    solid: np.ndarray,
    *,
    solid_poisson: float = 0.3,
    void_ratio: float = 1e-3,
    tol: float = 1e-5,
    max_iter: int = 1500,
    device: str | None = None,
) -> StiffnessResult:
    import torch

    dev = torch.device(device) if device else torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dtype = torch.float64
    s = torch.from_numpy(np.asarray(solid, dtype=bool)).to(dev)
    shape = tuple(s.shape)
    E = torch.where(s, torch.tensor(1.0, dtype=dtype, device=dev), torch.tensor(void_ratio, dtype=dtype, device=dev))
    nu = solid_poisson
    lam = E * nu / ((1 + nu) * (1 - 2 * nu))
    mu = E / (2 * (1 + nu))

    # Wave vectors (voxel units); the Nyquist plane of even sizes is dropped.
    freqs = []
    for n in shape:
        k = torch.fft.fftfreq(n, d=1.0 / n).to(dev, dtype)
        if n % 2 == 0:
            k[n // 2] = 0.0
        freqs.append(2 * np.pi * k / n)
    xi = torch.stack(torch.meshgrid(*freqs, indexing="ij"))  # (3, ...)
    xi2 = (xi * xi).sum(0)
    inv_xi2 = torch.where(xi2 > 0, 1.0 / xi2, torch.zeros_like(xi2))

    def stress(F):  # F: (3,3,...) displacement gradient
        eps = 0.5 * (F + F.transpose(0, 1))
        tr = eps[0, 0] + eps[1, 1] + eps[2, 2]
        sig = 2 * mu * eps
        for i in range(3):
            sig[i, i] = sig[i, i] + lam * tr
        return sig

    def project(T):
        Th = torch.fft.fftn(T, dim=(2, 3, 4))
        v = torch.einsum("im...,m...->i...", Th, xi.to(Th.dtype))
        G = torch.einsum("i...,j...->ij...", v, xi.to(Th.dtype)) * inv_xi2
        return torch.fft.ifftn(G, dim=(2, 3, 4)).real

    def operator(F):
        return project(stress(F))

    Cstar = np.zeros((6, 6))
    iterations = []
    all_converged = True
    for col, (a, b) in enumerate(VOIGT):
        Fbar = torch.zeros((3, 3) + shape, dtype=dtype, device=dev)
        if a == b:
            Fbar[a, a] = 1.0
        else:  # engineering shear strain gamma = 1
            Fbar[a, b] = 0.5
            Fbar[b, a] = 0.5
        # CG on G(sigma(dF)) = -G(sigma(Fbar)), dF compatible (starts at 0).
        rhs = -operator(Fbar)
        x = torch.zeros_like(rhs)
        r = rhs.clone()
        p = r.clone()
        rr = float((r * r).sum())
        b_norm = rr**0.5
        it = 0
        ok = b_norm == 0.0
        while not ok and it < max_iter:
            Ap = operator(p)
            alpha = rr / float((p * Ap).sum())
            x = x + alpha * p
            r = r - alpha * Ap
            rr_new = float((r * r).sum())
            it += 1
            if rr_new**0.5 <= tol * b_norm:
                ok = True
                break
            p = r + (rr_new / rr) * p
            rr = rr_new
        iterations.append(it)
        all_converged &= ok
        sig = stress(Fbar + x)
        mean = sig.mean(dim=(2, 3, 4))
        for row, (i, j) in enumerate(VOIGT):
            Cstar[row, col] = float(mean[i, j])
    Cstar = 0.5 * (Cstar + Cstar.T)
    S = np.linalg.inv(Cstar)
    youngs = [float(1.0 / S[i, i]) for i in range(3)]
    shear = [float(1.0 / S[i, i]) for i in range(3, 6)]
    poisson = [float(-S[1, 2] / S[1, 1]), float(-S[0, 2] / S[0, 0]), float(-S[0, 1] / S[0, 0])]
    c11 = float(np.mean([Cstar[i, i] for i in range(3)]))
    c12 = float(np.mean([Cstar[0, 1], Cstar[0, 2], Cstar[1, 2]]))
    c44 = float(np.mean([Cstar[i, i] for i in range(3, 6)]))
    zener = 2 * c44 / (c11 - c12) if abs(c11 - c12) > 1e-12 else None
    return StiffnessResult(
        relative_density=float(np.asarray(solid).mean()),
        youngs_relative=youngs,
        shear_relative=shear,
        poisson=poisson,
        zener_anisotropy=zener,
        iterations=iterations,
        converged=bool(all_converged),
        device=str(dev),
        solid_poisson=solid_poisson,
        void_stiffness_ratio=void_ratio,
        stiffness_voigt_relative=[[float(v) for v in row] for row in Cstar],
    )
