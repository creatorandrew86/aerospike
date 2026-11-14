"""Mesh sizing defaults and Gmsh transfinite-curve helpers."""

from math import cosh, floor, log, sinh, sqrt, tanh


DEFAULT_FARFIELD_CELL_SIZE = 0.19
DEFAULT_COWL_CELL_SIZE = 0.028
DEFAULT_INLET_CELL_NUMBER = 130
DEFAULT_THRUSTER_BL_CELL_NUMBER = 250
DEFAULT_SPIKE_BL_CELL_NUMBER = 1250


def _solve_u_over_sinh_u(target_ratio):
    lo, hi = 0.0, 1.0
    while hi < 700.0 and hi / sinh(hi) > target_ratio:
        hi *= 2.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if mid == lo or mid == hi:
            break
        if mid / sinh(mid) > target_ratio:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def bl_cells_and_progression(length, first_cell):
    r_max = 1.15
    target = length / first_cell
    if target <= 3.0:
        return 3, 1.0
    n = max(3, floor(log(1.0 + target * (r_max - 1.0)) / log(r_max)) + 1)
    while (r_max ** n - 1.0) / (r_max - 1.0) <= target:
        n += 1
    if target <= n:
        return n, 1.0
    lo, hi = 1.0, r_max
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if mid == lo or mid == hi:
            break
        if (mid ** n - 1.0) / (mid - 1.0) < target:
            lo = mid
        else:
            hi = mid
    return n, lo


def beta(curves, length, h0, h1, r0, min_cells=10):
    if abs(h0 - h1) <= 1e-9 * max(h0, h1):
        return transfinite(curves, max(min_cells, round(length / h1)), "Progression", 1.0)
    coef = 1.0 / sqrt(1.0 - min(h0, h1) / max(h0, h1))
    a = (coef + 1.0) / (coef - 1.0)
    mean_h = 2.0 * h1 / (coef * log(a)) if h0 < h1 else h1 * (0.5 + (a - 1.0 / a) / (4.0 * log(a)))
    cells = max(min_cells, round(length / mean_h), round(log(a) / abs(log(r0))))
    return transfinite(curves, cells, "Beta", coef)


def beta_fixed_n(curves, length, h_start, cells):
    mean_h = length / cells
    if h_start >= mean_h:
        return transfinite(curves, cells, "Progression", 1.0), mean_h
    u = _solve_u_over_sinh_u(h_start / mean_h)
    coef = 1.0 / tanh(0.5 * u)
    h_end = h_start * cosh(0.5 * u) ** 2
    return transfinite(curves, cells, "Beta", coef), h_end


def bump(curves, length, h_end, cells):
    mean_h = length / cells
    if h_end >= mean_h:
        return transfinite(curves, cells, "Progression", 1.0)
    u = _solve_u_over_sinh_u(h_end / mean_h)
    b = 1.0 / cosh(0.5 * u) ** 2
    return transfinite(curves, cells, "Bump", b)


def transfinite(curves, cells, method, value):
    point_count = cells + 1
    precision = ".12g" if method == "Beta" else ".8g"
    return f"Transfinite Curve {{{curves}}} = {point_count} Using {method} {value:{precision}};"
