import importlib
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core import cea, input as core_input

_angelino = importlib.import_module("core.performance.1d-modified-angelino")


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
                f.write("Condition,P_atm (bar),Thrust (kN),CF,Isp (s)\n")
                for r in data_rows:
                    f.write(f'"{r[0]}",{r[1]},{r[2]},{r[3]},{r[4]}\n')
            else:
                f.write(f"{'Condition':<18} {'P_atm (bar)':>12} {'Thrust (kN)':>14} {'CF':>8} {'Isp (s)':>10}\n")
                f.write("-" * 66 + "\n")
                for r in data_rows:
                    f.write(f"{r[0]:<18} {r[1]:>12} {r[2]:>14} {r[3]:>8} {r[4]:>10}\n")
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

    conditions = [
        ("Sea Level", 101325.0),
        ("Design Point", p_design),
        ("Vacuum", 0.0),
    ]

    for val in given_values:
        if mode == "Altitude":
            h_m = val * 1000.0
            p_atm = max(0.0, core_input.altitude_to_pressure(h_m))
            label = f"{val:g} km"
        else:
            p_atm = max(0.0, val * 1e5)
            label = f"{val:g} bar"
        conditions.append((label, p_atm))

    bg_parent = ttk.Style().lookup("TFrame", "background") or "SystemButtonFace"
    line_color = "#c5c8cc"

    window = tk.Toplevel(ui.root)
    window.title("Altitude Performance")
    window.geometry("480x320")
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

    for col, weight in enumerate((3, 3, 3, 2, 3)):
        table.columnconfigure(col, weight=weight)

    headers = [
        ([("#", False)], "w"),
        ([("P", False), ("atm", True), (" (bar)", False)], "e"),
        ([("Thrust(kN)", False)], "e"),
        ([("C", False), ("F", True)], "e"),
        ([("I", False), ("sp", True), ("(s)", False)], "e"),
    ]
    for col, (parts, anchor) in enumerate(headers):
        _header_cell(table, col, parts, bg_parent, anchor)

    rows_to_save = []
    for row_idx, (label, p_atm) in enumerate(conditions, start=1):
        cf, f_total, isp, _ = _angelino.thrust(inputs, calc_results, p_atm)
        thrust_str = f"{f_total / 1e3:.2f}" if is_sized else "—"
        p_str = f"{p_atm / 1e5:.3f}"
        cf_str = f"{cf:.3f}"
        isp_str = f"{isp:.1f}"

        rows_to_save.append((label, p_str, thrust_str, cf_str, isp_str))

        row_values = [
            (label, ("Arial", 9, "bold"), "w"),
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

    import matplotlib
    if matplotlib.get_backend().lower() != "agg":
        try:
            matplotlib.use("TkAgg")
        except Exception:
            pass
    import matplotlib.pyplot as plt

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
    h_design = core_input.pressure_to_altitude(p_design) if p_design is not None else 0.0

    is_pressure = mode == "Pressure"

    chosen_pts = []
    for val in given_values:
        if is_pressure:
            p_atm = max(0.0, float(val) * 1e5)
            x_val = float(val)
        else:
            p_atm = max(0.0, core_input.altitude_to_pressure(float(val) * 1000.0))
            x_val = float(val)
        _, f_tot, isp, _ = _angelino.thrust(inputs, calc_results, p_atm)
        chosen_pts.append((x_val, f_tot, isp))

    p_sl = 101325.0
    _, f_sl, isp_sl, _ = _angelino.thrust(inputs, calc_results, p_sl)
    _, f_des, isp_des, _ = _angelino.thrust(inputs, calc_results, p_design)
    _, f_vac, isp_vac, _ = _angelino.thrust(inputs, calc_results, 0.0)

    x_sl = 1.01325 if is_pressure else 0.0
    x_des = (p_design / 1e5) if is_pressure else (h_design / 1e3)
    x_vac = 0.0 if is_pressure else 80.0

    if is_pressure:
        base_x = [0.0, 0.02, 0.05, 0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 0.95, 1.01325]
        sample_x = sorted(set(round(x, 4) for x in base_x + [x_des] + [pt[0] for pt in chosen_pts] if x >= 0))
        sample_p = [x * 1e5 for x in sample_x]
    else:
        base_x = [0.0, 2.0, 5.0, 8.0, 11.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 60.0, 80.0]
        sample_x = sorted(set(round(x, 1) for x in base_x + [x_des] + [pt[0] for pt in chosen_pts] if x >= 0))
        sample_p = [max(0.0, core_input.altitude_to_pressure(x * 1e3)) for x in sample_x]

    line_x, line_thrust, line_isp = [], [], []
    for x, p in zip(sample_x, sample_p):
        _, f_tot, isp, _ = _angelino.thrust(inputs, calc_results, p)
        line_x.append(x)
        line_thrust.append(f_tot / 1e3)
        line_isp.append(isp)

    chosen_x = [pt[0] for pt in chosen_pts]
    chosen_thrust = [pt[1] / 1e3 for pt in chosen_pts]
    chosen_isp = [pt[2] for pt in chosen_pts]

    x_label = "Ambient Pressure $P_{atm}$ (bar)" if is_pressure else "Altitude (km)"
    title_thrust = "Thrust vs Ambient Pressure" if is_pressure else "Thrust vs Altitude"
    title_isp = "Specific Impulse vs Ambient Pressure" if is_pressure else "Specific Impulse vs Altitude"
    y_thrust_label = "Thrust (kN)" if is_sized else "Thrust (kN/m) [Unsized]"

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.0, 3.8), dpi=100)

    # Subplot 1: Thrust vs Altitude / Pressure
    ax1.plot(line_x, line_thrust, color="black", linewidth=1.6, label="Thrust", zorder=2)
    ax1.scatter([x_des], [f_des / 1e3], color="#dc2626", marker="o", s=45, zorder=5, label="Design Point")
    ax1.scatter([x_sl], [f_sl / 1e3], color="#2563eb", marker="s", s=45, zorder=5, label="Sea Level (SL)")
    ax1.scatter([x_vac], [f_vac / 1e3], color="#7c3aed", marker="^", s=45, zorder=5, label="Vacuum")
    if chosen_pts:
        ax1.scatter(chosen_x, chosen_thrust, color="#16a34a", marker="D", s=35, zorder=5, label="Given Points")
    else:
        ax1.scatter([], [], color="#16a34a", marker="D", s=35, label="Given Points")
    ax1.set_xlabel(x_label, fontsize=9)
    ax1.set_ylabel(y_thrust_label, fontsize=9)
    ax1.set_title(title_thrust, fontsize=10, fontweight="bold")
    ax1.grid(True, linestyle=":", alpha=0.6)
    if is_pressure:
        ax1.invert_xaxis()
    ax1.legend(loc="lower right", fontsize=8, frameon=True)

    # Subplot 2: Specific Impulse vs Altitude / Pressure
    ax2.plot(line_x, line_isp, color="black", linewidth=1.6, label="Isp", zorder=2)
    ax2.scatter([x_des], [isp_des], color="#dc2626", marker="o", s=45, zorder=5, label="Design Point")
    ax2.scatter([x_sl], [isp_sl], color="#2563eb", marker="s", s=45, zorder=5, label="Sea Level (SL)")
    ax2.scatter([x_vac], [isp_vac], color="#7c3aed", marker="^", s=45, zorder=5, label="Vacuum")
    if chosen_pts:
        ax2.scatter(chosen_x, chosen_isp, color="#16a34a", marker="D", s=35, zorder=5, label="Given Points")
    else:
        ax2.scatter([], [], color="#16a34a", marker="D", s=35, label="Given Points")
    ax2.set_xlabel(x_label, fontsize=9)
    ax2.set_ylabel("Specific Impulse $I_{sp}$ (s)", fontsize=9)
    ax2.set_title(title_isp, fontsize=10, fontweight="bold")
    ax2.grid(True, linestyle=":", alpha=0.6)
    if is_pressure:
        ax2.invert_xaxis()
    ax2.legend(loc="lower right", fontsize=8, frameon=True)

    fuel = definition.get("fuel", "")
    ox = definition.get("oxidizer", "")
    prop_str = f" ({ox}/{fuel})" if ox and fuel else ""
    pc_val = inputs.get("Pc", 0.0) / 1e5
    mr_val = definition.get("MR", 0.0)
    eps_val = definition.get("eps", 0.0)
    eps_t_val = definition.get("effective_throat_eps", 0.0)
    trunc_val = definition.get("truncate_percent", 100.0)
    perf_mode = "Pressure" if is_pressure else "Altitude"
    fig.suptitle(
        f"Aerospike {perf_mode} Performance{prop_str}\n"
        f"$P_c = {pc_val:.1f}\\ \\mathrm{{bar}},\\ \\mathrm{{MR}} = {mr_val:.2f},\\ "
        f"\\varepsilon = {eps_val:.1f},\\ \\varepsilon_t = {eps_t_val:.1f},\\ "
        f"\\mathrm{{Truncation}} = {trunc_val:.0f}\\%$",
        fontsize=9,
    )

    plt.tight_layout()
    plt.show()
