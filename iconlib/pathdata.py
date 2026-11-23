"""Affine transforms and exact path rewriting, used by the import cleaner to bake transforms into shapes.

A path is parsed into absolute segments M, L, C, Q, Z (arcs become cubic curves, which any affine
transform maps exactly), the matrix is applied to every point, and the result is written back as `d`.
Matrices are SVG-style 6-tuples (a, b, c, d, e, f):  x' = a*x + c*y + e,  y' = b*x + d*y + f.
"""
from __future__ import annotations

import math
import re

from .svgrender import _ARGS, _NUM, _Scanner

Matrix = tuple[float, float, float, float, float, float]
Segment = tuple[str, tuple[float, ...]]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


# ----------------------------------------------------------------------------- matrices
def mul(m: Matrix, n: Matrix) -> Matrix:
    """The transform that applies n first, then m (parent @ child)."""
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2, a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)


def is_identity(m: Matrix, eps: float = 1e-9) -> bool:
    return all(abs(x - y) < eps for x, y in zip(m, IDENTITY))


def scale_factor(m: Matrix) -> float:
    """Area scale as a length factor: what a stroke width is multiplied by."""
    return math.sqrt(abs(m[0] * m[3] - m[1] * m[2]))


def is_uniform(m: Matrix, tol: float = 0.01) -> bool:
    """False for non-uniform scaling (rotation, mirroring and uniform scaling are fine)."""
    sx, sy = math.hypot(m[0], m[1]), math.hypot(m[2], m[3])
    return abs(sx - sy) <= tol * max(sx, sy, 1e-12)


_T = re.compile(r"\s*([A-Za-z]+)\s*\(([^)]*)\)\s*,?")


def parse_transform(text: str) -> Matrix:
    """matrix, translate, scale, rotate, skewX, skewY (any number, in order). Raises ValueError."""
    text = (text or "").strip()
    m = IDENTITY
    pos = 0
    while pos < len(text):
        mt = _T.match(text, pos)
        if not mt:
            raise ValueError(f"cannot read transform {text!r}")
        name, args = mt.group(1), [float(x) for x in _NUM.findall(mt.group(2))]
        if name == "matrix" and len(args) == 6:
            n = tuple(args)
        elif name == "translate" and len(args) in (1, 2):
            n = (1.0, 0.0, 0.0, 1.0, args[0], args[1] if len(args) == 2 else 0.0)
        elif name == "scale" and len(args) in (1, 2):
            n = (args[0], 0.0, 0.0, args[1] if len(args) == 2 else args[0], 0.0, 0.0)
        elif name == "rotate" and len(args) in (1, 3):
            a = math.radians(args[0])
            rot = (math.cos(a), math.sin(a), -math.sin(a), math.cos(a), 0.0, 0.0)
            if len(args) == 3:
                cx, cy = args[1], args[2]
                n = mul(mul((1.0, 0.0, 0.0, 1.0, cx, cy), rot), (1.0, 0.0, 0.0, 1.0, -cx, -cy))
            else:
                n = rot
        elif name == "skewX" and len(args) == 1:
            n = (1.0, 0.0, math.tan(math.radians(args[0])), 1.0, 0.0, 0.0)
        elif name == "skewY" and len(args) == 1:
            n = (1.0, math.tan(math.radians(args[0])), 0.0, 1.0, 0.0, 0.0)
        else:
            raise ValueError(f"cannot read transform {mt.group(0).strip()!r}")
        m = mul(m, n)
        pos = mt.end()
    return m


# ----------------------------------------------------------------------------- arcs
def _arc_to_cubics(p0, rx, ry, phi_deg, large, sweep, p1) -> list[tuple[float, ...]]:
    """SVG endpoint arc -> cubic curves (one per quarter turn at most)."""
    (x1, y1), (x2, y2) = p0, p1
    if p0 == p1:
        return []
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(phi_deg)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = x1p ** 2 / rx ** 2 + y1p ** 2 / ry ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    co = math.sqrt(max(0.0, num / den)) * (-1 if large == sweep else 1)
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx = cp * cxp - sp * cyp + (x1 + x2) / 2
    cy = sp * cxp + cp * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        return math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)

    ux, uy = (x1p - cxp) / rx, (y1p - cyp) / ry
    vx, vy = (-x1p - cxp) / rx, (-y1p - cyp) / ry
    th1, dth = ang(1, 0, ux, uy), ang(ux, uy, vx, vy)
    if not sweep and dth > 0:
        dth -= 2 * math.pi
    elif sweep and dth < 0:
        dth += 2 * math.pi
    n = max(1, math.ceil(abs(dth) / (math.pi / 2) - 1e-9))
    step = dth / n
    alpha = 4 / 3 * math.tan(step / 4)

    def point(t):
        return (cx + rx * math.cos(t) * cp - ry * math.sin(t) * sp, cy + rx * math.cos(t) * sp + ry * math.sin(t) * cp)

    def deriv(t):
        return (-rx * math.sin(t) * cp - ry * math.cos(t) * sp, -rx * math.sin(t) * sp + ry * math.cos(t) * cp)

    out = []
    for i in range(n):
        t1, t2 = th1 + i * step, th1 + (i + 1) * step
        a, b, da, db = point(t1), point(t2), deriv(t1), deriv(t2)
        out.append((a[0] + alpha * da[0], a[1] + alpha * da[1], b[0] - alpha * db[0], b[1] - alpha * db[1], b[0], b[1]))
    out[-1] = (*out[-1][:4], x2, y2)                    # land exactly on the requested end point
    return out


