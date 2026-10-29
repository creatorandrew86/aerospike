import math
from core import cea

# Helper functions
def _prandtl_meyer_angle(mach: float, gamma: float) -> float:

    mach = max(mach, 1)
    pm_angle = math.sqrt((gamma + 1)/(gamma - 1)) * math.atan(math.sqrt((gamma - 1)/(gamma + 1) * (mach**2 - 1))) - math.atan(math.sqrt(mach**2 - 1))
    return pm_angle

def _mach_angle(mach: float) -> float:

    mach = max(mach, 1)
    return math.asin(1 / mach)



def generate_aerospike_contour(inputs: dict) -> tuple[dict, dict, list[str]]:
    errors = []

    truncate_percent     = inputs["truncate_percent"] / 100
    N                    = inputs["aerospike_resolution"]

    sizing         = inputs["sizing"]
    aerospike_type = inputs["aerospike_type"]
    mfr            = inputs["mfr"]
    radius         = inputs["radius"]
    width          = inputs["width"]
    length         = inputs["length"]


    results = {
        "aerospike_type": aerospike_type,
        "mfr": None,
        "radius": None,
        "length": None,
        "width": None,
        "throat_length": None,
        "ideal_expansion_pressure": None,
        "x": [None] * N,
        "R_x": [None] * N,
        "eps_x": [None] * N,
    }

    
    # Aerospike Throat Mach
    try:
        entry_mach = cea.entry_conditions(inputs)
    except Exception as e:
        errors.append(f"CFD inlet conditions calculation failed with {e}")
        return {}, {}, errors
    

    # Aerospike Exit Conditions
    try:
        exit_mach, exit_gamma = cea.exit_conditions(inputs)
        exit_pm_angle = _prandtl_meyer_angle(exit_mach, exit_gamma)
    except Exception as e:
        errors.append(f"Exit conditions calculation failed with {e} ")
        return {}, {}, errors


    # Results updating
    try:
        results["ideal_expansion_pressure"] = cea.ideal_expansion_pressure(inputs)
        cfd_setup = cea.cfd_setup(inputs)
    except Exception as e:
        errors.append(f"CEA Results calculation failed with {e} ")
        return {}, {}, errors

    


    # Loop - generates contour assuming throat_length = 1
    for i in range(N):
        mach = entry_mach + (i / N) * (exit_mach - entry_mach)

        # Station Values
        try:
            # Angles
            eps = cea.eps_from_mach(inputs, mach)
            gamma = cea.gamma_from_eps(inputs, eps)
            mach_angle = _mach_angle(mach)

            pm_angle   = _prandtl_meyer_angle(mach, gamma)
            flow_angle = mach_angle + (exit_pm_angle - pm_angle)

            # Length and coordinates
            characteristic_length = mach * eps

            x = characteristic_length * -math.cos(flow_angle)
            R = characteristic_length * math.sin(flow_angle)

        except Exception as e:
            errors.append(f"Station {i+1} calculation failed with {e}")
            return {}, {}, errors


        results["x"][i]     = x
        results["R_x"][i]   = R
        results["eps_x"][i] = eps


    throat_length = 1.0

    # Non-dimensionalization of coordinates
    if not sizing:
        max_length = max(max(abs(v) for v in results["x"]), max(abs(v) for v in results["R_x"]))
        
        results["x"]   = [v / max_length for v in results["x"]]
        results["R_x"] = [v / max_length for v in results["R_x"]]
        throat_length /= max_length


    # Sizing
    if sizing:
        if aerospike_type == "toroidal":
            if mfr is None:
                # Radius + eps -> throat area -> mass flow
                throat_length = radius / (2 * max(abs(v) for v in results["R_x"]))

                results["x"]   = [2 * v * throat_length for v in results["x"]]
                results["R_x"] = [2 * v * throat_length for v in results["R_x"]]

                try:
                    mfr = _get_mass_flow_toroidal(radius, inputs)
                except Exception as e:
                    errors.append(f"Mass flow calculation failed with {e}")
                    return {}, {}, errors
                

            if radius is None:
                # Mass flow -> throat area + area ratio -> exit area -> radius
                try:
                    radius = _get_radius_toroidal(mfr, inputs)
                except Exception as e:
                    errors.append(f"Cowl radius calculation failed with {e}")
                    return {}, {}, errors

                throat_length = radius / (2 * max(abs(v) for v in results["R_x"]))

                results["x"]   = [2 * v * throat_length for v in results["x"]]
                results["R_x"] = [2 * v * throat_length for v in results["R_x"]]

            results["mfr"]    = mfr
            results["radius"] = radius

        
        if aerospike_type == "linear":
            if mfr is None:
                # Width (radius equivalent) + area ratio -> throat area -> mass flow
                throat_length = width / max(abs(v) for v in results["R_x"])

                results["x"]   = [v * throat_length for v in results["x"]]
                results["R_x"] = [v * throat_length for v in results["R_x"]]

                try:
                    mfr = _get_mass_flow_linear(length, width, inputs)
                except Exception as e:
                    errors.append(f"Mass flow calculation failed with {e}")
                    return {}, {}, errors
                

            if length is None:
                # Width + mfr -> throat area + area ratio -> exit area -> length
                throat_length = width / max(abs(v) for v in results["R_x"])

                results["x"]   = [v * throat_length for v in results["x"]]
                results["R_x"] = [v * throat_length for v in results["R_x"]]

                try:
                    length = _get_length_linear(mfr, width, inputs)
                except Exception as e:
                    errors.append(f"Aerospike length calculation failed with {e}")
                    return {}, {}, errors
                
            
            if width is None:
                # Mass flow + length -> throat area + area ratio -> exit area -> width
                try:
                    width = _get_width_linear(mfr, length, inputs)
                except Exception as e:
                    errors.append(f"Width calculation failed with {e}")
                    return {}, {}, errors

                throat_length = width / max(abs(v) for v in results["R_x"])

                results["x"]   = [v * throat_length for v in results["x"]]
                results["R_x"] = [v * throat_length for v in results["R_x"]]

            results["mfr"]    = mfr
            results["length"] = length
            results["width"]  = width

    results["throat_length"] = throat_length
    results["nozzle_size"] = max(results["R_x"])

    # Truncating
    results["x"] = results["x"][:int(len(results["x"]) * truncate_percent)]
    results["R_x"] = results["R_x"][:int(len(results["R_x"]) * truncate_percent)]
    results["eps_x"] = results["eps_x"][:int(len(results["eps_x"]) * truncate_percent)]

    return results, cfd_setup, errors




