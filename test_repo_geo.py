import tempfile, os, sys, pathlib

td = tempfile.mkdtemp()
os.environ['USERPROFILE'] = td
os.environ['HOME'] = td
sys.path.insert(0, os.path.abspath('src'))

from core.input import process_inputs_on_solve
from core import geometry as geom
from cfd.geometry.write_gmsh_geometry_file import generate_geometry_file
from cfd.mesh_quality import compute_gmsh_mesh_quality
import gmsh

raw = {
    'oxidizer': 'LOX', 'fuel': 'RP1', 'Pc': 20.0, 'unit_Pc': 'bar', 'MR': 2.3,
    'nozzle_choice': 'area_ratio', 'eps': 10.0, 'design_pressure': None, 'unit_design_pressure': 'bar',
    'p_design': None, 'unit_p_design': 'bar', 'effective_throat_eps': 1.0, 'truncate_percent': 100.0,
    'aerospike_resolution': 100, 'sizing': True, 'aerospike_type': 'toroidal', 'mfr': None, 'unit_mfr': None,
    'radius': 0.1, 'unit_radius': 'm', 'width': None, 'unit_width': None, 'length': None, 'unit_length': None,
}
process_inputs_on_solve(raw)
res, cfd_setup, gerrs = geom.generate_aerospike_contour(raw)
case = {'definition': raw, 'results': res, 'cfd': {'inputs': {'contraction_ratio': 3.0, 'convergent_nozzle_angle': 45.0, 'thruster_nozzle': False, 'grid_density': 1.0, 'bl_mesh_density': 1.0}}}

geo_src = generate_geometry_file(case)
geo_file = pathlib.Path(td) / 'test.geo'
geo_file.write_text(geo_src, encoding='utf-8')

gmsh.initialize(interruptible=False)
gmsh.option.setNumber('General.Terminal', 0)
try:
    gmsh.open(str(geo_file))
    gmsh.model.mesh.generate(2)
    q = compute_gmsh_mesh_quality()
    print('Repo generate_geometry_file quads:', q['quads'], 'tris:', q['tris'])
    for m in q['metrics']:
        print(f"  {m['name']} ({m['element_type']}): {m['value_str']} {m['unit']}")
finally:
    gmsh.finalize()
