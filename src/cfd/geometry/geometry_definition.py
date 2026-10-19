"""Calculate physical geometry for Gmsh aerospike meshes."""

from dataclasses import dataclass
from math import atan2, cos, hypot, isfinite, sin

from cfd.geometry.cd_nozzle import cd_nozzle_contour
from cfd.geometry.conv_nozzle import conv_nozzle_contour
from core.input import process_inputs_on_gmsh_geometry


THROAT_END = (-5e-05, 0.9998)
FAR_RIGHT = 17.5
FAR_TOP = 8.5
FAR_LEFT = -2.5
THRUSTER_COWL_TOP = (-5e-05, 1.3)
THRUSTER_COWL_BACK = (-0.375, 1.3)


@dataclass
class Geometry:
    thruster_type: str
    scale: float
    spike: list
    boundary_layer: list
    cowl: list | None
    secondary_boundary_layer: list | None
    truncated: bool
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
    throat_length = results.get("throat_length")
    if throat_length is None:
        throat_length = _distance(surface[0], tuple(scale * value for value in THROAT_END))
    try:
        throat_length = float(throat_length)
    except (TypeError, ValueError) as error:
        raise ValueError("Throat length must be a positive finite value.") from error
    if not isfinite(throat_length) or throat_length <= 0:
        raise ValueError("Throat length must be a positive finite value.")
    direction = _left_normal(surface[0], surface[1])
    end = (surface[0][0] + throat_length * direction[0],
           surface[0][1] + throat_length * direction[1])
    return end, direction


def _round_truncation(surface, scale):
    if abs(surface[-1][1]) <= scale * 1e-9:
        return surface, False
    cutoff_x, cutoff_y = surface[-1]
    wanted_radius = scale * 0.025
    for i in range(len(surface) - 2, -1, -1):
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
            (center[0] + radius * cos(angle * (1.0 - fraction)),
             center[1] + radius * sin(angle * (1.0 - fraction)))
            for fraction in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
        ]
        return surface[:i + 1] + arc, True
    raise ValueError("Could not fit the truncation curvature to the aerospike contour.")


def _offset_contour(contour, thickness, normal_end):
    normals = [_left_normal(a, b) for a, b in zip(contour, contour[1:])]
    offset = [(contour[0][0] + thickness * normals[0][0],
               contour[0][1] + thickness * normals[0][1])]
    last_surface_index = len(contour) - 1 if normal_end else len(contour) - 2
    for i in range(1, last_surface_index):
        before, after = normals[i - 1], normals[i]
        denominator = 1.0 + before[0] * after[0] + before[1] * after[1]
        if denominator <= 1e-12:
            nx, ny = before
        else:
            nx = (before[0] + after[0]) / denominator
            ny = (before[1] + after[1]) / denominator
        offset.append((contour[i][0] + thickness * nx,
                       contour[i][1] + thickness * ny))
    if not normal_end:
        surface_end = contour[last_surface_index]
        offset.append((surface_end[0] + thickness, surface_end[1]))
        offset.append((contour[-1][0] + thickness, 0.0))
    else:
        surface_end = contour[-1]
        offset.append((surface_end[0] + thickness * normals[-1][0],
                       surface_end[1] + thickness * normals[-1][1]))
    return offset


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


def inlet_direction(results):
    aerospike_type = results.get("aerospike_type")
    scale = results.get("radius") if aerospike_type == "toroidal" else results.get("width")
    if aerospike_type not in {"toroidal", "linear"} or not scale or scale <= 0:
        raise ValueError("A sized toroidal or linear aerospike result is required.")
    surface = [(-float(x), scale - float(radius))
               for x, radius in zip(results["x"][:2], results["R_x"][:2])]
    _, throat_direction = _throat_geometry(results, surface, scale)
    return throat_direction[1], -throat_direction[0]


