import os, sys, math, tempfile, pathlib

td = tempfile.mkdtemp()
os.environ['USERPROFILE'] = td
os.environ['HOME'] = td
sys.path.insert(0, os.path.abspath('src'))

from core.input import process_inputs_on_solve
from core import geometry as geom
from cfd.geometry.domain_geometry import build_geometry, _curve_length, _distance
import cfd.geometry.domain_geometry as dg
import cfd.geometry.write_gmsh_geometry_file as wggf
from cfd.geometry import mesh
from cfd.mesh_quality import compute_gmsh_mesh_quality
import gmsh

def build_case(raw):
    process_inputs_on_solve(raw)
    res, cfd_setup, gerrs = geom.generate_aerospike_contour(raw)
    if gerrs:
        raise RuntimeError(f'Contour error: {gerrs}')
    return {
        'definition': raw,
        'results': res,
        'cfd': {
            'inputs': {
                'contraction_ratio': 3.0,
                'convergent_nozzle_angle': 45.0,
                'thruster_nozzle': False,
                'grid_density': 1.0,
                'bl_mesh_density': 1.0,
            }
        }
    }

def generate_geo_custom(case, wake_mode='beta', line308_start='wake_right_bot', max_end_bl_k=None):
    if max_end_bl_k is not None:
        old_factor = dg.MAX_END_BL_FACTOR
        dg.MAX_END_BL_FACTOR = max_end_bl_k
    try:
        geometry = build_geometry(case)
    finally:
        if max_end_bl_k is not None:
            dg.MAX_END_BL_FACTOR = old_factor

    scale = geometry.scale
    spike = geometry.spike
    boundary_layer = geometry.boundary_layer
    truncated = geometry.truncated
    anchors = geometry.anchors
    throat_index = geometry.throat_index
    point_count = len(spike)

    spike_ids = list(range(1, point_count + 1))
    offset_ids = list(range(wggf.MAIN_BOUNDARY_LAYER_START, wggf.MAIN_BOUNDARY_LAYER_START + point_count))
    nozzle_start, throat_end, cowl_top, cowl_back, cowl_bottom = range(wggf.COWL_START, wggf.COWL_START + 5)
    offset_start, offset_throat = range(wggf.SECONDARY_BOUNDARY_LAYER_START, wggf.SECONDARY_BOUNDARY_LAYER_START + 2)
    start_anchor = 'convergent_start' if geometry.thruster_type == 'conv' else 'inlet_end'
    anchor_ids = {
        start_anchor: nozzle_start, 'throat_end': throat_end, 'cowl_top': cowl_top,
        'cowl_back': cowl_back, 'cowl_bottom': cowl_bottom, 'offset_start': offset_start, 'offset_throat': offset_throat,
    }
    farfield_start = cowl_bottom + 1
    far_right_axis, far_right_top, far_left_top, far_left_axis = range(farfield_start, farfield_start + 4)
    anchor_ids.update({'far_right_axis': far_right_axis, 'far_right_top': far_right_top, 'far_left_top': far_left_top, 'far_left_axis': far_left_axis})
    wake_axis, wake_top = far_left_axis + 1, far_left_axis + 2
    anchor_ids.update({'wake_axis': wake_axis, 'wake_top': wake_top})
    fixed_points = {pid: anchors[name] for name, pid in anchor_ids.items()}

    cfd_inputs = (case.get('cfd') or {}).get('inputs') or {}
    factors = mesh.density_factors(cfd_inputs.get('grid_density', 1.0), cfd_inputs.get('bl_mesh_density', 1.0))
    farfield_cell_size = mesh.DEFAULT_FARFIELD_CELL_SIZE * scale / factors['farfield']
    cowl_cell_size = mesh.DEFAULT_COWL_CELL_SIZE * scale / factors['cowl']
    inlet_cell_number = max(3, round(mesh.DEFAULT_INLET_CELL_NUMBER * factors['inlet']))
    inlet_cell_size = geometry.lengths['inlet'] / inlet_cell_number
    inlet_bl_cell_size = 0.9 * inlet_cell_size
    spike_bl_start_cell_size = inlet_bl_cell_size

    spike_bl_cell_number = max(3, round(mesh.DEFAULT_SPIKE_BL_CELL_NUMBER * factors['spike']))
    spike_bl_curve, spike_bl_end_cell_size = mesh.beta_fixed_n(
        '1, 101', geometry.lengths['spike'], spike_bl_start_cell_size, spike_bl_cell_number
    )

    delta_y1 = float(case['results']['bl_first_cell'])
    bl_thickness = math.hypot(boundary_layer[0][0] - spike[0][0], boundary_layer[0][1] - spike[0][1])
    bl_cell_number, bl_progression = mesh.bl_cells_and_progression(bl_thickness, delta_y1)
    boundary_layer_curves = '102, 202, 203, 103'

    rp = wggf.WAKE_RIGHT_PROGRESSION
    wake_h = anchors['wake_top'][1]
    wake_right_bot = wake_h * (rp - 1.0) / (rp ** bl_cell_number - 1.0)
    wake_right_top = wake_right_bot * (rp ** (bl_cell_number - 1))

    end_bl_thickness = _distance(spike[-1], boundary_layer[-1])

    wake_geometry = [
        '', '// Wake block geometry',
        wggf._point(wake_axis, fixed_points[wake_axis]),
        wggf._point(wake_top, fixed_points[wake_top]),
        wggf._line(105, spike_ids[-1], wake_axis),
        wggf._line(106, offset_ids[-1], wake_top),
        wggf._line(107, wake_axis, wake_top),
    ]
    wake_surface = [
        '', '// Quad mesh surface - Wake Relaxation',
        'Curve Loop(104) = {106, -107, -105, 103};',
        'Plane Surface(104) = {104};',
        'Transfinite Surface {104};',
        'Recombine Surface {104};',
    ]

    if wake_mode == 'beta':
        wake_mesh = [
            mesh.beta('105, 106', geometry.lengths['wake'], spike_bl_end_cell_size, wake_right_top, 1.05, min_cells=10),
            mesh.transfinite('107', bl_cell_number, 'Progression', wggf.WAKE_RIGHT_PROGRESSION),
        ]
    elif wake_mode == 'uniform':
        wake_mesh = [
            mesh.transfinite('105, 106', max(3, round(geometry.lengths['wake'] / spike_bl_end_cell_size)), 'Progression', 1),
            mesh.transfinite('107', bl_cell_number, 'Progression', wggf.WAKE_RIGHT_PROGRESSION),
        ]
    else:
        raise ValueError(f'Unknown wake_mode {wake_mode}')

    nozzle_geometry = [
        '// Buffered throat',
        wggf._point(nozzle_start, fixed_points[nozzle_start]),
        wggf._point(throat_end, fixed_points[throat_end]),
        '', '// Cowl Boundary Layer',
        wggf._point(offset_start, fixed_points[offset_start]),
        wggf._point(offset_throat, fixed_points[offset_throat]),
        '', '// Buffered throat',
        wggf._line(2, nozzle_start, throat_end),
        wggf._line(202, nozzle_start, offset_start),
        wggf._line(201, offset_start, offset_throat),
        wggf._line(203, throat_end, offset_throat),
        '', '// Cowl',
        wggf._point(cowl_top, fixed_points[cowl_top]),
        wggf._point(cowl_back, fixed_points[cowl_back]),
        wggf._point(cowl_bottom, fixed_points[cowl_bottom]),
        wggf._line(301, throat_end, cowl_top),
        wggf._line(302, cowl_top, cowl_back),
        wggf._line(303, cowl_back, cowl_bottom),
        '', '// Inlet',
        wggf._line(102, spike_ids[0], offset_ids[0]),
        wggf._line(10, offset_start, offset_ids[0]),
        '', '// Offset end line',
        wggf._line(103, spike_ids[-1], offset_ids[-1]),
        *wake_geometry,
    ]

    triangle_loop = 'Curve Loop(1) = {304, 305, 306, 307, 308, 107, -106, -101, -10, 201, -203, 301, 302, 303};'
    cowl_surface = [
        '', '// Quad mesh surface - Cowl Boundary Layer',
        'Curve Loop(103) = {2, 203, -201, -202};',
        'Plane Surface(103) = {103};',
        f'Transfinite Surface {{103}} = {{{nozzle_start}, {throat_end}, {offset_throat}, {offset_start}}};',
        'Recombine Surface {103};',
    ]

    spike_bl_surfaces = [
        '// Quad mesh surface - Aerospike Boundary Layer',
        'Curve Loop(101) = {1, 103, -101, -102};',
        'Plane Surface(101) = {101};',
        f'Transfinite Surface {{101}} = {{{spike_ids[0]}, {spike_ids[-1]}, {offset_ids[-1]}, {offset_ids[0]}}};',
        'Recombine Surface {101};',
    ]

    line308_start_size = wake_right_bot if line308_start == 'wake_right_bot' else spike_bl_end_cell_size

    lines = [
        '// Aerospike Simulation Geometry',
        'SetFactory("OpenCASCADE");',
        *([wggf._point(i, point) for i, point in zip(spike_ids, spike)]),
        *([wggf._point(i, point) for i, point in zip(offset_ids, boundary_layer)]),
        '',
        wggf._id_list(1, spike_ids),
        wggf._id_list(101, offset_ids),
        *nozzle_geometry,
        '', '// Farfield domain',
        wggf._point(far_right_axis, fixed_points[far_right_axis]),
        wggf._point(far_right_top, fixed_points[far_right_top]),
        wggf._point(far_left_top, fixed_points[far_left_top]),
        wggf._point(far_left_axis, fixed_points[far_left_axis]),
        wggf._line(304, far_left_axis, cowl_bottom),
        wggf._line(305, far_left_top, far_left_axis),
        wggf._line(306, far_right_top, far_left_top),
        wggf._line(307, far_right_axis, far_right_top),
        wggf._line(308, wake_axis, far_right_axis),
        '', *spike_bl_surfaces, *wake_surface, *cowl_surface,
        '', '// Flow domain',
        triangle_loop,
        'Plane Surface(1) = {1};',
        'Mesh.Algorithm = 6;',
        '', '// Mesh setup',
        '// Boundary Layer',
        spike_bl_curve,
        mesh.transfinite(boundary_layer_curves, bl_cell_number, 'Progression', bl_progression),
        *wake_mesh,
        '', '// Inlet & Nozzle',
        mesh.transfinite('10', inlet_cell_number, 'Progression', 1),
        mesh.transfinite('2, 201', inlet_cell_number, 'Progression', 1),
        mesh.transfinite('202, 203', bl_cell_number, 'Progression', bl_progression),
        '', '// Farfield & Cowl mesh',
        mesh.transfinite('301', max(10, round(geometry.lengths['cowl_301'] / cowl_cell_size)), 'Progression', 1),
        mesh.transfinite('302', max(10, round(geometry.lengths['cowl_302'] / farfield_cell_size)), 'Progression', 1),
        mesh.transfinite('303', max(10, round(geometry.lengths['cowl_303'] / farfield_cell_size)), 'Progression', 1),
        mesh.transfinite('304', max(10, round(geometry.lengths['far_304'] / farfield_cell_size)), 'Progression', 1),
        *(
            mesh.transfinite(
                str(curve),
                max(10, round(geometry.lengths[f'far_{curve}'] / farfield_cell_size)),
                'Progression',
                1,
            )
            for curve in (305, 306, 307)
        ),
        mesh.beta(
            '-308',
            geometry.lengths['far_308'],
            line308_start_size,
            farfield_cell_size,
            1.02,
            min_cells=10,
        ),
        '',
        '// Physical groups',
        'Physical Surface("FLUID") = {1, 101, 104, 103};',
        'Physical Curve("FARFIELD") = {302, 303, 305, 306, 307};',
        'Physical Curve("INLET") = {10};',
        'Physical Curve("SYMMETRY") = {105, 304, 308};',
        'Physical Curve("WALL") = {1, 2, 301};',
        '',
    ]
    meta = {
        'end_bl_thickness': end_bl_thickness,
        'spike_bl_end_cell_size': spike_bl_end_cell_size,
        'wake_right_bot': wake_right_bot,
        'wake_right_top': wake_right_top,
        'wake_length': geometry.lengths['wake'],
    }
    return '\n'.join(lines), meta

