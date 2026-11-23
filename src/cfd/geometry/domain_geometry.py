"""Calculate physical geometry for Gmsh aerospike meshes."""

from bisect import bisect_right
from dataclasses import dataclass
from math import atan2, cos, hypot, isfinite, log, sin, sqrt

from cfd.geometry import mesh
from cfd.geometry.cd_thruster import cd_nozzle_contour
from cfd.geometry.conv_thruster import conv_nozzle_contour
from core.input import process_inputs_on_gmsh_geometry


FAR_RIGHT = 24
FAR_TOP = 9
FAR_LEFT = -2.5
COWL_TOP_FACTOR = 1.3
COWL_BACK_FACTOR = -0.375
COWL_CLEARANCE_FACTOR = 0.1
COWL_BACK_MIN_FACTOR = -2.0
COWL_TOP_MAX_FACTOR = 6.0
MAX_END_BL_FACTOR = 0.01
WAKE_LENGTH_FACTOR = 10.0


@dataclass
class Geometry:
    thruster_type: str
    scale: float
    spike: list
    boundary_layer: list
    cowl: list | None
    secondary_boundary_layer: list | None
    truncated: bool
    throat_index: int
    anchors: dict
    lengths: dict


def _distance(a, b):
    return hypot(b[0] - a[0], b[1] - a[1])


def _curve_length(points):
    return sum(_distance(a, b) for a, b in zip(points, points[1:]))


def _left_normal(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = hypot(dx, dy)
    if length == 0:
        raise ValueError("Aerospike contour contains consecutive duplicate points.")
    return -dy / length, dx / length


def _throat_geometry(results, surface, scale):
    throat_length = float(results["throat_length"])
    throat_direction = _left_normal(surface[0], surface[1])
    flow_direction = throat_direction[1], -throat_direction[0]
    cowl_lip = (0.0, scale)
    spike_entry = (
        cowl_lip[0] - throat_length * throat_direction[0],
        cowl_lip[1] - throat_length * throat_direction[1],
    )
    return cowl_lip, spike_entry, throat_direction, flow_direction


def _round_truncation(surface, scale, min_index=0):
    if abs(surface[-1][1]) <= scale * 1e-9:
        return surface, False
    cutoff_x, cutoff_y = surface[-1]
    wanted_radius = scale * 0.025
    for i in range(len(surface) - 2, min_index - 1, -1):
        start, end = surface[i], surface[i + 1]
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = hypot(dx, dy)
        if length == 0 or dx <= 0:
            continue
        tx, ty = dx / length, dy / length
        nx, ny = -ty, tx
        vertical_drop_per_radius = ny + (1.0 - nx) * ty / tx
        radius = wanted_radius
        if vertical_drop_per_radius > 0:
            radius = min(radius, 0.95 * cutoff_y / vertical_drop_per_radius)
        tangent_x = cutoff_x - radius * (1.0 - nx)
        if not start[0] <= tangent_x <= end[0]:
            continue
        fraction = (tangent_x - start[0]) / dx
        tangent_y = start[1] + fraction * dy
        center = tangent_x - radius * nx, tangent_y - radius * ny
        angle = atan2(ny, nx)
        arc = [
            (center[0] + radius * cos(angle * (1.0 - step / 20)),
             center[1] + radius * sin(angle * (1.0 - step / 20)))
            for step in range(21)
        ]
        return surface[:i + 1] + arc, True
    raise ValueError("Could not fit the truncation curvature to the aerospike contour.")


def _greville_resample(points, count, h0=1.0, h1=1.0):
    u_max = count - 3
    abscissae = [0.0, 1.0 / 3.0] + [float(i) for i in range(1, u_max)] + [u_max - 1.0 / 3.0, float(u_max)]
    if h0 > h1 * (1.0 + 1e-9):
        coef = 1.0 / sqrt(1.0 - h1 / h0)
        a = (coef + 1.0) / (coef - 1.0)
        s1 = 0.5 + (a - 1.0 / a) / (4.0 * log(a))
        def frac(u_hat):
            tau = 1.0 - log((coef + 1.0 - u_hat) / (coef - 1.0 + u_hat)) / log(a)
            y = a ** (1.0 - tau)
            return (0.5 * tau + ((a - 1.0 / a) - (y - 1.0 / y)) / (4.0 * log(a))) / s1
    else:
        def frac(u_hat):
            return u_hat
    cumulative = [0.0]
    for p0, p1 in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + _distance(p0, p1))
    total = cumulative[-1]
    resampled = [points[0]]
    j = 0
    for xi in abscissae[1:-1]:
        target = total * frac(xi / u_max)
        while j + 1 < len(cumulative) - 1 and cumulative[j + 1] < target:
            j += 1
        span = cumulative[j + 1] - cumulative[j]
        t = (target - cumulative[j]) / span if span > 0 else 0.0
        resampled.append((
            points[j][0] + t * (points[j + 1][0] - points[j][0]),
            points[j][1] + t * (points[j + 1][1] - points[j][1]),
        ))
    resampled.append(points[-1])
    return resampled


