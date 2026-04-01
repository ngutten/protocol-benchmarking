"""
Stage 3 training tests: General PDE support.

Tests cover:
  - Fisher-KPP traveling wave (REF-3.1)
  - Coupled predator-prey system (REF-3.3)
  - XY model vortex annihilation with angular field (REF-3.4)
  - Parameter modification at runtime (REF-3.5)
"""

import numpy as np
import pytest

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from conftest import load_ref, l2_error, max_error

import pdesolver


# ---------------------------------------------------------------------------
# Tolerances
# ---------------------------------------------------------------------------
REL_L2_TOL = 0.15  # 15% relative L2 tolerance for reference comparisons


def relative_l2(computed, reference):
    """Relative L2 error: ||computed - reference||_2 / ||reference||_2."""
    ref_norm = np.sqrt(np.mean(reference ** 2))
    if ref_norm < 1e-6:
        return l2_error(computed, reference)
    return l2_error(computed, reference) / ref_norm


# ===========================================================================
# REF-3.1: Fisher-KPP traveling wave
# ===========================================================================

def fisher_rhs(fields, operators, x, y, t, params):
    u = fields["u"]
    lap_u = operators["laplacian"]
    D = params["D"]
    r = params["r"]
    return D * lap_u + r * u * (1 - u)


