import importlib
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core import cea, input as core_input

_angelino = importlib.import_module("core.performance.1d-modified-angelino")
_calibrated = importlib.import_module("core.performance.1d-design-calibrated")


def _get_active_model(ui):
    choice = getattr(ui, "altitude_model_var", tk.StringVar(value="angelino")).get()
    return _calibrated if "calibrated" in choice.lower() else _angelino


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


def _save_table(data_rows, parent):
    file_path = filedialog.asksaveasfilename(
        parent=parent,
        defaultextension=".csv",
        initialfile="altitude_performance.csv",
        filetypes=[("CSV files", "*.csv"), ("Text files", "*.txt"), ("All files", "*.*")],
    )
    if not file_path:
        return
    try:
        is_csv = file_path.lower().endswith(".csv")
        with open(file_path, "w", encoding="utf-8") as f:
            if is_csv:
                f.write("Condition,Altitude (km),P_atm (bar),Thrust (kN),CF,Isp (s)\n")
                for r in data_rows:
                    f.write(f'"{r[0]}",{r[1]},{r[2]},{r[3]},{r[4]},{r[5]}\n')
            else:
                f.write(f"{'Condition':<18} {'Altitude (km)':>14} {'P_atm (bar)':>12} {'Thrust (kN)':>14} {'CF':>8} {'Isp (s)':>10}\n")
                f.write("-" * 81 + "\n")
                for r in data_rows:
                    f.write(f"{r[0]:<18} {r[1]:>14} {r[2]:>12} {r[3]:>14} {r[4]:>8} {r[5]:>10}\n")
        messagebox.showinfo("Saved", "Altitude performance table saved successfully.", parent=parent)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to save file: {e}", parent=parent)


def generate_altitude_performance_table(ui):
    results = ui.case.get("results", {})
    definition = ui.case.get("definition", {})
    if not results.get("x"):
        messagebox.showerror("Error", "Run the program before analyzing altitude performance.")
        return

    raw_text = ui.input_analysis.get().strip() if hasattr(ui, "input_analysis") else ""
    raw_mode = ui.analysis_type.get() if hasattr(ui, "analysis_type") else "Altitude"
    mode = "Pressure" if "pressure" in raw_mode.lower() else "Altitude"
    given_values = core_input.parse_analysis_inputs(raw_text)

    inputs = {**definition, "Pc": core_input.pressure_conversion(definition.get("Pc"), definition.get("unit_Pc"))}
    if inputs.get("eps") is None and results.get("eps") is not None:
        inputs["eps"] = results["eps"]
    is_sized = results.get("mfr") is not None
    if is_sized:
        calc_results = results
    else:
        v_t, rho_t = cea.effective_throat_conditions(inputs)
        calc_results = {**results, "length": 1.0, "mfr": rho_t * v_t * 2.0 * results["throat_length"]}

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

    bg_parent = ttk.Style().lookup("TFrame", "background") or "SystemButtonFace"
    line_color = "#c5c8cc"

    window = tk.Toplevel(ui.root)
    window.title("Altitude Performance")
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

    table = tk.Frame(canvas, bg=line_color, bd=0)
    win_item = canvas.create_window((0, 0), window=table, anchor="nw")
    table.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_item, width=e.width))

    for col, weight in enumerate((3, 2, 3, 3, 2, 3)):
        table.columnconfigure(col, weight=weight)

    headers = [
        ([("#", False)], "w"),
        ([("h", False), (" (km)", False)], "e"),
        ([("P", False), ("atm", True), (" (bar)", False)], "e"),
        ([("Thrust(kN)", False)], "e"),
        ([("C", False), ("F", True)], "e"),
        ([("I", False), ("sp", True), ("(s)", False)], "e"),
    ]
    for col, (parts, anchor) in enumerate(headers):
        _header_cell(table, col, parts, bg_parent, anchor)

    model = _get_active_model(ui)
    rows_to_save = []
    for row_idx, (label, p_atm, h_val) in enumerate(conditions, start=1):
        cf, f_total, isp, _ = model.thrust(inputs, calc_results, p_atm)
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

    save_btn = ttk.Button(bottom_bar, text="Save As", command=lambda: _save_table(rows_to_save, window))
    save_btn.pack(side="right")