def build_geometry(case):
    results = case["results"]
    cfd_input = case["cfd"]["inputs"]
    input_errors = process_inputs_on_gmsh_geometry(cfd_input)
    if input_errors:
        raise ValueError("\n".join(input_errors))
    thruster_nozzle = cfd_input["thruster_nozzle"]
    contraction_ratio = cfd_input["contraction_ratio"]
    convergent_nozzle_angle = cfd_input["convergent_nozzle_angle"]
    aerospike_type = results.get("aerospike_type")
    scale = results.get("radius") if aerospike_type == "toroidal" else results.get("width")
    x_values, radial_values = results.get("x"), results.get("R_x")
    if aerospike_type not in {"toroidal", "linear"} or not scale or scale <= 0:
        raise ValueError("A sized toroidal or linear aerospike result is required.")
    if not x_values or not radial_values or len(x_values) != len(radial_values) or len(x_values) < 10:
        raise ValueError("The aerospike contour must contain at least ten coordinate pairs.")
    if not all(isfinite(float(value)) for value in (*x_values, *radial_values)):
        raise ValueError("The aerospike contour contains a non-finite coordinate.")
    throat_eps = float(case["definition"]["effective_throat_eps"])
    thruster_type = "none" if not thruster_nozzle else "cd" if throat_eps > 1 else "conv"
    surface = [(-float(x), scale - float(radius)) for x, radius in zip(x_values, radial_values)]
    throat_end_point, throat_direction = _throat_geometry(results, surface, scale)
    throat_length = _distance(surface[0], throat_end_point)
    inlet_length = (throat_length if thruster_type == "none" else
                    throat_length * contraction_ratio / throat_eps if thruster_type == "cd" else
                    throat_length * contraction_ratio)
    boundary_layer_thickness = 0.09 * inlet_length
    secondary_boundary_layer_thickness = boundary_layer_thickness
    cowl = secondary_boundary_layer = None
    if thruster_type == "cd":
        if throat_length / throat_eps <= 2 * boundary_layer_thickness:
            raise ValueError("The CD throat is too small for the two boundary layers.")
        surface, cowl = cd_nozzle_contour(
            surface, throat_end_point, throat_direction, throat_length,
            contraction_ratio, throat_eps,
            boundary_layer_thickness=boundary_layer_thickness,
            convergent_nozzle_angle=convergent_nozzle_angle,
        )
    elif thruster_type == "conv":
        surface = conv_nozzle_contour(
            surface, throat_end_point, throat_direction, throat_length,
            contraction_ratio, boundary_layer_thickness, convergent_nozzle_angle,
        )
    else:
        extension_direction = throat_direction[1], -throat_direction[0]
        throat_buffer = throat_length / 5
        surface.insert(0, (
            surface[0][0] - throat_buffer * extension_direction[0],
            surface[0][1] - throat_buffer * extension_direction[1],
        ))
    surface, truncated = _round_truncation(surface, scale)
    spike = surface + ([(surface[-1][0], 0.0)] if truncated else [])
    if len(spike) > 800:
        raise ValueError("The spike contour must contain no more than 800 points for meshing.")
    boundary_layer = _offset_contour(spike, boundary_layer_thickness, normal_end=not truncated)
    if thruster_type == "cd":
        secondary_boundary_layer = _offset_contour(
            cowl, -secondary_boundary_layer_thickness, normal_end=True
        )
        axial = throat_direction[1], -throat_direction[0]
        if any(
            (b[0] - a[0]) * axial[0] + (b[1] - a[1]) * axial[1] <= 0
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
    reference_throat = tuple(scale * value for value in THROAT_END)
    shift = (throat_end_point[0] - reference_throat[0],
             throat_end_point[1] - reference_throat[1])

    def shifted(point):
        return scale * point[0] + shift[0], scale * point[1] + shift[1]

    if thruster_type == "cd":
        cowl_back_point = shifted(THRUSTER_COWL_BACK)
        anchors = {
            "cowl_top": shifted(THRUSTER_COWL_TOP),
            "cowl_back": cowl_back_point,
            "cowl_bottom": (cowl_back_point[0], 0.0),
        }
    elif thruster_type == "conv":
        extension_direction = throat_direction[1], -throat_direction[0]
        to_throat = (throat_end_point[0] - spike[0][0], throat_end_point[1] - spike[0][1])
        extension_length = (to_throat[0] * extension_direction[0]
                            + to_throat[1] * extension_direction[1])
        conv_inlet_length = (to_throat[0] * throat_direction[0]
                             + to_throat[1] * throat_direction[1])
        if extension_length <= 0 or conv_inlet_length <= 2 * boundary_layer_thickness:
            raise ValueError("The convergent inlet does not fit ahead of the spike throat.")
        convergent_start_point = (
            throat_end_point[0] - extension_length * extension_direction[0],
            throat_end_point[1] - extension_length * extension_direction[1],
        )
        offset_start_point = (
            convergent_start_point[0] - boundary_layer_thickness * throat_direction[0],
            convergent_start_point[1] - boundary_layer_thickness * throat_direction[1],
        )
        offset_throat_point = (
            throat_end_point[0] - boundary_layer_thickness * throat_direction[0],
            throat_end_point[1] - boundary_layer_thickness * throat_direction[1],
        )
        cowl_back_point = shifted(THRUSTER_COWL_BACK)
        anchors = {
            "throat_end": throat_end_point,
            "convergent_start": convergent_start_point,
            "offset_throat": offset_throat_point,
            "offset_start": offset_start_point,
            "cowl_top": shifted(THRUSTER_COWL_TOP),
            "cowl_back": cowl_back_point,
            "cowl_bottom": (cowl_back_point[0], 0.0),
        }
    else:
        cowl_back_point = shifted(THRUSTER_COWL_BACK)
        anchors = {
            "inlet_end": (
                throat_end_point[0] - throat_buffer * extension_direction[0],
                throat_end_point[1] - throat_buffer * extension_direction[1],
            ),
            "throat_end": throat_end_point,
            "offset_start": (
                throat_end_point[0] - throat_buffer * extension_direction[0]
                - secondary_boundary_layer_thickness * throat_direction[0],
                throat_end_point[1] - throat_buffer * extension_direction[1]
                - secondary_boundary_layer_thickness * throat_direction[1],
            ),
            "offset_throat": (
                throat_end_point[0] - secondary_boundary_layer_thickness * throat_direction[0],
                throat_end_point[1] - secondary_boundary_layer_thickness * throat_direction[1],
            ),
            "cowl_top": shifted(THRUSTER_COWL_TOP),
            "cowl_back": cowl_back_point,
            "cowl_bottom": (cowl_back_point[0], 0.0),
        }
    anchors.update({
        "far_right_axis": (scale * FAR_RIGHT, 0.0),
        "far_right_top": (scale * FAR_RIGHT, scale * FAR_TOP),
        "far_left_top": (scale * FAR_LEFT, scale * FAR_TOP),
        "far_left_axis": (scale * FAR_LEFT, 0.0),
    })
    farfield_end = spike[-1] if not truncated else boundary_layer[-1]
    lengths = {
        "spike": max(_curve_length(spike), _curve_length(boundary_layer)),
        "far_304": _distance(anchors["far_left_axis"], anchors["cowl_bottom"]),
        "far_305": _distance(anchors["far_left_top"], anchors["far_left_axis"]),
        "far_306": _distance(anchors["far_right_top"], anchors["far_left_top"]),
        "far_307": _distance(anchors["far_right_axis"], anchors["far_right_top"]),
        "far_308": _distance(farfield_end, anchors["far_right_axis"]),
    }
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
                    truncated, anchors, lengths)
