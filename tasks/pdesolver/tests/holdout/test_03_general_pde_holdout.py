"""
Holdout tests for Stage 3: General PDE via callable RHS.

These tests are hidden from the LLM and exercise edge cases not covered
in the training set.  They rely on analytical solutions and physical
properties rather than reference data files.
"""

import sys
import os
import pytest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from conftest import l2_error, max_error

import pdesolver


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _relative_l2(computed, reference):
    """Relative L2 error: ||computed - ref|| / ||ref||."""
    ref_norm = np.sqrt(np.mean(reference ** 2))
    if ref_norm < 0.01:
        return np.sqrt(np.mean((computed - reference) ** 2))
    return np.sqrt(np.mean((computed - reference) ** 2)) / ref_norm


# ===========================================================================
# 1. Pure diffusion reproduced via general RHS
# ===========================================================================

class TestPureDiffusionViaGeneral:
    """
    RHS = D * laplacian(u) expressed through the general callable interface
    must reproduce the same result as the built-in diffusion equation.
    Analytical solution: sin(pi*x)*sin(pi*y)*exp(-2*pi^2*D*t).
    """

    @pytest.fixture()
    def sim(self):
        D_val = 1.0

        def diffusion_rhs(fields, operators, x, y, t, params):
            lap_u = operators["laplacian"]
            return params["D"] * lap_u

        s = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        s.add_field("u", rhs=diffusion_rhs, params={"D": D_val})
        s.set_initial_condition(
            "u", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y)
        )
        s.set_bc("u", "all", "dirichlet", value=0.0)
        return s

    def test_matches_analytical_t005(self, sim):
        """General-RHS diffusion matches analytical at t=0.05."""
        t_target = 0.05
        sim.run_until(t_target, dt=1e-4)
        u = sim.get_field("u")
        x, y = sim.coordinates()
        X, Y = np.meshgrid(x, y, indexing="ij")
        u_exact = (
            np.sin(np.pi * X) * np.sin(np.pi * Y)
            * np.exp(-2 * np.pi ** 2 * 1.0 * t_target)
        )
        assert _relative_l2(u, u_exact) < 0.20, (
            f"Relative L2 error {_relative_l2(u, u_exact):.4e} exceeds 20%"
        )

    def test_matches_analytical_t01(self, sim):
        """General-RHS diffusion matches analytical at t=0.1."""
        t_target = 0.1
        sim.run_until(t_target, dt=1e-4)
        u = sim.get_field("u")
        x, y = sim.coordinates()
        X, Y = np.meshgrid(x, y, indexing="ij")
        u_exact = (
            np.sin(np.pi * X) * np.sin(np.pi * Y)
            * np.exp(-2 * np.pi ** 2 * 1.0 * t_target)
        )
        assert _relative_l2(u, u_exact) < 0.20


# ===========================================================================
# 2. Linear growth (pure exponential, no diffusion)
# ===========================================================================

class TestLinearGrowth:
    """
    RHS = r * u  (no spatial derivatives).
    Starting from sin(pi*x)*sin(pi*y), the field should grow as
    exp(r*t) * IC at every grid point.
    """

    @pytest.fixture()
    def sim(self):
        r_val = 2.0

        def growth_rhs(fields, operators, x, y, t, params):
            u = fields["u"]
            return params["r"] * u

        s = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=31, ny=31)
        s.add_field("u", rhs=growth_rhs, params={"r": r_val})
        s.set_initial_condition(
            "u", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y)
        )
        s.set_bc("u", "all", "neumann", flux=0.0)
        return s

    def test_exponential_growth_short(self, sim):
        """After a few steps, u matches exp(r*t)*IC."""
        t_target = 0.05
        sim.run_until(t_target, dt=5e-4)
        u = sim.get_field("u")
        x, y = sim.coordinates()
        X, Y = np.meshgrid(x, y, indexing="ij")
        u_exact = np.sin(np.pi * X) * np.sin(np.pi * Y) * np.exp(2.0 * t_target)
        assert _relative_l2(u, u_exact) < 0.20

    def test_exponential_growth_longer(self, sim):
        """After more time, u still matches exp(r*t)*IC."""
        t_target = 0.2
        sim.run_until(t_target, dt=5e-4)
        u = sim.get_field("u")
        x, y = sim.coordinates()
        X, Y = np.meshgrid(x, y, indexing="ij")
        u_exact = np.sin(np.pi * X) * np.sin(np.pi * Y) * np.exp(2.0 * t_target)
        assert _relative_l2(u, u_exact) < 0.20


# ===========================================================================
# 3. Source term only (no spatial derivatives)
# ===========================================================================

