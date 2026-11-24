from collections.abc import Callable
import math
import warnings
from core import cea


def _mach_angle(mach: float) -> float:
    mach = max(mach, 1)
    return math.asin(1 / mach)


def _toroidal_throat_gap(radius: float, throat_area: float, expansion_angle: float) -> float:
    """Compute conical-frustum throat gap normal to flow inclined at expansion_angle."""
    disc = radius**2 - (throat_area / math.pi) * math.cos(expansion_angle)
    if disc < 0.0:
        raise ValueError("Toroidal throat area exceeds available annular cross-section for this radius.")
    return (throat_area / math.pi) / (radius + math.sqrt(disc))


def generate_aerospike_contour(inputs: dict) -> tuple[dict, dict, list[str]]:
    """Generate aerospike contour coordinates, sizing parameters, and CFD inlet setup.

    ponytail: Angelino straight-Mach-line approximation for toroidal; replace with
    axisymmetric MoC only if sub-1% tip accuracy is needed.
    """
    errors = []

    truncate_percent = inputs["truncate_percent"] / 100
    N = inputs["aerospike_resolution"]

    if N is None or N < 2:
        errors.append("Aerospike resolution must be at least 2.")
        return {}, {}, errors

    sizing = inputs["sizing"]
    aerospike_type = inputs["aerospike_type"]
    mfr = inputs["mfr"]
    radius = inputs["radius"]
    width = inputs["width"]
    length = inputs["length"]

    results = {
        "aerospike_type": aerospike_type,
        "mfr": None,
        "radius": None,
        "length": None,
        "width": None,
        "throat_length": None,
        "entry_pm_angle": None,
        "bl_thickness": None,
        "bl_first_cell": None,
        "bl_thickness_x": None,
        "ideal_expansion_pressure": None,
        "x": [None] * N,
        "R_x": [None] * N,
        "eps_x": [None] * N,
    }

    if inputs.get("nozzle_choice") in ("design_pressure", "pressure", "pressure_ratio") or (
        inputs.get("eps") is None and inputs.get("pressure_ratio") is not None
    ):
        try:
            inputs["eps"] = cea.eps_from_pressure_ratio(inputs)
        except Exception as e:
            errors.append(f"Failed to calculate area ratio from pressure ratio: {e}")
            return {}, {}, errors

    results["eps"] = inputs.get("eps")

    try:
        pm_from_mach = cea.prandtl_meyer_from_mach(inputs)
        entry_mach = cea.entry_conditions(inputs)
        entry_pm_angle = pm_from_mach(entry_mach)
        results["entry_pm_angle"] = entry_pm_angle
    except Exception as e:
        errors.append(f"CFD inlet conditions calculation failed with {e}")
        return {}, {}, errors

    try:
        exit_mach = cea.exit_mach(inputs)
        exit_pm_angle = pm_from_mach(exit_mach)
    except Exception as e:
        errors.append(f"Exit conditions calculation failed with {e} ")
        return {}, {}, errors

    try:
        results["ideal_expansion_pressure"] = cea.ideal_expansion_pressure(inputs)
        cfd_setup = cea.cfd_setup(inputs)
    except Exception as e:
        errors.append(f"CEA Results calculation failed with {e} ")
        return {}, {}, errors

    expansion_angle = exit_pm_angle - entry_pm_angle
    if expansion_angle <= 0.0:
        errors.append("Design area ratio must exceed effective_throat_eps.")
        return {}, {}, errors
    if expansion_angle >= math.pi / 2.0:
        errors.append(
            f"Total expansion turning angle ({math.degrees(expansion_angle):.1f} deg) must be less than 90 deg; "
            "increase effective_throat_eps or reduce eps."
        )
        return {}, {}, errors

    bl_thickness = bl_first_cell = None
    if sizing:
        if aerospike_type == "toroidal":
            try:
                mfr, radius, throat_area, throat_length, bl_thickness, bl_first_cell = sizing_toroidal(
                    inputs, expansion_angle, mfr, radius
                )
            except Exception as e:
                errors.append(f"Toroidal sizing calculation failed with {e}")
                return {}, {}, errors

        if aerospike_type == "linear":
            try:
                mfr, width, length, throat_area, throat_length, bl_thickness, bl_first_cell = sizing_linear(
                    inputs, mfr, width, length
                )
            except Exception as e:
                errors.append(f"Linear sizing calculation failed with {e}")
                return {}, {}, errors

    elif not sizing:
        radius = 1.0
        if aerospike_type == "toroidal":
            throat_length = _toroidal_throat_gap(
                radius, math.pi * inputs["effective_throat_eps"] / inputs["eps"], expansion_angle
            )
        else:
            throat_length = 1.0

    u_start = math.sqrt(max(0.0, entry_mach**2 - 1.0))
    u_end = math.sqrt(max(0.0, exit_mach**2 - 1.0))
    mach_x = [None] * N

    for i in range(N):
        if i == 0:
            mach = entry_mach
        elif i == N - 1:
            mach = exit_mach
        else:
            u = u_start + (i / (N - 1)) * (u_end - u_start)
            mach = math.hypot(1.0, u)

        try:
            flow_angle = exit_pm_angle - pm_from_mach(mach)
            mach_angle = _mach_angle(mach)
            beta = (math.pi / 2) - mach_angle - flow_angle
            eps = inputs["eps"] if i == N - 1 else cea.eps_from_mach(inputs, mach)

            if aerospike_type == "toroidal":
                C = (mach * eps) / inputs["eps"]
                radicand = 0.0 if i == N - 1 else max(0.0, 1.0 - C * math.cos(beta))
                characteristic_length = radius * C / (1.0 + math.sqrt(radicand))
            else:
                half_width = width / 2 if sizing else throat_length * inputs["eps"] / inputs["effective_throat_eps"]
                characteristic_length = half_width * (mach * eps) / inputs["eps"]

            x = -characteristic_length * math.sin(beta)
            R = (
                (radius if aerospike_type == "toroidal" else half_width)
                if i == N - 1
                else characteristic_length * math.cos(beta)
            )
        except Exception as e:
            errors.append(f"Station {i+1} calculation failed with {e}")
            return {}, {}, errors

        results["x"][i] = x
        results["R_x"][i] = R
        results["eps_x"][i] = eps
        mach_x[i] = mach

    if not sizing:
        spike_length = max(results["x"]) - min(results["x"])
        results["x"] = [v / spike_length for v in results["x"]]
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

    if truncate_percent < 1.0:
        cutoff = results["x"][0] - (results["x"][0] - results["x"][-1]) * truncate_percent
        keep = sum(x >= cutoff for x in results["x"])
        x_t, r_t, e_t, m_t = results["x"][:keep], results["R_x"][:keep], results["eps_x"][:keep], mach_x[:keep]
        if 0 < keep < len(results["x"]) and x_t[-1] > cutoff:
            x0, x1 = results["x"][keep - 1], results["x"][keep]
            t = (x0 - cutoff) / (x0 - x1)
            x_t.append(cutoff)
            r_t.append(results["R_x"][keep - 1] + t * (results["R_x"][keep] - results["R_x"][keep - 1]))
            e_t.append(results["eps_x"][keep - 1] + t * (results["eps_x"][keep] - results["eps_x"][keep - 1]))
            m_t.append(mach_x[keep - 1] + t * (mach_x[keep] - mach_x[keep - 1]))
        results["x"], results["R_x"], results["eps_x"], mach_x = x_t, r_t, e_t, m_t

    if sizing and bl_thickness is not None and results["x"]:
        try:
            _, _, _, results["bl_thickness_x"] = _boundary_layer_properties(
                throat_length, inputs, spike=(results["x"], results["R_x"], mach_x)
            )
        except (ValueError, ZeroDivisionError, RuntimeError) as exc:
            warnings.warn(
                f"Spike boundary-layer march failed; using fixed throat thickness ({exc})",
                RuntimeWarning,
                stacklevel=2,
            )
            results["bl_thickness_x"] = None

    return results, cfd_setup, errors


