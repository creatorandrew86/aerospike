import tkinter as tk
from tkinter import font, ttk

from core import cea, input as core_input
from core.output import output


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


def build_interface(ui):
    section_font = font.Font(family="Arial", size=10, weight="bold")
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

    ttk.Label(ui.aerospike_tab, text='Design Area Ratio:').grid(column=0, row=5, **pad_label)
    ui.input_eps = ttk.Entry(ui.aerospike_tab, width=18)
    ui.input_eps.grid(column=1, row=5, **pad_input)

    # Definition tab: nozzle inputs
    ttk.Label(ui.aerospike_tab, text='Nozzle Definition', font=section_font).grid(
        column=0, row=6, columnspan=2, padx=10, pady=(10, 5), sticky='W'
    )
    ttk.Label(ui.aerospike_tab, text='Effective Throat Area Ratio:').grid(column=0, row=7, **pad_label)
    ui.input_effective_throat_eps = ttk.Entry(ui.aerospike_tab, width=18)
    ui.input_effective_throat_eps.grid(column=1, row=7, **pad_input)

    ttk.Label(ui.aerospike_tab, text='Truncate at (%):').grid(column=0, row=8, **pad_label)
    ui.input_truncate_percentage = ttk.Entry(ui.aerospike_tab, width=18)
    ui.input_truncate_percentage.grid(column=1, row=8, **pad_input)

    ttk.Label(ui.aerospike_tab, text='Aerospike Resolution:').grid(column=0, row=9, **pad_label)
    ui.input_aerospike_resolution = ttk.Entry(ui.aerospike_tab, width=18)
    ui.input_aerospike_resolution.grid(column=1, row=9, **pad_input)

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
    run_area.grid(column=0, row=2, pady=(0, 10), sticky='EW')
    for column, weight in enumerate((1, 8, 1)):
        run_area.columnconfigure(column, weight=weight, uniform='run')
    ttk.Button(run_area, text='Run', command=ui.on_run).grid(column=1, row=0, sticky='EW')
    ui.progress_box = ttk.Frame(run_area, height=22)
    ui.progress_box.grid(column=1, row=1, columnspan=2, sticky='EW', pady=(4, 0))
    ui.progress_box.grid_propagate(False)
    ui.progress_box.columnconfigure(0, weight=1)

    ui.progress = ttk.Progressbar(ui.progress_box, maximum=100)
    ui.progress_label = ttk.Label(ui.progress_box, text='0%', width=4)
    ui.progress.grid(column=0, row=0, sticky='EW')
    ui.progress_label.grid(column=1, row=0, padx=(4, 0))
    ui.progress.grid_remove()
    ui.progress_label.grid_remove()

    # Results tab
    ui.results_frame = ttk.LabelFrame(ui.results_tab, padding=14)
    ui.results_frame.grid(column=0, row=0, padx=(10, 5), pady=10, sticky="NSEW")
    ui.results_title = ttk.Label(ui.results_frame, text="Geometry", font=section_font)
    ui.results_frame.configure(labelwidget=ui.results_title)
    ui.main_output = ttk.Frame(ui.results_frame)
    ui.main_output.grid(column=0, row=0, sticky="NSEW")
    ui.main_output.columnconfigure(0, weight=1)
    ui.results_frame.columnconfigure(0, weight=1)
    ui.results_frame.rowconfigure(0, weight=1)
    ttk.Label(ui.main_output, text="No results available.", foreground="gray40").grid(column=0, row=0, sticky="W")
    ui.graph_button = ttk.Button(ui.results_frame, text='Generate Graph', command=lambda: output.graph_output(ui), state='disabled')
    ui.graph_button.grid(column=0, row=1, pady=(6, 0), sticky='EW')

    ui.performance_frame = ttk.LabelFrame(ui.results_tab, padding=10)
    ui.performance_frame.grid(column=1, row=0, padx=(5, 10), pady=10, sticky="NSEW")
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

    ui.analysis_type = ttk.Combobox(
        ui.altitude_analysis_frame,
        values=["Altitude (km)", "Pressure (bar)"],
        width=13,
        state="readonly",
    )
    ui.analysis_type.set("Altitude (km)")
    ui.analysis_type.grid(column=0, row=1, sticky="W", padx=(0, 6), pady=1)

    ui.input_analysis = ttk.Entry(ui.altitude_analysis_frame)
    ui.input_analysis.grid(column=1, row=1, sticky="EW", pady=1)
    ui.input_altitude = ui.input_analysis

    action_row = ttk.Frame(ui.altitude_analysis_frame)
    action_row.grid(column=0, row=2, columnspan=2, sticky="EW", pady=(4, 1))
    action_row.columnconfigure(0, weight=1, uniform="analysis_btn")
    action_row.columnconfigure(1, weight=1, uniform="analysis_btn")
    action_row.columnconfigure(2, weight=0)

    ui.table_analysis_button = ttk.Button(
        action_row, text="Table", command=lambda: output.generate_altitude_performance_table(ui)
    )
    ui.table_analysis_button.grid(column=0, row=0, sticky="EW", padx=(0, 2))

    ui.graph_analysis_button = ttk.Button(
        action_row, text="Graph", command=lambda: output.generate_altitude_performance_graph(ui)
    )
    ui.graph_analysis_button.grid(column=1, row=0, sticky="EW", padx=(2, 0))

    ui.generate_analysis_button = ui.table_analysis_button
    ui.input_analysis.bind("<Return>", lambda e: output.generate_altitude_performance_table(ui))

    ui.info_button = tk.Label(action_row, text="ⓘ", font=("Arial", 10), fg="#6b7280", cursor="hand2")
    ui.info_button.grid(column=2, row=0, padx=(6, 0))
    _create_tooltip(ui.info_button, "Enter one or multiple values separated by comma ','")

    ui.altitude_analysis_frame.grid_remove()

    ui.save_frame = ttk.LabelFrame(ui.results_tab, padding=(5, 2, 7, 6))
    ui.save_frame.configure(labelwidget=ttk.Frame(ui.save_frame, width=0, height=0))
    ui.save_frame.place(relx=1.0, rely=1.0, x=2, y=2, anchor="se")
    ui.contour_button = ttk.Button(ui.save_frame, text='Save As', command=lambda: output.save_results_file(ui), state='disabled')
    ui.contour_button.grid(column=0, row=0)

    ui.results_tab.columnconfigure(0, weight=0, minsize=195)
    ui.results_tab.columnconfigure(1, weight=1)
    ui.results_tab.rowconfigure(0, weight=1)

    # CFD tab: thruster inputs
    ui.thruster_nozzle_var = tk.BooleanVar(value=False)
    ui.thruster_frame = ttk.LabelFrame(ui.cfd_tab)
    ui.thruster_frame.grid(column=0, row=0, columnspan=2, padx=10, pady=10, sticky='EW')
    ui.thruster_nozzle_check = ttk.Checkbutton(
        ui.thruster_frame, text="Model Thruster", variable=ui.thruster_nozzle_var, command=ui.on_thruster_toggle
    )
    ui.thruster_frame.configure(labelwidget=ui.thruster_nozzle_check)
    for column in range(2):
        ui.thruster_frame.columnconfigure(column, weight=1, uniform='thruster')
    ttk.Label(ui.thruster_frame, text='Contraction Ratio:').grid(column=0, row=0, padx=10, pady=(8, 2), sticky='W')
    ui.input_contraction_ratio = ttk.Entry(ui.thruster_frame, state='disabled')
    ui.input_contraction_ratio.grid(column=0, row=1, padx=(10, 5), pady=(0, 10), sticky='EW')
    ttk.Label(ui.thruster_frame, text='Convergent Nozzle Angle (deg):').grid(column=1, row=0, padx=10, pady=(8, 2), sticky='W')
    ui.input_convergent_nozzle_angle = ttk.Entry(ui.thruster_frame, state='disabled')
    ui.input_convergent_nozzle_angle.grid(column=1, row=1, padx=(5, 10), pady=(0, 10), sticky='EW')

    # CFD export actions
    ui.mesh_button = ttk.Button(ui.cfd_tab, text='Export Mesh', command=lambda: output.save_mesh_file(ui), state='disabled')
    ui.mesh_button.grid(column=0, row=1, padx=(10, 4), pady=3, sticky='EW')
    ui.cfd_case_definition_button = ttk.Button(
        ui.cfd_tab, text='Save CFD Case Definition', command=lambda: output.save_cfd_case_definition(ui), state='disabled'
    )
    ui.cfd_case_definition_button.grid(column=0, row=2, padx=(10, 4), pady=3, sticky='EW')
    ui.geo_button = ttk.Button(ui.cfd_tab, text='Export CFD Geometry', command=lambda: output.save_gmsh_geometry_file(ui), state='disabled')
    ui.geo_button.grid(column=1, row=1, padx=4, pady=3, sticky='EW')
    ui.cfd_buttons = (ui.mesh_button, ui.cfd_case_definition_button, ui.geo_button)
    for column in range(2):
        ui.cfd_tab.columnconfigure(column, weight=1)

    ui.on_thruster_toggle()
    ui.on_sizing_toggle()


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
        ttk.Label(ui.performance_output, text="No results available.", foreground="gray40").grid(column=0, row=0, sticky="W")
        return

    ui.altitude_analysis_frame.grid()

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
    tk.Label(row_frame, text=f"H={h_design:,.0f} m, ", font=("Arial", 9, "bold"), **label_style).pack(side="left")
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
