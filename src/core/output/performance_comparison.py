import csv
import importlib
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import numpy as np

from core import cea, input as core_input

_models_modules = {
    "angelino": importlib.import_module("core.performance.1d-modified-angelino"),
    "streamtube": importlib.import_module("core.performance.1d-streamtube"),
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


def _pack_parts(parent, parts, bg, size=9):
    for text, is_sub in parts:
        tk.Label(
            parent,
            text=text,
            font=("Arial", max(7, size - 2), "bold") if is_sub else ("Arial", size, "bold"),
            bg=bg,
            fg="#111827",
            bd=0,
            padx=0,
            pady=0,
            highlightthickness=0,
        ).pack(side="left", pady=(3, 0) if is_sub else 0)


def _header_cell(parent, col, parts, bg, anchor="e"):
    cell = tk.Frame(parent, bg=bg, padx=5, pady=4)
    cell.grid(column=col, row=0, sticky="NSEW", padx=(0 if col == 0 else 1, 0), pady=(0, 1))
    inner = tk.Frame(cell, bg=bg)
    inner.pack(anchor=anchor)
    _pack_parts(inner, parts, bg)


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


def _prepare_calc_context(case):
    results = case.get("results", {})
    definition = case.get("definition", {})
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


def _get_selected_methods(inputs, angelino, streamtube, bell_ideal, bell_eps):
    eps_val = inputs.get("eps") or 0.0
    selected = []
    if angelino:
        selected.append({
            "key": "angelino",
            "name": "Angelino Modified",
            "legend": "Angelino Modified",
            "color": "#dc2626",
            "linestyle": "-",
            "module": _models_modules["angelino"],
        })
    if streamtube:
        selected.append({
            "key": "streamtube",
            "name": "1D Modified",
            "legend": f"1D Modified ($\\eta = {_models_modules['streamtube'].ETA:.2f}$)",
            "color": "#1d4ed8",
            "linestyle": "-",
            "module": _models_modules["streamtube"],
        })
    if bell_ideal:
        selected.append({
            "key": "bell_ideal",
            "name": "Bell (Ideal Expansion)",
            "legend": r"1D-Ideal (Variable $\varepsilon$)",
            "color": "#16a34a",
            "linestyle": ":",
            "module": _models_modules["bell_ideal"],
        })
    if bell_eps:
        selected.append({
            "key": "bell_eps",
            "name": "Bell (Design \u03b5)",
            "legend": f"1D-Bell ($\\varepsilon = {eps_val:.1f}$, unseparated)",
            "color": "#d97706",
            "linestyle": "-",
            "module": _models_modules["bell_eps"],
        })
    return selected


def _get_conditions(raw_text, raw_mode, inputs, results):
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


def _write_comparison_tables(file_path, col_names, tables_data):
    is_csv = file_path.lower().endswith(".csv")
    with open(file_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f) if is_csv else None
        for title, rows in tables_data:
            if is_csv:
                writer.writerow([title])
                writer.writerow(col_names)
                writer.writerows(rows)
                writer.writerow([])
            else:
                widths = [max(len(col_names[i]), *(len(r[i]) for r in rows)) + 2 for i in range(len(col_names))]
                f.write(f"=== {title} ===\n")
                f.write(" ".join(f"{col_names[i]:<{widths[i]}}" if i == 0 else f"{col_names[i]:>{widths[i]}}" for i in range(len(col_names))) + "\n")
                f.write("-" * (sum(widths) + len(widths) - 1) + "\n")
                for r in rows:
                    f.write(" ".join(f"{r[i]:<{widths[i]}}" if i == 0 else f"{r[i]:>{widths[i]}}" for i in range(len(col_names))) + "\n")
                f.write("\n")


def _save_comparison_tables(col_names, tables_data, parent):
    file_path = filedialog.asksaveasfilename(
        parent=parent,
        defaultextension=".csv",
        initialfile="performance_comparison.csv",
        filetypes=[("CSV files", "*.csv"), ("Text files", "*.txt"), ("All files", "*.*")],
    )
    if not file_path:
        return
    try:
        _write_comparison_tables(file_path, col_names, tables_data)
        messagebox.showinfo("Saved", "Performance comparison table saved successfully.", parent=parent)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to save file: {e}", parent=parent)


def _resolve_comparison_inputs(ui, angelino, streamtube, bell_ideal, bell_eps):
    results = ui.case.get("results", {})
    definition = ui.case.get("definition", {})
    if not results.get("x"):
        messagebox.showerror("Error", "Run the program before analyzing performance.")
        return None
    flags = [
        flag if flag is not None else bool(getattr(ui, attr, tk.BooleanVar()).get())
        for flag, attr in (
            (angelino, "compare_angelino_var"),
            (streamtube, "compare_streamtube_var"),
            (bell_ideal, "compare_bell_ideal_var"),
            (bell_eps, "compare_bell_eps_var"),
        )
    ]
    base_inputs = {**definition, "eps": definition.get("eps") if definition.get("eps") is not None else results.get("eps")}
    methods = _get_selected_methods(base_inputs, *flags)
    if not methods:
        messagebox.showerror("Selection Error", "Select at least one performance method to compare.")
        return None
    raw_text = ui.input_analysis.get().strip() if hasattr(ui, "input_analysis") else ""
    raw_mode = ui.analysis_type.get() if hasattr(ui, "analysis_type") else "Altitude"
    return methods, raw_text, raw_mode, ui.case


def generate_table(
    ui,
    angelino: bool = None,
    streamtube: bool = None,
    bell_ideal: bool = None,
    bell_eps: bool = None,
):
    resolved = _resolve_comparison_inputs(ui, angelino, streamtube, bell_ideal, bell_eps)
    if resolved is None:
        return
    methods, raw_text, raw_mode, case_snapshot = resolved

    from ui.layout import run_with_loading_circle

    def compute():
        inputs, calc_results, _, is_sized = _prepare_calc_context(case_snapshot)
        _, _, conditions = _get_conditions(raw_text, raw_mode, inputs, calc_results)

        thrust_rows, isp_rows, cf_rows = [], [], []
        for label, p_atm, h_val in conditions:
            h_str = f"{h_val:.2f}" if h_val is not None else "—"
            p_str = f"{p_atm / 1e5:.3f}"
            t_row, i_row, c_row = [label, h_str, p_str], [label, h_str, p_str], [label, h_str, p_str]
            for method in methods:
                cf, f_total, isp, _ = method["module"].thrust(inputs, calc_results, p_atm)
                t_row.append(f"{f_total / 1e3:.2f}" if is_sized else "—")
                i_row.append(f"{isp:.1f}")
                c_row.append(f"{cf:.3f}")
            thrust_rows.append(t_row)
            isp_rows.append(i_row)
            cf_rows.append(c_row)
        return thrust_rows, isp_rows, cf_rows

    def render(data):
        thrust_rows, isp_rows, cf_rows = data
        bg_parent = ttk.Style().lookup("TFrame", "background") or "SystemButtonFace"
        line_color = "#c5c8cc"

        window = tk.Toplevel(ui.root)
        window.title("Performance Comparison")

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

        tables = [
            ("Thrust (kN)", [("Thrust (kN)", False)], thrust_rows),
            ("Isp (s)", [("I", False), ("sp", True), (" (s)", False)], isp_rows),
            ("CF", [("C", False), ("F", True)], cf_rows),
        ]
        headers = [
            ([("#", False)], "w"),
            ([("H", False), (" (km)", False)], "e"),
            ([("P", False), ("atm", True), (" (bar)", False)], "e"),
            *(([(m["name"], False)], "e") for m in methods),
        ]
        col_names = ["Condition", "H (km)", "P_atm (bar)", *(m["name"] for m in methods)]

        for table_idx, (_, title_parts, rows) in enumerate(tables):
            title_frame = tk.Frame(tables_frame, bg=bg_parent)
            title_frame.grid(column=0, row=table_idx * 2, sticky="W", pady=(4 if table_idx > 0 else 0, 4))
            _pack_parts(title_frame, title_parts, bg_parent, size=10)

            table = tk.Frame(tables_frame, bg=line_color, bd=0)
            table.grid(column=0, row=table_idx * 2 + 1, sticky="EW", pady=(0, 18 if table_idx < 2 else 4))

            for col in range(len(headers)):
                table.columnconfigure(col, weight=2 if col == 1 else 3)

            for col, (parts, anchor) in enumerate(headers):
                _header_cell(table, col, parts, bg_parent, anchor)

            for row_idx, row_vals in enumerate(rows, start=1):
                for col, val in enumerate(row_vals):
                    cell = tk.Frame(table, bg=bg_parent, padx=5, pady=4)
                    cell.grid(
                        column=col,
                        row=row_idx,
                        sticky="NSEW",
                        padx=(0 if col == 0 else 1, 0),
                        pady=(0, 0 if row_idx == len(rows) else 1),
                    )
                    tk.Label(
                        cell,
                        text=val,
                        font=("Arial", 9, "bold") if col == 0 else ("Arial", 9),
                        bg=bg_parent,
                        fg="#111827",
                        bd=0,
                        padx=0,
                        pady=0,
                        highlightthickness=0,
                    ).pack(anchor="w" if col == 0 else "e")

        save_data = [(title, rows) for title, _, rows in tables]
        save_btn = ttk.Button(bottom_bar, text="Save As", command=lambda: _save_comparison_tables(col_names, save_data, window))
        save_btn.pack(side="right")

        window.update_idletasks()
        width = max(540, tables_frame.winfo_reqwidth() + 42)
        height = min(560, max(320, tables_frame.winfo_reqheight() + 56))
        window.geometry(f"{width}x{height}")

    run_with_loading_circle(ui, "comparison_loading_circle", compute, render)


def generate_graph(
    ui,
    angelino: bool = None,
    streamtube: bool = None,
    bell_ideal: bool = None,
    bell_eps: bool = None,
):
    resolved = _resolve_comparison_inputs(ui, angelino, streamtube, bell_ideal, bell_eps)
    if resolved is None:
        return
    methods, raw_text, raw_mode, case_snapshot = resolved

    from ui.layout import run_with_loading_circle

    def compute():
        from matplotlib.figure import Figure
        from scipy.interpolate import PchipInterpolator

        inputs, calc_results, def_snap, is_sized = _prepare_calc_context(case_snapshot)
        mode, given_values, _ = _get_conditions(raw_text, raw_mode, inputs, calc_results)
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

        return (
            Figure, PchipInterpolator, inputs, def_snap, is_sized, is_pressure,
            alt_sample_x, alt_series_data, press_sample_x, press_series_data,
        )

    def render(data):
        (
            Figure, PchipInterpolator, inputs, def_snap, is_sized, is_pressure,
            alt_sample_x, alt_series_data, press_sample_x, press_series_data,
        ) = data
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

        y_thrust_label = "Thrust (kN)" if is_sized else "Thrust (kN/m) [Unsized]"
        y_isp_label = "Specific Impulse $I_{sp}$ (s)"
        y_cf_label = "Thrust Coefficient $C_F$"

        prop_title = _propellant_title(def_snap)
        pc_val = inputs.get("Pc", 0.0) / 1e5
        mr_val = def_snap.get("MR", 0.0)
        eps_val = def_snap.get("eps", 0.0)
        eps_t_val = def_snap.get("effective_throat_eps", 0.0)
        trunc_val = def_snap.get("truncate_percent", 100.0)
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

            x_plot = np.linspace(active_x[0], active_x[-1], 300) if len(active_x) >= 2 else active_x
            for method, line_thrust, line_isp, line_cf in active_series:
                if metric == "thrust":
                    y_data = line_thrust
                elif metric == "isp":
                    y_data = line_isp
                else:
                    y_data = line_cf

                y_plot = PchipInterpolator(active_x, y_data)(x_plot) if len(active_x) >= 2 else y_data
                ax.plot(
                    x_plot,
                    y_plot,
                    label=method["legend"],
                    color=method["color"],
                    linestyle=method["linestyle"],
                    linewidth=2.0 if method["linestyle"] == ":" else 1.8,
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

    run_with_loading_circle(ui, "comparison_loading_circle", compute, render)


generate_performance_comparison_table = generate_table
generate_performance_comparison_graph = generate_graph
