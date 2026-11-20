"""Fast 2D CFD mesh quality evaluation using Gmsh and vectorized NumPy."""

import numpy as np

QUAD_ELEMENT_TYPE = 3
TRI_ELEMENT_TYPE = 2


def _polygon_area(pts):
    x, y = pts[..., 0], pts[..., 1]
    return 0.5 * np.abs(np.sum(x * np.roll(y, -1, axis=1) - np.roll(x, -1, axis=1) * y, axis=1))


def _element_angles_and_edges(pts):
    """Return interior angles (deg) and edge lengths for (N, K, 2) polygons."""
    v_next = np.roll(pts, -1, axis=1) - pts
    v_prev = np.roll(pts, 1, axis=1) - pts
    lengths = np.linalg.norm(v_next, axis=2)
    denom = np.maximum(lengths * np.roll(lengths, 1, axis=1), 1e-30)
    angles_deg = np.degrees(np.arccos(np.clip(np.sum(v_next * v_prev, axis=2) / denom, -1.0, 1.0)))
    return angles_deg, lengths


def _equiangle_skewness(angles_deg, ideal_angle):
    return np.clip(
        np.maximum(
            (np.max(angles_deg, axis=1) - ideal_angle) / (180.0 - ideal_angle),
            (ideal_angle - np.min(angles_deg, axis=1)) / ideal_angle,
        ),
        0.0,
        1.0,
    )


def _volume_ratios(t_idx, t_area):
    """Return max edge-neighbor volume ratio per triangle cell."""
    n = len(t_idx)
    u, v = t_idx.ravel(), np.roll(t_idx, -1, axis=1).ravel()
    edges = (np.minimum(u, v).astype(np.int64) << 32) | np.maximum(u, v).astype(np.int64)
    cells = np.repeat(np.arange(n, dtype=np.int64), 3)
    order = np.argsort(edges)
    sk, sc = edges[order], cells[order]
    shared = sk[:-1] == sk[1:]
    c1, c2 = sc[:-1][shared], sc[1:][shared]
    ratios = np.maximum(t_area[c1], t_area[c2]) / np.maximum(np.minimum(t_area[c1], t_area[c2]), 1e-30)
    max_r = np.ones(n, dtype=np.float64)
    np.maximum.at(max_r, c1, ratios)
    np.maximum.at(max_r, c2, ratios)
    return max_r


def _format_metric(name, element_type, worst, mean, unit, fmt):
    return {
        "name": name,
        "element_type": element_type,
        "value_str": f"{worst:{fmt}} / {mean:{fmt}}",
        "unit": unit,
    }


def compute_gmsh_mesh_quality():
    """Compute CFD quality metrics from the currently loaded Gmsh 2D model."""
    import gmsh

    node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
    if len(node_tags) == 0:
        raise RuntimeError("No mesh nodes found in the Gmsh model.")

    node_tags = np.asarray(node_tags, dtype=np.int64)
    coords = np.asarray(node_coords, dtype=np.float64).reshape(-1, 3)[:, :2]
    lut = np.empty(int(node_tags.max()) + 1, dtype=np.intp)
    lut[node_tags] = np.arange(len(node_tags))

    elem_types, elem_tags_list, elem_nodes_list = gmsh.model.mesh.getElements(2)
    q_tags = np.empty(0, dtype=np.uint64)
    q_idx = np.empty((0, 4), dtype=np.intp)
    t_idx = np.empty((0, 3), dtype=np.intp)

    for etype, etags, enodes in zip(elem_types, elem_tags_list, elem_nodes_list):
        if not len(etags):
            continue
        if etype == QUAD_ELEMENT_TYPE:
            q_tags = np.concatenate([q_tags, np.asarray(etags, dtype=np.uint64)])
            q_idx = np.vstack([q_idx, lut[np.asarray(enodes, dtype=np.int64).reshape(-1, 4)]])
        elif etype == TRI_ELEMENT_TYPE:
            t_idx = np.vstack([t_idx, lut[np.asarray(enodes, dtype=np.int64).reshape(-1, 3)]])

    metrics = []
    if len(q_idx):
        q_angles, _ = _element_angles_and_edges(coords[q_idx])
        q_skew = _equiangle_skewness(q_angles, 90.0)
        q_non_ortho = np.max(np.abs(q_angles - 90.0), axis=1)
        q_minsj = np.asarray(gmsh.model.mesh.getElementQualities(q_tags, "minSJ"), dtype=np.float64)
        metrics.extend([
            _format_metric("Equiangle Skewness", "quad (bl)", np.max(q_skew), np.mean(q_skew), "—", ".3f"),
            _format_metric("Scaled Jacobian (minSJ)", "quad (bl)", np.min(q_minsj), np.mean(q_minsj), "—", ".3f"),
            _format_metric("Max Non-Orthogonality", "quad (bl)", np.max(q_non_ortho), np.mean(q_non_ortho), "deg", ".1f"),
        ])

    if len(t_idx):
        t_pts = coords[t_idx]
        t_area = _polygon_area(t_pts)
        t_angles, t_lengths = _element_angles_and_edges(t_pts)
        t_skew = _equiangle_skewness(t_angles, 60.0)
        t_ar = (np.sqrt(3.0) / 4.0) * np.max(t_lengths, axis=1) ** 2 / np.maximum(t_area, 1e-30)
        t_vr = _volume_ratios(t_idx, t_area)
        metrics.extend([
            _format_metric("Equiangle Skewness", "tri", np.max(t_skew), np.mean(t_skew), "—", ".3f"),
            _format_metric("Aspect Ratio", "tri", np.max(t_ar), np.mean(t_ar), "—", ".2f"),
            _format_metric("Volume Ratio", "tri", np.max(t_vr), np.mean(t_vr), "—", ".2f"),
        ])

    return {
        "nodes": int(len(node_tags)),
        "elements": int(len(q_idx) + len(t_idx)),
        "quads": int(len(q_idx)),
        "tris": int(len(t_idx)),
        "metrics": metrics,
    }
