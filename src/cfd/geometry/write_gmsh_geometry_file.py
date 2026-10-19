"""Write physical aerospike geometry as Gmsh ``.geo`` source."""

from cfd.geometry import mesh_definition as mesh
from cfd.geometry.geometry_definition import build_geometry


MAIN_BOUNDARY_LAYER_START = 1001
SECONDARY_BOUNDARY_LAYER_START = 4001
COWL_START = 3001


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
    geometry = build_geometry(case)
    thruster_type = geometry.thruster_type
    scale = geometry.scale
    spike = geometry.spike
    boundary_layer = geometry.boundary_layer
    cowl = geometry.cowl
    secondary_boundary_layer = geometry.secondary_boundary_layer
    truncated = geometry.truncated
    anchors = geometry.anchors
    mesh_settings = mesh.NOZZLE_MESH

    point_count = len(spike)
    spike_ids = list(range(1, point_count + 1))
    offset_ids = list(range(MAIN_BOUNDARY_LAYER_START, MAIN_BOUNDARY_LAYER_START + point_count))
    if thruster_type == "cd":
        if cowl is None or secondary_boundary_layer is None:
            raise ValueError("CD geometry requires cowl and secondary boundary-layer contours.")
        cowl_ids = list(range(COWL_START, COWL_START + len(cowl)))
        convergent_start, throat_end = cowl_ids[0], cowl_ids[-1]
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
    elif thruster_type == "conv":
        convergent_start, throat_end, cowl_top, cowl_back, cowl_bottom = range(
            COWL_START, COWL_START + 5
        )
        offset_start, offset_throat = range(
            SECONDARY_BOUNDARY_LAYER_START, SECONDARY_BOUNDARY_LAYER_START + 2
        )
        anchor_ids = {
            "convergent_start": convergent_start,
            "throat_end": throat_end,
            "cowl_top": cowl_top,
            "cowl_back": cowl_back,
            "cowl_bottom": cowl_bottom,
            "offset_start": offset_start,
            "offset_throat": offset_throat,
        }
    else:
        inlet_end, throat_end, cowl_top, cowl_back, cowl_bottom = range(
            COWL_START, COWL_START + 5
        )
        offset_start, offset_throat = range(
            SECONDARY_BOUNDARY_LAYER_START, SECONDARY_BOUNDARY_LAYER_START + 2
        )
        anchor_ids = {
            "inlet_end": inlet_end,
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
    fixed_points = {point_id: anchors[name] for name, point_id in anchor_ids.items()}
    farfield_end_id = spike_ids[-1] if not truncated else offset_ids[-1]
    triangle_offset_end = "103, " if not truncated else ""
    symmetry_curves = "304, 308" if not truncated else "103, 304, 308"
    cells = {key: mesh.cells(length, scale, mesh_settings, key, 10)
             for key, length in geometry.lengths.items()}
    cells["bl"] = mesh.BOUNDARY_LAYER_POINT_COUNT - 1
    cells["inlet"] = mesh.INLET_POINT_COUNT - 1
    if thruster_type == "cd":
        nozzle_geometry = [
            "// CD Nozzle",
            *(_point(i, point) for i, point in zip(cowl_ids, cowl)),
            "",
            "// Cowl",
            _point(cowl_top, fixed_points[cowl_top]),
            _point(cowl_back, fixed_points[cowl_back]),
            _point(cowl_bottom, fixed_points[cowl_bottom]),
            "",
            "// Cowl Boundary Layer",
            *(_point(i, point) for i, point in zip(cowl_offset_ids, secondary_boundary_layer)),
            "",
            "// Inlet",
            _line(102, spike_ids[0], offset_ids[0]),
            _line(10, offset_start, offset_ids[0]),
            "",
            "// Offset end line",
            _line(103, spike_ids[-1], offset_ids[-1]),
            "",
            "// CD Nozzle",
            _id_list(2, cowl_ids),
            _line(202, convergent_start, offset_start),
            _id_list(201, cowl_offset_ids),
            _line(203, throat_end, offset_throat),
            "",
            "// Cowl",
            _line(301, throat_end, cowl_top),
            _line(302, cowl_top, cowl_back),
            _line(303, cowl_back, cowl_bottom),
        ]
        triangle_loop = (
            f"Curve Loop(1) = {{304, 305, 306, 307, 308, {triangle_offset_end}-101, -10, 201, -203, 301, 302, 303}};"
        )
        cowl_surface = [
            "",
            "// Quad mesh surface - Cowl Boundary Layer",
            "Curve Loop(103) = {2, 203, -201, -202};",
            "Plane Surface(103) = {103};",
            f"Transfinite Surface {{103}} = {{{convergent_start}, {throat_end}, {offset_throat}, {offset_start}}};",
            "Recombine Surface {103};",
        ]
        inlet_curves = "102, 10, 202"
        boundary_layer_curves = "102, 103"
        nozzle_mesh = [
            "// Inlet",
            mesh.transfinite("10", cells["inlet"], "Bump", 0.5),
            "",
            "// Cowl boundary layer",
            mesh.transfinite("202, 203", cells["bl"], "Progression",
                             mesh.progression(mesh_settings, "bl", cells["bl"])),
            "",
            "// CD Nozzle",
            mesh.transfinite("2, 201", 2 * cells["nozzle"], "Progression",
                             mesh.progression(mesh_settings, "nozzle", 2 * cells["nozzle"])),
            "",
            "// Cowl",
            *(mesh.transfinite(str(curve), cells[f"cowl_{curve}"], "Progression",
                               mesh.progression(mesh_settings, f"cowl_{curve}", cells[f"cowl_{curve}"])) for curve in (301, 302, 303)),
        ]
    elif thruster_type == "conv":
        nozzle_geometry = [
            "// Convergent Nozzle",
            _point(convergent_start, fixed_points[convergent_start]),
            _point(throat_end, fixed_points[throat_end]),
            "",
            "// Cowl",
            _point(cowl_top, fixed_points[cowl_top]),
            _point(cowl_back, fixed_points[cowl_back]),
            _point(cowl_bottom, fixed_points[cowl_bottom]),
            "",
            "// Cowl Boundary Layer",
            _point(offset_start, fixed_points[offset_start]),
            _point(offset_throat, fixed_points[offset_throat]),
            "",
            "// Inlet",
            _line(102, spike_ids[0], offset_ids[0]),
            _line(10, offset_start, offset_ids[0]),
            "",
            "// Offset end line",
            _line(103, spike_ids[-1], offset_ids[-1]),
            "",
            "// Convergent Nozzle",
            _line(2, convergent_start, throat_end),
            _line(202, convergent_start, offset_start),
            _line(201, offset_start, offset_throat),
            _line(203, throat_end, offset_throat),
            "",
            "// Cowl",
            _line(301, throat_end, cowl_top),
            _line(302, cowl_top, cowl_back),
            _line(303, cowl_back, cowl_bottom),
        ]
        triangle_loop = (
            f"Curve Loop(1) = {{304, 305, 306, 307, 308, {triangle_offset_end}-101, -10, 201, -203, 301, 302, 303}};"
        )
        cowl_surface = [
            "",
            "// Quad mesh surface - Cowl Boundary Layer",
            "Curve Loop(103) = {2, 203, -201, -202};",
            "Plane Surface(103) = {103};",
            f"Transfinite Surface {{103}} = {{{convergent_start}, {throat_end}, {offset_throat}, {offset_start}}};",
            "Recombine Surface {103};",
        ]
        inlet_curves = "102, 10, 202"
        boundary_layer_curves = "102, 202, 203, 103"
        nozzle_mesh = [
            "// Inlet",
            mesh.transfinite("10", cells["inlet"], "Bump", 0.5),
            "",
            "// Convergent Nozzle",
            mesh.transfinite("2, 201", cells["nozzle"], "Progression",
                             mesh.progression(mesh_settings, "nozzle", cells["nozzle"])),
            "",
            "// Cowl",
            *(mesh.transfinite(str(curve), cells[f"cowl_{curve}"], "Progression",
                               mesh.progression(mesh_settings, f"cowl_{curve}", cells[f"cowl_{curve}"])) for curve in (301, 302, 303)),
        ]
    else:
        nozzle_geometry = [
            "// Buffered throat",
            _point(inlet_end, fixed_points[inlet_end]),
            _point(throat_end, fixed_points[throat_end]),
            "",
            "// Cowl",
            _point(cowl_top, fixed_points[cowl_top]),
            _point(cowl_back, fixed_points[cowl_back]),
            _point(cowl_bottom, fixed_points[cowl_bottom]),
            "",
            "// Cowl Boundary Layer",
            _point(offset_start, fixed_points[offset_start]),
            _point(offset_throat, fixed_points[offset_throat]),
            "",
            "// Inlet",
            _line(102, spike_ids[0], offset_ids[0]),
            _line(10, offset_start, offset_ids[0]),
            "",
            "// Offset end line",
            _line(103, spike_ids[-1], offset_ids[-1]),
            "",
            "// Buffered throat",
            _line(2, inlet_end, throat_end),
            _line(202, inlet_end, offset_start),
            _line(201, offset_start, offset_throat),
            _line(203, throat_end, offset_throat),
            "",
            "// Cowl",
            _line(301, throat_end, cowl_top),
            _line(302, cowl_top, cowl_back),
            _line(303, cowl_back, cowl_bottom),
        ]
        triangle_loop = (
            f"Curve Loop(1) = {{304, 305, 306, 307, 308, {triangle_offset_end}-101, -10, 201, -203, 301, 302, 303}};"
        )
        cowl_surface = [
            "",
            "// Quad mesh surface - Cowl Boundary Layer",
            "Curve Loop(103) = {2, 203, -201, -202};",
            "Plane Surface(103) = {103};",
            f"Transfinite Surface {{103}} = {{{inlet_end}, {throat_end}, {offset_throat}, {offset_start}}};",
            "Recombine Surface {103};",
        ]
        inlet_curves = "102, 10, 202"
        boundary_layer_curves = "102, 202, 203, 103"
        nozzle_mesh = [
            "// Inlet",
            mesh.transfinite("10", cells["inlet"], "Bump", 0.5),
            "",
            "// Buffered throat",
            mesh.transfinite("2, 201", 2 * cells["nozzle"], "Progression", 1),
            "",
            "// Cowl",
            *(mesh.transfinite(str(curve), cells[f"cowl_{curve}"], "Progression",
                               mesh.progression(mesh_settings, f"cowl_{curve}", cells[f"cowl_{curve}"])) for curve in (301, 302, 303)),
        ]

    fluid_surfaces = "1, 101, 103"

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
        _id_list(1, spike_ids),
        "",
        _id_list(101, offset_ids),
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
        "// Quad mesh surface - Boundary Layer",
        "Curve Loop(101) = {101, -103, -1, 102};",
        "Plane Surface(101) = {101};",
        "",
        "Transfinite Surface {101};",
        "Recombine Surface {101};",
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
        'Physical Curve("spike", 54) = {1};',
        'Physical Curve("cowl", 55) = {2, 301, 302, 303};',
        "",
        "// Inlet",
        f'Physical Curve("inlet", 56) = {{{inlet_curves}}};',
        "",
        "",
        "// ---------------------------------------- Mesh Definition ----------------------------------------",
        "",
        "",
        "// Boundary Layer",
        mesh.transfinite("1, 101", cells["spike"], "Progression", mesh.progression(mesh_settings, "spike", cells["spike"])),
        mesh.transfinite(boundary_layer_curves, cells["bl"], "Progression",
                         mesh.progression(mesh_settings, "bl", cells["bl"])),
        "",
        *nozzle_mesh,
        "",
        "",
        "// Farfield",
        *(mesh.transfinite(str(curve), cells[f"far_{curve}"], "Progression",
                           mesh.progression(mesh_settings, f"far_{curve}", cells[f"far_{curve}"])) for curve in (304, 305, 306, 307, 308)),
        "",
    ]
    return "\n".join(lines)
