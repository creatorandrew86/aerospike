import math
import threading
import tkinter as tk
from tkinter import font, messagebox, ttk

from core import cea, input as core_input
from core.output import index


def _create_tooltip(widget, text):
    tip = [None]

    def show(_):
        if tip[0]:
            return
        x, y = widget.winfo_rootx() + 18, widget.winfo_rooty() + 5
        t = tk.Toplevel(widget)
        t.wm_overrideredirect(True)
        t.geometry(f"+{x}+{y}")
        tk.Label(t, text=text, bg="#1f2937", fg="#ffffff", font=("Arial", 8), padx=6, pady=3).pack()
        tip[0] = t

    def hide(_):
        if tip[0]:
            tip[0].destroy()
            tip[0] = None

    widget.bind("<Enter>", show)
    widget.bind("<Leave>", hide)
    widget.bind("<Destroy>", hide)


def _create_loading_circle(parent, bg, size=20):
    blank = tk.PhotoImage(width=size, height=size)
    label = tk.Label(parent, image=blank, bg=bg, bd=0, highlightthickness=0)
    label._blank_image = blank
    label._bg_name = bg
    return label


def _loading_circle_frames(widget, bg, size=20):
    root = widget.winfo_toplevel()
    if hasattr(root, "_loading_frames"):
        return root._loading_frames
    bg_rgb = tuple(c >> 8 for c in widget.winfo_rgb(bg))
    track, arc = (210, 214, 220), (95, 103, 115)
    cx = cy = (size - 1) / 2.0
    r_mid, half_w, sweep = 6.2, 1.6, math.radians(220)
    frames = []
    for step in range(24):
        a0 = math.radians(-step * 15)
        caps = ((r_mid * math.cos(a0), -r_mid * math.sin(a0)), (r_mid * math.cos(a0 + sweep), -r_mid * math.sin(a0 + sweep)))
        rows = []
        for y in range(size):
            dy = y - cy
            row = []
            for x in range(size):
                dx = x - cx
                d_ring = abs(math.hypot(dx, dy) - r_mid) - half_w
                ang = (-math.atan2(dy, dx) - a0) % (2.0 * math.pi)
                d_arc = d_ring if ang <= sweep else min(math.hypot(dx - ex, dy - ey) for ex, ey in caps) - half_w
                a_t = min(1.0, max(0.0, 0.5 - d_ring))
                a_a = min(1.0, max(0.0, 0.5 - d_arc))
                cr = bg_rgb[0] + (track[0] - bg_rgb[0]) * a_t
                cg = bg_rgb[1] + (track[1] - bg_rgb[1]) * a_t
                cb = bg_rgb[2] + (track[2] - bg_rgb[2]) * a_t
                row.append(f"#{int(cr + (arc[0] - cr) * a_a):02x}{int(cg + (arc[1] - cg) * a_a):02x}{int(cb + (arc[2] - cb) * a_a):02x}")
            rows.append("{" + " ".join(row) + "}")
        img = tk.PhotoImage(width=size, height=size)
        img.put(" ".join(rows))
        frames.append(img)
    root._loading_frames = frames
    return frames


