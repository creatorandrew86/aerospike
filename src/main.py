import tkinter as tk
from pathlib import Path
import sys

import core.geometry as geometry, ui.interface as interface, core.input as input, ui.layout as layout
from core.output import output

def get_base_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        # Running from source (python main.py).
        return Path(__file__).resolve().parent


def on_solve():
    inputs = ui.get_inputs_on_solve()
    definition = inputs.copy()
    ui.case["errors"] = []

    input_errors = input.process_inputs_on_solve(inputs)
    if input_errors:
        ui.case["definition"] = {}
        ui.case["results"] = {}
        ui.case["cfd"]["setup"] = {}
        ui.case["errors"] = input_errors
        output.show_errors(ui)
        return

    ui.case["definition"] = definition
    results, cfd_setup, solver_errors = geometry.generate_aerospike_contour(inputs)
    if solver_errors:
        ui.case["results"] = {}
        ui.case["cfd"]["setup"] = {}
        ui.case["errors"] = solver_errors
        output.show_errors(ui)
        return

    ui.case["results"] = results
    ui.case["cfd"]["setup"] = cfd_setup
    layout.build_results_frame(ui)

if __name__ == "__main__":
    root = tk.Tk()
    root.title('Aerospike')
    root.geometry('570x330')
    root.resizable(False, False)

    ICON = get_base_path() / "assets" / "icon.ico"
    root.iconbitmap(ICON)

    ui = interface.Interface(root=root, on_solve=on_solve, case=None)

    root.mainloop()