class TestSourceTermOnly:
    """
    RHS = sin(pi*x)*sin(pi*y)  (constant source, independent of u).
    Starting from IC=0, after time T the field should equal
    T * sin(pi*x)*sin(pi*y).
    """

    @pytest.fixture()
    def sim(self):
        def source_rhs(fields, operators, x, y, t, params):
            return np.sin(np.pi * x) * np.sin(np.pi * y)

        s = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=31, ny=31)
        s.add_field("u", rhs=source_rhs, params={})
        s.set_initial_condition("u", lambda x, y: np.zeros_like(x))
        s.set_bc("u", "all", "neumann", flux=0.0)
        return s

    def test_linear_accumulation(self, sim):
        """After time T, u should equal T * source_pattern."""
        T = 0.1
        sim.run_until(T, dt=5e-4)
        u = sim.get_field("u")
        x, y = sim.coordinates()
        X, Y = np.meshgrid(x, y, indexing="ij")
        u_exact = T * np.sin(np.pi * X) * np.sin(np.pi * Y)
        assert _relative_l2(u, u_exact) < 0.20, (
            f"Relative L2 error {_relative_l2(u, u_exact):.4e} exceeds 20%"
        )

    def test_field_grows_from_zero(self, sim):
        """Field should increase away from zero with a positive source."""
        sim.run_until(0.05, dt=5e-4)
        u = sim.get_field("u")
        assert np.max(np.abs(u)) > 1e-4, "Field should be nonzero after sourcing"


# ===========================================================================
# 4. Nonlinear saturation (logistic, no diffusion)
# ===========================================================================

class TestNonlinearSaturation:
    """
    RHS = u*(1-u) (logistic growth, no diffusion).
    Starting from u0=0.1 uniform, the field should approach 1.0
    monotonically.
    """

    @pytest.fixture()
    def sim(self):
        def logistic_rhs(fields, operators, x, y, t, params):
            u = fields["u"]
            return u * (1.0 - u)

        s = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=21, ny=21)
        s.add_field("u", rhs=logistic_rhs, params={})
        s.set_initial_condition("u", lambda x, y: 0.1 * np.ones_like(x))
        s.set_bc("u", "all", "neumann", flux=0.0)
        return s

    def test_u_increases(self, sim):
        """u should increase from its initial value of 0.1."""
        u0 = sim.get_field("u").copy()
        sim.run_until(0.5, dt=5e-3)
        u1 = sim.get_field("u")
        assert np.mean(u1) > np.mean(u0), "Mean of u should increase under logistic growth"

    def test_u_bounded_by_one(self, sim):
        """u should not exceed 1.0 (the carrying capacity)."""
        sim.run_until(3.0, dt=5e-3)
        u = sim.get_field("u")
        assert np.all(u <= 1.0 + 1e-6), (
            f"Max u = {np.max(u):.6f} exceeds carrying capacity 1.0"
        )

    def test_approaches_steady_state(self, sim):
        """After long integration, u should be close to 1.0."""
        sim.run_until(8.0, dt=5e-3)
        u = sim.get_field("u")
        assert np.allclose(u, 1.0, atol=0.05), (
            f"u not converged to 1.0: mean={np.mean(u):.6f}, max deviation={np.max(np.abs(u - 1.0)):.6e}"
        )

    def test_matches_ode_solution(self, sim):
        """Compare to the exact ODE solution u(t) = u0*exp(t) / (1 + u0*(exp(t)-1))."""
        t_target = 2.0
        sim.run_until(t_target, dt=5e-3)
        u = sim.get_field("u")
        u0 = 0.1
        u_exact = u0 * np.exp(t_target) / (1.0 + u0 * (np.exp(t_target) - 1.0))
        # Since IC is uniform, all grid points should match the scalar ODE solution
        assert np.allclose(u, u_exact, atol=0.05), (
            f"u deviates from ODE solution: max error = {np.max(np.abs(u - u_exact)):.6e}"
        )


# ===========================================================================
# 5. Parameter change multiple times
# ===========================================================================

