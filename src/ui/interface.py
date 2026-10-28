import tkinter as tk

from .layout import build_interface


class Interface:
    def __init__(self, root: tk, case: dict | None, on_solve: callable):
        self.root = root
        self.on_solve = on_solve
        self.case = case if case is not None else {
            "definition": {},
            "results": {},
            "cfd": {"inputs": {}, "setup": {}},
            "errors": [],
        }
        self.build_interface()


    @staticmethod
    def _parse_float(value):
        if not value:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_int(value):
        if not value:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def get_inputs_on_solve(self) -> dict:
        aerospike_type = None
        if self.sizing_var.get():
            if self.linear_var.get():
                aerospike_type = "linear"
            elif self.toroidal_var.get():
                aerospike_type = "toroidal"

        mass_flow_val = mass_flow_unit = radius_val = radius_unit = None
        width_val = width_unit = length_val = length_unit = None
        if aerospike_type == "linear":
            mass_flow_val, mass_flow_unit = self._get_field_value("linear_massflow")
            length_val, length_unit = self._get_field_value("linear_length")
            width_val, width_unit = self._get_field_value("linear_width")
        elif aerospike_type == "toroidal":
            if self.toroidal_choice.get() == "massflow" and self.toroidal_massflow_entry.get():
                mass_flow_val = self._parse_float(self.toroidal_massflow_entry.get())
                mass_flow_unit = self.toroidal_massflow_unit.get()
            elif self.toroidal_choice.get() == "radius" and self.toroidal_radius_entry.get():
                radius_val = self._parse_float(self.toroidal_radius_entry.get())
                radius_unit = self.toroidal_radius_unit.get()

        return {
            "oxidizer": self.input_oxidizer.get() or None,
            "fuel": self.input_fuel.get() or None,
            "Pc": self._parse_float(self.input_Pc.get()),
            "unit_Pc": self.unit_Pc.get() or None,
            "MR": self._parse_float(self.input_MR.get()),
            "eps": self._parse_float(self.input_eps.get()),
            "effective_throat_eps": self._parse_float(self.input_effective_throat_eps.get()),
            "truncate_percent": self._parse_float(self.input_truncate_percentage.get()),
            "aerospike_resolution": self._parse_int(self.input_aerospike_resolution.get()),
            "sizing": self.sizing_var.get(),
            "aerospike_type": aerospike_type,
            "mfr": mass_flow_val, "unit_mfr": mass_flow_unit,
            "radius": radius_val, "unit_radius": radius_unit,
            "width": width_val, "unit_width": width_unit,
            "length": length_val, "unit_length": length_unit,
        }


    def get_inputs_on_gmsh_geometry(self) -> dict:
        inputs = {
            "contraction_ratio": self._parse_float(self.input_contraction_ratio.get()),
            "convergent_nozzle_angle": self._parse_float(self.input_convergent_nozzle_angle.get()),
            "thruster_nozzle": self.thruster_nozzle_var.get(),
        }
        self.case["cfd"]["inputs"] = inputs
        return inputs


    def on_sizing_toggle(self):
        state = 'normal' if self.sizing_var.get() else 'disabled'
        self.linear_check.configure(state=state)
        self.toroidal_check.configure(state=state)
        for button in getattr(self, "cfd_buttons", ()):
            button.configure(state=state)
        if not self.sizing_var.get():
            self.linear_var.set(False)
            self.toroidal_var.set(False)
        self.on_linear_toggle()
        self.on_toroidal_toggle()


    def on_run(self):
        self.on_solve()
        state = 'normal' if self.case["results"].get("x") else 'disabled'
        self.contour_button.configure(state=state)
        self.graph_button.configure(state=state)


    def on_thruster_toggle(self):
        state = 'normal' if self.thruster_nozzle_var.get() else 'disabled'
        self.input_contraction_ratio.configure(state=state)
        self.input_convergent_nozzle_angle.configure(state=state)


    def on_linear_toggle(self):
        if self.linear_var.get() and self.sizing_var.get():
            self.toroidal_var.set(False)
            self._set_toroidal_fields_state('disabled')
            self.toroidal_choice.set("massflow")
        linear_on = self.linear_var.get() and self.sizing_var.get()
        state = 'normal' if linear_on else 'disabled'
        for key in ("linear_massflow", "linear_length", "linear_width"):
            getattr(self, f"{key}_chk").configure(state=state)
        self.on_sizing_field_toggle(None, group=("linear_massflow", "linear_length", "linear_width"), max_checked=2)
        self.toroidal_check.configure(state='disabled' if linear_on else ('normal' if self.sizing_var.get() else 'disabled'))


    def on_toroidal_toggle(self):
        if self.toroidal_var.get() and self.sizing_var.get():
            self.linear_var.set(False)
            self._set_linear_fields_state('disabled')
            self.linear_massflow_var.set(False)
            self.linear_length_var.set(False)
            self.linear_width_var.set(False)
        toroidal_on = self.toroidal_var.get() and self.sizing_var.get()
        state = 'normal' if toroidal_on else 'disabled'
        self.toroidal_massflow_radio.configure(state=state)
        self.toroidal_radius_radio.configure(state=state)
        self.on_toroidal_choice_change()
        self.linear_check.configure(state='disabled' if toroidal_on else ('normal' if self.sizing_var.get() else 'disabled'))


    def on_toroidal_choice_change(self):
        if not (self.toroidal_var.get() and self.sizing_var.get()):
            self.toroidal_massflow_entry.configure(state='disabled')
            self.toroidal_massflow_unit.configure(state='disabled')
            self.toroidal_radius_entry.configure(state='disabled')
            self.toroidal_radius_unit.configure(state='disabled')
            return
        if self.toroidal_choice.get() == "massflow":
            self.toroidal_massflow_entry.configure(state='normal')
            self.toroidal_massflow_unit.configure(state='readonly')
            self.toroidal_radius_entry.configure(state='disabled')
            self.toroidal_radius_unit.configure(state='disabled')
            self.toroidal_radius_entry.delete(0, tk.END)
        else:
            self.toroidal_radius_entry.configure(state='normal')
            self.toroidal_radius_unit.configure(state='readonly')
            self.toroidal_massflow_entry.configure(state='disabled')
            self.toroidal_massflow_unit.configure(state='disabled')
            self.toroidal_massflow_entry.delete(0, tk.END)


    def on_sizing_field_toggle(self, changed_key, group=None, max_checked=None):
        if group is None:
            if changed_key and changed_key.startswith("linear_"):
                group, max_checked = ("linear_massflow", "linear_length", "linear_width"), 2
            else:
                return
        vars_ = {key: getattr(self, f"{key}_var") for key in group}
        checked = [key for key in group if vars_[key].get()]
        if len(checked) > max_checked and changed_key is not None:
            for key in list(checked):
                if key != changed_key and len(checked) > max_checked:
                    vars_[key].set(False)
                    checked.remove(key)

        parent_on = self._group_parent_on(group)
        for key in group:
            entry, unit = getattr(self, f"{key}_entry"), getattr(self, f"{key}_unit")
            if parent_on and vars_[key].get():
                entry.configure(state='normal')
                unit.configure(state='readonly')
            else:
                entry.configure(state='disabled')
                unit.configure(state='disabled')
                entry.delete(0, tk.END)

        if parent_on:
            n_checked = sum(var.get() for var in vars_.values())
            for key in group:
                getattr(self, f"{key}_chk").configure(
                    state='normal' if vars_[key].get() or n_checked < max_checked else 'disabled'
                )


    def _group_parent_on(self, group):
        return self.linear_var.get() and self.sizing_var.get() if group[0].startswith("linear_") else self.toroidal_var.get() and self.sizing_var.get()


    def _set_linear_fields_state(self, state):
        for key in ("linear_massflow", "linear_length", "linear_width"):
            getattr(self, f"{key}_chk").configure(state=state)
            getattr(self, f"{key}_entry").configure(state='disabled')
            getattr(self, f"{key}_unit").configure(state='disabled')


    def _set_toroidal_fields_state(self, state):
        self.toroidal_massflow_radio.configure(state=state)
        self.toroidal_radius_radio.configure(state=state)
        self.toroidal_massflow_entry.configure(state='disabled')
        self.toroidal_massflow_unit.configure(state='disabled')
        self.toroidal_radius_entry.configure(state='disabled')
        self.toroidal_radius_unit.configure(state='disabled')


    def _get_field_value(self, key):
        entry, var, unit = getattr(self, f"{key}_entry"), getattr(self, f"{key}_var"), getattr(self, f"{key}_unit")
        return (self._parse_float(entry.get()), unit.get()) if var.get() and entry.get() else (None, None)


    def fit_results_frame(self):
        self.results_frame.grid_propagate(True)


    def build_interface(self):
        build_interface(self)
