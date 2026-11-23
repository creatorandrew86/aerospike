import tempfile, os, sys, pathlib

td = tempfile.mkdtemp()
os.environ['USERPROFILE'] = td
os.environ['HOME'] = td
sys.path.insert(0, os.path.abspath('src'))

from core.input import process_inputs_on_solve
from core import geometry as geom
import cfd.geometry.domain_geometry as dg
import cfd.geometry.write_gmsh_geometry_file as wggf
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

def run_variation(case, wake_mode, line308_mode, max_end_bl_k=None):
    # patch write_gmsh_geometry_file.generate_geometry_file dynamically or wrap it
    orig_generate = wggf.generate_geometry_file
    
    # We can inspect the source or patch by text replacement on the output of generate_geometry_file!
    # Because generate_geometry_file produces the complete geo source:
    if max_end_bl_k is not None:
        old_k = dg.MAX_END_BL_FACTOR
        dg.MAX_END_BL_FACTOR = max_end_bl_k
    try:
        geometry = dg.build_geometry(case)
        geo_src = orig_generate(case)
    finally:
        if max_end_bl_k is not None:
            dg.MAX_END_BL_FACTOR = old_k

    scale = geometry.scale
    rp = wggf.WAKE_RIGHT_PROGRESSION
    delta_y1 = float(case['results']['bl_first_cell'])
    bl_thickness = math_hypot = ((geometry.boundary_layer[0][0] - geometry.spike[0][0])**2 + (geometry.boundary_layer[0][1] - geometry.spike[0][1])**2)**0.5
    from cfd.geometry import mesh
    bl_cell_number, _ = mesh.bl_cells_and_progression(bl_thickness, delta_y1)
    wake_h = geometry.anchors['wake_top'][1]
    wake_right_bot = wake_h * (rp - 1.0) / (rp ** bl_cell_number - 1.0)
    wake_right_top = wake_right_bot * (rp ** (bl_cell_number - 1))
    
    # compute spike_bl_end_cell_size
    factors = mesh.density_factors(1.0, 1.0)
    inlet_cell_number = max(3, round(mesh.DEFAULT_INLET_CELL_NUMBER * factors['inlet']))
    inlet_cell_size = geometry.lengths['inlet'] / inlet_cell_number
    spike_bl_start_cell_size = 0.9 * inlet_cell_size
    spike_bl_cell_number = max(3, round(mesh.DEFAULT_SPIKE_BL_CELL_NUMBER * factors['spike']))
    _, spike_bl_end_cell_size = mesh.beta_fixed_n('1, 101', geometry.lengths['spike'], spike_bl_start_cell_size, spike_bl_cell_number)
    
    end_bl_thickness = geometry.anchors['wake_top'][1]
    wake_len = geometry.lengths['wake']
    
    # Now replace in geo_src:
    # 1. wake block (105, 106)
    if wake_mode == 'uniform':
        old_wake_line = mesh.beta('105, 106', wake_len, spike_bl_end_cell_size, wake_right_top, 1.05, min_cells=10)
        new_wake_line = mesh.transfinite('105, 106', max(3, round(wake_len / spike_bl_end_cell_size)), 'Progression', 1)
        if old_wake_line not in geo_src:
            raise RuntimeError(f"Could not find old_wake_line in geo_src:\n{old_wake_line}")
        geo_src = geo_src.replace(old_wake_line, new_wake_line)
    
    # 2. Line(-308)
    if line308_mode == 'spike_bl_end_cell_size':
        farfield_cell_size = mesh.DEFAULT_FARFIELD_CELL_SIZE * scale / factors['farfield']
        old_308 = mesh.beta('-308', geometry.lengths['far_308'], wake_right_bot, farfield_cell_size, 1.02, min_cells=10)
        new_308 = mesh.beta('-308', geometry.lengths['far_308'], spike_bl_end_cell_size, farfield_cell_size, 1.02, min_cells=10)
        if old_308 not in geo_src:
            raise RuntimeError(f"Could not find old_308 in geo_src:\n{old_308}")
        geo_src = geo_src.replace(old_308, new_308)

    geo_file = pathlib.Path(td) / 'eval.geo'
    geo_file.write_text(geo_src, encoding='utf-8')
    gmsh.initialize(interruptible=False)
    gmsh.option.setNumber('General.Terminal', 0)
    try:
        gmsh.open(str(geo_file))
        gmsh.model.mesh.generate(2)
        q = compute_gmsh_mesh_quality()
    finally:
        gmsh.finalize()
    
    meta = {
        'end_bl_thickness': end_bl_thickness,
        'spike_bl_end_cell_size': spike_bl_end_cell_size,
        'wake_right_bot': wake_right_bot,
        'wake_right_top': wake_right_top,
        'wake_length': wake_len,
    }
    return q, meta

