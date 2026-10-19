"""Convergent-divergent Rao nozzle contours for Gmsh aerospike meshes."""

from math import cos, hypot, isfinite, radians, sin, tan

from cfd.geometry.conv_nozzle import corner_fillet


CONVERGENT_NOZZLE_ANGLE = 45
CONICAL_NOZZLE_ANGLE = 20
RAO_THROAT_ANGLE = 40
BELL_LENGTH_PERCENT = 0.8
CONVERGENT_RADIUS_RATIO = 1.5
DIVERGENT_RADIUS_RATIO = 0.4
NOZZLE_POINT_COUNT = 22
FILLET_RADIUS_RATIO = 0.04
def fillet(
    contour,
    throat_length,
    convergent_radius_ratio=CONVERGENT_RADIUS_RATIO,
    divergent_radius_ratio=DIVERGENT_RADIUS_RATIO,
    boundary_layer_thickness=0.0,
    convergent_nozzle_angle=CONVERGENT_NOZZLE_ANGLE,
):
    """Replace a three-point construction with a 22-point rounded Rao profile."""
    if len(contour) != 3:
        raise ValueError("A CD nozzle construction must contain exactly three points.")
    ratios = convergent_radius_ratio, divergent_radius_ratio
    if not all(isfinite(value) for value in ratios) or min(ratios) <= 0:
        raise ValueError("CD nozzle fillet ratios must be positive.")
    if not isfinite(boundary_layer_thickness) or boundary_layer_thickness < 0:
        raise ValueError("Boundary-layer thickness must be finite and nonnegative.")

    _, transition, throat = contour
    throat_x, throat_radius = throat
    chamber_radius = transition[1]
    exit_radius = throat_length / 2
    convergent_angle = radians(convergent_nozzle_angle)
    bell_angle = radians(RAO_THROAT_ANGLE)
    inlet_length = 2 * chamber_radius
    clear_inlet_length = inlet_length - 2 * boundary_layer_thickness
    if clear_inlet_length <= 0:
        raise ValueError("The CD inlet is too narrow for its boundary layers.")
    available_fillet_radius = (
        (chamber_radius - throat_radius) / (1 - cos(convergent_angle))
    )
    # Reserve part of the corner height for the straight run between both fillets.
    inlet_radius = min(
        boundary_layer_thickness + clear_inlet_length * FILLET_RADIUS_RATIO,
        0.45 * available_fillet_radius,
    )
    if inlet_radius <= boundary_layer_thickness:
        raise ValueError("The CD inlet fillet cannot fit its boundary-layer offset.")
    convergent_radius = min(
        convergent_radius_ratio * throat_radius,
        0.9 * available_fillet_radius - inlet_radius,
    )

    # The bell control point must stay between its start and the exit.
    bell_rise = exit_radius - throat_radius
    available_bell_length = -throat_x - bell_rise / tan(bell_angle)
    if available_bell_length <= 0:
        raise ValueError("The bell is too short for its throat angle.")
    divergent_radius = min(
        divergent_radius_ratio * throat_radius,
        0.5 * available_bell_length
        / (sin(bell_angle) - (1 - cos(bell_angle)) / tan(bell_angle)),
    )

    convergent_center = throat_x, throat_radius + convergent_radius
    start_angle = -radians(90) - convergent_angle
    convergent_arc = [
        (
            convergent_center[0] + convergent_radius * cos(start_angle + convergent_angle * step / 4),
            convergent_center[1] + convergent_radius * sin(start_angle + convergent_angle * step / 4),
        )
        for step in range(5)
    ]
    if convergent_arc[0][1] >= chamber_radius:
        raise ValueError("The convergent throat fillet does not fit the contraction ratio.")

    transition = (
        convergent_arc[0][0]
        - (chamber_radius - convergent_arc[0][1]) / tan(convergent_angle),
        chamber_radius,
    )
    inlet = transition[0] - (contour[1][0] - contour[0][0]), chamber_radius
    inlet_tangent = inlet_radius * tan(convergent_angle / 2)
    inlet_fillet_start = transition[0] - inlet_tangent, chamber_radius
    inlet_fillet_end = (
        transition[0] + inlet_tangent * cos(convergent_angle),
        chamber_radius - inlet_tangent * sin(convergent_angle),
    )
    inlet_fillet = [
        inlet_fillet_start,
        *corner_fillet(inlet_fillet_start, (1, 0), -convergent_angle, inlet_radius, 3),
        inlet_fillet_end,
    ]

    divergent_center = throat_x, throat_radius + divergent_radius
    divergent_arc = [
        (
            divergent_center[0] + divergent_radius * cos(-radians(90) + bell_angle * step / 3),
            divergent_center[1] + divergent_radius * sin(-radians(90) + bell_angle * step / 3),
        )
        for step in range(1, 4)
    ]
    bell_start = divergent_arc[-1]
    bell_length = -bell_start[0]
    if bell_length <= 0 or bell_start[1] >= exit_radius:
        raise ValueError("The divergent throat fillet does not fit the bell nozzle.")

    control = (
        bell_start[0] + (exit_radius - bell_start[1]) / tan(bell_angle),
        exit_radius,
    )
    if not bell_start[0] < control[0] < 0:
        raise ValueError("The selected ratios do not leave room for the Rao parabola.")

    bell = []
    for step in range(1, 10):
        fraction = step / 9
        remaining = 1 - fraction
        bell.append((
            remaining ** 2 * bell_start[0] + 2 * remaining * fraction * control[0],
            remaining ** 2 * bell_start[1]
            + 2 * remaining * fraction * control[1]
            + fraction ** 2 * exit_radius,
        ))

    profile = [inlet, *inlet_fillet, *convergent_arc, *divergent_arc, *bell]
    assert len(profile) == NOZZLE_POINT_COUNT
    return profile