# Torroidal aerospike values
def _get_mass_flow_toroidal(radius: float, inputs: dict) -> float:
    effective_throat_velocity, effective_throat_rho = cea.effective_throat_conditions(inputs)
    throat_area = math.pi * pow(radius, 2) / (inputs["eps"] / inputs["effective_throat_eps"])
    mfr = throat_area * effective_throat_velocity * effective_throat_rho

    return mfr

def _get_radius_toroidal(mfr: float, inputs: dict) -> float:
    effective_throat_velocity, effective_throat_rho = cea.effective_throat_conditions(inputs)
    throat_area = mfr / (effective_throat_velocity * effective_throat_rho)
    exit_area = throat_area * (inputs["eps"] / inputs["effective_throat_eps"])
    radius = math.sqrt(exit_area / math.pi)

    return radius




# Linear aerospike values
def _get_mass_flow_linear(length: float, width: float, inputs: dict) -> float:
    effective_throat_velocity, effective_throat_rho = cea.effective_throat_conditions(inputs)
    throat_area = length * width / (inputs["eps"] / inputs["effective_throat_eps"])
    mfr = throat_area * effective_throat_velocity * effective_throat_rho

    return mfr

def _get_length_linear(mfr: float, width: float, inputs: dict) -> float:
    effective_throat_velocity, effective_throat_rho = cea.effective_throat_conditions(inputs)
    throat_area = mfr / (effective_throat_velocity * effective_throat_rho)
    exit_area = throat_area * (inputs["eps"] / inputs["effective_throat_eps"])
    length = exit_area / width

    return length

def _get_width_linear(mfr: float, length: float, inputs: dict) -> float:
    effective_throat_velocity, effective_throat_rho = cea.effective_throat_conditions(inputs)
    throat_area = mfr / (effective_throat_velocity * effective_throat_rho)
    exit_area = throat_area * (inputs["eps"] / inputs["effective_throat_eps"])
    width = exit_area / length

    return width
