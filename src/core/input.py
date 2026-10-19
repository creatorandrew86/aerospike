# Unit Conversion
def pressure_conversion(value: float, unit: str) -> float:
    match unit:
        case "Pa" :  return value
        case "kPa" : return value * 1e3
        case "MPa" : return value * 1e6
        case "bar" : return value * 1e5
        case "atm" : return value * 101325
        case "psi" : return value * 6894.76

def length_conversion(value: float, unit: str) -> float:
    match unit:
        case "m":   return value
        case "cm":  return value / 100
        case "mm":  return value / 1000
        case "in":  return value * 0.0254
        case "ft":  return value / 3.28

def mass_flow_conversion(value, unit):
    match unit:
        case "kg/s":   return value
        case "lb/s":   return value * 0.453592



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
        errors.append("Aerospike effective throat area ratio must be selected and greater than 1.")

        if inputs["eps"] is None or inputs["eps"] <= inputs["effective_throat_eps"]:
            errors.append("Area Ratio must be selected and greater than the effective throat area ratio.")
    

    if inputs["truncate_percent"] is None or inputs["truncate_percent"] < 40 or inputs["truncate_percent"] > 100:
        errors.append(f"The truncating percentage must be selected and in between 40% and 100%")

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