def cd_nozzle_contour(
    surface,
    throat_end,
    throat_direction,
    throat_length,
    contraction_ratio,
    expansion_ratio,
    convergent_radius_ratio=CONVERGENT_RADIUS_RATIO,
    divergent_radius_ratio=DIVERGENT_RADIUS_RATIO,
    boundary_layer_thickness=0.0,
    convergent_nozzle_angle=CONVERGENT_NOZZLE_ANGLE,
):
    """Return the extended spike surface and matching upper CD-nozzle wall."""
    if len(surface) < 2:
        raise ValueError("The aerospike contour must contain at least two points.")
    direction_length = hypot(*throat_direction)
    if direction_length == 0:
        raise ValueError("The throat direction must be non-zero.")

    radial = tuple(value / direction_length for value in throat_direction)
    axial = radial[1], -radial[0]
    center = (
        (surface[0][0] + throat_end[0]) / 2,
        (surface[0][1] + throat_end[1]) / 2,
    )
    values = throat_length, contraction_ratio, expansion_ratio
    if not all(isfinite(value) for value in values):
        raise ValueError("CD nozzle dimensions and ratios must be finite.")
    if throat_length <= 0 or contraction_ratio <= 1 or expansion_ratio <= 1:
        raise ValueError("CD nozzle length must be positive and both ratios must exceed 1.")

    angle = radians(CONICAL_NOZZLE_ANGLE)
    convergent_angle = radians(CONVERGENT_NOZZLE_ANGLE)
    if not 0 < angle < radians(90) or not 0 < convergent_angle < radians(90):
        raise ValueError("CD nozzle angles must be between 0 and 90 degrees.")

    small_throat_length = throat_length / expansion_ratio
    throat_radius = small_throat_length / 2
    chamber_radius = contraction_ratio * throat_radius
    bell_length = (
        BELL_LENGTH_PERCENT
        * (throat_length - small_throat_length) / 2
        / tan(angle)
    )
    throat = -bell_length, throat_radius
    transition = (
        throat[0] - (chamber_radius - throat_radius) / tan(convergent_angle),
        chamber_radius,
    )
    inlet = transition[0] - chamber_radius / 2, chamber_radius
    profile = fillet(
        [inlet, transition, throat], throat_length,
        convergent_radius_ratio, divergent_radius_ratio, boundary_layer_thickness,
        convergent_nozzle_angle,
    )

    def placed(side):
        return [
            (
                center[0] + x * axial[0] + side * radius * radial[0],
                center[1] + x * axial[1] + side * radius * radial[1],
            )
            for x, radius in profile
        ]

    lower, upper = placed(-1), placed(1)
    lower[-1], upper[-1] = surface[0], throat_end
    return lower[:-1] + surface, upper
