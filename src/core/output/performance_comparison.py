import importlib
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import numpy as np

from core import cea, input as core_input

_models_modules = {
    "angelino": importlib.import_module("core.performance.1d-modified-angelino"),
    "design_calibrated": importlib.import_module("core.performance.1d-design-calibrated"),
    "bell_ideal": importlib.import_module("core.performance.1d-ideal"),
    "bell_eps": importlib.import_module("core.performance.1d-bell"),
}


class AutoScrollbar(ttk.Scrollbar):
    def set(self, lo, hi):
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            self.grid_remove()
        else:
            self.grid()
        super().set(lo, hi)


def _header_cell(parent, col, parts, bg, anchor="e"):
    cell = tk.Frame(parent, bg=bg, padx=5, pady=4)
    cell.grid(column=col, row=0, sticky="NSEW", padx=(0 if col == 0 else 1, 0), pady=(0, 1))
    inner = tk.Frame(cell, bg=bg)
    inner.pack(anchor=anchor)
    for text, is_sub in parts:
        tk.Label(
            inner,
            text=text,
            font=("Arial", 7, "bold") if is_sub else ("Arial", 9, "bold"),
            bg=bg,
            fg="#111827",
            bd=0,
            padx=0,
            pady=0,
            highlightthickness=0,
        ).pack(side="left", pady=(3, 0) if is_sub else 0)


def _propellant_title(definition):
    fuel = definition.get("fuel", "")
    ox = definition.get("oxidizer", "")
    prop_names = {
        ("LOX", "LH2"): "Hydrolox",
        ("LOX", "GH2"): "Hydrolox",
        ("LOX", "RP1"): "Kerolox",
        ("LOX", "JetA"): "Kerolox",
        ("LOX", "JP10"): "Kerolox",
        ("LOX", "CH4"): "Methalox",
        ("LOX", "GCH4"): "Methalox",
    }
    name = prop_names.get((ox, fuel))
    if name:
        return f"{name} ({ox}/{fuel}) Nozzle Models Comparison"
    elif ox and fuel:
        return f"{ox}/{fuel} Nozzle Models Comparison"
    return "Nozzle Models Comparison"


def _prepare_calc_context(ui):
    results = ui.case.get("results", {})
    definition = ui.case.get("definition", {})
    if not results.get("x"):
        return None, None, None, None

    inputs = {**definition, "Pc": core_input.pressure_conversion(definition.get("Pc"), definition.get("unit_Pc"))}
    if inputs.get("eps") is None and results.get("eps") is not None:
        inputs["eps"] = results["eps"]

    is_sized = results.get("mfr") is not None
    if is_sized:
        calc_results = results
    else:
        v_t, rho_t = cea.effective_throat_conditions(inputs)
        calc_results = {**results, "length": 1.0, "mfr": rho_t * v_t * 2.0 * results["throat_length"]}

    return inputs, calc_results, definition, is_sized


def _get_selected_methods(inputs, angelino, design_calibrated, bell_ideal, bell_eps):
    eps_val = inputs.get("eps") or 0.0
    selected = []
    if angelino:
        selected.append({
            "key": "angelino",
            "name": "Angelino Modified",
            "legend": "1D-Modified Aerospike",
            "color": "#dc2626",
            "linestyle": "--",
            "module": _models_modules["angelino"],
        })
    if design_calibrated:
        selected.append({
            "key": "design_calibrated",
            "name": "Design Calibrated",
            "legend": "1D-Design-Calibrated Aerospike",
            "color": "#1f77b4",
            "linestyle": "-",
            "module": _models_modules["design_calibrated"],
        })
    if bell_ideal:
        selected.append({
            "key": "bell_ideal",
            "name": "Bell (Ideal Expansion)",
            "legend": r"1D-Ideal (Variable $\varepsilon$)",
            "color": "#2ca02c",
            "linestyle": ":",
            "module": _models_modules["bell_ideal"],
        })
    if bell_eps:
        selected.append({
            "key": "bell_eps",
            "name": "Bell (Constant \u03b5)",
            "legend": f"1D-Bell ($\\varepsilon = {eps_val:.1f}$, unseparated)",
            "color": "#9467bd",
            "linestyle": "-.",
            "module": _models_modules["bell_eps"],
        })
    return selected


