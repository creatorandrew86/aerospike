"""Mesh sizing presets and Gmsh transfinite-curve helpers."""

from math import floor


BOUNDARY_LAYER_POINT_COUNT = 16
INLET_POINT_COUNT = 91

# Reference line-length ratio, cell count and progression.
MESH = {
    "spike": (1.386814261, 900, 1.002),
    "bl": (0.012, 20, 1.15),
    "inlet": (0.054980958, 90, None),
    "nozzle": (0.012514092, 50, 0.99),
    "cowl_301": (0.0622, 60, 1.05),
    "cowl_302": (0.2535, 30, 1.02),
    "cowl_303": (1.05, 30, 1.0),
    "far_304": (2.25, 40, 1.0),
    "far_305": (8.5, 60, 1.0),
    "far_306": (20.0, 140, 1.0),
    "far_307": (8.5, 60, 1.0),
    "far_308": (16.80175, 320, 1 / 1.015),
}

NOZZLE_MESH = {
    **MESH,
    "inlet": (0.1768838255, 180, None),
    "nozzle": (0.188604089, 190, 1.0),
    "cowl_301": (0.3002, 60, 1.05),
    "cowl_302": (0.37495, 30, 1.02),
    "cowl_303": (1.3, 30, 1.0),
    "far_304": (2.125, 40, 1.0),
}


def cells(length, scale, mesh, mesh_key, multiple=10):
    reference_length_ratio, reference_cells, _ = mesh[mesh_key]
    target_size_ratio = reference_length_ratio / reference_cells
    return max(multiple, int(floor(length / scale / target_size_ratio / multiple + 0.5)) * multiple)


def progression(mesh, mesh_key, cells):
    _, reference_cells, reference_progression = mesh[mesh_key]
    return reference_progression ** (reference_cells / cells)


def transfinite(curves, cells, method, value):
    point_count = cells + 1
    return f"Transfinite Curve {{{curves}}} = {point_count} Using {method} {value:.8g};"
