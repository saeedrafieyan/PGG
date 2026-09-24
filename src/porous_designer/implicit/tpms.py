"""Triply periodic minimal surfaces with analytic gradients.

Each surface is given by its standard nodal (trigonometric) approximation
``f(x, y, z) = 0`` in angle coordinates ``x = 2*pi*u`` where ``u`` is the
position in unit-cell units (period 1). The functions return ``f`` and its
gradient with respect to ``(x, y, z)``.

The gradient turns the dimensionless level-set value into an approximate
distance in millimetres, ``d ~ f / |grad_X f|``, which is what makes wall
thickness a physical quantity:

* sheet variant: solid where ``|f| / |grad f| <= t / 2`` (sheet of thickness t),
* network variant: solid where ``f / |grad f| <= c`` (one side, offset c).

References for the nodal forms: Schoen (1970); Wohlgemuth et al.,
Macromolecules 34 (2001) 6083; Al-Ketan & Abu Al-Rub, Adv. Eng. Mater. 21
(2019) 1900524.
"""

from __future__ import annotations

from typing import Callable

from porous_designer.domain.enums import StructureFamily


def gyroid(ops, x, y, z):
    sx, cx, sy, cy, sz, cz = ops.sin(x), ops.cos(x), ops.sin(y), ops.cos(y), ops.sin(z), ops.cos(z)
    f = sx * cy + sy * cz + sz * cx
    gx = cx * cy - sz * sx
    gy = -sx * sy + cy * cz
    gz = -sy * sz + cz * cx
    return f, gx, gy, gz


def primitive(ops, x, y, z):
    f = ops.cos(x) + ops.cos(y) + ops.cos(z)
    return f, -ops.sin(x), -ops.sin(y), -ops.sin(z)


def diamond(ops, x, y, z):
    sx, cx, sy, cy, sz, cz = ops.sin(x), ops.cos(x), ops.sin(y), ops.cos(y), ops.sin(z), ops.cos(z)
    f = sx * sy * sz + sx * cy * cz + cx * sy * cz + cx * cy * sz
    gx = cx * sy * sz + cx * cy * cz - sx * sy * cz - sx * cy * sz
    gy = sx * cy * sz - sx * sy * cz + cx * cy * cz - cx * sy * sz
    gz = sx * sy * cz - sx * cy * sz - cx * sy * sz + cx * cy * cz
    return f, gx, gy, gz


def iwp(ops, x, y, z):
    sx, cx, sy, cy, sz, cz = ops.sin(x), ops.cos(x), ops.sin(y), ops.cos(y), ops.sin(z), ops.cos(z)
    f = 2.0 * (cx * cy + cy * cz + cz * cx) - (ops.cos(2 * x) + ops.cos(2 * y) + ops.cos(2 * z))
    gx = -2.0 * sx * (cy + cz) + 2.0 * ops.sin(2 * x)
    gy = -2.0 * sy * (cx + cz) + 2.0 * ops.sin(2 * y)
    gz = -2.0 * sz * (cx + cy) + 2.0 * ops.sin(2 * z)
    return f, gx, gy, gz


def neovius(ops, x, y, z):
    sx, cx, sy, cy, sz, cz = ops.sin(x), ops.cos(x), ops.sin(y), ops.cos(y), ops.sin(z), ops.cos(z)
    f = 3.0 * (cx + cy + cz) + 4.0 * cx * cy * cz
    gx = -3.0 * sx - 4.0 * sx * cy * cz
    gy = -3.0 * sy - 4.0 * cx * sy * cz
    gz = -3.0 * sz - 4.0 * cx * cy * sz
    return f, gx, gy, gz


def fischer_koch_s(ops, x, y, z):
    sx, cx, sy, cy, sz, cz = ops.sin(x), ops.cos(x), ops.sin(y), ops.cos(y), ops.sin(z), ops.cos(z)
    s2x, c2x, s2y, c2y, s2z, c2z = ops.sin(2 * x), ops.cos(2 * x), ops.sin(2 * y), ops.cos(2 * y), ops.sin(2 * z), ops.cos(2 * z)
    f = c2x * sy * cz + cx * c2y * sz + sx * cy * c2z
    gx = -2.0 * s2x * sy * cz - sx * c2y * sz + cx * cy * c2z
    gy = c2x * cy * cz - 2.0 * cx * s2y * sz - sx * sy * c2z
    gz = -c2x * sy * sz + cx * c2y * cz - 2.0 * sx * cy * s2z
    return f, gx, gy, gz


def lidinoid(ops, x, y, z):
    sx, cx, sy, cy, sz, cz = ops.sin(x), ops.cos(x), ops.sin(y), ops.cos(y), ops.sin(z), ops.cos(z)
    s2x, c2x, s2y, c2y, s2z, c2z = ops.sin(2 * x), ops.cos(2 * x), ops.sin(2 * y), ops.cos(2 * y), ops.sin(2 * z), ops.cos(2 * z)
    f = 0.5 * (s2x * cy * sz + s2y * cz * sx + s2z * cx * sy) - 0.5 * (c2x * c2y + c2y * c2z + c2z * c2x) + 0.15
    gx = 0.5 * (2.0 * c2x * cy * sz + cx * s2y * cz - sx * sy * s2z) + s2x * (c2y + c2z)
    gy = 0.5 * (-s2x * sy * sz + 2.0 * c2y * cz * sx + s2z * cx * cy) + s2y * (c2x + c2z)
    gz = 0.5 * (s2x * cy * cz - s2y * sz * sx + 2.0 * c2z * cx * sy) + s2z * (c2x + c2y)
    return f, gx, gy, gz


SURFACES: dict[StructureFamily, Callable] = {
    StructureFamily.GYROID: gyroid,
    StructureFamily.PRIMITIVE: primitive,
    StructureFamily.DIAMOND: diamond,
    StructureFamily.IWP: iwp,
    StructureFamily.NEOVIUS: neovius,
    StructureFamily.FISCHER_KOCH_S: fischer_koch_s,
    StructureFamily.LIDINOID: lidinoid,
}

EQUATIONS: dict[StructureFamily, str] = {
    StructureFamily.GYROID: "sin x cos y + sin y cos z + sin z cos x",
    StructureFamily.PRIMITIVE: "cos x + cos y + cos z",
    StructureFamily.DIAMOND: "sin x sin y sin z + sin x cos y cos z + cos x sin y cos z + cos x cos y sin z",
    StructureFamily.IWP: "2(cos x cos y + cos y cos z + cos z cos x) - (cos 2x + cos 2y + cos 2z)",
    StructureFamily.NEOVIUS: "3(cos x + cos y + cos z) + 4 cos x cos y cos z",
    StructureFamily.FISCHER_KOCH_S: "cos 2x sin y cos z + cos x cos 2y sin z + sin x cos y cos 2z",
    StructureFamily.LIDINOID: "0.5(sin 2x cos y sin z + sin 2y cos z sin x + sin 2z cos x sin y) - 0.5(cos 2x cos 2y + cos 2y cos 2z + cos 2z cos 2x) + 0.15",
}