def _boundary_layer_properties(
    throat_gap: float,
    inputs: dict,
    spike: tuple[list[float], list[float], list[float]] | None = None,
) -> tuple[float, float, float] | tuple[float, float, float, list[float]]:
    """Compute sonic-throat Cd, BL thickness, y+=1 first cell height, and optional spike BL march.

    Uses Stratford (1964) turbulent Cd (Rc/dh=1), Crocco-Busemann 1/7-law delta/delta*,
    Tang & Fenn (1978) laminar Cd, clamped low-Re bounds, and an optional compressible 2D
    Von Karman momentum-integral march along the spike surface.
    """
    v_t, rho_t, mu_t, pr, gamma, t0, t_t = cea.sonic_throat_state(inputs)
    if min(throat_gap, v_t, rho_t, mu_t, t_t) <= 0.0:
        raise ValueError("Throat gap and sonic transport properties must be positive.")

    # Compute sonic-throat Reynolds number and turbulent (Stratford) or laminar (Tang & Fenn) closures.
    sonic_gap = throat_gap / max(1.0, float(inputs.get("effective_throat_eps") or 1.0))
    d_h = 2.0 * sonic_gap
    re_t = max((rho_t * v_t * d_h) / mu_t, 1e-6)

    if re_t >= 1e5:
        cd = 1.0 - 0.0525 * (re_t ** -0.2)
        delta_over_delta_star = 1.0 / (0.125 + 0.175 * (pr ** (1.0 / 3.0)) * max(0.0, t0 / t_t - 1.0))
        cf = 0.058 * (re_t ** -0.2)
    else:
        re_cd = max(re_t, 1.0)
        cd = (
            1.0
            - ((gamma + 1.0) / 2.0) ** 0.75 * (3.266 - 2.128 / (gamma + 1.0)) * (re_cd ** -0.5)
            + 0.9428 * (gamma - 1.0) * (gamma + 2.0) / math.sqrt(gamma + 1.0) / re_cd
        )
        delta_over_delta_star = 5.0 / 1.7208
        cf = 0.664 * (re_t ** -0.5)

    # Derive throat BL thickness and y+=1 first cell height from bounded Cd and wall shear.
    cd = min(1.0, max(cd, 0.1))
    bl_thickness = min(delta_over_delta_star * 0.5 * (1.0 - cd) * sonic_gap, 0.5 * sonic_gap)
    u_tau = v_t * math.sqrt(0.5 * cf)
    delta_y1 = mu_t / (rho_t * u_tau)

    if spike is None:
        return float(cd), float(bl_thickness), float(delta_y1)

    spike_x, spike_radius, spike_mach = spike
    if not spike_x or not (len(spike_x) == len(spike_radius) == len(spike_mach)):
        raise ValueError("Spike coordinates and Mach distribution must be non-empty and equal length.")

    # Select compressible closure constants and initialize momentum thickness at the spike entry.
    is_turbulent = re_t >= 1e5
    recovery_factor = pr ** (1.0 / 3.0 if is_turbulent else 0.5)
    incompressible_delta_over_theta = 72.0 / 7.0 if is_turbulent else 5.0 / 0.664
    incompressible_shape_factor = 9.0 / 7.0 if is_turbulent else 2.592
    shape_factor_mach_slope = 2.22 if is_turbulent else 3.592
    gamma_minus_one = max(gamma - 1.0, 1e-6)

    entry_mach = max(float(spike_mach[0]), 1.0)
    entry_recovery_heating = recovery_factor * 0.5 * gamma_minus_one * entry_mach**2
    momentum_thickness = bl_thickness / (incompressible_delta_over_theta * (1.0 + 0.30 * entry_recovery_heating))
    prev_temp_ratio = (gamma + 1.0) / (2.0 + gamma_minus_one * entry_mach**2)
    prev_edge_velocity = v_t * entry_mach * math.sqrt(prev_temp_ratio)
    prev_mach = entry_mach
    spike_bl_thicknesses = [float(bl_thickness)]

    # March momentum thickness along each spike segment using midpoint isentropic edge properties.
    for i in range(1, len(spike_x)):
        segment_length = math.hypot(spike_x[i] - spike_x[i - 1], spike_radius[i] - spike_radius[i - 1])
        curr_mach = max(float(spike_mach[i]), 1.0)
        curr_temp_ratio = (gamma + 1.0) / (2.0 + gamma_minus_one * curr_mach**2)
        curr_edge_velocity = v_t * curr_mach * math.sqrt(curr_temp_ratio)

        mid_mach = 0.5 * (prev_mach + curr_mach)
        mid_temp_ratio = (gamma + 1.0) / (2.0 + gamma_minus_one * mid_mach**2)
        mid_edge_density = rho_t * (mid_temp_ratio ** (1.0 / gamma_minus_one))
        mid_edge_velocity = v_t * mid_mach * math.sqrt(mid_temp_ratio)
        mid_edge_viscosity = mu_t * (mid_temp_ratio ** 0.7)
        mid_recovery_heating = recovery_factor * 0.5 * gamma_minus_one * mid_mach**2
        eckert_temp_ratio = 1.0 + 0.72 * mid_recovery_heating

        # Evaluate Eckert skin friction, compressible shape factor, and exact integrating-factor step.
        momentum_reynolds = max((mid_edge_density * mid_edge_velocity * momentum_thickness) / mid_edge_viscosity, 10.0)
        half_skin_friction = (
            0.0128 * (eckert_temp_ratio ** -0.575) * (momentum_reynolds ** -0.25)
            if is_turbulent
            else 0.2205 * (eckert_temp_ratio ** -0.3) * (momentum_reynolds ** -1.0)
        )
        mid_shape_factor = incompressible_shape_factor + shape_factor_mach_slope * mid_recovery_heating
        acceleration_exponent = max(
            -20.0,
            min(
                20.0,
                (mid_shape_factor + 2.0 - mid_mach**2)
                * math.log(max(curr_edge_velocity, 1e-12) / max(prev_edge_velocity, 1e-12)),
            ),
        )
        step_average_factor = (
            1.0 if abs(acceleration_exponent) < 1e-6 else (1.0 - math.exp(-acceleration_exponent)) / acceleration_exponent
        )

        # Advance momentum thickness and recover physical boundary-layer thickness at station i.
        momentum_thickness = max(
            1e-12,
            momentum_thickness * math.exp(-acceleration_exponent)
            + half_skin_friction * segment_length * step_average_factor,
        )
        curr_recovery_heating = recovery_factor * 0.5 * gamma_minus_one * curr_mach**2
        curr_bl_thickness = momentum_thickness * incompressible_delta_over_theta * (1.0 + 0.30 * curr_recovery_heating)
        spike_bl_thicknesses.append(float(curr_bl_thickness))

        prev_edge_velocity = curr_edge_velocity
        prev_mach = curr_mach

    return float(cd), float(bl_thickness), float(delta_y1), spike_bl_thicknesses