def _offset_contour(contour, thickness, normal_end):
    thicknesses = [thickness] * len(contour) if isinstance(thickness, (int, float)) else thickness
    if len(thicknesses) != len(contour):
        raise ValueError("Boundary-layer thickness array must match contour point count.")
    normals = [_left_normal(a, b) for a, b in zip(contour, contour[1:])]
    offset = [(contour[0][0] + thicknesses[0] * normals[0][0],
               contour[0][1] + thicknesses[0] * normals[0][1])]
    last_surface_index = len(contour) - 1 if normal_end else len(contour) - 2
    for i in range(1, last_surface_index):
        before, after = normals[i - 1], normals[i]
        denominator = 1.0 + before[0] * after[0] + before[1] * after[1]
        if denominator <= 1e-12:
            nx, ny = before
        else:
            nx = (before[0] + after[0]) / denominator
            ny = (before[1] + after[1]) / denominator
        offset.append((contour[i][0] + thicknesses[i] * nx,
                       contour[i][1] + thicknesses[i] * ny))
    if not normal_end:
        surface_end = contour[last_surface_index]
        offset.append((surface_end[0] + thicknesses[last_surface_index], surface_end[1]))
        offset.append((contour[-1][0] + thicknesses[-1], 0.0))
    else:
        surface_end = contour[-1]
        offset.append((surface_end[0] + thicknesses[-1] * normals[-1][0],
                       surface_end[1] + thicknesses[-1] * normals[-1][1]))
    return offset


def _spike_bl_thicknesses(spike, throat_index, start_x, throat_bl, max_end_bl, x_ref, bl_ref):
    """Map throat and marched spike BL thicknesses onto resampled spike contour points."""
    if (
        not bl_ref
        or len(bl_ref) != len(x_ref)
        or any(v is None or not isfinite(float(v)) or float(v) <= 0 for v in bl_ref)
        or any(x is None or not isfinite(float(x)) for x in x_ref)
    ):
        return [float(throat_bl)] * len(spike)

    ref_x = [float(start_x)]
    ref_t = [float(throat_bl)]
    for x_val, bl_val in zip(x_ref, bl_ref):
        x_coord = float(x_val)
        clamped = min(max_end_bl, max(ref_t[-1], 3.0 * float(bl_val)))
        if x_coord > ref_x[-1]:
            ref_x.append(x_coord)
            ref_t.append(clamped)

    thicknesses = []
    for i, (x_pt, _) in enumerate(spike):
        if i <= throat_index or x_pt <= ref_x[0]:
            thicknesses.append(float(throat_bl))
        elif x_pt >= ref_x[-1]:
            thicknesses.append(ref_t[-1])
        else:
            idx = bisect_right(ref_x, x_pt) - 1
            span = ref_x[idx + 1] - ref_x[idx]
            frac = (x_pt - ref_x[idx]) / span if span > 0 else 0.0
            thicknesses.append(ref_t[idx] + frac * (ref_t[idx + 1] - ref_t[idx]))
    return thicknesses