# ----------------------------------------------------------------------------- path <-> segments
def parse_segments(d: str) -> list[Segment]:
    """Path data -> absolute M / L / C / Q / Z segments. Raises ValueError on unreadable data."""
    sc = _Scanner(d)
    segs: list[Segment] = []
    cur = start = (0.0, 0.0)
    last_c = last_q = None
    cmd = None
    while True:
        c = sc.command()
        if c is None:
            if cmd is None or not sc.more_numbers():
                break
            c = cmd if cmd not in "Mm" else ("L" if cmd == "M" else "l")
        cmd = c
        lo, rel = c.lower(), c.islower()
        if lo not in _ARGS:
            raise ValueError(f"unsupported path command {c!r}")
        if lo == "z":
            segs.append(("Z", ()))
            cur = start
            last_c = last_q = None
            continue
        first = True
        while first or sc.more_numbers():
            first = False
            ox, oy = cur if rel else (0.0, 0.0)
            if lo == "m":
                cur = start = (sc.number() + ox, sc.number() + oy)
                segs.append(("M", cur))
                cmd, lo = ("l" if rel else "L"), "l"            # further pairs are implicit linetos
                last_c = last_q = None
                continue
            if lo == "l":
                cur = (sc.number() + ox, sc.number() + oy)
                segs.append(("L", cur))
                last_c = last_q = None
            elif lo == "h":
                cur = (sc.number() + ox, cur[1])
                segs.append(("L", cur))
                last_c = last_q = None
            elif lo == "v":
                cur = (cur[0], sc.number() + oy)
                segs.append(("L", cur))
                last_c = last_q = None
            elif lo in "cs":
                if lo == "c":
                    p1 = (sc.number() + ox, sc.number() + oy)
                else:
                    p1 = (2 * cur[0] - last_c[0], 2 * cur[1] - last_c[1]) if last_c else cur
                p2 = (sc.number() + ox, sc.number() + oy)
                p3 = (sc.number() + ox, sc.number() + oy)
                segs.append(("C", (*p1, *p2, *p3)))
                cur, last_c, last_q = p3, p2, None
            elif lo in "qt":
                if lo == "q":
                    q = (sc.number() + ox, sc.number() + oy)
                else:
                    q = (2 * cur[0] - last_q[0], 2 * cur[1] - last_q[1]) if last_q else cur
                p3 = (sc.number() + ox, sc.number() + oy)
                segs.append(("Q", (*q, *p3)))
                cur, last_q, last_c = p3, q, None
            elif lo == "a":
                rx, ry, rot = sc.number(), sc.number(), sc.number()
                large, sweep = sc.flag(), sc.flag()
                p3 = (sc.number() + ox, sc.number() + oy)
                if rx == 0 or ry == 0:
                    segs.append(("L", p3))
                else:
                    segs += [("C", c6) for c6 in _arc_to_cubics(cur, rx, ry, rot, large, sweep, p3)]
                cur, last_c, last_q = p3, None, None
    return segs


def transform_segments(segs: list[Segment], m: Matrix) -> list[Segment]:
    a, b, c, d, e, f = m
    out: list[Segment] = []
    for cmd, pts in segs:
        moved: list[float] = []
        for i in range(0, len(pts), 2):
            x, y = pts[i], pts[i + 1]
            moved += [a * x + c * y + e, b * x + d * y + f]
        out.append((cmd, tuple(moved)))
    return out


def fmt(v: float) -> str:
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def to_d(segs: list[Segment]) -> str:
    return " ".join(cmd + " ".join(fmt(v) for v in pts) if pts else cmd for cmd, pts in segs)


def points_to_segments(pts: list[tuple[float, float]], close: bool) -> list[Segment]:
    if not pts:
        return []
    segs: list[Segment] = [("M", pts[0])] + [("L", p) for p in pts[1:]]
    return segs + [("Z", ())] if close else segs