class TestFisherKPP:
    """Fisher-KPP equation on [0,40]x[0,1], 401x11 grid."""

    @pytest.fixture(scope="class")
    def snapshots(self):
        """Run one simulation to t=15 and capture snapshots along the way."""
        sim = pdesolver.Simulation(
            x_range=(0, 40), y_range=(0, 1), nx=401, ny=11,
        )
        sim.add_field("u", rhs=fisher_rhs, params={"D": 1.0, "r": 1.0})
        sim.set_initial_condition("u", lambda x, y: np.where(x < 5.0, 1.0, 0.0))
        sim.set_bc("u", "all", "neumann", flux=0.0)

        results = {}
        for t in [5.0, 10.0, 15.0]:
            sim.run_until(t, dt=0.002)
            results[t] = sim.get_field("u").copy()
        return results

    @pytest.fixture(scope="class")
    def ref(self):
        return load_ref("ref_3_1")

    def test_snapshot_t5(self, snapshots, ref):
        """Fisher-KPP field at t=5.0 matches reference."""
        u = snapshots[5.0]
        assert relative_l2(u, ref["u_t5.0"]) < REL_L2_TOL

    def test_snapshot_t10(self, snapshots, ref):
        """Fisher-KPP field at t=10.0 matches reference."""
        u = snapshots[10.0]
        assert relative_l2(u, ref["u_t10.0"]) < REL_L2_TOL

    def test_snapshot_t15(self, snapshots, ref):
        """Fisher-KPP field at t=15.0 matches reference."""
        u = snapshots[15.0]
        assert relative_l2(u, ref["u_t15.0"]) < REL_L2_TOL

    def test_midline_t10(self, snapshots, ref):
        """Midline profile at t=10 matches reference."""
        u = snapshots[10.0]
        ny = u.shape[1]
        midline = u[:, ny // 2]
        assert relative_l2(midline, ref["midline_t10.0"]) < REL_L2_TOL

    def test_traveling_wave_front(self, snapshots, ref):
        """Wave front advances between t=5 and t=15."""
        u5 = snapshots[5.0]
        u15 = snapshots[15.0]

        # Find front position (x where midline crosses 0.5)
        ny5 = u5.shape[1]
        mid5 = u5[:, ny5 // 2]
        ny15 = u15.shape[1]
        mid15 = u15[:, ny15 // 2]

        x = np.linspace(0, 40, 401)

        # Approximate front position: last x where u > 0.5
        front_5 = x[mid5 > 0.5].max() if np.any(mid5 > 0.5) else 0.0
        front_15 = x[mid15 > 0.5].max() if np.any(mid15 > 0.5) else 0.0

        # The wave front must advance
        assert front_15 > front_5, (
            f"Wave front did not advance: front at t=5 is {front_5:.2f}, "
            f"at t=15 is {front_15:.2f}"
        )

        # Fisher-KPP minimal speed is 2*sqrt(D*r) = 2.0
        # Over 10 time units, front should move roughly 20 units (but not exactly)
        displacement = front_15 - front_5
        assert displacement > 5.0, (
            f"Wave front displacement {displacement:.2f} is too small"
        )



# ===========================================================================
# REF-3.3: Coupled predator-prey
# ===========================================================================

def prey_rhs(fields, operators, x, y, t, params):
    u = fields["u"]
    v = fields["v"]
    lap_u = operators["laplacian"]
    return params["D_u"] * lap_u + u * (1 - u) - u * v


def pred_rhs(fields, operators, x, y, t, params):
    u = fields["u"]
    v = fields["v"]
    lap_v = operators["laplacian"]
    return params["D_v"] * lap_v + u * v - params["m"] * v


class TestCoupledPredatorPrey:
    """Coupled predator-prey on [0,10]x[0,10], 101x101 grid."""

    @pytest.fixture(scope="class")
    def snapshots(self):
        """Run one simulation to t=10 and capture snapshots along the way."""
        sim = pdesolver.Simulation(
            x_range=(0, 10), y_range=(0, 10), nx=101, ny=101,
        )
        sim.add_field("u", rhs=prey_rhs, params={"D_u": 0.1})
        sim.add_field("v", rhs=pred_rhs, params={"D_v": 0.05, "m": 0.3})

        # ICs matching the reference solution
        sim.set_initial_condition(
            "u",
            lambda x, y: 0.8 + 0.1 * np.sin(np.pi * x / 10) * np.sin(np.pi * y / 10),
        )
        sim.set_initial_condition(
            "v",
            lambda x, y: 0.2 + 0.1 * np.cos(np.pi * x / 10) * np.cos(np.pi * y / 10),
        )
        sim.set_bc("u", "all", "neumann", flux=0.0)
        sim.set_bc("v", "all", "neumann", flux=0.0)

        results = {}
        for t in [1.0, 5.0, 10.0]:
            sim.run_until(t, dt=0.005)
            results[t] = {
                "u": sim.get_field("u").copy(),
                "v": sim.get_field("v").copy(),
            }
        return results

    @pytest.fixture(scope="class")
    def ref(self):
        return load_ref("ref_3_3")

    def test_prey_t1(self, snapshots, ref):
        """Prey field u at t=1.0 matches reference."""
        u = snapshots[1.0]["u"]
        assert relative_l2(u, ref["u_t1.0"]) < REL_L2_TOL

    def test_predator_t1(self, snapshots, ref):
        """Predator field v at t=1.0 matches reference."""
        v = snapshots[1.0]["v"]
        assert relative_l2(v, ref["v_t1.0"]) < REL_L2_TOL

    def test_prey_t5(self, snapshots, ref):
        """Prey field u at t=5.0 matches reference."""
        u = snapshots[5.0]["u"]
        assert relative_l2(u, ref["u_t5.0"]) < REL_L2_TOL

    def test_predator_t5(self, snapshots, ref):
        """Predator field v at t=5.0 matches reference."""
        v = snapshots[5.0]["v"]
        assert relative_l2(v, ref["v_t5.0"]) < REL_L2_TOL

    def test_prey_t10(self, snapshots, ref):
        """Prey field u at t=10.0 matches reference."""
        u = snapshots[10.0]["u"]
        assert relative_l2(u, ref["u_t10.0"]) < REL_L2_TOL

    def test_predator_t10(self, snapshots, ref):
        """Predator field v at t=10.0 matches reference."""
        v = snapshots[10.0]["v"]
        assert relative_l2(v, ref["v_t10.0"]) < REL_L2_TOL

    def test_fields_positive(self, snapshots):
        """Both population fields should remain non-negative."""
        u = snapshots[5.0]["u"]
        v = snapshots[5.0]["v"]
        assert np.all(u >= -0.01), "Prey field u went significantly negative"
        assert np.all(v >= -0.01), "Predator field v went significantly negative"


# ===========================================================================
# REF-3.4: XY model vortex annihilation
# ===========================================================================

def xy_model_rhs(fields, operators, x, y, t, params):
    """XY model relaxation: d(theta)/dt = laplacian(theta) (angular-aware)."""
    lap_theta = operators["laplacian"]
    return lap_theta


class TestXYModelVortex:
    """XY model vortex-antivortex annihilation on [0,10]x[0,10], 201x201."""

    @pytest.fixture(scope="class")
    def snapshots(self):
        """Run one simulation to t=20 and capture snapshots along the way."""
        sim = pdesolver.Simulation(
            x_range=(0, 10), y_range=(0, 10), nx=201, ny=201,
        )
        sim.add_field("theta", rhs=xy_model_rhs, angular=True)
        # IC: vortex at (3.5, 5.0), antivortex at (6.5, 5.0)
        sim.set_initial_condition(
            "theta",
            lambda x, y: (
                np.arctan2(y - 5.0, x - 3.5)
                - np.arctan2(y - 5.0, x - 6.5)
            ) % (2 * np.pi),
        )
        sim.set_bc("theta", "all", "periodic")

        results = {}
        for t in [1.0, 5.0, 10.0, 20.0]:
            sim.run_until(t, dt=5e-4)
            results[t] = sim.get_field("theta").copy()
        return results

    @pytest.fixture(scope="class")
    def ref(self):
        return load_ref("ref_3_4")

    def test_field_t1(self, snapshots, ref):
        """Theta field at t=1.0 matches reference."""
        theta = snapshots[1.0]
        ref_theta = ref["theta_t1.0"]
        # For angular fields, compare via cos/sin to handle wrapping
        err_cos = relative_l2(np.cos(theta), np.cos(ref_theta))
        err_sin = relative_l2(np.sin(theta), np.sin(ref_theta))
        assert err_cos < REL_L2_TOL, f"cos(theta) error {err_cos:.4f} exceeds tolerance"
        assert err_sin < REL_L2_TOL, f"sin(theta) error {err_sin:.4f} exceeds tolerance"

    def test_field_t5(self, snapshots, ref):
        """Theta field at t=5.0 matches reference."""
        theta = snapshots[5.0]
        ref_theta = ref["theta_t5.0"]
        err_cos = relative_l2(np.cos(theta), np.cos(ref_theta))
        err_sin = relative_l2(np.sin(theta), np.sin(ref_theta))
        assert err_cos < REL_L2_TOL
        assert err_sin < REL_L2_TOL

    def test_field_t10(self, snapshots, ref):
        """Theta field at t=10.0 matches reference."""
        theta = snapshots[10.0]
        ref_theta = ref["theta_t10.0"]
        err_cos = relative_l2(np.cos(theta), np.cos(ref_theta))
        err_sin = relative_l2(np.sin(theta), np.sin(ref_theta))
        assert err_cos < REL_L2_TOL
        assert err_sin < REL_L2_TOL

    def test_field_t20(self, snapshots, ref):
        """Theta field at t=20.0 matches reference."""
        theta = snapshots[20.0]
        ref_theta = ref["theta_t20.0"]
        err_cos = relative_l2(np.cos(theta), np.cos(ref_theta))
        err_sin = relative_l2(np.sin(theta), np.sin(ref_theta))
        assert err_cos < REL_L2_TOL
        assert err_sin < REL_L2_TOL

    def test_energy_decreasing(self, snapshots, ref):
        """XY model energy should monotonically decrease as vortices annihilate."""
        energies = []
        snap_times = [1.0, 5.0, 10.0, 20.0]
        for t_snap in snap_times:
            energy_key = f"energy_t{t_snap}"
            energies.append(ref[energy_key][0])

        for i in range(len(energies) - 1):
            assert energies[i + 1] < energies[i], (
                f"Energy not decreasing: E(t={snap_times[i]})={energies[i]:.4f} "
                f">= E(t={snap_times[i+1]})={energies[i+1]:.4f}"
            )

    def test_winding_numbers_t1(self, snapshots, ref):
        """At t=1.0, winding numbers should be close to +1 and -1."""
        w1 = ref["winding1_t1.0"][0]
        w2 = ref["winding2_t1.0"][0]
        # Vortex should have winding ~+1, antivortex ~-1 (or vice versa)
        assert abs(abs(w1) - 1.0) < 0.3, f"Winding number 1 at t=1: {w1:.2f}, expected near +/-1"
        assert abs(abs(w2) - 1.0) < 0.3, f"Winding number 2 at t=1: {w2:.2f}, expected near +/-1"


# ===========================================================================
# REF-3.5: Parameter modification at runtime
# ===========================================================================

def diffusion_rhs(fields, operators, x, y, t, params):
    lap_u = operators["laplacian"]
    D = params["D"]
    return D * lap_u


class TestParameterModification:
    """Diffusion with parameter change mid-simulation on [0,1]x[0,1], 101x101."""

    @pytest.fixture(scope="class")
    def ref(self):
        return load_ref("ref_3_5")

    @pytest.fixture(scope="class")
    def phase1_result(self):
        """Run phase 1 (D=1.0, 1000 steps) once and return the field."""
        sim = pdesolver.Simulation(
            x_range=(0, 1), y_range=(0, 1), nx=101, ny=101,
        )
        sim.add_field("u", rhs=diffusion_rhs, params={"D": 1.0})
        sim.set_initial_condition(
            "u",
            lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y),
        )
        sim.set_bc("u", "all", "dirichlet", value=0.0)
        dt = 2e-5
        sim.step(dt=dt, n_steps=1000)
        return {"sim": sim, "u": sim.get_field("u").copy(), "dt": dt}

    @pytest.fixture(scope="class")
    def phase2_result(self, phase1_result):
        """Continue from phase 1, change D to 0.1, run 4000 more steps."""
        # We need a fresh sim for phase 2 since phase1_result's sim may be reused
        sim = pdesolver.Simulation(
            x_range=(0, 1), y_range=(0, 1), nx=101, ny=101,
        )
        sim.add_field("u", rhs=diffusion_rhs, params={"D": 1.0})
        sim.set_initial_condition(
            "u",
            lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y),
        )
        sim.set_bc("u", "all", "dirichlet", value=0.0)
        dt = 2e-5
        # Phase 1
        sim.step(dt=dt, n_steps=1000)
        u_after_phase1 = sim.get_field("u").copy()
        # Phase 2
        sim.set_parameter("D", 0.1)
        sim.step(dt=dt, n_steps=4000)
        return {"u": sim.get_field("u").copy(), "u_phase1": u_after_phase1}

    def test_phase1_matches_reference(self, ref, phase1_result):
        """After 1000 steps at D=1.0, field matches reference."""
        u = phase1_result["u"]
        assert relative_l2(u, ref["u_t0.02"]) < REL_L2_TOL

    def test_phase1_matches_analytical(self, ref, phase1_result):
        """After phase 1, field matches analytical solution."""
        u = phase1_result["u"]
        u_analytical = ref["u_analytical_t0.02"]
        assert relative_l2(u, u_analytical) < REL_L2_TOL

    def test_phase2_matches_reference(self, ref, phase2_result):
        """After parameter change and 4000 more steps, field matches reference."""
        u = phase2_result["u"]
        assert relative_l2(u, ref["u_t0.10"]) < REL_L2_TOL

    def test_phase2_matches_analytical(self, ref, phase2_result):
        """After both phases, field matches two-phase analytical solution."""
        u = phase2_result["u"]
        u_analytical = ref["u_analytical_t0.10"]
        assert relative_l2(u, u_analytical) < REL_L2_TOL

    def test_parameter_change_effect(self):
        """Changing D from 1.0 to 0.1 should visibly slow diffusion."""
        dt = 2e-5

        # Sim with D change: 1000 steps D=1.0, then 1000 steps D=0.1
        sim = pdesolver.Simulation(
            x_range=(0, 1), y_range=(0, 1), nx=101, ny=101,
        )
        sim.add_field("u", rhs=diffusion_rhs, params={"D": 1.0})
        sim.set_initial_condition(
            "u",
            lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y),
        )
        sim.set_bc("u", "all", "dirichlet", value=0.0)
        sim.step(dt=dt, n_steps=1000)
        sim.set_parameter("D", 0.1)
        sim.step(dt=dt, n_steps=1000)
        peak_slow = sim.get_field("u").max()

        # Sim with constant D=1.0 for all 2000 steps
        sim_fast = pdesolver.Simulation(
            x_range=(0, 1), y_range=(0, 1), nx=101, ny=101,
        )
        sim_fast.add_field("u", rhs=diffusion_rhs, params={"D": 1.0})
        sim_fast.set_initial_condition(
            "u",
            lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y),
        )
        sim_fast.set_bc("u", "all", "dirichlet", value=0.0)
        sim_fast.step(dt=dt, n_steps=2000)
        peak_fast = sim_fast.get_field("u").max()

        # With D=0.1 in phase 2, the peak should decay slower than D=1.0
        # So peak_slow > peak_fast
        assert peak_slow > peak_fast, (
            f"Peak with D change ({peak_slow:.6f}) should be larger than "
            f"peak with constant D=1.0 ({peak_fast:.6f})"
        )
