from collections.abc import Callable
import math
from scipy.integrate import quad
from core import cea

# Helper functions
def _prandtl_meyer_angle(mach: float, gamma_from_mach: Callable[[float], float]) -> float:
    if mach <= 1.0:
        return 0.0

    def integrand(m: float) -> float:
        gamma = gamma_from_mach(m)
        return math.sqrt(max(0.0, m**2 - 1.0)) / (m * (1.0 + (gamma - 1.0) / 2.0 * m**2))

    angle, _ = quad(integrand, 1.0, mach)
    return float(angle)

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

    
    # Aerospike Throat Conditions
    try:
        gamma_from_mach = cea.gamma_from_mach(inputs)
        entry_mach = cea.entry_conditions(inputs)
        entry_pm_angle = _prandtl_meyer_angle(entry_mach, gamma_from_mach)
    except Exception as e:
        errors.append(f"CFD inlet conditions calculation failed with {e}")
        return {}, {}, errors
    

    # Aerospike Exit Conditions
    try:
        gamma_from_mach = cea.gamma_from_mach(inputs)
        exit_mach = cea.exit_mach(inputs)
        exit_pm_angle = _prandtl_meyer_angle(exit_mach, gamma_from_mach)
    except Exception as e:
        errors.append(f"Exit conditions calculation failed with {e} ")
        return {}, {}, errors


    # Results updating - expansion pressure and cfd setup
    try:
        results["ideal_expansion_pressure"] = cea.ideal_expansion_pressure(inputs)
        cfd_setup = cea.cfd_setup(inputs)
    except Exception as e:
        errors.append(f"CEA Results calculation failed with {e} ")
        return {}, {}, errors



    # Sizing the nozzle throat
    if sizing:
        expansion_angle = exit_pm_angle - entry_pm_angle

        if aerospike_type == "toroidal":
            try:
                mfr, radius, throat_area, throat_length = sizing_toroidal(inputs, expansion_angle, mfr, radius)
            except Exception as e:
                errors.append(f"Toroidal sizing calculation failed with {e}")
                return {}, {}, errors

        if aerospike_type == "linear":
            try:
                mfr, width, length, throat_area, throat_length = sizing_linear(inputs, mfr, width, length)
            except Exception as e:
                errors.append(f"Linear sizing calculation failed with {e}")
                return {}, {}, errors

    elif not sizing:
        # Default throat length and radius values
        throat_length, radius = 1.0, 1.0 

    


    # Mach number marching from entry to exit
    for i in range(N):
        mach = entry_mach + (i / (N-1)) * (exit_mach - entry_mach)

        try:
            flow_angle = exit_pm_angle - _prandtl_meyer_angle(mach, gamma_from_mach)
            mach_angle = _mach_angle(mach)

            # Characteristic line angle relative to the cowl-point radius
            beta = (math.pi / 2) - mach_angle - flow_angle

            # CEA area ratio
            eps = cea.eps_from_mach(inputs, mach)

            # Characteristic line length
            if aerospike_type == "toroidal":
                C = (mach * eps) / inputs["eps"]
                characteristic_length = radius * C / (1.0 + math.sqrt(max(0.0, 1.0 - C * math.cos(beta))))
            else:
                characteristic_length = throat_length * mach * eps

            # Coordinates
            x = -characteristic_length * math.sin(beta)
            R = characteristic_length * math.cos(beta)

        except Exception as e:
            errors.append(f"Station {i+1} calculation failed with {e}")
            return {}, {}, errors


        results["x"][i]     = x
        results["R_x"][i]   = R
        results["eps_x"][i] = eps


    # Non-dimensionalization of coordinates
    if not sizing:
        spike_length = max(results["x"]) - min(results["x"])
        results["x"]   = [v / spike_length for v in results["x"]]
        results["R_x"] = [v / spike_length for v in results["R_x"]]
        throat_length /= spike_length
    else:
        results["mfr"] = mfr
        if aerospike_type == "toroidal":
            results["radius"] = radius
        elif aerospike_type == "linear":
            results["width"] = width
            results["length"] = length

    results["throat_length"] = throat_length
    results["nozzle_size"] = max(results["R_x"])

    # Truncating
    if truncate_percent < 1.0:
        cutoff = results["x"][0] - (results["x"][0] - results["x"][-1]) * truncate_percent
        keep = sum(x >= cutoff for x in results["x"])
        results["x"] = results["x"][:keep]
        results["R_x"] = results["R_x"][:keep]
        results["eps_x"] = results["eps_x"][:keep]

    return results, cfd_setup, errors



def sizing_toroidal(inputs: dict, expansion_angle: float, mfr: float | None = None, radius: float | None = None) -> tuple[float, float, float, float]:
    exit_velocity, exit_rho = cea.exit_conditions(inputs)

    # Given radius
    if mfr is None:
        exit_area = math.pi * pow(radius, 2)
        mfr = exit_rho * exit_velocity * exit_area

    # Given mass flow
    elif radius is None:
        exit_area = mfr / (exit_rho * exit_velocity)
        radius = math.sqrt(exit_area / math.pi)

    # Throat area
    effective_throat_velocity, effective_throat_rho = cea.effective_throat_conditions(inputs)
    throat_area = mfr / (effective_throat_rho * effective_throat_velocity)

    # Throat angle
    throat_angle = expansion_angle + _mach_angle(cea.exit_mach(inputs)) - math.pi / 2

    # Throat length
    throat_length = (radius - math.sqrt(max(0.0, radius**2 - (throat_area * math.cos(throat_angle)) / math.pi))) / math.cos(throat_angle)

    return mfr, radius, throat_area, throat_length


def sizing_linear(inputs: dict, mfr: float | None = None, width: float | None = None, length: float | None = None) -> tuple[float, float, float, float, float]:
    exit_velocity, exit_rho = cea.exit_conditions(inputs)

    # Given length and width
    if mfr is None:
        exit_area = length * width
        mfr = exit_rho * exit_velocity * exit_area

    # Given mfr and width
    elif length is None:
        exit_area = mfr / (exit_rho * exit_velocity)
        length = exit_area / width

    # Given mfr and length
    elif width is None:
        exit_area = mfr / (exit_rho * exit_velocity)
        width = exit_area / length

    # Throat area
    effective_throat_velocity, effective_throat_rho = cea.effective_throat_conditions(inputs)
    throat_area = mfr / (effective_throat_rho * effective_throat_velocity)

    # Throat length
    throat_length = throat_area / (2 * width)

    return mfr, width, length, throat_area, throat_length

