from pathlib import Path


_SIZING_FIELDS = {
    "toroidal": (("Mass Flow Rate", "mfr", "unit_mfr"), ("Cowl Radius", "radius", "unit_radius")),
    "linear": (("Mass Flow Rate", "mfr", "unit_mfr"), ("Length", "length", "unit_length"), ("Width", "width", "unit_width")),
}


def _format_value(value, unit=""):
    if value is None:
        return "Not specified"
    return f"{value:.3f}{f' {unit}' if unit else ''}" if isinstance(value, (float, int)) else str(value)


def _line(label, value):
    return f"{label:<28}: {value}"


def _definition_section(definition, aerospike_type, sizing_type):
    lines = [
        "DEFINITION",
        "-" * 72,
        _line("Oxidizer", _format_value(definition.get("oxidizer"))),
        _line("Fuel", _format_value(definition.get("fuel"))),
        _line("Chamber Pressure", _format_value(definition.get("Pc"), definition.get("unit_Pc", ""))),
        _line("Mixture Ratio", _format_value(definition.get("MR"))),
        _line("Design Area Ratio", _format_value(definition.get("eps"))),
        _line("Effective Throat Area Ratio", _format_value(definition.get("effective_throat_eps"))),
        _line("Truncation", _format_value(definition.get("truncate_percent"), "%")),
        _line("Aerospike Resolution", _format_value(definition.get("aerospike_resolution"))),
        _line("Sizing", "Enabled" if definition.get("sizing", False) else "Disabled"),
        _line("Sizing Type", sizing_type),
    ]
    for label, key, unit_key in _SIZING_FIELDS.get(aerospike_type, ()):
        lines.append(_line(label, _format_value(definition.get(key), definition.get(unit_key, ""))))
    return lines


def _results_section(results, coordinate_unit, coordinate_scale):
    lines = [
        "RESULTS",
        "-" * 72,
        _line("Throat Length", _format_value(
            None if results.get("throat_length") is None else results["throat_length"] * coordinate_scale,
            coordinate_unit,
        )),
        _line("Ideal Expansion Pressure", _format_value(
            None if results.get("ideal_expansion_pressure") is None else results["ideal_expansion_pressure"] / 1e5,
            "bar",
        )),
    ]
    x_values = results.get("x", [])
    if x_values:
        lines.append(_line("Axial Length", _format_value((max(x_values) - min(x_values)) * coordinate_scale, coordinate_unit)))
    return lines


def format_results_report(case):
    definition = case["definition"]
    results = case["results"]
    aerospike_type = results.get("aerospike_type")
    sizing_type = aerospike_type.title() if aerospike_type else "None"
    is_sized = definition.get("sizing", False)
    coordinate_unit = "cm" if is_sized else "normalized"
    coordinate_scale = 100 if is_sized else 1

    lines = [
        "AEROSPIKE DESIGN REPORT",
        "=" * 72,
        "",
        *_definition_section(definition, aerospike_type, sizing_type),
        "",
        *_results_section(results, coordinate_unit, coordinate_scale),
        "",
        "=" * 72,
        "CONTOUR POINTS",
        "=" * 72,
        f"{'No.':>5}  {'x (' + coordinate_unit + ')':>20}  {'R (' + coordinate_unit + ')':>20}  {'Area Ratio':>14}",
        "-" * 72,
    ]
    for index, (x, radius, area_ratio) in enumerate(zip(results.get("x", []), results.get("R_x", []), results.get("eps_x", [])), start=1):
        lines.append(f"{index:>5}  {x * coordinate_scale:>20.3f}  {radius * coordinate_scale:>20.3f}  {area_ratio:>14.3f}")
    return "\n".join(lines) + "\n"


def write_results(case, path):
    Path(path).write_text(format_results_report(case), encoding="utf-8")