def mesh_and_eval(geo_src):
    geo_file = pathlib.Path(td) / 'temp_eval.geo'
    geo_file.write_text(geo_src, encoding='utf-8')
    gmsh.initialize(interruptible=False)
    gmsh.option.setNumber('General.Terminal', 0)
    try:
        gmsh.open(str(geo_file))
        gmsh.model.mesh.generate(2)
        q = compute_gmsh_mesh_quality()
    finally:
        gmsh.finalize()
    return q

# Define test cases:
# 1. Kerolox eps=10 baseline
case_kerolox_raw = {
    'oxidizer': 'LOX', 'fuel': 'RP1', 'Pc': 20.0, 'unit_Pc': 'bar', 'MR': 2.3,
    'nozzle_choice': 'area_ratio', 'eps': 10.0, 'design_pressure': None, 'unit_design_pressure': 'bar',
    'p_design': None, 'unit_p_design': 'bar', 'effective_throat_eps': 1.0, 'truncate_percent': 100.0,
    'aerospike_resolution': 100, 'sizing': True, 'aerospike_type': 'toroidal', 'mfr': None, 'unit_mfr': None,
    'radius': 0.1, 'unit_radius': 'm', 'width': None, 'unit_width': None, 'length': None, 'unit_length': None,
}
case_kerolox = build_case(case_kerolox_raw)