class TestParameterChangeMultipleTimes:
    """
    Change a parameter 3 times during simulation.  Each phase should use
    the correct parameter value.  We use pure exponential growth
    RHS = r*u so the analytical solution per phase is known.
    """

    def test_three_phase_parameter_change(self):
        """Change r three times; final u should reflect all three growth rates."""
        def growth_rhs(fields, operators, x, y, t, params):
            u = fields["u"]
            return params["r"] * u

        sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=11, ny=11)
        sim.add_field("u", rhs=growth_rhs, params={"r": 1.0})
        sim.set_initial_condition("u", lambda x, y: np.ones_like(x))
        sim.set_bc("u", "all", "neumann", flux=0.0)

        dt = 5e-4
        phase_duration = 0.05

        # Phase 1: r=1.0
        sim.run_until(phase_duration, dt=dt)
        u1 = sim.get_field("u").copy()
        expected1 = np.exp(1.0 * phase_duration)
        assert np.allclose(u1, expected1, rtol=0.20), (
            f"Phase 1: expected {expected1:.6f}, got mean {np.mean(u1):.6f}"
        )

        # Phase 2: r=2.0
        sim.set_parameter("r", 2.0)
        sim.run_until(2 * phase_duration, dt=dt)
        u2 = sim.get_field("u").copy()
        expected2 = expected1 * np.exp(2.0 * phase_duration)
        assert np.allclose(u2, expected2, rtol=0.20), (
            f"Phase 2: expected {expected2:.6f}, got mean {np.mean(u2):.6f}"
        )

        # Phase 3: r=0.5
        sim.set_parameter("r", 0.5)
        sim.run_until(3 * phase_duration, dt=dt)
        u3 = sim.get_field("u").copy()
        expected3 = expected2 * np.exp(0.5 * phase_duration)
        assert np.allclose(u3, expected3, rtol=0.20), (
            f"Phase 3: expected {expected3:.6f}, got mean {np.mean(u3):.6f}"
        )

    def test_parameter_change_takes_effect_immediately(self):
        """After set_parameter, the very next step should use the new value."""
        def growth_rhs(fields, operators, x, y, t, params):
            u = fields["u"]
            return params["r"] * u

        sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=11, ny=11)
        sim.add_field("u", rhs=growth_rhs, params={"r": 0.0})
        sim.set_initial_condition("u", lambda x, y: np.ones_like(x))
        sim.set_bc("u", "all", "neumann", flux=0.0)

        # With r=0, u should stay at 1.0
        sim.run_until(0.01, dt=5e-4)
        u_before = sim.get_field("u").copy()
        assert np.allclose(u_before, 1.0, atol=0.01), "r=0 should keep u constant"

        # Now set r=10 and step; u should grow noticeably
        sim.set_parameter("r", 10.0)
        sim.run_until(0.02, dt=5e-4)
        u_after = sim.get_field("u")
        assert np.mean(u_after) > 1.05, (
            f"After setting r=10, u should grow; got mean {np.mean(u_after):.6f}"
        )


# ===========================================================================
# 6. Coupled fields conservation
# ===========================================================================

class TestCoupledFieldsConservation:
    """
    Two coupled fields with mass-conserving exchange:
        du/dt = -k*u + k*v
        dv/dt =  k*u - k*v
    Total (u + v) should be conserved.  Each field should relax
    toward the average of the initial conditions.
    """

    @pytest.fixture()
    def sim(self):
        k_val = 5.0

        def rhs_u(fields, operators, x, y, t, params):
            u = fields["u"]
            v = fields["v"]
            return -params["k"] * u + params["k"] * v

        def rhs_v(fields, operators, x, y, t, params):
            u = fields["u"]
            v = fields["v"]
            return params["k"] * u - params["k"] * v

        s = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=31, ny=31)
        s.add_field("u", rhs=rhs_u, params={"k": k_val})
        s.add_field("v", rhs=rhs_v, params={"k": k_val})
        s.set_initial_condition("u", lambda x, y: 2.0 * np.ones_like(x))
        s.set_initial_condition("v", lambda x, y: np.zeros_like(x))
        s.set_bc("u", "all", "neumann", flux=0.0)
        s.set_bc("v", "all", "neumann", flux=0.0)
        return s

    def _total_mass(self, sim):
        u = sim.get_field("u")
        v = sim.get_field("v")
        x, y = sim.coordinates()
        dx = x[1] - x[0]
        dy = y[1] - y[0]
        total = u + v
        _trapz = getattr(np, "trapezoid", getattr(np, "trapz", None))
        return _trapz(_trapz(total, dx=dx, axis=0), dx=dy)

    def test_total_mass_conserved(self, sim):
        """Total u+v integral should be conserved at several time points."""
        mass_initial = self._total_mass(sim)
        for t in [0.05, 0.1, 0.2]:
            sim.run_until(t, dt=5e-4)
            mass = self._total_mass(sim)
            rel_diff = abs(mass - mass_initial) / abs(mass_initial)
            assert rel_diff < 0.05, (
                f"Mass not conserved at t={t}: initial={mass_initial:.8e}, "
                f"current={mass:.8e}, rel_diff={rel_diff:.4e}"
            )

    def test_fields_equalize(self, sim):
        """After long integration, u and v should both approach 1.0 (average of 2 and 0)."""
        sim.run_until(0.5, dt=5e-4)
        u = sim.get_field("u")
        v = sim.get_field("v")
        assert np.allclose(u, 1.0, atol=0.01), (
            f"u should approach 1.0; got mean {np.mean(u):.6f}"
        )
        assert np.allclose(v, 1.0, atol=0.01), (
            f"v should approach 1.0; got mean {np.mean(v):.6f}"
        )