def run_with_loading_circle(ui, circle_attr, work_fn, done_fn):
    circle = getattr(ui, circle_attr, None)
    if circle is None or not hasattr(ui, "root"):
        done_fn(work_fn())
        return
    if getattr(ui, "_loading_busy", False):
        return

    buttons = [
        btn for name in (
            "run_button",
            "table_analysis_button",
            "graph_analysis_button",
            "table_comparison_button",
            "graph_comparison_button",
            "mesh_button",
            "geo_button",
            "cfd_case_definition_button",
            "mesh_quality_button",
        )
        if (btn := getattr(ui, name, None)) is not None and str(btn.cget("state")) != "disabled"
    ]
    ui._loading_busy = True
    for btn in buttons:
        btn.configure(state="disabled")

    frames = _loading_circle_frames(circle, circle._bg_name)
    result, error = [], []

    def worker():
        try:
            result.append(work_fn())
        except Exception as exc:
            error.append(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    def tick(frame=0):
        if not ui.root.winfo_exists() or not circle.winfo_exists():
            ui._loading_busy = False
            return
        if thread.is_alive():
            circle.configure(image=frames[frame])
            ui.root.after(50, tick, (frame + 1) % len(frames))
            return
        circle.configure(image=circle._blank_image)
        ui._loading_busy = False
        for btn in buttons:
            btn.configure(state="normal")
        if error:
            messagebox.showerror("Error", str(error[0]))
            return
        done_fn(result[0])

    tick()


def build_interface(ui):
    section_font = font.Font(family="Arial", size=10, weight="bold")
    bg_parent = ttk.Style().lookup("TFrame", "background") or "SystemButtonFace"
    ui.notebook = ttk.Notebook(ui.root)
    ui.notebook.grid(column=0, row=0, sticky='NSEW')
    ui.root.columnconfigure(0, weight=1)
    ui.root.rowconfigure(0, weight=1)

    ui.aerospike_tab = ttk.Frame(ui.notebook)
    ui.results_tab = ttk.Frame(ui.notebook)
    ui.cfd_tab = ttk.Frame(ui.notebook)
    ui.notebook.add(ui.aerospike_tab, text="Definition")
    ui.notebook.add(ui.results_tab, text="Results")
    ui.notebook.add(ui.cfd_tab, text="CFD")

    oxidizer_items = ["LOX", "GOX", "N2O4", "N2O", "IRFNA", "H2O2", "Peroxide90", "Peroxide98", "MON3", "MON15", "MON25"]
    fuel_items = ["RP1", "LH2", "CH4", "MMH", "N2H4", "UDMH", "A50", "Ethanol", "Methanol", "GH2", "GCH4", "JetA", "JP10"]
    pad_label = dict(padx=(10, 4), pady=(1, 2), sticky='W')
    pad_input = dict(padx=(0, 10), pady=(1, 2), sticky='W')

    # Definition tab: engine inputs
    ttk.Label(ui.aerospike_tab, text="Engine Definition", font=section_font).grid(
        column=0, row=0, columnspan=2, padx=10, pady=(10, 5), sticky='W'
    )
    ttk.Label(ui.aerospike_tab, text='Oxidizer:').grid(column=0, row=1, **pad_label)
    ui.input_oxidizer = ttk.Combobox(ui.aerospike_tab, values=oxidizer_items, width=15, state='readonly')
    ui.input_oxidizer.grid(column=1, row=1, **pad_input)

    ttk.Label(ui.aerospike_tab, text='Fuel:').grid(column=0, row=2, **pad_label)
    ui.input_fuel = ttk.Combobox(ui.aerospike_tab, values=fuel_items, width=15, state='readonly')
    ui.input_fuel.grid(column=1, row=2, **pad_input)

    ttk.Label(ui.aerospike_tab, text='Chamber Pressure:').grid(column=0, row=3, **pad_label)
    pc_row = ttk.Frame(ui.aerospike_tab)
    pc_row.grid(column=1, row=3, padx=(0, 10), pady=(1, 2), sticky='W')
    ui.input_Pc = ttk.Entry(pc_row, width=8)
    ui.input_Pc.grid(column=0, row=0, sticky='W')
    ui.unit_Pc = ttk.Combobox(pc_row, values=["bar", "Pa", "atm", "kPa", "psi", "MPa"], width=5, state='readonly')
    ui.unit_Pc.grid(column=1, row=0, padx=(6, 0), sticky='W')
    ui.unit_Pc.set("bar")

    ttk.Label(ui.aerospike_tab, text='Mixture Ratio:').grid(column=0, row=4, **pad_label)
    ui.input_MR = ttk.Entry(ui.aerospike_tab, width=18)
    ui.input_MR.grid(column=1, row=4, **pad_input)

    # Definition tab: nozzle inputs
    ttk.Label(ui.aerospike_tab, text='Nozzle Definition', font=section_font).grid(
        column=0, row=5, columnspan=2, padx=10, pady=(10, 5), sticky='W'
    )
    ui.nozzle_choice = tk.StringVar(value="area_ratio")
    ui.area_ratio_radio = ttk.Radiobutton(
        ui.aerospike_tab, text='Design Area Ratio:', value='area_ratio', variable=ui.nozzle_choice, command=ui.on_nozzle_choice_change
    )
    ui.area_ratio_radio.grid(column=0, row=6, **pad_label)
    ui.input_eps = ttk.Entry(ui.aerospike_tab, width=18)
    ui.input_eps.grid(column=1, row=6, **pad_input)

    ui.pressure_radio = ttk.Radiobutton(
        ui.aerospike_tab, text='Design Pressure:', value='design_pressure', variable=ui.nozzle_choice, command=ui.on_nozzle_choice_change
    )
    ui.pressure_radio.grid(column=0, row=7, **pad_label)
    p_row = ttk.Frame(ui.aerospike_tab)
    p_row.grid(column=1, row=7, padx=(0, 10), pady=(1, 2), sticky='W')
    ui.input_design_pressure = ttk.Entry(p_row, width=8, state='disabled')
    ui.input_design_pressure.grid(column=0, row=0, sticky='W')
    ui.unit_design_pressure = ttk.Combobox(p_row, values=["bar", "Pa", "atm", "kPa", "psi", "MPa"], width=5, state='disabled')
    ui.unit_design_pressure.grid(column=1, row=0, padx=(6, 0), sticky='W')
    ui.unit_design_pressure.set("bar")
    ui.input_pressure_ratio = ui.input_design_pressure
    ui.pressure_ratio_radio = ui.pressure_radio

    ttk.Label(ui.aerospike_tab, text='Thruster Area Ratio:').grid(column=0, row=8, padx=(10, 4), pady=(6, 2), sticky='W')
    ui.input_effective_throat_eps = ttk.Entry(ui.aerospike_tab, width=18)
    ui.input_effective_throat_eps.grid(column=1, row=8, padx=(0, 10), pady=(6, 2), sticky='W')

    ttk.Label(ui.aerospike_tab, text='Truncate at (%):').grid(column=0, row=9, **pad_label)
    ui.input_truncate_percentage = ttk.Entry(ui.aerospike_tab, width=18)
    ui.input_truncate_percentage.grid(column=1, row=9, **pad_input)

    ttk.Label(ui.aerospike_tab, text='Number of Points Analyzed:').grid(column=0, row=10, **pad_label)
    ui.input_aerospike_resolution = ttk.Entry(ui.aerospike_tab, width=18)
    ui.input_aerospike_resolution.grid(column=1, row=10, **pad_input)

    # Placeholder on last row of column 1 to absorb excess height and preserve original gaps
    ui.placeholder = ttk.Label(ui.aerospike_tab, text='')
    ui.placeholder.grid(column=1, row=11, sticky='NSEW')
    ui.aerospike_tab.rowconfigure(11, weight=1)

    # Definition tab: sizing controls
    ui.sizing_area = ttk.Frame(ui.aerospike_tab)
    ui.sizing_area.grid(column=2, row=0, rowspan=12, columnspan=2, padx=5, sticky='NW')
    ttk.Label(ui.sizing_area, text="Aerospike Sizing Method", font=section_font).grid(
        column=0, row=0, pady=(10, 2), sticky='W'
    )
    ui.sizing_var = tk.BooleanVar(value=False)
    ui.sizing_frame = ttk.LabelFrame(ui.sizing_area)
    ui.sizing_frame.grid(column=0, row=1, pady=(0, 6), sticky='W')
    ui.sizing_check = ttk.Checkbutton(ui.sizing_frame, text="Sizing", variable=ui.sizing_var, command=ui.on_sizing_toggle)
    ui.sizing_frame.configure(labelwidget=ui.sizing_check)

    # Linear sizing inputs
    ui.linear_var = tk.BooleanVar(value=False)
    ui.linear_frame = ttk.LabelFrame(ui.sizing_frame)
    ui.linear_frame.grid(column=0, row=1, padx=8, pady=(4, 4), sticky='WE')
    ui.linear_check = ttk.Checkbutton(ui.linear_frame, text="Linear", variable=ui.linear_var, command=ui.on_linear_toggle)
    ui.linear_frame.configure(labelwidget=ui.linear_check)
    ui.linear_massflow_var = tk.BooleanVar(value=False)
    ui.linear_length_var = tk.BooleanVar(value=False)
    ui.linear_width_var = tk.BooleanVar(value=False)
    _build_sizing_row(ui, ui.linear_frame, 0, "Mass Flow:", "linear_massflow", ["kg/s", "lb/s"])
    _build_sizing_row(ui, ui.linear_frame, 1, "Length:", "linear_length", ["m", "cm", "mm", "in", "ft"])
    _build_sizing_row(ui, ui.linear_frame, 2, "Width:", "linear_width", ["m", "cm", "mm", "in", "ft"])

    # Toroidal sizing inputs
    ui.toroidal_var = tk.BooleanVar(value=False)
    ui.toroidal_frame = ttk.LabelFrame(ui.sizing_frame)
    ui.toroidal_frame.grid(column=0, row=2, padx=8, pady=(4, 6), sticky='WE')
    ui.toroidal_check = ttk.Checkbutton(ui.toroidal_frame, text="Toroidal", variable=ui.toroidal_var, command=ui.on_toroidal_toggle)
    ui.toroidal_frame.configure(labelwidget=ui.toroidal_check)
    ui.toroidal_choice = tk.StringVar(value="massflow")
    ui.toroidal_massflow_radio = ttk.Radiobutton(
        ui.toroidal_frame, text="Mass Flow:", value="massflow", variable=ui.toroidal_choice, command=ui.on_toroidal_choice_change
    )
    ui.toroidal_massflow_radio.grid(column=0, row=0, padx=(20, 4), pady=2, sticky='W')
    ui.toroidal_massflow_entry = ttk.Entry(ui.toroidal_frame, width=10, state='disabled')
    ui.toroidal_massflow_entry.grid(column=1, row=0, padx=4, pady=2, sticky='W')
    ui.toroidal_massflow_unit = ttk.Combobox(ui.toroidal_frame, values=["kg/s", "lb/s"], width=5, state='disabled')
    ui.toroidal_massflow_unit.set("kg/s")
    ui.toroidal_massflow_unit.grid(column=2, row=0, padx=2, pady=2, sticky='W')
    ui.toroidal_radius_radio = ttk.Radiobutton(
        ui.toroidal_frame, text="Cowl Radius:", value="radius", variable=ui.toroidal_choice, command=ui.on_toroidal_choice_change
    )
    ui.toroidal_radius_radio.grid(column=0, row=1, padx=(20, 4), pady=2, sticky='W')
    ui.toroidal_radius_entry = ttk.Entry(ui.toroidal_frame, width=10, state='disabled')
    ui.toroidal_radius_entry.grid(column=1, row=1, padx=4, pady=2, sticky='W')
    ui.toroidal_radius_unit = ttk.Combobox(ui.toroidal_frame, values=["m", "cm", "mm", "in", "ft"], width=5, state='disabled')
    ui.toroidal_radius_unit.set("m")
    ui.toroidal_radius_unit.grid(column=2, row=1, padx=2, pady=2, sticky='W')

    # Run action
    run_area = ttk.Frame(ui.sizing_area)
    run_area.grid(column=0, row=2, pady=(2, 10), sticky='EW')
    run_area.columnconfigure(0, weight=1)
    ui.run_button = ttk.Button(run_area, text='Run', command=ui.on_run)
    ui.run_button.grid(column=0, row=0, padx=(0, 6), sticky='EW')
    ui.run_loading_circle = _create_loading_circle(run_area, bg_parent)
    ui.run_loading_circle.grid(column=1, row=0)

    # Results tab
    ui.results_frame = ttk.LabelFrame(ui.results_tab, padding=14)
    ui.results_frame.grid(column=0, row=0, padx=(10, 5), pady=(10, 4), sticky="NSEW")
    ui.results_title = ttk.Label(ui.results_frame, text="Geometry", font=section_font)
    ui.results_frame.configure(labelwidget=ui.results_title)
    ui.main_output = ttk.Frame(ui.results_frame)
    ui.main_output.grid(column=0, row=0, sticky="NSEW")
    ui.main_output.columnconfigure(0, weight=1)
    ui.results_frame.columnconfigure(0, weight=1)
    ui.results_frame.rowconfigure(0, weight=1)
    ttk.Label(ui.main_output, text="No results available.", foreground="gray40").grid(column=0, row=0, sticky="W")
    ui.graph_button = ttk.Button(ui.results_frame, text='Contour Graph', command=lambda: index.graph_output(ui), state='disabled')
    ui.graph_button.grid(column=0, row=1, pady=(6, 0), sticky='EW')

    ui.performance_frame = ttk.LabelFrame(ui.results_tab, padding=10)
    ui.performance_frame.grid(column=1, row=0, padx=(5, 10), pady=(10, 4), sticky="NSEW")
    ui.performance_title = ttk.Label(ui.performance_frame, text="Performance", font=section_font)
    ui.performance_frame.configure(labelwidget=ui.performance_title)
    ui.performance_output = ttk.Frame(ui.performance_frame)
    ui.performance_output.grid(column=0, row=0, sticky="EW")
    ui.performance_output.columnconfigure(0, weight=1)
    ui.performance_frame.columnconfigure(0, weight=1)
    ttk.Label(ui.performance_output, text="No results available.", foreground="gray40").grid(column=0, row=0, sticky="W")

    # Altitude analysis section (inside performance frame, shown after run)
    ui.altitude_analysis_frame = ttk.Frame(ui.performance_frame)
    ui.altitude_analysis_frame.grid(column=0, row=1, pady=(3, 0), sticky="EW")
    ui.altitude_analysis_frame.columnconfigure(1, weight=1)

    title_row = ttk.Frame(ui.altitude_analysis_frame)
    title_row.grid(column=0, row=0, columnspan=2, sticky="EW", pady=(2, 3))
    title_row.columnconfigure(0, weight=1)
    title_row.columnconfigure(2, weight=1)
    ttk.Separator(title_row, orient="horizontal").grid(column=0, row=0, sticky="EW")
    ttk.Label(
        title_row,
        text="Altitude Performance",
        font=font.Font(family="Arial", size=9, weight="bold"),
    ).grid(column=1, row=0, padx=8)
    ttk.Separator(title_row, orient="horizontal").grid(column=2, row=0, sticky="EW")

    # Model selection row
    model_row = ttk.Frame(ui.altitude_analysis_frame)
    model_row.grid(column=0, row=1, columnspan=2, sticky="W", pady=(1, 3))
    ttk.Label(model_row, text="Model :", font=font.Font(family="Arial", size=9)).pack(side="left", padx=(0, 6))
    ui.altitude_model_var = tk.StringVar(value="angelino")
    ttk.Radiobutton(
        model_row, text="Angelino Modified", value="angelino", variable=ui.altitude_model_var
    ).pack(side="left", padx=(0, 6))
    ttk.Radiobutton(
        model_row, text="Calibrated", value="calibrated", variable=ui.altitude_model_var
    ).pack(side="left")

    entry_row = ttk.Frame(ui.altitude_analysis_frame)
    entry_row.grid(column=0, row=2, columnspan=2, sticky="EW", pady=1)
    entry_row.columnconfigure(1, weight=1)

    ui.analysis_type = ttk.Combobox(
        entry_row,
        values=["Altitude (km)", "Pressure (bar)"],
        width=13,
        state="readonly",
    )
    ui.analysis_type.set("Altitude (km)")
    ui.analysis_type.grid(column=0, row=0, sticky="W", padx=(0, 6))

    ui.input_analysis = ttk.Entry(entry_row)
    ui.input_analysis.grid(column=1, row=0, sticky="EW")
    ui.input_altitude = ui.input_analysis

    ui.info_button = tk.Label(entry_row, text="ⓘ", font=("Arial", 10), fg="#6b7280", cursor="hand2")
    ui.info_button.grid(column=2, row=0, padx=(6, 0))
    _create_tooltip(ui.info_button, "Enter one or multiple values separated by comma ','")

    action_row = ttk.Frame(ui.altitude_analysis_frame)
    action_row.grid(column=0, row=3, columnspan=2, sticky="EW", pady=(4, 1))
    action_row.columnconfigure(0, weight=1, uniform="analysis_btn")
    action_row.columnconfigure(1, weight=1, uniform="analysis_btn")

    ui.table_analysis_button = ttk.Button(
        action_row, text="Table", command=lambda: index.generate_altitude_performance_table(ui)
    )
    ui.table_analysis_button.grid(column=0, row=0, sticky="EW", padx=(0, 2))

    ui.graph_analysis_button = ttk.Button(
        action_row, text="Graph", command=lambda: index.generate_altitude_performance_graph(ui)
    )
    ui.graph_analysis_button.grid(column=1, row=0, sticky="EW", padx=(2, 0))

    ui.altitude_loading_circle = _create_loading_circle(action_row, bg_parent)
    ui.altitude_loading_circle.grid(column=2, row=0, padx=(6, 0))

    ui.generate_analysis_button = ui.table_analysis_button
    ui.input_analysis.bind("<Return>", lambda e: index.generate_altitude_performance_table(ui))

    ui.altitude_analysis_frame.grid_remove()

    # Performance comparison section (inside performance frame, shown after run)
    ui.performance_comparison_frame = ttk.Frame(ui.performance_frame)
    ui.performance_comparison_frame.grid(column=0, row=2, pady=(10, 0), sticky="EW")
    ui.performance_comparison_frame.columnconfigure(0, weight=1)
    ui.performance_comparison_frame.columnconfigure(1, weight=1)

    comp_title_row = ttk.Frame(ui.performance_comparison_frame)
    comp_title_row.grid(column=0, row=0, columnspan=2, sticky="EW", pady=(2, 3))
    comp_title_row.columnconfigure(0, weight=1)
    comp_title_row.columnconfigure(2, weight=1)
    ttk.Separator(comp_title_row, orient="horizontal").grid(column=0, row=0, sticky="EW")
    ttk.Label(
        comp_title_row,
        text="Performance Comparison",
        font=font.Font(family="Arial", size=9, weight="bold"),
    ).grid(column=1, row=0, padx=8)
    ttk.Separator(comp_title_row, orient="horizontal").grid(column=2, row=0, sticky="EW")

    ui.compare_angelino_var = tk.BooleanVar(value=False)
    ui.compare_angelino_check = ttk.Checkbutton(
        ui.performance_comparison_frame, text="Angelino Modified", variable=ui.compare_angelino_var
    )
    ui.compare_angelino_check.grid(column=0, row=1, sticky="W", pady=1)

    ui.compare_design_var = tk.BooleanVar(value=False)
    ui.compare_design_check = ttk.Checkbutton(
        ui.performance_comparison_frame, text="Design Calibrated", variable=ui.compare_design_var
    )
    ui.compare_design_check.grid(column=0, row=2, sticky="W", pady=1)

    ui.compare_bell_ideal_var = tk.BooleanVar(value=False)
    ui.compare_bell_ideal_check = ttk.Checkbutton(
        ui.performance_comparison_frame, text="Bell (Ideal Expansion)", variable=ui.compare_bell_ideal_var
    )
    ui.compare_bell_ideal_check.grid(column=1, row=1, sticky="W", pady=1)

    ui.compare_bell_eps_var = tk.BooleanVar(value=False)
    ui.compare_bell_eps_check = ttk.Checkbutton(
        ui.performance_comparison_frame, text="Bell (Constant \u03b5)", variable=ui.compare_bell_eps_var
    )
    ui.compare_bell_eps_check.grid(column=1, row=2, sticky="W", pady=1)

    comp_action_row = ttk.Frame(ui.performance_comparison_frame)
    comp_action_row.grid(column=0, row=3, columnspan=2, sticky="EW", pady=(4, 1))
    comp_action_row.columnconfigure(0, weight=1, uniform="comp_btn")
    comp_action_row.columnconfigure(1, weight=1, uniform="comp_btn")

    ui.table_comparison_button = ttk.Button(
        comp_action_row, text="Table", command=lambda: index.generate_performance_comparison_table(ui)
    )
    ui.table_comparison_button.grid(column=0, row=0, sticky="EW", padx=(0, 2))

    ui.graph_comparison_button = ttk.Button(
        comp_action_row, text="Graph", command=lambda: index.generate_performance_comparison_graph(ui)
    )
    ui.graph_comparison_button.grid(column=1, row=0, sticky="EW", padx=(2, 0))

    ui.comparison_loading_circle = _create_loading_circle(comp_action_row, bg_parent)
    ui.comparison_loading_circle.grid(column=2, row=0, padx=(6, 0))

    ui.performance_comparison_frame.grid_remove()

    ui.contour_button = ttk.Button(
        ui.results_tab, text='Save As', command=lambda: index.save_results_file(ui), state='disabled'
    )
    ui.contour_button.grid(row=1, column=1, sticky='SE', padx=(0, 10), pady=(0, 6))

    ui.results_tab.columnconfigure(0, weight=0, minsize=195)
    ui.results_tab.columnconfigure(1, weight=1)
    ui.results_tab.rowconfigure(0, weight=0, minsize=294)
    ui.results_tab.rowconfigure(1, weight=1)

    # CFD tab: thruster inputs
    ui.thruster_nozzle_var = tk.BooleanVar(value=False)
    ui.thruster_frame = ttk.LabelFrame(ui.cfd_tab)
    ui.thruster_frame.grid(column=0, row=0, padx=10, pady=(6, 4), sticky='EW')
    ui.thruster_nozzle_check = ttk.Checkbutton(
        ui.thruster_frame, text="Model Thruster", variable=ui.thruster_nozzle_var, command=ui.on_thruster_toggle, state='disabled'
    )
    ui.thruster_frame.configure(labelwidget=ui.thruster_nozzle_check)
    for column in (1, 3):
        ui.thruster_frame.columnconfigure(column, weight=1, uniform='thruster')
    ttk.Label(ui.thruster_frame, text='Contraction Ratio:').grid(column=0, row=0, padx=(10, 4), pady=(6, 8), sticky='W')
    ui.input_contraction_ratio = ttk.Entry(ui.thruster_frame, width=10, state='disabled')
    ui.input_contraction_ratio.grid(column=1, row=0, padx=(0, 10), pady=(6, 8), sticky='EW')
    ttk.Label(ui.thruster_frame, text='Convergent Nozzle Angle (deg):').grid(column=2, row=0, padx=(4, 4), pady=(6, 8), sticky='W')
    ui.input_convergent_nozzle_angle = ttk.Entry(ui.thruster_frame, width=10, state='disabled')
    ui.input_convergent_nozzle_angle.grid(column=3, row=0, padx=(0, 10), pady=(6, 8), sticky='EW')

    # CFD tab: mesh density inputs
    cfd_density_row = ttk.Frame(ui.cfd_tab)
    cfd_density_row.grid(column=0, row=1, padx=10, pady=(4, 6), sticky='EW')
    for column in (1, 3):
        cfd_density_row.columnconfigure(column, weight=1, uniform='density')
    ttk.Label(cfd_density_row, text='Grid Density Factor:').grid(column=0, row=0, padx=(0, 4), sticky='W')
    ui.input_grid_density = ttk.Entry(cfd_density_row, width=10)
    ui.input_grid_density.insert(0, "1")
    ui.input_grid_density.grid(column=1, row=0, sticky='EW')
    ttk.Label(cfd_density_row, text='Boundary Layer Density Factor:').grid(column=2, row=0, padx=(12, 4), sticky='W')
    ui.input_bl_mesh_density = ttk.Entry(cfd_density_row, width=10)
    ui.input_bl_mesh_density.insert(0, "1")
    ui.input_bl_mesh_density.grid(column=3, row=0, sticky='EW')

    # CFD export actions
    cfd_actions_frame = ttk.Frame(ui.cfd_tab)
    cfd_actions_frame.grid(column=0, row=2, padx=10, pady=(2, 8), sticky='EW')
    for column in range(3):
        cfd_actions_frame.columnconfigure(column, weight=1, uniform='cfd_btn')
    ui.mesh_button = ttk.Button(
        cfd_actions_frame, text='Export Mesh', command=lambda: index.save_mesh_file(ui), state='disabled'
    )
    ui.mesh_button.grid(column=0, row=0, padx=(0, 4), sticky='EW')
    ui.geo_button = ttk.Button(
        cfd_actions_frame, text='Export CFD Geometry', command=lambda: index.save_gmsh_geometry_file(ui), state='disabled'
    )
    ui.geo_button.grid(column=1, row=0, padx=2, sticky='EW')
    ui.cfd_case_definition_button = ttk.Button(
        cfd_actions_frame, text='Save CFD Case Definition', command=lambda: index.save_cfd_case_definition(ui), state='disabled'
    )
    ui.cfd_case_definition_button.grid(column=2, row=0, padx=(4, 0), sticky='EW')
    ui.mesh_loading_circle = _create_loading_circle(cfd_actions_frame, bg_parent)
    ui.mesh_loading_circle.grid(column=3, row=0, padx=(6, 0))

    # CFD mesh quality panel
    ui.mesh_quality_frame = ttk.LabelFrame(ui.cfd_tab, padding=(8, 4))
    ui.mesh_quality_frame.grid(column=0, row=3, padx=10, pady=(6, 8), sticky='NSEW')
    ui.mesh_quality_title = ttk.Label(ui.mesh_quality_frame, text="Mesh Quality", font=section_font)
    ui.mesh_quality_frame.configure(labelwidget=ui.mesh_quality_title)
    ui.mesh_quality_frame.columnconfigure(0, weight=1)
    ui.mesh_quality_frame.rowconfigure(0, weight=1)

    quality_viewport = ttk.Frame(ui.mesh_quality_frame)
    quality_viewport.grid(column=0, row=0, sticky='NSEW')
    quality_viewport.columnconfigure(0, weight=1)
    quality_viewport.rowconfigure(0, weight=1)

    ui.mesh_quality_canvas = tk.Canvas(quality_viewport, bg=bg_parent, bd=0, highlightthickness=0, width=1, height=1)
    ui.mesh_quality_canvas.grid(column=0, row=0, sticky='NSEW')
    ui.mesh_quality_scrollbar = ttk.Scrollbar(
        quality_viewport, orient='vertical', command=ui.mesh_quality_canvas.yview
    )
    ui.mesh_quality_scrollbar.grid(column=1, row=0, sticky='NS')
    ui.mesh_quality_canvas.configure(yscrollcommand=ui.mesh_quality_scrollbar.set)

    ui.mesh_quality_output = ttk.Frame(ui.mesh_quality_canvas)
    ui.mesh_quality_window = ui.mesh_quality_canvas.create_window((0, 0), window=ui.mesh_quality_output, anchor='nw')

    def _sync_mesh_quality_scroll(_event=None):
        content_h = ui.mesh_quality_output.winfo_reqheight()
        view_h = ui.mesh_quality_canvas.winfo_height()
        ui.mesh_quality_canvas.configure(scrollregion=(0, 0, ui.mesh_quality_canvas.winfo_width(), content_h))
        if view_h > 1 and content_h > view_h:
            ui.mesh_quality_scrollbar.grid()
        else:
            ui.mesh_quality_scrollbar.grid_remove()
            ui.mesh_quality_canvas.yview_moveto(0)

    def _on_quality_canvas_configure(event):
        ui.mesh_quality_canvas.itemconfigure(ui.mesh_quality_window, width=event.width)
        _sync_mesh_quality_scroll()

    def _on_quality_mousewheel(event):
        if ui.mesh_quality_output.winfo_reqheight() > ui.mesh_quality_canvas.winfo_height():
            ui.mesh_quality_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    ui.mesh_quality_canvas.bind("<Configure>", _on_quality_canvas_configure)
    ui.mesh_quality_output.bind("<Configure>", _sync_mesh_quality_scroll)
    quality_viewport.bind("<Enter>", lambda _e: ui.mesh_quality_canvas.bind_all("<MouseWheel>", _on_quality_mousewheel))
    quality_viewport.bind("<Leave>", lambda _e: ui.mesh_quality_canvas.unbind_all("<MouseWheel>"))
    quality_viewport.bind("<Destroy>", lambda _e: ui.mesh_quality_canvas.unbind_all("<MouseWheel>"))

    ui.mesh_quality_button = ttk.Button(
        ui.mesh_quality_frame, text='Check Mesh Quality', command=lambda: index.show_mesh_quality(ui), state='disabled'
    )
    ui.mesh_quality_button.grid(column=0, row=1, pady=(6, 0), sticky='EW')
    reset_mesh_quality_frame(ui)

    ui.cfd_buttons = (ui.mesh_button, ui.cfd_case_definition_button, ui.geo_button, ui.mesh_quality_button)
    ui.cfd_tab.columnconfigure(0, weight=1)
    ui.cfd_tab.rowconfigure(3, weight=1)

    ui.on_thruster_toggle()
    ui.on_sizing_toggle()
    ui.on_nozzle_choice_change()


def build_results_frame(ui):
    label_font = font.Font(family="Arial", size=9)
    value_font = font.Font(family="Arial", size=9, weight="bold")
    header_font = font.Font(family="Arial", size=11, weight="bold")

    for widget in ui.main_output.winfo_children():
        widget.destroy()

    results = ui.case["results"]
    aerospike_type = results.get("aerospike_type")
    type_label = {"toroidal": "Toroidal Aerospike", "linear": "Linear Aerospike"}.get(aerospike_type, "Aerospike")
    ttk.Label(ui.main_output, text=type_label, font=header_font).grid(
        column=0, row=0, columnspan=2, sticky='W', pady=(0, 10)
    )

    if aerospike_type == "linear":
        fields = [("mfr", "Mass Flow Rate", "kg/s"), ("length", "Length", "m"), ("width", "Width", "m")]
    elif aerospike_type == "toroidal":
        fields = [("mfr", "Mass Flow Rate", "kg/s"), ("radius", "Cowl Radius", "m")]
    else:
        fields = []

    row = 1
    ttk.Separator(ui.main_output, orient='horizontal').grid(column=0, row=row, columnspan=2, sticky='EW', pady=(0, 8))
    row += 1
    if not fields:
        ttk.Label(ui.main_output, text="No sizing results available.", font=label_font, foreground="gray40").grid(
            column=0, row=row, columnspan=2, sticky='W'
        )
        row += 1
    else:
        for key, label, unit in fields:
            value = results.get(key)
            display_value = "—" if value is None else f"{value:.2g} {unit}"
            ttk.Label(ui.main_output, text=f"{label}:", font=label_font).grid(
                column=0, row=row, sticky='W', padx=(0, 12), pady=3
            )
            ttk.Label(ui.main_output, text=display_value, font=value_font).grid(
                column=1, row=row, sticky='E', padx=(0, 8), pady=3
            )
            row += 1

    x_values = [value for value in results.get("x", []) if value is not None]
    if x_values:
        ttk.Separator(ui.main_output, orient='horizontal').grid(column=0, row=row, columnspan=2, sticky='EW', pady=(8, 8))
        row += 1
        throat_length = results.get("throat_length")
        throat_display = "—" if throat_length is None else f"{throat_length * 1e3:.2f} mm"
        ttk.Label(ui.main_output, text="Throat length:", font=label_font).grid(
            column=0, row=row, sticky='W', padx=(0, 12), pady=2
        )
        ttk.Label(ui.main_output, text=throat_display, font=value_font).grid(
            column=1, row=row, sticky='E', padx=(0, 8), pady=2
        )
        row += 1
        ttk.Label(ui.main_output, text="Axial length:", font=label_font).grid(
            column=0, row=row, sticky='W', padx=(0, 12), pady=2
        )
        ttk.Label(ui.main_output, text=f"{max(x_values) - min(x_values):.4g} m", font=value_font).grid(
            column=1, row=row, sticky='E', padx=(0, 8), pady=2
        )
        row += 1

    ui.fit_results_frame()
    ui.notebook.select(ui.results_tab)


def build_performance_frame(ui):
    for widget in ui.performance_output.winfo_children():
        widget.destroy()

    results = ui.case.get("results", {})
    definition = ui.case.get("definition", {})
    if not results.get("x"):
        ui.altitude_analysis_frame.grid_remove()
        ui.performance_comparison_frame.grid_remove()
        ttk.Label(ui.performance_output, text="No results available.", foreground="gray40").grid(column=0, row=0, sticky="W")
        return

    ui.altitude_analysis_frame.grid()
    ui.performance_comparison_frame.grid()

    inputs = {**definition, "Pc": core_input.pressure_conversion(definition.get("Pc"), definition.get("unit_Pc"))}
    p_design = results.get("ideal_expansion_pressure")
    if p_design is None:
        p_design = cea.ideal_expansion_pressure(inputs)

    h_design = core_input.pressure_to_altitude(p_design) if p_design is not None else 0.0
    p_bar = p_design / 1e5 if p_design is not None else 0.0

    bg_parent = ttk.Style().lookup("TFrame", "background") or "SystemButtonFace"
    label_style = dict(bg=bg_parent, fg="#111827", bd=0, padx=0, pady=0, highlightthickness=0)

    row_frame = tk.Frame(ui.performance_output, bg=bg_parent)
    row_frame.grid(column=0, row=0, sticky="W", padx=(0, 4), pady=(1, 2))

    tk.Label(row_frame, text="Ideal Expansion : ", font=("Arial", 9), **label_style).pack(side="left")
    tk.Label(row_frame, text=f"H={h_design / 1e3:.2f} km, ", font=("Arial", 9, "bold"), **label_style).pack(side="left")
    tk.Label(row_frame, text="P", font=("Arial", 9, "bold"), **label_style).pack(side="left")
    tk.Label(row_frame, text="atm", font=("Arial", 6, "bold"), **label_style).pack(side="left", pady=(3, 0))
    tk.Label(row_frame, text=f"={p_bar:.3f} bar", font=("Arial", 9, "bold"), **label_style).pack(side="left")


def _build_sizing_row(ui, parent, row_idx, label_text, key, units):
    var = getattr(ui, f"{key}_var")
    chk = ttk.Checkbutton(parent, text=label_text, variable=var, command=lambda: ui.on_sizing_field_toggle(key))
    chk.grid(column=0, row=row_idx, padx=(20, 4), pady=2, sticky='W')
    entry = ttk.Entry(parent, width=10, state='disabled')
    entry.grid(column=1, row=row_idx, padx=4, pady=2, sticky='W')
    unit_box = ttk.Combobox(parent, values=units, width=5, state='disabled')
    unit_box.set(units[0])
    unit_box.grid(column=2, row=row_idx, padx=2, pady=2, sticky='W')
    setattr(ui, f"{key}_chk", chk)
    setattr(ui, f"{key}_entry", entry)
    setattr(ui, f"{key}_unit", unit_box)


def reset_mesh_quality_frame(ui, message="No mesh generated yet."):
    for widget in ui.mesh_quality_output.winfo_children():
        widget.destroy()
    ui.mesh_quality_output.columnconfigure(0, weight=1)
    for col in range(1, 4):
        ui.mesh_quality_output.columnconfigure(col, weight=0)
    ttk.Label(ui.mesh_quality_output, text=message, foreground="gray40", font=("Arial", 10)).grid(
        column=0, row=0, sticky="W", pady=4
    )
    ui.mesh_quality_canvas.yview_moveto(0)


def build_mesh_quality_frame(ui):
    for widget in ui.mesh_quality_output.winfo_children():
        widget.destroy()

    quality = (ui.case.get("cfd") or {}).get("mesh_quality") or {}
    metrics = quality.get("metrics") or []
    if not metrics:
        reset_mesh_quality_frame(ui)
        return

    hdr_font = font.Font(family="Arial", size=10, weight="bold")
    row_font = font.Font(family="Arial", size=10)
    for col, weight in enumerate((4, 2, 3, 1)):
        ui.mesh_quality_output.columnconfigure(col, weight=weight)

    summary = f"Nodes: {quality.get('nodes', 0):,}    Elements: {quality.get('elements', 0):,}"
    ttk.Label(ui.mesh_quality_output, text=summary, font=row_font).grid(
        column=0, row=0, columnspan=4, sticky="W", padx=2, pady=(0, 4)
    )
    for col, text in enumerate(("Metric", "Type", "Worst / Mean", "Unit")):
        ttk.Label(ui.mesh_quality_output, text=text, font=hdr_font).grid(
            column=col, row=1, sticky="W" if col < 2 else "E", padx=2, pady=(0, 2)
        )
    ttk.Separator(ui.mesh_quality_output, orient="horizontal").grid(
        column=0, row=2, columnspan=4, sticky="EW", pady=2
    )

    for row_idx, item in enumerate(metrics, start=3):
        ttk.Label(ui.mesh_quality_output, text=item["name"], font=row_font).grid(
            column=0, row=row_idx, sticky="W", padx=2, pady=2
        )
        ttk.Label(ui.mesh_quality_output, text=item["element_type"], font=row_font).grid(
            column=1, row=row_idx, sticky="W", padx=2, pady=2
        )
        ttk.Label(ui.mesh_quality_output, text=item["value_str"], font=row_font).grid(
            column=2, row=row_idx, sticky="E", padx=2, pady=2
        )
        ttk.Label(ui.mesh_quality_output, text=item["unit"], font=row_font).grid(
            column=3, row=row_idx, sticky="E", padx=2, pady=2
        )
    ui.mesh_quality_canvas.yview_moveto(0)