def _iterate_bl(gap_from_cd: Callable[[float], float], inputs: dict) -> tuple[float, float | None, float | None]:
    """Run a 3-step 0.5-damped fixed-point BL loop with RuntimeWarning fallback to Cd=1.0."""
    try:
        cd = 1.0
        for step in range(3):
            next_cd, bl_thickness, bl_first_cell = _boundary_layer_properties(gap_from_cd(cd), inputs)
            damped = next_cd if step == 0 else 0.5 * (cd + next_cd)
            if abs(damped - cd) < 1e-4:
                cd = damped
                break
            cd = damped
        _, bl_thickness, bl_first_cell = _boundary_layer_properties(gap_from_cd(cd), inputs)
        return cd, bl_thickness, bl_first_cell
    except (ValueError, ZeroDivisionError, RuntimeError) as exc:
        warnings.warn(f"Boundary-layer calculation failed; falling back to Cd=1.0 ({exc})", RuntimeWarning, stacklevel=2)
        return 1.0, None, None


def sizing_toroidal(
    inputs: dict,
    expansion_angle: float,
    mfr: float | None = None,
    radius: float | None = None,
) -> tuple[float, float, float, float, float | None, float | None]:
    """Size toroidal aerospike using inclined conical-frustum throat gap and viscous Cd correction."""
    exit_velocity, exit_rho = cea.exit_conditions(inputs)
    effective_throat_velocity, effective_throat_rho = cea.effective_throat_conditions(inputs)

    if mfr is None:
        exit_area = math.pi * radius**2
        mfr_ideal = exit_rho * exit_velocity * exit_area
        throat_area = mfr_ideal / (effective_throat_rho * effective_throat_velocity)
        throat_length = _toroidal_throat_gap(radius, throat_area, expansion_angle)
        cd, bl_thickness, bl_first_cell = _iterate_bl(lambda _: throat_length, inputs)
        mfr = cd * mfr_ideal
    elif radius is None:
        exit_area = mfr / (exit_rho * exit_velocity)
        radius = math.sqrt(exit_area / math.pi)
        throat_area = mfr / (effective_throat_rho * effective_throat_velocity)
        _ = _toroidal_throat_gap(radius, throat_area, expansion_angle)
        cd, bl_thickness, bl_first_cell = _iterate_bl(
            lambda c: _toroidal_throat_gap(radius / math.sqrt(c), throat_area / c, expansion_angle),
            inputs,
        )
        radius /= math.sqrt(cd)
        throat_area /= cd
        throat_length = _toroidal_throat_gap(radius, throat_area, expansion_angle)

    return mfr, radius, throat_area, throat_length, bl_thickness, bl_first_cell


