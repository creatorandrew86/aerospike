"""Generate an aerospike mesh with Gmsh."""

from pathlib import Path
from tempfile import TemporaryDirectory

from cfd.geometry.write_gmsh_geometry_file import generate_geometry_file


SUPPORTED_FORMATS = {".msh", ".su2", ".cgns", ".vtk"}


def write_mesh(case, path, mesh_format):
    """Write a 2D mesh in the requested Gmsh-supported format."""
    path = Path(path)
    mesh_format = mesh_format.lower()
    if mesh_format not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported mesh format: {mesh_format}")
    if path.suffix.lower() != mesh_format:
        path = path.with_suffix(mesh_format)

    try:
        import gmsh
    except ImportError as error:
        raise RuntimeError("Gmsh is required to generate mesh files.") from error

    with TemporaryDirectory() as directory:
        geo_path = Path(directory) / "geometry.geo"
        geo_path.write_text(generate_geometry_file(case), encoding="utf-8")

        gmsh.initialize()
        try:
            gmsh.open(str(geo_path))
            gmsh.model.mesh.generate(2)
            gmsh.write(str(path))
        finally:
            gmsh.finalize()

    return path