def _get_conditions(ui, inputs, results):
    raw_text = ui.input_analysis.get().strip() if hasattr(ui, "input_analysis") else ""
    raw_mode = ui.analysis_type.get() if hasattr(ui, "analysis_type") else "Altitude"
    mode = "Pressure" if "pressure" in raw_mode.lower() else "Altitude"
    given_values = core_input.parse_analysis_inputs(raw_text)

    p_design = results.get("ideal_expansion_pressure")
    if p_design is None:
        p_design = cea.ideal_expansion_pressure(inputs)
    h_design = (core_input.pressure_to_altitude(p_design) / 1000.0) if (p_design is not None and p_design <= 101325.0) else None

    conditions = [
        ("Sea Level", 101325.0, 0.0),
        ("Design Point", p_design, h_design),
        ("Vacuum", 0.0, None),
    ]

    for val in given_values:
        if mode == "Altitude":
            h_val = float(val)
            p_atm = max(0.0, core_input.altitude_to_pressure(h_val * 1000.0))
            label = f"{val:g} km"
        else:
            p_atm = max(0.0, float(val) * 1e5)
            h_val = (core_input.pressure_to_altitude(p_atm) / 1000.0) if p_atm <= 101325.0 else None
            label = f"{val:g} bar"
        conditions.append((label, p_atm, h_val))

    return mode, given_values, conditions


def _save_comparison_tables(all_data, parent):
    file_path = filedialog.asksaveasfilename(
        parent=parent,
        defaultextension=".csv",
        initialfile="performance_comparison.csv",
        filetypes=[("CSV files", "*.csv"), ("Text files", "*.txt"), ("All files", "*.*")],
    )
    if not file_path:
        return
    try:
        is_csv = file_path.lower().endswith(".csv")
        with open(file_path, "w", encoding="utf-8") as f:
            for method_name, rows in all_data.items():
                if is_csv:
                    f.write(f'"{method_name}"\n')
                    f.write("Condition,Altitude (km),P_atm (bar),Thrust (kN),CF,Isp (s)\n")
                    for r in rows:
                        f.write(f'"{r[0]}",{r[1]},{r[2]},{r[3]},{r[4]},{r[5]}\n')
                    f.write("\n")
                else:
                    f.write(f"=== {method_name} ===\n")
                    f.write(f"{'Condition':<18} {'Altitude (km)':>14} {'P_atm (bar)':>12} {'Thrust (kN)':>14} {'CF':>8} {'Isp (s)':>10}\n")
                    f.write("-" * 81 + "\n")
                    for r in rows:
                        f.write(f"{r[0]:<18} {r[1]:>14} {r[2]:>12} {r[3]:>14} {r[4]:>8} {r[5]:>10}\n")
                    f.write("\n")
        messagebox.showinfo("Saved", "Performance comparison table saved successfully.", parent=parent)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to save file: {e}", parent=parent)


