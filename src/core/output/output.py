import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from .write_results_file import write_results


def graph_output(ui):
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt

    results = ui.case["results"]
    x, y = results["x"], results["R_x"]
    max_radius = results["nozzle_size"]
    radius = [max_radius - value for value in y]
    plt.figure()
    plt.plot(radius, x, color='black')
    plt.plot([-value for value in radius], x, color='black')
    truncate_percent = ui.case.get("definition", {}).get("truncate_percent")
    if truncate_percent is None:
        try:
            truncate_percent = float(ui.input_truncate_percentage.get())
        except (ValueError, TypeError):
            truncate_percent = 100
    if truncate_percent < 100:
        plt.plot([radius[-1], -radius[-1]], [x[-1], x[-1]], color='black', linestyle='--')
    plt.gca().set_aspect('equal', adjustable='box')
    plt.xlabel('R')
    plt.ylabel('x')
    plt.grid()
    plt.show()


def show_errors(ui):
    messagebox.showerror("Errors", "\n".join(ui.case["errors"]))


def save_results_file(ui):
    if not ui.case["results"].get("x"):
        messagebox.showerror("Error", "Run the program before saving the results.")
        return
    try:
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt", initialfile="Results.txt", filetypes=[("Text files", "*.txt")]
        )
        if not file_path:
            return
        write_results(ui.case, file_path)
        messagebox.showinfo("File Saved", "Results file successfully saved.")
    except Exception as error:
        messagebox.showerror("Error", f"An error occurred while saving the file: {error}")


def save_cfd_case_definition(ui):
    if not ui.case["results"].get("x"):
        messagebox.showerror("Error", "Run the program before saving the case definition.")
        return
    try:
        from cfd.write_cfd_case_definition_file import format_cfd_case_definition

        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt", initialfile="cfd_case_definition.txt", filetypes=[("Text files", "*.txt")]
        )
        if not file_path:
            return
        Path(file_path).write_text(format_cfd_case_definition(ui.case), encoding="utf-8")
        messagebox.showinfo("File Saved", "CFD case definition file successfully saved.")
    except Exception as error:
        messagebox.showerror("Error", f"An error occurred while saving the case definition: {error}")


def save_mesh_file(ui):
    if not ui.case["results"].get("aerospike_type"):
        messagebox.showerror("Error", "Run a sized aerospike case before saving a CFD file.")
        return
    ui.get_inputs_on_gmsh_geometry()
    mesh_type = tk.StringVar()
    mesh_path = filedialog.asksaveasfilename(
        initialfile="mesh",
        filetypes=[(".msh", "*.msh"), (".su2", "*.su2"), (".cgns", "*.cgns"), (".vtk", "*.vtk")],
        typevariable=mesh_type,
    )
    if not mesh_path:
        return
    mesh_format = Path(mesh_path).suffix.lower() or mesh_type.get().lower()
    if not mesh_format:
        messagebox.showerror("Error", "Choose a mesh extension: .msh, .su2, .cgns, or .vtk.")
        return
    if not Path(mesh_path).suffix:
        mesh_path += mesh_format
    try:
        from cfd.write_mesh_file import write_mesh

        write_mesh(ui.case, mesh_path, mesh_format)
        messagebox.showinfo("Mesh Saved", "Mesh successfully saved.")
    except Exception as error:
        messagebox.showerror("Error", f"An error occurred while saving the mesh: {error}")


def save_gmsh_geometry_file(ui):
    if not ui.case["results"].get("aerospike_type"):
        messagebox.showerror("Error", "Run a sized aerospike case before saving a CFD file.")
        return
    ui.get_inputs_on_gmsh_geometry()
    geo_path = filedialog.asksaveasfilename(
        defaultextension=".geo", initialfile="geometry.geo", filetypes=[("Gmsh Geometry", "*.geo")]
    )
    if not geo_path:
        return
    try:
        from cfd.geometry.write_gmsh_geometry_file import generate_geometry_file

        Path(geo_path).write_text(generate_geometry_file(ui.case), encoding="utf-8")
        messagebox.showinfo("Geometry Saved", "Gmsh geometry file successfully saved.")
    except Exception as error:
        messagebox.showerror("Error", f"An error occurred while saving the geometry: {error}")
