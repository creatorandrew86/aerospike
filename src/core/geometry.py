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
        "bl_thickness": None,
        "bl_first_cell": None,
        "ideal_expansion_pressure": None,
        "x": [None] * N,
        "R_x": [None] * N,
        "eps_x": [None] * N,
    }

    # Area ratio from pressure ratio
    if inputs.get("nozzle_choice") in ("design_pressure", "pressure_ratio") or (inputs.get("eps") is None and inputs.get("pressure_ratio") is not None):
        try:
            inputs["eps"] = cea.eps_from_pressure_ratio(inputs)
        except Exception as e:
            errors.append(f"Failed to calculate area ratio from pressure ratio: {e}")
            return {}, {}, errors

    results["eps"] = inputs.get("eps")

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
    bl_thickness = bl_first_cell = None
    if sizing:
        expansion_angle = exit_pm_angle - entry_pm_angle

        if aerospike_type == "toroidal":
            try:
                mfr, radius, throat_area, throat_length, bl_thickness, bl_first_cell = sizing_toroidal(inputs, expansion_angle, mfr, radius)
            except Exception as e:
                errors.append(f"Toroidal sizing calculation failed with {e}")
                return {}, {}, errors

        if aerospike_type == "linear":
            try:
                mfr, width, length, throat_area, throat_length, bl_thickness, bl_first_cell = sizing_linear(inputs, mfr, width, length)
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
            eps = inputs["eps"] if i == N - 1 else cea.eps_from_mach(inputs, mach)

            # Characteristic line length
            if aerospike_type == "toroidal":
                C = (mach * eps) / inputs["eps"]
                radicand = 0.0 if i == N - 1 else max(0.0, 1.0 - C * math.cos(beta))
                characteristic_length = radius * C / (1.0 + math.sqrt(radicand))
            else:
                half_width = width / 2 if sizing else throat_length * inputs["eps"] / inputs["effective_throat_eps"]
                characteristic_length = half_width * (mach * eps) / inputs["eps"]

            # Coordinates
            x = -characteristic_length * math.sin(beta)
            R = radius if (i == N - 1 and aerospike_type == "toroidal" and sizing) else characteristic_length * math.cos(beta)

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
    results["bl_thickness"] = bl_thickness
    results["bl_first_cell"] = bl_first_cell
    results["nozzle_size"] = max(results["R_x"])
    results["x_full"], results["R_x_full"], results["eps_x_full"] = results["x"], results["R_x"], results["eps_x"]

    # Truncating
    if truncate_percent < 1.0:
        cutoff = results["x"][0] - (results["x"][0] - results["x"][-1]) * truncate_percent
        keep = sum(x >= cutoff for x in results["x"])
        results["x"] = results["x"][:keep]
        results["R_x"] = results["R_x"][:keep]
        results["eps_x"] = results["eps_x"][:keep]

    return results, cfd_setup, errors




def _boundary_layer_properties(throat_gap: float, inputs: dict) -> tuple[float, float, float]:
    """Computes the nozzle discharge coefficient (Cd), boundary-layer thickness, and y+=1 first cell height."""
    v_t, rho_t = cea.effective_throat_conditions(inputs)
    c = cea._cea_object(inputs)
    transport = c.get_Throat_Transport(Pc=inputs["Pc"], MR=inputs["MR"])
    mu_t = float(transport[1]) * 1.0e-4

    d_h = 2.0 * throat_gap
    re_t = (rho_t * v_t * d_h) / mu_t

    if re_t >= 1e5:
        cd = 1.0 - 0.15 * (re_t ** -0.2)
        shape_factor = 8.0
        cf = 0.058 * (re_t ** -0.2)
    else:
        cd = 1.0 - 1.5 * (re_t ** -0.5)
        shape_factor = 5.0 / 1.7208
        cf = 0.664 * (re_t ** -0.5)

    bl_thickness = shape_factor * 0.5 * (1.0 - cd) * throat_gap
    u_tau = v_t * math.sqrt(0.5 * cf)
    delta_y1 = mu_t / (rho_t * u_tau)
    return float(cd), float(bl_thickness), float(delta_y1)


def sizing_toroidal(inputs: dict, expansion_angle: float, mfr: float | None = None, radius: float | None = None) -> tuple[float, float, float, float, float | None, float | None]:
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

    # Throat length (flow-normal gap from annular continuity)
    throat_length = radius - math.sqrt(max(0.0, radius**2 - throat_area / math.pi))

    # Boundary layer discharge coefficient correction
    try:
        cd, bl_thickness, bl_first_cell = _boundary_layer_properties(throat_length, inputs)
    except Exception:
        cd, bl_thickness, bl_first_cell = 1.0, None, None

    throat_area /= cd
    throat_length = radius - math.sqrt(max(0.0, radius**2 - throat_area / math.pi))

    return mfr, radius, throat_area, throat_length, bl_thickness, bl_first_cell


def sizing_linear(inputs: dict, mfr: float | None = None, width: float | None = None, length: float | None = None) -> tuple[float, float, float, float, float, float | None, float | None]:
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

    # Throat length (flow-normal gap from continuity)
    throat_length = throat_area / (2 * length)

    # Boundary layer discharge coefficient correction
    try:
        cd, bl_thickness, bl_first_cell = _boundary_layer_properties(throat_length, inputs)
    except Exception:
        cd, bl_thickness, bl_first_cell = 1.0, None, None

    throat_area /= cd
    throat_length = throat_area / (2 * length)

    return mfr, width, length, throat_area, throat_length, bl_thickness, bl_first_cell