def generate_table(
    ui,
    angelino: bool = None,
    design_calibrated: bool = None,
    bell_ideal: bool = None,
    bell_eps: bool = None,
):
    inputs, calc_results, _, is_sized = _prepare_calc_context(ui)
    if inputs is None:
        messagebox.showerror("Error", "Run the program before analyzing performance.")
        return

    if angelino is None:
        angelino = bool(getattr(ui, "compare_angelino_var", tk.BooleanVar()).get())
    if design_calibrated is None:
        design_calibrated = bool(getattr(ui, "compare_design_var", tk.BooleanVar()).get())
    if bell_ideal is None:
        bell_ideal = bool(getattr(ui, "compare_bell_ideal_var", tk.BooleanVar()).get())
    if bell_eps is None:
        bell_eps = bool(getattr(ui, "compare_bell_eps_var", tk.BooleanVar()).get())

    methods = _get_selected_methods(inputs, angelino, design_calibrated, bell_ideal, bell_eps)
    if not methods:
        messagebox.showerror("Selection Error", "Select at least one performance method to compare.")
        return

    _, _, conditions = _get_conditions(ui, inputs, calc_results)

    bg_parent = ttk.Style().lookup("TFrame", "background") or "SystemButtonFace"
    line_color = "#c5c8cc"

    window = tk.Toplevel(ui.root)
    window.title("Performance Comparison")
    window.geometry("540x320")
    window.resizable(False, False)

    bottom_bar = ttk.Frame(window, padding=(10, 0, 10, 8))
    bottom_bar.pack(fill="x", side="bottom")

    container = ttk.Frame(window, padding=(10, 10, 10, 4))
    container.pack(fill="both", expand=True)
    container.columnconfigure(0, weight=1)
    container.rowconfigure(0, weight=1)

    scrollbar = AutoScrollbar(container, orient="vertical")
    scrollbar.grid(column=1, row=0, sticky="ns")

    canvas = tk.Canvas(container, bg=bg_parent, bd=0, highlightthickness=0, yscrollcommand=scrollbar.set)
    canvas.grid(column=0, row=0, sticky="nsew")
    scrollbar.configure(command=canvas.yview)

    window.bind(
        "<MouseWheel>",
        lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units") if scrollbar.winfo_ismapped() else None,
    )

    tables_frame = tk.Frame(canvas, bg=bg_parent, bd=0)
    win_item = canvas.create_window((0, 0), window=tables_frame, anchor="nw")
    tables_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_item, width=e.width))
    tables_frame.columnconfigure(0, weight=1)

    all_saved_data = {}
    for table_idx, method in enumerate(methods):
        table = tk.Frame(tables_frame, bg=line_color, bd=0)
        table.grid(column=0, row=table_idx, sticky="EW", pady=(0, 10))

        for col, weight in enumerate((4, 2, 3, 3, 2, 3)):
            table.columnconfigure(col, weight=weight)

        headers = [
            ([(method["name"], False)], "w"),
            ([("h", False), (" (km)", False)], "e"),
            ([("P", False), ("atm", True), (" (bar)", False)], "e"),
            ([("Thrust(kN)", False)], "e"),
            ([("C", False), ("F", True)], "e"),
            ([("I", False), ("sp", True), ("(s)", False)], "e"),
        ]
        for col, (parts, anchor) in enumerate(headers):
            _header_cell(table, col, parts, bg_parent, anchor)

        rows_to_save = []
        for row_idx, (label, p_atm, h_val) in enumerate(conditions, start=1):
            cf, f_total, isp, _ = method["module"].thrust(inputs, calc_results, p_atm)
            thrust_str = f"{f_total / 1e3:.2f}" if is_sized else "—"
            h_str = f"{h_val:.2f}" if h_val is not None else "—"
            p_str = f"{p_atm / 1e5:.3f}"
            cf_str = f"{cf:.3f}"
            isp_str = f"{isp:.1f}"

            rows_to_save.append((label, h_str, p_str, thrust_str, cf_str, isp_str))

            row_values = [
                (label, ("Arial", 9, "bold"), "w"),
                (h_str, ("Arial", 9), "e"),
                (p_str, ("Arial", 9), "e"),
                (thrust_str, ("Arial", 9), "e"),
                (cf_str, ("Arial", 9), "e"),
                (isp_str, ("Arial", 9), "e"),
            ]
            for col, (val, fnt, anchor) in enumerate(row_values):
                cell = tk.Frame(table, bg=bg_parent, padx=5, pady=4)
                cell.grid(
                    column=col,
                    row=row_idx,
                    sticky="NSEW",
                    padx=(0 if col == 0 else 1, 0),
                    pady=(0, 0 if row_idx == len(conditions) else 1),
                )
                tk.Label(
                    cell,
                    text=val,
                    font=fnt,
                    bg=bg_parent,
                    fg="#111827",
                    bd=0,
                    padx=0,
                    pady=0,
                    highlightthickness=0,
                ).pack(anchor=anchor)

        all_saved_data[method["name"]] = rows_to_save

    save_btn = ttk.Button(bottom_bar, text="Save As", command=lambda: _save_comparison_tables(all_saved_data, window))
    save_btn.pack(side="right")