def generate_altitude_performance_graph(ui):
    results = ui.case.get("results", {})
    definition = ui.case.get("definition", {})
    if not results.get("x"):
        messagebox.showerror("Error", "Run the program before analyzing altitude performance.")
        return

    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    from matplotlib.figure import Figure

    raw_text = ui.input_analysis.get().strip() if hasattr(ui, "input_analysis") else ""
    raw_mode = ui.analysis_type.get() if hasattr(ui, "analysis_type") else "Altitude"
    mode = "Pressure" if "pressure" in raw_mode.lower() else "Altitude"
    given_values = core_input.parse_analysis_inputs(raw_text)

    inputs = {**definition, "Pc": core_input.pressure_conversion(definition.get("Pc"), definition.get("unit_Pc"))}
    if inputs.get("eps") is None and results.get("eps") is not None:
        inputs["eps"] = results["eps"]
    is_sized = results.get("mfr") is not None
    if is_sized:
        calc_results = results
    else:
        v_t, rho_t = cea.effective_throat_conditions(inputs)
        calc_results = {**results, "length": 1.0, "mfr": rho_t * v_t * 2.0 * results["throat_length"]}

    p_design = results.get("ideal_expansion_pressure")
    if p_design is None:
        p_design = cea.ideal_expansion_pressure(inputs)
    h_design = core_input.pressure_to_altitude(p_design) if (p_design is not None and p_design <= 101325.0) else None

    model = _get_active_model(ui)

    is_pressure = mode == "Pressure"

    p_sl = 101325.0
    cf_sl, f_sl, isp_sl, _ = model.thrust(inputs, calc_results, p_sl)
    cf_des, f_des, isp_des, _ = model.thrust(inputs, calc_results, p_design)
    cf_vac, f_vac, isp_vac, _ = model.thrust(inputs, calc_results, 0.0)

    chosen_pts = []
    for val in given_values:
        if is_pressure:
            p_atm = max(0.0, float(val) * 1e5)
            h_km = (core_input.pressure_to_altitude(p_atm) / 1000.0) if p_atm <= 101325.0 else None
            p_bar = float(val)
        else:
            h_km = float(val)
            p_atm = max(0.0, core_input.altitude_to_pressure(h_km * 1000.0))
            p_bar = p_atm / 1e5
        cf_val, f_tot, isp, _ = model.thrust(inputs, calc_results, p_atm)
        chosen_pts.append({"h": h_km, "p": p_bar, "thrust": f_tot / 1e3, "isp": isp, "cf": cf_val})

    # 1. Precalculate Altitude Series
    alt_base_x = [0.0, 2.0, 5.0, 8.0, 11.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 60.0, 80.0]
    h_des_km = (h_design / 1000.0) if h_design is not None else None
    alt_user_x = [pt["h"] for pt in chosen_pts if pt["h"] is not None and 0.0 <= pt["h"] <= 80.0]
    alt_sample_x = sorted(set(round(x, 2) for x in alt_base_x + alt_user_x + ([h_des_km] if h_des_km is not None else [])))
    alt_sample_p = [max(0.0, core_input.altitude_to_pressure(x * 1e3)) for x in alt_sample_x]
    alt_line_thrust, alt_line_isp, alt_line_cf = [], [], []
    for p in alt_sample_p:
        cf_val, f_tot, isp, _ = model.thrust(inputs, calc_results, p)
        alt_line_thrust.append(f_tot / 1e3)
        alt_line_isp.append(isp)
        alt_line_cf.append(cf_val)

    # 2. Precalculate Pressure Series
    press_base_x = [0.0, 0.02, 0.05, 0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 0.95, 1.01325]
    p_des_bar = p_design / 1e5
    press_user_x = [pt["p"] for pt in chosen_pts if pt["p"] is not None and 0.0 <= pt["p"] <= 1.01325]
    press_sample_x = sorted(set(round(x, 4) for x in press_base_x + press_user_x + [p_des_bar] if 0.0 <= x <= 1.01325))
    press_sample_p = [x * 1e5 for x in press_sample_x]
    press_line_thrust, press_line_isp, press_line_cf = [], [], []
    for p in press_sample_p:
        cf_val, f_tot, isp, _ = model.thrust(inputs, calc_results, p)
        press_line_thrust.append(f_tot / 1e3)
        press_line_isp.append(isp)
        press_line_cf.append(cf_val)

    y_thrust_label = "Thrust (kN)" if is_sized else "Thrust (kN/m) [Unsized]"
    y_isp_label = "Specific Impulse $I_{sp}$ (s)"
    y_cf_label = "Thrust Coefficient $C_F$"

    window = tk.Toplevel(ui.root)
    window.title("Altitude Performance Graph")
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

    fig = Figure(figsize=(6.4, 4.4), dpi=100)
    ax = fig.add_subplot(111)

    canvas = FigureCanvasTkAgg(fig, master=plot_frame)
    toolbar = NavigationToolbar2Tk(canvas, plot_frame)
    toolbar.update()
    toolbar.pack(side="bottom", fill="x")
    canvas.get_tk_widget().pack(side="top", fill="both", expand=True)

    fuel = definition.get("fuel", "")
    ox = definition.get("oxidizer", "")
    prop_str = f" ({ox}/{fuel})" if ox and fuel else ""
    pc_val = inputs.get("Pc", 0.0) / 1e5
    mr_val = definition.get("MR", 0.0)
    eps_val = definition.get("eps", 0.0)
    eps_t_val = definition.get("effective_throat_eps", 0.0)
    trunc_val = definition.get("truncate_percent", 100.0)

    def render_plot():
        ax.clear()
        x_selected = plot_x_choice.get()
        is_p = "pressure" in x_selected.lower()

        if is_p:
            line_x = press_sample_x
            line_thrust = press_line_thrust
            line_isp = press_line_isp
            line_cf = press_line_cf
            x_label = "Ambient Pressure $P_{atm}$ (bar)"
            x_sl = 1.01325
            x_des = p_des_bar
            x_vac = 0.0
            user_x = [pt["p"] for pt in chosen_pts if pt["p"] is not None]
        else:
            line_x = alt_sample_x
            line_thrust = alt_line_thrust
            line_isp = alt_line_isp
            line_cf = alt_line_cf
            x_label = "Altitude (km)"
            x_sl = 0.0
            x_des = h_des_km
            x_vac = 80.0
            user_x = [pt["h"] for pt in chosen_pts if pt["h"] is not None]

        selected = plot_choice.get()
        if "thrust" in selected.lower():
            metric = "thrust"
        elif "c" in selected.lower() or "\ua730" in selected:
            metric = "cf"
        else:
            metric = "isp"

        x_prefix = "Ambient Pressure" if is_p else "Altitude"
        if metric == "thrust":
            y_label = y_thrust_label
            plot_title = f"{x_prefix}-Thrust Performance"
            curve_y = line_thrust
            des_y = f_des / 1e3
            sl_y = f_sl / 1e3
            vac_y = f_vac / 1e3
            user_y = [pt["thrust"] for pt in chosen_pts if (pt["p"] if is_p else pt["h"]) is not None]
            curve_label = "Thrust"
        elif metric == "isp":
            y_label = y_isp_label
            plot_title = f"{x_prefix}-Isp Performance"
            curve_y = line_isp
            des_y = isp_des
            sl_y = isp_sl
            vac_y = isp_vac
            user_y = [pt["isp"] for pt in chosen_pts if (pt["p"] if is_p else pt["h"]) is not None]
            curve_label = "Isp"
        else:
            y_label = y_cf_label
            plot_title = f"{x_prefix}-Thrust Coefficient Performance"
            curve_y = line_cf
            des_y = cf_des
            sl_y = cf_sl
            vac_y = cf_vac
            user_y = [pt["cf"] for pt in chosen_pts if (pt["p"] if is_p else pt["h"]) is not None]
            curve_label = "$C_F$"

        ax.plot(line_x, curve_y, color="black", linewidth=1.6, label=curve_label, zorder=2)
        if x_des is not None:
            ax.scatter([x_des], [des_y], color="#dc2626", marker="o", s=45, zorder=5, label="Design Point")
        ax.scatter([x_sl], [sl_y], color="#2563eb", marker="s", s=45, zorder=5, label="Sea Level (SL)")
        ax.scatter([x_vac], [vac_y], color="#7c3aed", marker="^", s=45, zorder=5, label="Vacuum")
        if user_x:
            ax.scatter(user_x, user_y, color="#16a34a", marker="D", s=35, zorder=5, label="Given Points")
        else:
            ax.scatter([], [], color="#16a34a", marker="D", s=35, label="Given Points")

        ax.set_xlabel(x_label, fontsize=9)
        ax.set_ylabel(y_label, fontsize=9)
        ax.set_title("", fontsize=10, fontweight="bold")
        ax.grid(True, linestyle=":", alpha=0.6)
        if is_p:
            ax.invert_xaxis()
        ax.legend(loc="lower right" if (is_p and metric != "thrust") else "best", fontsize=8, frameon=True)

        subtitle = (
            f"{plot_title}{prop_str}\n"
            f"$P_c = {pc_val:.1f}\\ \\mathrm{{bar}},\\ \\mathrm{{MR}} = {mr_val:.2f},\\ "
            f"\\varepsilon = {eps_val:.1f},\\ \\varepsilon_t = {eps_t_val:.1f},\\ "
            f"\\mathrm{{Truncation}} = {trunc_val:.0f}\\%$"
        )
        fig.suptitle(subtitle, fontsize=9)
        fig.tight_layout()
        canvas.draw()
        toolbar.update()

    apply_btn = ttk.Button(sidebar, text="Apply", command=render_plot)
    apply_btn.pack(fill="x", pady=(2, 0))

    render_plot()
