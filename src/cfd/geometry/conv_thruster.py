"""Convergent-nozzle geometry helpers for Gmsh aerospike meshes."""

from math import atan2, cos, hypot, radians, sin, tan

CONVERGENT_NOZZLE_ANGLE = 45
FILLET_RADIUS_RATIO = 0.04


def _cross(first, second):
    return first[0] * second[1] - first[1] * second[0]


def corner_fillet(start, direction, turn, radius, segments):
    normal = -direction[1], direction[0]
    side = 1 if turn > 0 else -1
    center = start[0] + side * radius * normal[0], start[1] + side * radius * normal[1]
    radial = start[0] - center[0], start[1] - center[1]
    return [
        (center[0] + radial[0] * cos(turn * step / segments) - radial[1] * sin(turn * step / segments),
         center[1] + radial[0] * sin(turn * step / segments) + radial[1] * cos(turn * step / segments))
        for step in range(1, segments)
    ]


def conv_nozzle_contour(
    surface, throat_end, throat_direction, throat_length, contraction_ratio, boundary_layer_thickness,
    convergent_nozzle_angle=CONVERGENT_NOZZLE_ANGLE,
):
    """Build the convergent spike extension from two normally filleted corners."""
    target_dx = surface[1][0] - surface[0][0]
    target_dy = surface[1][1] - surface[0][1]
    target_length = hypot(target_dx, target_dy)
    if target_length == 0:
        raise ValueError("The aerospike throat must begin with two distinct points.")

    extension_direction = throat_direction[1], -throat_direction[0]
    angle = radians(convergent_nozzle_angle)

    inlet_length = throat_length * contraction_ratio
    clear_inlet_length = inlet_length - 2 * boundary_layer_thickness
    if clear_inlet_length <= 0:
        raise ValueError("The inlet length must exceed its two boundary-layer offsets.")
    fillet_radius = boundary_layer_thickness + clear_inlet_length * FILLET_RADIUS_RATIO
    spike_start = surface[0]
    directions = (
        (extension_direction[0] * cos(angle) - extension_direction[1] * sin(angle),
         extension_direction[0] * sin(angle) + extension_direction[1] * cos(angle)),
        (extension_direction[0] * cos(angle) + extension_direction[1] * sin(angle),
         -extension_direction[0] * sin(angle) + extension_direction[1] * cos(angle)),
    )
    line_direction = max(
        directions,
        key=lambda direction: direction[0] * throat_direction[0] + direction[1] * throat_direction[1],
    )
    spike_direction = target_dx / target_length, target_dy / target_length
    first_turn = atan2(
        _cross(extension_direction, line_direction),
        extension_direction[0] * line_direction[0] + extension_direction[1] * line_direction[1],
    )
    second_turn = atan2(
        _cross(line_direction, spike_direction),
        line_direction[0] * spike_direction[0] + line_direction[1] * spike_direction[1],
    )
    if min(abs(first_turn), abs(second_turn)) < 1e-8:
        raise ValueError("The convergent fillets require two distinct directions.")

    first_tangent = fillet_radius * tan(abs(first_turn) / 2)
    second_tangent = fillet_radius * tan(abs(second_turn) / 2)
    throat_corner = (
        spike_start[0] - second_tangent * spike_direction[0],
        spike_start[1] - second_tangent * spike_direction[1],
    )
    current_inlet_projection = (
        (throat_end[0] - throat_corner[0]) * throat_direction[0]
        + (throat_end[1] - throat_corner[1]) * throat_direction[1]
    )
    convergent_projection = (
        line_direction[0] * throat_direction[0] + line_direction[1] * throat_direction[1]
    )
    convergent_length = (inlet_length - current_inlet_projection) / convergent_projection
    if (convergent_length <= 0 or first_tangent >= inlet_length / 4
            or first_tangent + second_tangent >= convergent_length):
        raise ValueError("The convergent fillet radius is too large for this geometry.")

    # The sharp temporary corners are recovered from the tangent point at the spike.
    inlet_corner = (
        throat_corner[0] - convergent_length * line_direction[0],
        throat_corner[1] - convergent_length * line_direction[1],
    )
    inlet_start = (
        inlet_corner[0] - inlet_length / 4 * extension_direction[0],
        inlet_corner[1] - inlet_length / 4 * extension_direction[1],
    )
    point_2 = (
        inlet_corner[0] - first_tangent * extension_direction[0],
        inlet_corner[1] - first_tangent * extension_direction[1],
    )
    point_5 = (
        inlet_corner[0] + first_tangent * line_direction[0],
        inlet_corner[1] + first_tangent * line_direction[1],
    )
    point_6 = (
        throat_corner[0] - second_tangent * line_direction[0],
        throat_corner[1] - second_tangent * line_direction[1],
    )

    point_3, point_4 = corner_fillet(point_2, extension_direction, first_turn, fillet_radius, 3)
    point_7, point_8, point_9 = corner_fillet(point_6, line_direction, second_turn, fillet_radius, 4)
    return [inlet_start, point_2, point_3, point_4, point_5, point_6, point_7, point_8, point_9] + surface