# Case 1: Kerolox toroidal eps=10 baseline
case_kerolox_raw = {
    'oxidizer': 'LOX', 'fuel': 'RP1', 'Pc': 20.0, 'unit_Pc': 'bar', 'MR': 2.3,
    'nozzle_choice': 'area_ratio', 'eps': 10.0, 'design_pressure': None, 'unit_design_pressure': 'bar',
    'p_design': None, 'unit_p_design': 'bar', 'effective_throat_eps': 1.0, 'truncate_percent': 100.0,
    'aerospike_resolution': 100, 'sizing': True, 'aerospike_type': 'toroidal', 'mfr': None, 'unit_mfr': None,
    'radius': 0.1, 'unit_radius': 'm', 'width': None, 'unit_width': None, 'length': None, 'unit_length': None,
}
case_k = build_case(case_kerolox_raw)

# Case 2: Hydrolox toroidal eps=250 (teps=2.0)
case_hydrolox_raw = {
    'oxidizer': 'LOX', 'fuel': 'LH2', 'Pc': 100.0, 'unit_Pc': 'bar', 'MR': 6.0,
    'nozzle_choice': 'area_ratio', 'eps': 250.0, 'design_pressure': None, 'unit_design_pressure': 'bar',
    'p_design': None, 'unit_p_design': 'bar', 'effective_throat_eps': 2.0, 'truncate_percent': 100.0,
    'aerospike_resolution': 100, 'sizing': True, 'aerospike_type': 'toroidal', 'mfr': None, 'unit_mfr': None,
    'radius': 0.1, 'unit_radius': 'm', 'width': None, 'unit_width': None, 'length': None, 'unit_length': None,
}
case_h = build_case(case_hydrolox_raw)

# For Hydrolox, what is k such that k * spike_length ≈ 0.04 * scale?
# scale = 0.1, 0.04*scale = 0.004 m.
# spike curve_length for hydrolox eps=250 teps=2.0 was 0.574356 m.
# k = 0.004 / 0.574356 = 0.006964.
# If max_end_bl_thickness = k * spike_length = 0.004 m!
# Let's verify what happens if we use the clamp:
# In domain_geometry: max_end_bl_thickness = max(boundary_layer_thickness, MAX_END_BL_FACTOR * scale)
# If MAX_END_BL_FACTOR = 0.04, then MAX_END_BL_FACTOR * scale = 0.004.
# If we set k_factor = 0.006964 * (spike_length / scale) = 0.04, it's 0.004 m.
# What if unclamped? unclamped was 19.317 mm (0.019317 m).
# With 0.04*scale (or k*spike_length ≈ 0.04*scale), max_end_bl_thickness is clamped to 0.004 m (4.0 mm)!

variations = [
    ("1. Kerolox eps=10 | Beta wake | Line(-308) from wake_right_bot (Current Repo)", case_k, 'beta', 'wake_right_bot', None),
    ("2. Kerolox eps=10 | Beta wake | Line(-308) from spike_bl_end_cell_size", case_k, 'beta', 'spike_bl_end_cell_size', None),
    ("3. Kerolox eps=10 | Uniform wake | Line(-308) from wake_right_bot", case_k, 'uniform', 'wake_right_bot', None),
    ("4. Kerolox eps=10 | Uniform wake | Line(-308) from spike_bl_end_cell_size", case_k, 'uniform', 'spike_bl_end_cell_size', None),

    ("5. Hydrolox eps=250 (k*spike clamp = 4mm) | Beta wake | Line(-308) from wake_right_bot", case_h, 'beta', 'wake_right_bot', 0.04),
    ("6. Hydrolox eps=250 (k*spike clamp = 4mm) | Beta wake | Line(-308) from spike_bl_end_cell_size", case_h, 'beta', 'spike_bl_end_cell_size', 0.04),
    ("7. Hydrolox eps=250 (k*spike clamp = 4mm) | Uniform wake | Line(-308) from wake_right_bot", case_h, 'uniform', 'wake_right_bot', 0.04),
    ("8. Hydrolox eps=250 (k*spike clamp = 4mm) | Uniform wake | Line(-308) from spike_bl_end_cell_size", case_h, 'uniform', 'spike_bl_end_cell_size', 0.04),
]

for label, c, w_mode, l308, k_factor in variations:
    print(f"\n========================================\n{label}\n========================================")
    q, meta = run_variation(c, w_mode, l308, k_factor)
    print(f"  end_bl_thickness:       {meta['end_bl_thickness']*1000:.4f} mm")
    print(f"  spike_bl_end_cell_size: {meta['spike_bl_end_cell_size']*1000:.4f} mm")
    print(f"  wake_right_bot:         {meta['wake_right_bot']*1000:.4f} mm")
    print(f"  wake_length:            {meta['wake_length']*1000:.4f} mm")
    print(f"  Quads: {q['quads']}, Tris: {q['tris']}")
    for m in q['metrics']:
        print(f"    {m['name']:25s} ({m['element_type']:9s}): {m['value_str']} {m['unit']}")