# ===========================================================================
# 7. Coordinate-dependent RHS
# ===========================================================================

class TestCoordinateDependentRHS:
    """
    RHS that explicitly depends on spatial coordinates:
        du/dt = D * laplacian(u) + sin(pi*x) * cos(pi*y)
    This should run without error and produce a non-trivial steady state.
    """

    @pytest.fixture()
    def sim(self):
        def coord_rhs(fields, operators, x, y, t, params):
            lap_u = operators["laplacian"]
            return params["D"] * lap_u + np.sin(np.pi * x) * np.cos(np.pi * y)

        s = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=31, ny=31)
        s.add_field("u", rhs=coord_rhs, params={"D": 1.0})
        s.set_initial_condition("u", lambda x, y: np.zeros_like(x))
        s.set_bc("u", "all", "dirichlet", value=0.0)
        return s

    def test_runs_without_error(self, sim):
        """Coordinate-dependent RHS should run without exceptions."""
        sim.run_until(0.05, dt=2e-4)
        u = sim.get_field("u")
        assert np.all(np.isfinite(u)), "Solution contains NaN/Inf"

    def test_nontrivial_solution(self, sim):
        """The source term should drive u away from zero."""
        sim.run_until(0.05, dt=2e-4)
        u = sim.get_field("u")
        assert np.max(np.abs(u)) > 1e-3, (
            "Field should be nonzero with a coordinate-dependent source"
        )

    def test_approaches_steady_state(self, sim):
        """Solution should converge to a steady state (change between late snapshots is small)."""
        sim.run_until(0.2, dt=2e-4)
        u_late1 = sim.get_field("u").copy()
        sim.run_until(0.5, dt=2e-4)
        u_late2 = sim.get_field("u")
        change = np.max(np.abs(u_late2 - u_late1))
        assert change < 0.01, (
            f"Solution not converging to steady state; max change = {change:.4e}"
        )


# ===========================================================================
# 8. Time-dependent RHS
# ===========================================================================

class TestTimeDependentRHS:
    """
    RHS that depends on time:
        du/dt = D * laplacian(u) + A * sin(omega * t)
    The simulation should run without errors and the forcing should
    produce oscillatory behavior.
    """

    @pytest.fixture()
    def sim(self):
        A_val = 1.0
        omega_val = 2.0 * np.pi

        def time_rhs(fields, operators, x, y, t, params):
            lap_u = operators["laplacian"]
            return params["D"] * lap_u + params["A"] * np.sin(params["omega"] * t)

        s = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=21, ny=21)
        s.add_field("u", rhs=time_rhs, params={"D": 0.1, "A": A_val, "omega": omega_val})
        s.set_initial_condition("u", lambda x, y: np.zeros_like(x))
        s.set_bc("u", "all", "neumann", flux=0.0)
        return s

    def test_runs_without_error(self, sim):
        """Time-dependent RHS should run for multiple periods without error."""
        sim.run_until(1.0, dt=5e-3)
        u = sim.get_field("u")
        assert np.all(np.isfinite(u)), "Solution contains NaN/Inf"

    def test_solution_oscillates(self, sim):
        """The mean of u should oscillate (not be monotonically increasing)."""
        means = []
        for t in np.linspace(0.1, 1.5, 10):
            sim.run_until(t, dt=5e-3)
            means.append(np.mean(sim.get_field("u")))

        # Check that the mean changes sign of its increments at least once
        diffs = np.diff(means)
        sign_changes = np.sum(np.diff(np.sign(diffs)) != 0)
        assert sign_changes >= 1, (
            f"Expected oscillatory behavior but found {sign_changes} direction changes"
        )

    def test_bounded_solution(self, sim):
        """Solution should remain bounded for moderate integration time."""
        sim.run_until(1.0, dt=5e-3)
        u = sim.get_field("u")
        assert np.all(np.isfinite(u)), "Solution contains NaN/Inf"
        assert np.max(np.abs(u)) < 100.0, (
            f"Solution magnitude {np.max(np.abs(u)):.2f} unreasonably large"
        )