def _offset_arc(points, thickness):
    first, middle, last = points[0], points[len(points) // 2], points[-1]
    denominator = 2 * (
        first[0] * (middle[1] - last[1])
        + middle[0] * (last[1] - first[1])
        + last[0] * (first[1] - middle[1])
    )
    if abs(denominator) < 1e-12:
        return None
    center = (
        ((first[0] ** 2 + first[1] ** 2) * (middle[1] - last[1])
         + (middle[0] ** 2 + middle[1] ** 2) * (last[1] - first[1])
         + (last[0] ** 2 + last[1] ** 2) * (first[1] - middle[1])) / denominator,
        ((first[0] ** 2 + first[1] ** 2) * (last[0] - middle[0])
         + (middle[0] ** 2 + middle[1] ** 2) * (first[0] - last[0])
         + (last[0] ** 2 + last[1] ** 2) * (middle[0] - first[0])) / denominator,
    )
    turn = ((middle[0] - first[0]) * (last[1] - middle[1])
            - (middle[1] - first[1]) * (last[0] - middle[0]))
    radius = _distance(center, first)
    offset_radius = radius - (thickness if turn > 0 else -thickness)
    if offset_radius <= 0:
        raise ValueError("The boundary-layer thickness exceeds the convergent fillet radius.")
    return [
        (center[0] + (point[0] - center[0]) * offset_radius / radius,
         center[1] + (point[1] - center[1]) * offset_radius / radius)
        for point in points
    ]


def _subdivide_segment(start, end, segments):
    return [
        (start[0] + (end[0] - start[0]) * step / segments,
         start[1] + (end[1] - start[1]) * step / segments)
        for step in range(1, segments)
    ]


def _cowl_anchors(cowl_lip, scale, thruster_points):
    min_x = min(point[0] for point in thruster_points)
    max_y = max(point[1] for point in thruster_points)
    cowl_back_x = min(scale * COWL_BACK_FACTOR, min_x - scale * COWL_CLEARANCE_FACTOR)
    cowl_top_y = max(scale * COWL_TOP_FACTOR, max_y + scale * COWL_CLEARANCE_FACTOR)
    if cowl_back_x < scale * COWL_BACK_MIN_FACTOR or cowl_top_y > scale * COWL_TOP_MAX_FACTOR:
        raise ValueError("The thruster geometry exceeds the allowed outer cowl expansion bounds.")
    if any(point[1] <= 0 for point in thruster_points):
        raise ValueError("The thruster geometry crosses the symmetry axis.")
    return {
        "cowl_top": (cowl_lip[0], cowl_top_y),
        "cowl_back": (cowl_back_x, cowl_top_y),
        "cowl_bottom": (cowl_back_x, 0.0),
    }


def _domain_scale(results):
    aerospike_type = results.get("aerospike_type")
    scale = (
        results.get("radius") if aerospike_type == "toroidal"
        else results["width"] / 2 if aerospike_type == "linear" and results.get("width") is not None
        else None
    )
    if not scale or scale <= 0:
        raise ValueError("A sized toroidal or linear aerospike result is required.")
    return scale


def inlet_direction(results):
    scale = _domain_scale(results)
    surface = [(-float(x), scale - float(radius))
               for x, radius in zip(results["x"][:2], results["R_x"][:2])]
    _, _, _, flow_direction = _throat_geometry(results, surface, scale)
    return flow_direction


def build_geometry(case):
    results = case["results"]
    cfd_input = case["cfd"]["inputs"]
    input_errors = process_inputs_on_gmsh_geometry(cfd_input)
    if input_errors:
        raise ValueError("\n".join(input_errors))
    thruster_nozzle = cfd_input["thruster_nozzle"]
    contraction_ratio = cfd_input["contraction_ratio"]
    convergent_nozzle_angle = cfd_input["convergent_nozzle_angle"]
    scale = _domain_scale(results)
    throat_eps = float(case["definition"]["effective_throat_eps"])
    thruster_type = "none" if not thruster_nozzle else "cd" if throat_eps > 1 else "conv"
    surface = [(-float(x), scale - float(radius)) for x, radius in zip(results["x"], results["R_x"])]
    cowl_lip, spike_entry, throat_direction, flow_direction = _throat_geometry(results, surface, scale)
    throat_length = float(results["throat_length"])
    sonic_throat_length = throat_length / throat_eps if thruster_type == "cd" else throat_length
    max_bl_thickness = 0.15 * sonic_throat_length
    predicted_bl = results.get("bl_thickness")
    boundary_layer_thickness = (
        min(3.0 * float(predicted_bl), max_bl_thickness)
        if predicted_bl is not None and isfinite(float(predicted_bl)) and float(predicted_bl) > 0
        else max_bl_thickness
    )
    cowl = secondary_boundary_layer = None
    original_surface_count = len(surface)
    throat_index = 0
    throat_buffer = throat_length / 5
    if throat_eps > 1:
        if (surface[0][0] - spike_entry[0]) * flow_direction[0] + (surface[0][1] - spike_entry[1]) * flow_direction[1] <= 0:
            raise ValueError("First spike point must lie downstream of spike_entry for throat_eps > 1.")
        # ponytail: Option A embeds the straight uniform-flow ramp inside BSpline(1) (~7.6 um max deviation); switch to Option B (explicit Line(12) in write_gmsh_geometry_file.py) if exact straightness is required.
        if thruster_type == "cd":
            if throat_length / throat_eps <= 2 * boundary_layer_thickness:
                raise ValueError("The CD throat is too small for the two boundary layers.")
            entry_pm_angle = results.get("entry_pm_angle")
            if entry_pm_angle is None or not isfinite(float(entry_pm_angle)) or float(entry_pm_angle) <= 0:
                raise ValueError("A positive finite entry_pm_angle is required for CD thruster geometry.")
            lower, cowl = cd_nozzle_contour(
                spike_entry, cowl_lip, throat_direction, throat_length,
                contraction_ratio, throat_eps, float(entry_pm_angle) / 2,
                boundary_layer_thickness=boundary_layer_thickness,
                convergent_nozzle_angle=convergent_nozzle_angle,
                toroidal=results.get("aerospike_type") == "toroidal",
            )
            surface = lower + surface
            throat_index = len(lower) - 1
        else:
            inlet_end_spike = (
                spike_entry[0] - throat_buffer * flow_direction[0],
                spike_entry[1] - throat_buffer * flow_direction[1],
            )
            segments = max(1, min(16, 770 - len(surface)))
            surface = [
                inlet_end_spike,
                spike_entry,
                *_subdivide_segment(spike_entry, surface[0], segments),
                *surface,
            ]
    else:
        surface[0] = spike_entry
        if (surface[1][0] - surface[0][0]) * flow_direction[0] + (surface[1][1] - surface[0][1]) * flow_direction[1] <= 0:
            raise ValueError("Second spike point must lie downstream of spike_entry.")
        if thruster_type == "conv":
            surface = conv_nozzle_contour(
                surface, cowl_lip, throat_direction, throat_length,
                contraction_ratio, boundary_layer_thickness, convergent_nozzle_angle,
            )
            throat_index = len(surface) - original_surface_count
        else:
            surface.insert(0, (
                spike_entry[0] - throat_buffer * flow_direction[0],
                spike_entry[1] - throat_buffer * flow_direction[1],
            ))
    surface, truncated = _round_truncation(surface, scale, min_index=throat_index)
    spike = surface + ([(surface[-1][0], 0.0)] if truncated else [])
    if len(spike) > 800:
        raise ValueError("The spike contour must contain no more than 800 points for meshing.")
    h_start = (
        _curve_length(spike[:throat_index + 1]) / mesh.DEFAULT_THRUSTER_BL_CELL_NUMBER
        if throat_index > 0
        else 0.9 * max(throat_length - 2.0 * boundary_layer_thickness, 1e-9) / mesh.DEFAULT_INLET_CELL_NUMBER
    )
    h_spike = _curve_length(spike[throat_index:]) / mesh.DEFAULT_SPIKE_BL_CELL_NUMBER
    open_count = min(800 - throat_index, max(len(spike) - throat_index, 400))
    spike = spike[:throat_index] + _greville_resample(spike[throat_index:], open_count, h_start, h_spike)
    max_end_bl_thickness = max(boundary_layer_thickness, MAX_END_BL_FACTOR * _curve_length(spike[throat_index:]))
    spike_thicknesses = _spike_bl_thicknesses(
        spike,
        throat_index,
        spike[throat_index][0] if throat_index > 0 else spike_entry[0],
        boundary_layer_thickness,
        max_end_bl_thickness,
        [-float(x) for x in results["x"]],
        results.get("bl_thickness_x"),
    )
    boundary_layer = _offset_contour(spike, spike_thicknesses, normal_end=not truncated)
    if thruster_type == "cd":
        secondary_boundary_layer = _offset_contour(
            cowl, -boundary_layer_thickness, normal_end=True
        )
        if any(
            (b[0] - a[0]) * flow_direction[0] + (b[1] - a[1]) * flow_direction[1] <= 0
            for contour in (boundary_layer[:len(cowl)], secondary_boundary_layer)
            for a, b in zip(contour, contour[1:])
        ):
            raise ValueError(
                "The CD boundary layer folds at this geometry; increase the contraction "
                "or expansion ratio."
            )
    elif thruster_type == "conv":
        boundary_layer[1:5] = _offset_arc(spike[1:5], boundary_layer_thickness)
        boundary_layer[5:10] = _offset_arc(spike[5:10], boundary_layer_thickness)
        boundary_layer[0] = (
            spike[0][0] + boundary_layer_thickness * throat_direction[0],
            spike[0][1] + boundary_layer_thickness * throat_direction[1],
        )
    if any(
        (ob[0] - oa[0]) * (sb[0] - sa[0]) + (ob[1] - oa[1]) * (sb[1] - sa[1]) <= 0
        for (sa, sb), (oa, ob) in zip(
            zip(spike[throat_index:], spike[throat_index + 1:]),
            zip(boundary_layer[throat_index:], boundary_layer[throat_index + 1:]),
        )
    ):
        raise ValueError("The spike boundary layer folds at this geometry.")
    if thruster_type == "cd":
        anchors = _cowl_anchors(cowl_lip, scale, spike[:throat_index + 1] + cowl)
    elif thruster_type == "conv":
        to_throat = (cowl_lip[0] - spike[0][0], cowl_lip[1] - spike[0][1])
        extension_length = (to_throat[0] * flow_direction[0]
                            + to_throat[1] * flow_direction[1])
        conv_inlet_length = (to_throat[0] * throat_direction[0]
                             + to_throat[1] * throat_direction[1])
        if extension_length <= 0 or conv_inlet_length <= 2 * boundary_layer_thickness:
            raise ValueError("The convergent inlet does not fit ahead of the spike throat.")
        convergent_start_point = (
            cowl_lip[0] - extension_length * flow_direction[0],
            cowl_lip[1] - extension_length * flow_direction[1],
        )
        offset_start_point = (
            convergent_start_point[0] - boundary_layer_thickness * throat_direction[0],
            convergent_start_point[1] - boundary_layer_thickness * throat_direction[1],
        )
        offset_throat_point = (
            cowl_lip[0] - boundary_layer_thickness * throat_direction[0],
            cowl_lip[1] - boundary_layer_thickness * throat_direction[1],
        )
        anchors = {
            "throat_end": cowl_lip,
            "convergent_start": convergent_start_point,
            "offset_throat": offset_throat_point,
            "offset_start": offset_start_point,
            **_cowl_anchors(cowl_lip, scale, [convergent_start_point, cowl_lip, *spike[:throat_index + 1]]),
        }
    else:
        inlet_end_point = (
            cowl_lip[0] - throat_buffer * flow_direction[0],
            cowl_lip[1] - throat_buffer * flow_direction[1],
        )
        anchors = {
            "inlet_end": inlet_end_point,
            "throat_end": cowl_lip,
            "offset_start": (
                inlet_end_point[0] - boundary_layer_thickness * throat_direction[0],
                inlet_end_point[1] - boundary_layer_thickness * throat_direction[1],
            ),
            "offset_throat": (
                cowl_lip[0] - boundary_layer_thickness * throat_direction[0],
                cowl_lip[1] - boundary_layer_thickness * throat_direction[1],
            ),
            **_cowl_anchors(cowl_lip, scale, [inlet_end_point, cowl_lip, spike[0], spike_entry]),
        }
    anchors.update({
        "far_right_axis": (scale * FAR_RIGHT, 0.0),
        "far_right_top": (scale * FAR_RIGHT, scale * FAR_TOP),
        "far_left_top": (scale * FAR_LEFT, scale * FAR_TOP),
        "far_left_axis": (scale * FAR_LEFT, 0.0),
    })
    if not truncated:
        end_bl_thickness = _distance(spike[-1], boundary_layer[-1])
        wake_length = min(
            WAKE_LENGTH_FACTOR * end_bl_thickness,
            0.5 * (anchors["far_right_axis"][0] - spike[-1][0]),
        )
        anchors["wake_axis"] = (spike[-1][0] + wake_length, 0.0)
        anchors["wake_top"] = (spike[-1][0] + wake_length, end_bl_thickness)
    farfield_end = anchors["wake_axis"] if not truncated else boundary_layer[-1]
    lengths = {
        "spike": max(_curve_length(spike[throat_index:]), _curve_length(boundary_layer[throat_index:])),
        "far_304": _distance(anchors["far_left_axis"], anchors["cowl_bottom"]),
        "far_305": _distance(anchors["far_left_top"], anchors["far_left_axis"]),
        "far_306": _distance(anchors["far_right_top"], anchors["far_left_top"]),
        "far_307": _distance(anchors["far_right_axis"], anchors["far_right_top"]),
        "far_308": _distance(farfield_end, anchors["far_right_axis"]),
    }
    if not truncated:
        lengths["wake"] = max(
            _distance(spike[-1], anchors["wake_axis"]),
            _distance(boundary_layer[-1], anchors["wake_top"]),
        )
    if throat_index > 0:
        lengths["thruster"] = max(
            _curve_length(spike[:throat_index + 1]),
            _curve_length(boundary_layer[:throat_index + 1]),
        )
    if thruster_type == "cd":
        lengths.update({
            "inlet": _distance(boundary_layer[0], secondary_boundary_layer[0]),
            "nozzle": max(_curve_length(cowl), _curve_length(secondary_boundary_layer)),
            "cowl_301": _distance(cowl[-1], anchors["cowl_top"]),
            "cowl_302": _distance(anchors["cowl_top"], anchors["cowl_back"]),
            "cowl_303": _distance(anchors["cowl_back"], anchors["cowl_bottom"]),
        })
    elif thruster_type == "conv":
        lengths.update({
            "inlet": _distance(boundary_layer[0], anchors["offset_start"]),
            "nozzle": max(_distance(anchors["convergent_start"], anchors["throat_end"]),
                          _distance(anchors["offset_start"], anchors["offset_throat"])),
            "cowl_301": _distance(anchors["throat_end"], anchors["cowl_top"]),
            "cowl_302": _distance(anchors["cowl_top"], anchors["cowl_back"]),
            "cowl_303": _distance(anchors["cowl_back"], anchors["cowl_bottom"]),
        })
    else:
        lengths.update({
            "inlet": _distance(boundary_layer[0], anchors["offset_start"]),
            "nozzle": max(_distance(anchors["inlet_end"], anchors["throat_end"]),
                          _distance(anchors["offset_start"], anchors["offset_throat"])),
            "cowl_301": _distance(anchors["throat_end"], anchors["cowl_top"]),
            "cowl_302": _distance(anchors["cowl_top"], anchors["cowl_back"]),
            "cowl_303": _distance(anchors["cowl_back"], anchors["cowl_bottom"]),
        })
    return Geometry(thruster_type, scale, spike, boundary_layer, cowl, secondary_boundary_layer,
                    truncated, throat_index, anchors, lengths)
