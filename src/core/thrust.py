import math
from core import cea
from core.geometry import _prandtl_meyer_angle

G0 = 9.80665


def _thruser_component(inputs: dict, results: dict, ambient_pressure: float) -> float:
    throat_velocity, throat_rho = cea.effective_throat_conditions(inputs)
    throat_pressure = cea.pressure_from_eps(inputs, inputs["effective_throat_eps"])
    mfr = results["mfr"]
    throat_area = mfr / (throat_rho * throat_velocity)

    gamma_from_mach = cea.gamma_from_mach(inputs)
    entry_mach = cea.entry_conditions(inputs)
    exit_mach = cea.exit_mach(inputs)
    throat_angle = _prandtl_meyer_angle(exit_mach, gamma_from_mach) - _prandtl_meyer_angle(entry_mach, gamma_from_mach)

    return (mfr * throat_velocity + (throat_pressure - ambient_pressure) * throat_area) * math.cos(throat_angle)


def _spike_pressure_component(inputs: dict, results: dict, ambient_pressure: float) -> float:
    entry_mach = cea.entry_conditions(inputs)
    exit_mach = cea.exit_mach(inputs)
    N = inputs["aerospike_resolution"]

    x = results["x"]
    R_x = results["R_x"]
    eps_x = results.get("eps_x")
    n_points = len(R_x)

    ps = [None] * n_points
    for i in range(n_points):
        eps = eps_x[i] if eps_x and eps_x[i] is not None else cea.eps_from_mach(
            inputs, entry_mach + (i / (N - 1)) * (exit_mach - entry_mach)
        )
        ps[i] = max(cea.pressure_from_eps(inputs, eps), ambient_pressure)

    aerospike_type = results["aerospike_type"]
    spike_thrust = 0.0
    for i in range(n_points - 1):
        dl = math.hypot(x[i + 1] - x[i], R_x[i + 1] - R_x[i])
        normal_x = (R_x[i + 1] - R_x[i]) / dl
        if aerospike_type == "toroidal":
            r1 = results["radius"] - R_x[i]
            r2 = results["radius"] - R_x[i + 1]
            spike_area = math.pi * (r1 + r2) * dl
        else:
            spike_area = 2.0 * results["width"] * dl
        p_avg = 0.5 * (ps[i] + ps[i + 1])
        spike_thrust += (p_avg - ambient_pressure) * normal_x * spike_area

    return spike_thrust


def _base_component(inputs: dict, results: dict, ambient_pressure: float) -> float:
    if inputs["truncate_percent"] >= 100:
        return 0.0

    R_x = results["R_x"]
    if results["aerospike_type"] == "toroidal":
        base_radius = max(0.0, results["radius"] - R_x[-1])
        base_area = math.pi * base_radius**2
    else:
        base_height = max(0.0, results["nozzle_size"] - R_x[-1])
        base_area = 2.0 * results["width"] * base_height

    entry_mach = cea.entry_conditions(inputs)
    exit_mach = cea.exit_mach(inputs)
    tip_mach = entry_mach + ((len(R_x) - 1) / (inputs["aerospike_resolution"] - 1)) * (exit_mach - entry_mach)
    tip_eps = cea.eps_from_mach(inputs, tip_mach)
    tip_pressure = cea.pressure_from_eps(inputs, tip_eps)
    base_pressure = max(0.5 * tip_pressure, ambient_pressure)

    return (base_pressure - ambient_pressure) * base_area


def thrust(inputs: dict, results: dict, ambient_pressure: float) -> tuple[float, float, float]:
    total_thrust = (
        _thruser_component(inputs, results, ambient_pressure)
        + _spike_pressure_component(inputs, results, ambient_pressure)
        + _base_component(inputs, results, ambient_pressure)
    )
    throat_velocity, throat_rho = cea.effective_throat_conditions(inputs)
    throat_area = results["mfr"] / (throat_rho * throat_velocity)
    sonic_throat_area = throat_area / inputs["effective_throat_eps"]

    cf = total_thrust / (inputs["Pc"] * sonic_throat_area)
    isp = total_thrust / (results["mfr"] * G0)
    return cf, total_thrust, isp
