"""Write physical aerospike geometry as Gmsh ``.geo`` source."""

from math import hypot, isfinite

from cfd.geometry import mesh
from cfd.geometry.domain_geometry import build_geometry


MAIN_BOUNDARY_LAYER_START = 1001
SECONDARY_BOUNDARY_LAYER_START = 4001
COWL_START = 3001
WAKE_RIGHT_PROGRESSION = 1.04  # ponytail: fixed progression across wake right edge; upgrade to adaptive if needed


def _point(point_id, coordinates):
    return f"Point({point_id}) = {{{coordinates[0]:.8f}, {coordinates[1]:.8f}, 0, 1.0}};"


def _line(line_id, start, end):
    return f"Line({line_id}) = {{{start}, {end}}};"


def _id_list(entity_id, point_ids):
    chunks = [point_ids[i:i + 20] for i in range(0, len(point_ids), 20)]
    indent = " " * (len(f"BSpline({entity_id}) = {{"))
    body = (",\n" + indent).join(", ".join(map(str, chunk)) for chunk in chunks)
    return f"BSpline({entity_id}) = {{{body}}};"


def generate_geometry_file(case):
    """Return Gmsh source for a sized result from ``generate_aerospike_contour``."""
    try:
        delta_y1 = float(case["results"].get("bl_first_cell"))
    except (TypeError, ValueError) as error:
        raise ValueError("Boundary-layer first cell height ('bl_first_cell') is required.") from error
    if not isfinite(delta_y1) or delta_y1 <= 0:
        raise ValueError("Boundary-layer first cell height ('bl_first_cell') must be positive and finite.")

    geometry = build_geometry(case)
    thruster_type = geometry.thruster_type
    scale = geometry.scale
    spike = geometry.spike
    boundary_layer = geometry.boundary_layer
    cowl = geometry.cowl
    secondary_boundary_layer = geometry.secondary_boundary_layer
    truncated = geometry.truncated
    anchors = geometry.anchors
    throat_index = geometry.throat_index

    point_count = len(spike)
    spike_ids = list(range(1, point_count + 1))
    offset_ids = list(range(MAIN_BOUNDARY_LAYER_START, MAIN_BOUNDARY_LAYER_START + point_count))
    if thruster_type == "cd":
        cowl_ids = list(range(COWL_START, COWL_START + len(cowl)))
        nozzle_start, throat_end = cowl_ids[0], cowl_ids[-1]
        cowl_top, cowl_back, cowl_bottom = range(cowl_ids[-1] + 1, cowl_ids[-1] + 4)
        cowl_offset_ids = list(range(
            SECONDARY_BOUNDARY_LAYER_START,
            SECONDARY_BOUNDARY_LAYER_START + len(secondary_boundary_layer),
        ))
        offset_start, offset_throat = cowl_offset_ids[0], cowl_offset_ids[-1]
        anchor_ids = {
            "cowl_top": cowl_top,
            "cowl_back": cowl_back,
            "cowl_bottom": cowl_bottom,
        }
    else:
        nozzle_start, throat_end, cowl_top, cowl_back, cowl_bottom = range(
            COWL_START, COWL_START + 5
        )
        offset_start, offset_throat = range(
            SECONDARY_BOUNDARY_LAYER_START, SECONDARY_BOUNDARY_LAYER_START + 2
        )
        start_anchor = "convergent_start" if thruster_type == "conv" else "inlet_end"
        anchor_ids = {
            start_anchor: nozzle_start,
            "throat_end": throat_end,
            "cowl_top": cowl_top,
            "cowl_back": cowl_back,
            "cowl_bottom": cowl_bottom,
            "offset_start": offset_start,
            "offset_throat": offset_throat,
        }

    farfield_start = cowl_bottom + 1
    far_right_axis, far_right_top, far_left_top, far_left_axis = range(
        farfield_start, farfield_start + 4
    )
    anchor_ids.update({
        "far_right_axis": far_right_axis,
        "far_right_top": far_right_top,
        "far_left_top": far_left_top,
        "far_left_axis": far_left_axis,
    })
    if not truncated:
        wake_axis, wake_top = far_left_axis + 1, far_left_axis + 2
        anchor_ids.update({
            "wake_axis": wake_axis,
            "wake_top": wake_top,
        })
    fixed_points = {point_id: anchors[name] for name, point_id in anchor_ids.items()}
    farfield_end_id = wake_axis if not truncated else offset_ids[-1]
    triangle_offset_end = "107, -106, " if not truncated else ""
    thruster_loop_curve = "-111, " if throat_index > 0 else ""
    symmetry_curves = "105, 304, 308" if not truncated else "103, 304, 308"

    cfd_inputs = (case.get("cfd") or {}).get("inputs") or {}
    grid_density = cfd_inputs.get("grid_density", 1.0)
    bl_mesh_density = cfd_inputs.get("bl_mesh_density", 1.0)
    factors = mesh.density_factors(
        1.0 if grid_density is None else grid_density,
        1.0 if bl_mesh_density is None else bl_mesh_density,
    )
    farfield_cell_number = max(10, round(mesh.DEFAULT_FARFIELD_CELL_NUMBER * factors["farfield"]))
    farfield_cell_size = geometry.lengths["far_305"] / farfield_cell_number
    cowl_cell_size = mesh.DEFAULT_COWL_CELL_SIZE * scale / factors["cowl"]
    inlet_cell_number = max(3, round(mesh.DEFAULT_INLET_CELL_NUMBER * factors["inlet"]))
    inlet_cell_size = geometry.lengths["inlet"] / inlet_cell_number
    inlet_bl_cell_size = 0.9 * inlet_cell_size

    if throat_index > 0:
        thruster_bl_cell_number = max(3, round(mesh.DEFAULT_THRUSTER_BL_CELL_NUMBER * factors["thruster"]))
        thruster_bl_cell_size = geometry.lengths["thruster"] / thruster_bl_cell_number
        spike_bl_start_cell_size = thruster_bl_cell_size
    else:
        spike_bl_start_cell_size = inlet_bl_cell_size

    secondary_bl_cell_number = max(3, round(geometry.lengths["nozzle"] / spike_bl_start_cell_size))
    spike_bl_cell_number = max(3, round(mesh.DEFAULT_SPIKE_BL_CELL_NUMBER * factors["spike"]))
    spike_bl_curve, spike_bl_end_cell_size = mesh.beta_fixed_n(
        "1, 101", geometry.lengths["spike"], spike_bl_start_cell_size, spike_bl_cell_number
    )

    bl_thickness = hypot(boundary_layer[0][0] - spike[0][0], boundary_layer[0][1] - spike[0][1])
    bl_cell_number, bl_progression = mesh.bl_cells_and_progression(bl_thickness, delta_y1)
    boundary_layer_curves = "102, 104, 202, 203, 103" if throat_index > 0 else "102, 202, 203, 103"

    if not truncated:
        rp = WAKE_RIGHT_PROGRESSION
        wake_right_bot = anchors["wake_top"][1] * (rp - 1.0) / (rp ** bl_cell_number - 1.0)
        wake_cell_number = max(3, round(geometry.lengths["wake"] / spike_bl_end_cell_size))
        wake_geometry = [
            "",
            "// Wake block geometry",
            _point(wake_axis, fixed_points[wake_axis]),
            _point(wake_top, fixed_points[wake_top]),
            _line(105, spike_ids[-1], wake_axis),
            _line(106, offset_ids[-1], wake_top),
            _line(107, wake_axis, wake_top),
        ]
        wake_surface = [
            "",
            "// Quad mesh surface - Wake Relaxation",
            "Curve Loop(104) = {106, -107, -105, 103};",
            "Plane Surface(104) = {104};",
            "Transfinite Surface {104};",
            "Recombine Surface {104};",
        ]
        wake_mesh = [
            mesh.transfinite("105, 106", wake_cell_number, "Progression", 1),
            mesh.transfinite("107", bl_cell_number, "Progression", rp),
        ]
    else:
        wake_right_bot = None
        wake_geometry = []
        wake_surface = []
        wake_mesh = []

    if thruster_type == "cd":
        nozzle_points_and_curves = [
            "// CD Nozzle",
            *(_point(i, point) for i, point in zip(cowl_ids, cowl)),
            "",
            "// Cowl Boundary Layer",
            *(_point(i, point) for i, point in zip(cowl_offset_ids, secondary_boundary_layer)),
            "",
            "// CD Nozzle",
            _id_list(2, cowl_ids),
            _line(202, nozzle_start, offset_start),
            _id_list(201, cowl_offset_ids),
            _line(203, throat_end, offset_throat),
        ]
    else:
        nozzle_label = "Convergent Nozzle" if thruster_type == "conv" else "Buffered throat"
        nozzle_points_and_curves = [
            f"// {nozzle_label}",
            _point(nozzle_start, fixed_points[nozzle_start]),
            _point(throat_end, fixed_points[throat_end]),
            "",
            "// Cowl Boundary Layer",
            _point(offset_start, fixed_points[offset_start]),
            _point(offset_throat, fixed_points[offset_throat]),
            "",
            f"// {nozzle_label}",
            _line(2, nozzle_start, throat_end),
            _line(202, nozzle_start, offset_start),
            _line(201, offset_start, offset_throat),
            _line(203, throat_end, offset_throat),
        ]

    nozzle_geometry = [
        *nozzle_points_and_curves,
        "",
        "// Cowl",
        _point(cowl_top, fixed_points[cowl_top]),
        _point(cowl_back, fixed_points[cowl_back]),
        _point(cowl_bottom, fixed_points[cowl_bottom]),
        _line(301, throat_end, cowl_top),
        _line(302, cowl_top, cowl_back),
        _line(303, cowl_back, cowl_bottom),
        "",
        "// Inlet",
        _line(102, spike_ids[0], offset_ids[0]),
        _line(10, offset_start, offset_ids[0]),
        "",
        "// Offset end line",
        _line(103, spike_ids[-1], offset_ids[-1]),
        *wake_geometry,
    ]

    triangle_loop = (
        f"Curve Loop(1) = {{304, 305, 306, 307, 308, {triangle_offset_end}-101, "
        f"{thruster_loop_curve}-10, 201, -203, 301, 302, 303}};"
    )
    cowl_surface = [
        "",
        "// Quad mesh surface - Cowl Boundary Layer",
        "Curve Loop(103) = {2, 203, -201, -202};",
        "Plane Surface(103) = {103};",
        f"Transfinite Surface {{103}} = {{{nozzle_start}, {throat_end}, {offset_throat}, {offset_start}}};",
        "Recombine Surface {103};",
    ]

    if throat_index > 0:
        spike_splines = [
            _id_list(11, spike_ids[:throat_index + 1]),
            "",
            _id_list(111, offset_ids[:throat_index + 1]),
            "",
            _id_list(1, spike_ids[throat_index:]),
            "",
            _id_list(101, offset_ids[throat_index:]),
            "",
            _line(104, spike_ids[throat_index], offset_ids[throat_index]),
        ]
        spike_bl_surfaces = [
            "// Quad mesh surface - Thruster Boundary Layer",
            "Curve Loop(102) = {111, -104, -11, 102};",
            "Plane Surface(102) = {102};",
            "",
            "Transfinite Surface {102};",
            "Recombine Surface {102};",
            "",
            "// Quad mesh surface - Boundary Layer",
            "Curve Loop(101) = {101, -103, -1, 104};",
            "Plane Surface(101) = {101};",
            "",
            "Transfinite Surface {101};",
            "Recombine Surface {101};",
        ]
        fluid_surfaces = "1, 101, 102, 103"
        spike_bc_curves = "11, 1"
        thruster_bl_mesh = [mesh.transfinite("11, 111", thruster_bl_cell_number, "Progression", 1)]
    else:
        spike_splines = [
            _id_list(1, spike_ids),
            "",
            _id_list(101, offset_ids),
        ]
        spike_bl_surfaces = [
            "// Quad mesh surface - Boundary Layer",
            "Curve Loop(101) = {101, -103, -1, 102};",
            "Plane Surface(101) = {101};",
            "",
            "Transfinite Surface {101};",
            "Recombine Surface {101};",
        ]
        fluid_surfaces = "1, 101, 103"
        spike_bc_curves = "1"
        thruster_bl_mesh = []

    if not truncated:
        fluid_surfaces += ", 104"

    lines = [
        "// Aerospike Simulation Geometry",
        'SetFactory("OpenCASCADE");',
        "",
        "",
        "// ---------------------------------------- Spike geometry ----------------------------------------",
        "",
        *(_point(i, point) for i, point in zip(spike_ids, spike)),
        "",
        "",
        "// ---------------------------------------- Spike offset geometry ----------------------------------------",
        "",
        *(_point(i, point) for i, point in zip(offset_ids, boundary_layer)),
        "",
        "",
        *spike_splines,
        "",
        "",
        *nozzle_geometry,
        "",
        "",
        "",
        "// ---------------------------------------- Farfield Geometry -------------------------------------",
        "",
        "// Points Definition : counterclockwise from symmetry-end",
        *(_point(i, fixed_points[i]) for i in (far_right_axis, far_right_top, far_left_top, far_left_axis)),
        "",
        "// Lines Definition",
        f"{_line(304, cowl_bottom, far_left_axis)}     // symmetry (right side, above the spike)",
        f"{_line(305, far_left_axis, far_left_top)}     // left",
        f"{_line(306, far_left_top, far_right_top)}     // top",
        f"{_line(307, far_right_top, far_right_axis)}     // right (outflow)",
        f"{_line(308, far_right_axis, farfield_end_id)}     // symmetry (left side, below the spike)",
        "",
        "",
        "// ---------------------------------------- Surfaces Definition -----------------------------------",
        "",
        "// Triangle mesh surface",
        triangle_loop,
        "Plane Surface(1) = {1};",
        "",
        "",
        *spike_bl_surfaces,
        *wake_surface,
        *cowl_surface,
        "",
        "// Flow domain",
        f'Physical Surface("fluid", 1) = {{{fluid_surfaces}}};',
        "",
        "",
        "// ---------------------------------------- BC Definition ------------------------------------------",
        "",
        "// Domain ends",
        f'Physical Curve("symmetry", 50) = {{{symmetry_curves}}};',
        'Physical Curve("farRight", 51) = {307};',
        'Physical Curve("farTop", 52) = {306};',
        'Physical Curve("farLeft", 53) = {305};',
        "",
        "// Walls",
        f'Physical Curve("spike", 54) = {{{spike_bc_curves}}};',
        'Physical Curve("cowl", 55) = {2, 301, 302, 303};',
        "",
        "// Inlet",
        'Physical Curve("inlet", 56) = {102, 10, 202};',
        "",
        "",
        "// ---------------------------------------- Mesh Definition ----------------------------------------",
        "",
        "",
        "// Boundary Layer",
        *thruster_bl_mesh,
        spike_bl_curve,
        mesh.transfinite(boundary_layer_curves, bl_cell_number, "Progression", bl_progression),
        *wake_mesh,
        "",
        "// Inlet & Nozzle",
        mesh.transfinite("10", inlet_cell_number, "Progression", 1),
        mesh.transfinite("2, 201", secondary_bl_cell_number, "Progression", 1),
        "",
        "// Cowl",
        mesh.beta("301", geometry.lengths["cowl_301"], delta_y1, cowl_cell_size, 1.1, min_cells=3),
        *(
            mesh.transfinite(
                str(curve),
                max(3, round(geometry.lengths[f"cowl_{curve}"] / cowl_cell_size)),
                "Progression",
                1,
            )
            for curve in (302, 303)
        ),
        "",
        "// Farfield",
        mesh.beta("304", geometry.lengths["far_304"], cowl_cell_size, farfield_cell_size, 1.2, min_cells=10),
        mesh.transfinite("305, 307", farfield_cell_number, "Progression", 1),
        mesh.transfinite("306", max(10, round(geometry.lengths["far_306"] / farfield_cell_size)), "Progression", 1),
        mesh.beta(
            "-308",
            geometry.lengths["far_308"],
            wake_right_bot if not truncated else spike_bl_end_cell_size,
            farfield_cell_size,
            1.02,
            min_cells=10,
        ),
        "",
    ]
    return "\n".join(lines)
