"""Convergent-divergent Rao nozzle contours for Gmsh aerospike meshes."""

from math import cos, hypot, isfinite, radians, sin, tan

from cfd.geometry.conv_thruster import corner_fillet


CONVERGENT_NOZZLE_ANGLE = 45
CONVERGENT_RADIUS_RATIO = 1.5
DIVERGENT_RADIUS_RATIO = 0.4
NOZZLE_POINT_COUNT = 22
FILLET_RADIUS_RATIO = 0.04


def _build_profile(
    throat_length,
    contraction_ratio,
    expansion_ratio,
    bell_angle,
    convergent_radius_ratio=CONVERGENT_RADIUS_RATIO,
    divergent_radius_ratio=DIVERGENT_RADIUS_RATIO,
    boundary_layer_thickness=0.0,
    convergent_nozzle_angle=CONVERGENT_NOZZLE_ANGLE,
    throat_y_slope=0.0,
):
    """Build the 22-point symmetric CD nozzle half-profile ending at the exit lip."""
    values = (
        throat_length, contraction_ratio, expansion_ratio, bell_angle,
        convergent_radius_ratio, divergent_radius_ratio,
        boundary_layer_thickness, convergent_nozzle_angle, throat_y_slope,
    )
    if not all(isfinite(value) for value in values):
        raise ValueError("CD nozzle parameters must be finite.")
    if throat_length <= 0 or contraction_ratio <= 1 or expansion_ratio <= 1:
        raise ValueError("CD nozzle length must be positive and both ratios must exceed 1.")
    if min(convergent_radius_ratio, divergent_radius_ratio) <= 0:
        raise ValueError("CD nozzle fillet ratios must be positive.")
    if boundary_layer_thickness < 0:
        raise ValueError("Boundary-layer thickness must be finite and nonnegative.")
    convergent_angle = radians(convergent_nozzle_angle)
    if not 0 < bell_angle < radians(90) or not 0 < convergent_angle < radians(90):
        raise ValueError("CD nozzle angles must be between 0 and 90 degrees.")

    exit_radius = throat_length / 2
    throat_radius = exit_radius / expansion_ratio
    for step in range(6):
        bell_rise = exit_radius - throat_radius
        divergent_radius = min(
            divergent_radius_ratio * throat_radius,
            0.5 * bell_rise / (1 - cos(bell_angle)),
        )
        arc_dx = divergent_radius * sin(bell_angle)
        arc_dr = divergent_radius * (1 - cos(bell_angle))
        throat_x = -(arc_dx + 2 * (bell_rise - arc_dr) / tan(bell_angle))
        if not throat_y_slope or step == 5:
            break
        area_scale = 1 + throat_x * throat_y_slope
        if area_scale <= 0:
            raise ValueError("Toroidal throat sits beyond the axis of symmetry.")
        throat_radius = (exit_radius / expansion_ratio) / area_scale
    if throat_radius <= boundary_layer_thickness:
        raise ValueError("The CD throat is too small for the two boundary layers.")
    if throat_radius >= exit_radius:
        raise ValueError("The CD throat radius must remain smaller than the exit radius.")

    chamber_radius = contraction_ratio * throat_radius
    inlet_length = 2 * chamber_radius
    clear_inlet_length = inlet_length - 2 * boundary_layer_thickness
    if clear_inlet_length <= 0:
        raise ValueError("The CD inlet is too narrow for its boundary layers.")
    available_fillet_radius = (chamber_radius - throat_radius) / (1 - cos(convergent_angle))
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

    transition_x = (
        convergent_arc[0][0]
        - (chamber_radius - convergent_arc[0][1]) / tan(convergent_angle)
    )
    inlet = transition_x - chamber_radius / 2, chamber_radius
    inlet_tangent = inlet_radius * tan(convergent_angle / 2)
    inlet_fillet_start = transition_x - inlet_tangent, chamber_radius
    inlet_fillet_end = (
        transition_x + inlet_tangent * cos(convergent_angle),
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
    control = bell_start[0] / 2, exit_radius
    end = 0.0, exit_radius
    knots = [0.0] * 4 + [k / 7 for k in range(1, 7)] + [1.0] * 4
    bell = []
    for t1, t2, t3 in zip(knots[2:11], knots[3:12], knots[4:13]):
        w0 = ((1 - t1) * (1 - t2) + (1 - t2) * (1 - t3) + (1 - t3) * (1 - t1)) / 3
        w2 = (t1 * t2 + t2 * t3 + t3 * t1) / 3
        w1 = 1 - w0 - w2
        bell.append((
            w0 * bell_start[0] + w1 * control[0] + w2 * end[0],
            w0 * bell_start[1] + w1 * control[1] + w2 * end[1],
        ))

    profile = [inlet, *inlet_fillet, *convergent_arc, *divergent_arc, *bell]
    assert len(profile) == NOZZLE_POINT_COUNT
    return profile


def cd_nozzle_contour(
    spike_entry,
    cowl_lip,
    throat_direction,
    throat_length,
    contraction_ratio,
    expansion_ratio,
    bell_angle,
    convergent_radius_ratio=CONVERGENT_RADIUS_RATIO,
    divergent_radius_ratio=DIVERGENT_RADIUS_RATIO,
    boundary_layer_thickness=0.0,
    convergent_nozzle_angle=CONVERGENT_NOZZLE_ANGLE,
    toroidal=False,
):
    """Return the lower and upper CD-nozzle walls placed between spike_entry and cowl_lip."""
    direction_length = hypot(*throat_direction)
    if direction_length == 0:
        raise ValueError("The throat direction must be non-zero.")

    radial = tuple(value / direction_length for value in throat_direction)
    axial = radial[1], -radial[0]
    center = (
        (spike_entry[0] + cowl_lip[0]) / 2,
        (spike_entry[1] + cowl_lip[1]) / 2,
    )
    if toroidal and center[1] <= 0:
        raise ValueError("Toroidal CD nozzle center must lie above the symmetry axis.")
    throat_y_slope = axial[1] / center[1] if toroidal else 0.0
    profile = _build_profile(
        throat_length, contraction_ratio, expansion_ratio, bell_angle,
        convergent_radius_ratio, divergent_radius_ratio,
        boundary_layer_thickness, convergent_nozzle_angle,
        throat_y_slope=throat_y_slope,
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
    lower[-1], upper[-1] = spike_entry, cowl_lip
    return lower, upper
