import math


# Unit Conversion
def pressure_conversion(value: float, unit: str) -> float:
    if value is None:
        return None
    match unit:
        case "Pa" :  return value
        case "kPa" : return value * 1e3
        case "MPa" : return value * 1e6
        case "bar" : return value * 1e5
        case "atm" : return value * 101325
        case "psi" : return value * 6894.76
        case _:      return value

def length_conversion(value: float, unit: str) -> float:
    if value is None:
        return None
    match unit:
        case "m":   return value
        case "cm":  return value / 100
        case "mm":  return value / 1000
        case "in":  return value * 0.0254
        case "ft":  return value / 3.28
        case _:     return value

def mass_flow_conversion(value, unit):
    if value is None:
        return None
    match unit:
        case "kg/s":   return value
        case "lb/s":   return value * 0.453592
        case _:        return value


def altitude_to_pressure(altitude: float) -> float:
    """Converts altitude (m) to ambient pressure (Pa) using the standard atmosphere model."""
    if altitude is None:
        return None
    if altitude <= 0:
        return 101325.0
    if altitude >= 80000.0:
        return 0.0
    if altitude <= 11000.0:
        return 101325.0 * (1.0 - 0.0065 * altitude / 288.15) ** 5.2559
    if altitude <= 20000.0:
        return 22632.1 * math.exp(-0.000157688 * (altitude - 11000.0))
    return 101325.0 * math.exp(-altitude / 7200.0)


def pressure_to_altitude(pressure: float) -> float:
    """Converts ambient pressure (Pa) to geometric altitude (m) using the standard atmosphere model."""
    if pressure is None or pressure <= 0:
        return 80000.0
    if pressure >= 101325.0:
        return 0.0
    if pressure >= 22632.1:
        return 44330.8 * (1.0 - (pressure / 101325.0) ** 0.190263)
    if pressure >= 5474.9:
        return 11000.0 - math.log(pressure / 22632.1) / 0.000157688
    return -7200.0 * math.log(pressure / 101325.0)


def parse_analysis_inputs(raw: str) -> list[float]:
    """Parses comma-separated floats and start:step:stop or start:stop range syntax."""
    if not raw or not raw.strip():
        return []
    values = []
    for token in raw.replace(";", ",").split(","):
        token = token.strip()
        if not token:
            continue
        if ":" in token:
            try:
                parts = [float(p.strip()) for p in token.split(":")]
                if len(parts) == 3:
                    start, step, stop = parts
                    if step != 0 and (stop - start) / step >= 0:
                        curr = start
                        while (curr <= stop + 1e-9) if step > 0 else (curr >= stop - 1e-9):
                            values.append(round(curr, 6))
                            curr += step
                elif len(parts) == 2:
                    start, stop = parts
                    step = (stop - start) / 5.0
                    for i in range(6):
                        values.append(round(start + i * step, 6))
            except ValueError:
                continue
        else:
            try:
                values.append(float(token))
            except ValueError:
                continue
    seen = set()
    return [x for x in values if not (x in seen or seen.add(x))]



# Process inputs
def process_inputs_on_solve(inputs: dict) -> list[str]:
    errors = []

    # Engine Definition
    if inputs["oxidizer"] is None:
        errors.append("Oxidizer must be selected.")

    if inputs["fuel"] is None:
        errors.append("Fuel must be selected.")


    if inputs["MR"] is None or inputs["MR"] <= 0:
        errors.append("Mixture Ratio must be selected and greater than 0.")

    if inputs["Pc"] is None or inputs["Pc"] <= 0:
        errors.append("Chamber Pressure must be selected and greater than 0.")
    else:
        inputs["Pc"] = pressure_conversion(inputs["Pc"], inputs["unit_Pc"])


    # Aerospike Definition
    if inputs["effective_throat_eps"] is None or inputs["effective_throat_eps"] < 1:
        errors.append("Aerospike effective throat area ratio must be selected and greater than or equal to 1.")

    if inputs["eps"] is None or inputs["eps"] <= 1:
        errors.append("Area Ratio must be selected and greater than 1.")
    elif inputs["effective_throat_eps"] is not None and inputs["eps"] <= inputs["effective_throat_eps"]:
        errors.append("Area Ratio must be greater than the effective throat area ratio.")
    

    if inputs["truncate_percent"] is None or inputs["truncate_percent"] < 20 or inputs["truncate_percent"] > 100:
        errors.append(f"The truncating percentage must be selected and in between 20% and 100%")

    if inputs["aerospike_resolution"] is None or inputs["aerospike_resolution"] < 10 or inputs["aerospike_resolution"] > 10000:
        errors.append("The aerospike resolution must be selected and in between 10 and 10000 points.")


    # Sizing
    if inputs["sizing"] and inputs["aerospike_type"] is None:
        errors.append("You must select aerospike type.")

    # Linear type check
    if inputs["aerospike_type"] == "linear":
        if sum(v is not None and v > 0 for v in [inputs["mfr"], inputs["width"], inputs["length"]]) != 2:
            errors.append("2 of 3 sizing inputs must be selected and greater than 0 for linear aerospike.")

        inputs["mfr"]    = mass_flow_conversion(inputs["mfr"], inputs["unit_mfr"])
        inputs["width"]  = length_conversion(inputs["width"], inputs["unit_width"])
        inputs["length"] = length_conversion(inputs["length"], inputs["unit_length"])

    # Torroidal type check
    if inputs["aerospike_type"] == "toroidal":
        if ((inputs["mfr"] is None or inputs["mfr"] <= 0) and (inputs["radius"] is None or inputs["radius"] <= 0)):
            errors.append("A sizing input must be selected and greater than 0 for torroidal aerospike.")

        inputs["mfr"]    = mass_flow_conversion(inputs["mfr"], inputs["unit_mfr"])
        inputs["radius"] = length_conversion(inputs["radius"], inputs["unit_radius"])

    return errors


def process_inputs_on_gmsh_geometry(inputs: dict) -> list[str]:
    errors = []

    if inputs["thruster_nozzle"]:
        if inputs["contraction_ratio"] is None or inputs["contraction_ratio"] <= 1:
            errors.append("Contraction Ratio must be selected and greater than 1.")

        if (inputs["convergent_nozzle_angle"] is None
                or inputs["convergent_nozzle_angle"] <= 25
                or inputs["convergent_nozzle_angle"] >= 65):
            errors.append("Convergent Nozzle Angle must be selected and between 25 and 65 degrees.")

    return errors