# 2. Hydrolox eps=250 toroidal (teps=2.0)
case_hydrolox_raw = {
    'oxidizer': 'LOX', 'fuel': 'LH2', 'Pc': 100.0, 'unit_Pc': 'bar', 'MR': 6.0,
    'nozzle_choice': 'area_ratio', 'eps': 250.0, 'design_pressure': None, 'unit_design_pressure': 'bar',
    'p_design': None, 'unit_p_design': 'bar', 'effective_throat_eps': 2.0, 'truncate_percent': 100.0,
    'aerospike_resolution': 100, 'sizing': True, 'aerospike_type': 'toroidal', 'mfr': None, 'unit_mfr': None,
    'radius': 0.1, 'unit_radius': 'm', 'width': None, 'unit_width': None, 'length': None, 'unit_length': None,
}
case_hydrolox = build_case(case_hydrolox_raw)

print("Starting simulations...")
test_matrix = [
    ("Kerolox eps=10 (Current repo: Beta wake, Line(-308) from wake_right_bot)", case_kerolox, 'beta', 'wake_right_bot', None),
    ("Kerolox eps=10 (Uniform wake, Line(-308) from wake_right_bot)", case_kerolox, 'uniform', 'wake_right_bot', None),
    ("Kerolox eps=10 (Uniform wake, Line(-308) from spike_bl_end_cell_size)", case_kerolox, 'uniform', 'spike_bl_end_cell_size', None),
    ("Kerolox eps=10 (Beta wake, Line(-308) from spike_bl_end_cell_size)", case_kerolox, 'beta', 'spike_bl_end_cell_size', None),
    
    ("Hydrolox eps=250 (Current repo 0.04*scale clamp, Beta wake, Line(-308) from wake_right_bot)", case_hydrolox, 'beta', 'wake_right_bot', 0.04),
    ("Hydrolox eps=250 (k*spike_length clamp k=0.007, Beta wake, Line(-308) from wake_right_bot)", case_hydrolox, 'beta', 'wake_right_bot', 0.04), # wait, let's see how k is clamped
]

for label, c, w_mode, l308, k_factor in test_matrix[:4]:
    print(f"\nRunning {label}...")
    geo_src, meta = generate_geo_custom(c, wake_mode=w_mode, line308_start=l308, max_end_bl_k=k_factor)
    q = mesh_and_eval(geo_src)
    print(f"  end_bl_thickness: {meta['end_bl_thickness']*1000:.4f} mm")
    print(f"  spike_bl_end_cell_size: {meta['spike_bl_end_cell_size']*1000:.4f} mm")
    print(f"  wake_right_bot: {meta['wake_right_bot']*1000:.4f} mm")
    print(f"  Quads: {q['quads']}, Tris: {q['tris']}")
    for m in q['metrics']:
        print(f"    {m['name']} ({m['element_type']}): {m['value_str']} {m['unit']}")