def sizing_linear(
    inputs: dict,
    mfr: float | None = None,
    width: float | None = None,
    length: float | None = None,
) -> tuple[float, float, float, float, float, float | None, float | None]:
    """Size symmetric two-sided linear aerospike with unified viscous Cd contour/CFD correction."""
    exit_velocity, exit_rho = cea.exit_conditions(inputs)
    effective_throat_velocity, effective_throat_rho = cea.effective_throat_conditions(inputs)

    if mfr is None:
        mfr_ideal = exit_rho * exit_velocity * length * width
        throat_area = mfr_ideal / (effective_throat_rho * effective_throat_velocity)
        throat_length = throat_area / (2.0 * length)
        cd, bl_thickness, bl_first_cell = _iterate_bl(lambda _: throat_length, inputs)
        mfr = cd * mfr_ideal
    elif length is None:
        length = mfr / (exit_rho * exit_velocity * width)
        throat_area = mfr / (effective_throat_rho * effective_throat_velocity)
        throat_length = throat_area / (2.0 * length)
        cd, bl_thickness, bl_first_cell = _iterate_bl(lambda _: throat_length, inputs)
        length /= cd
        throat_area /= cd
    elif width is None:
        width = mfr / (exit_rho * exit_velocity * length)
        throat_area = mfr / (effective_throat_rho * effective_throat_velocity)
        cd, bl_thickness, bl_first_cell = _iterate_bl(lambda c: (throat_area / c) / (2.0 * length), inputs)
        width /= cd
        throat_area /= cd
        throat_length = throat_area / (2.0 * length)

    return mfr, width, length, throat_area, throat_length, bl_thickness, bl_first_cell