def generate_graph(
    ui,
    angelino: bool = None,
    design_calibrated: bool = None,
    bell_ideal: bool = None,
    bell_eps: bool = None,
):
    inputs, calc_results, definition, is_sized = _prepare_calc_context(ui)
    if inputs is None:
        messagebox.showerror("Error", "Run the program before analyzing performance.")
        return

    if angelino is None:
        angelino = bool(getattr(ui, "compare_angelino_var", tk.BooleanVar()).get())
    if design_calibrated is None:
        design_calibrated = bool(getattr(ui, "compare_design_var", tk.BooleanVar()).get())
    if bell_ideal is None:
        bell_ideal = bool(getattr(ui, "compare_bell_ideal_var", tk.BooleanVar()).get())
    if bell_eps is None:
        bell_eps = bool(getattr(ui, "compare_bell_eps_var", tk.BooleanVar()).get())

    methods = _get_selected_methods(inputs, angelino, design_calibrated, bell_ideal, bell_eps)
    if not methods:
        messagebox.showerror("Selection Error", "Select at least one performance method to compare.")
        return

    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    from matplotlib.figure import Figure

    mode, given_values, _ = _get_conditions(ui, inputs, calc_results)
    is_pressure = mode == "Pressure"

    if is_pressure:
        user_p = [float(v) for v in given_values]
        user_alt = [core_input.pressure_to_altitude(float(v) * 1e5) / 1000.0 for v in given_values if float(v) * 1e5 <= 101325.0]
    else:
        user_alt = [float(v) for v in given_values]
        user_p = [core_input.altitude_to_pressure(float(v) * 1000.0) / 1e5 for v in given_values]

    # Pre-calculate Altitude Series
    alt_base_x = [0.0, 2.0, 5.0, 8.0, 11.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0]
    alt_sample_x = sorted(set(round(float(x), 1) for x in alt_base_x + user_alt if 0.0 <= float(x) <= 40.0))
    alt_sample_p = [max(0.0, core_input.altitude_to_pressure(x * 1e3)) for x in alt_sample_x]

    # Pre-calculate Pressure Series
    press_base_x = [0.0, 0.02, 0.05, 0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 0.95, 1.01325]
    press_sample_x = sorted(set(round(float(x), 4) for x in press_base_x + user_p if 0.0 <= float(x) <= 1.01325))
    press_sample_p = [x * 1e5 for x in press_sample_x]

    y_thrust_label = "Thrust (kN)" if is_sized else "Thrust (kN/m) [Unsized]"
    y_isp_label = "Specific Impulse $I_{sp}$ (s)"
    y_cf_label = "Thrust Coefficient $C_F$"

    alt_series_data = []
    press_series_data = []
    for method in methods:
        alt_line_thrust, alt_line_isp, alt_line_cf = [], [], []
        for p in alt_sample_p:
            cf, f_tot, isp, _ = method["module"].thrust(inputs, calc_results, p)
            alt_line_thrust.append(f_tot / 1e3)
            alt_line_isp.append(isp)
            alt_line_cf.append(cf)
        alt_series_data.append((method, alt_line_thrust, alt_line_isp, alt_line_cf))

        press_line_thrust, press_line_isp, press_line_cf = [], [], []
        for p in press_sample_p:
            cf, f_tot, isp, _ = method["module"].thrust(inputs, calc_results, p)
            press_line_thrust.append(f_tot / 1e3)
            press_line_isp.append(isp)
            press_line_cf.append(cf)
        press_series_data.append((method, press_line_thrust, press_line_isp, press_line_cf))

    prop_title = _propellant_title(definition)
    pc_val = inputs.get("Pc", 0.0) / 1e5
    mr_val = definition.get("MR", 0.0)
    eps_val = definition.get("eps", 0.0)
    eps_t_val = definition.get("effective_throat_eps", 0.0)
    trunc_val = definition.get("truncate_percent", 100.0)
    subtitle = (
        f"$P_c = {pc_val:.1f}\\ \\mathrm{{bar}},\\ \\mathrm{{MR}} = {mr_val:.2f},\\ "
        f"\\varepsilon = {eps_val:.1f},\\ \\varepsilon_t = {eps_t_val:.1f},\\ "
        f"\\mathrm{{Truncation}} = {trunc_val:.0f}\\%$"
    )

    # Separate Tkinter window
    window = tk.Toplevel(ui.root)
    window.title("Performance Comparison Graph")
    window.geometry("740x540")

    # Left sidebar column for plot selection controls
    sidebar = ttk.Frame(window, padding=(12, 12, 10, 12))
    sidebar.pack(side="left", fill="y")

    ttk.Label(sidebar, text="Plot", font=("Arial", 10, "bold")).pack(anchor="w", pady=(0, 8))

    x_frame = ttk.Frame(sidebar)
    x_frame.pack(anchor="w", pady=(0, 6))
    ttk.Label(x_frame, text="X:", font=("Arial", 9, "bold")).pack(side="left", padx=(0, 6))
    plot_x_choice = ttk.Combobox(
        x_frame,
        values=["Altitude", "Pressure"],
        state="readonly",
        width=8,
    )
    plot_x_choice.set("Pressure" if is_pressure else "Altitude")
    plot_x_choice.pack(side="left")

    y_frame = ttk.Frame(sidebar)
    y_frame.pack(anchor="w", pady=(0, 8))
    ttk.Label(y_frame, text="Y:", font=("Arial", 9, "bold")).pack(side="left", padx=(0, 6))
    plot_choice = ttk.Combobox(
        y_frame,
        values=["Thrust", "Isp", "C\ua730"],
        state="readonly",
        width=8,
    )
    plot_choice.set("Thrust")
    plot_choice.pack(side="left")

    plot_frame = ttk.Frame(window)
    plot_frame.pack(side="right", fill="both", expand=True)

    # Matplotlib Figure and Tk Canvas
    fig = Figure(figsize=(6.4, 4.4), dpi=100)
    ax = fig.add_subplot(111)

    canvas = FigureCanvasTkAgg(fig, master=plot_frame)
    toolbar = NavigationToolbar2Tk(canvas, plot_frame)
    toolbar.update()
    toolbar.pack(side="bottom", fill="x")
    canvas.get_tk_widget().pack(side="top", fill="both", expand=True)

    def render_plot():
        ax.clear()
        x_selected = plot_x_choice.get()
        is_p = "pressure" in x_selected.lower()

        if is_p:
            active_x = press_sample_x
            active_series = press_series_data
            x_label = "Ambient Pressure $P_{atm}$ (bar)"
        else:
            active_x = alt_sample_x
            active_series = alt_series_data
            x_label = "Altitude (km)"

        selected = plot_choice.get()
        if "thrust" in selected.lower():
            metric = "thrust"
        elif "c" in selected.lower() or "\ua730" in selected:
            metric = "cf"
        else:
            metric = "isp"

        if metric == "thrust":
            y_label = y_thrust_label
            plot_title = f"Thrust vs {x_selected}"
        elif metric == "isp":
            y_label = y_isp_label
            plot_title = f"Specific Impulse vs {x_selected}"
        else:
            y_label = y_cf_label
            plot_title = f"Thrust Coefficient vs {x_selected}"

        for method, line_thrust, line_isp, line_cf in active_series:
            if metric == "thrust":
                y_data = line_thrust
            elif metric == "isp":
                y_data = line_isp
            else:
                y_data = line_cf

            ax.plot(
                active_x,
                y_data,
                label=method["legend"],
                color=method["color"],
                linestyle=method["linestyle"],
                linewidth=1.8,
            )

        ax.set_xlabel(x_label, fontsize=9)
        ax.set_ylabel(y_label, fontsize=9)
        ax.set_title(plot_title, fontsize=10, fontweight="bold")
        ax.grid(True, linestyle=":", alpha=0.6)
        if is_p:
            ax.invert_xaxis()
        ax.legend(loc="lower right" if (is_p and metric != "thrust") else "best", fontsize=8, frameon=True)

        fig.suptitle(f"{prop_title}\n{subtitle}", fontsize=9)
        fig.tight_layout()
        canvas.draw()
        toolbar.update()

    apply_btn = ttk.Button(sidebar, text="Apply", command=render_plot)
    apply_btn.pack(fill="x", pady=(2, 0))

    render_plot()


generate_performance_comparison_table = generate_table
generate_performance_comparison_graph = generate_graph
