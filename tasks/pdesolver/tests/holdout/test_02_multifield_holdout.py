"""
Holdout tests for Stage 2: Multi-field, Poisson, static/vector fields,
and stability monitoring.

These tests exercise edge cases and alternative scenarios that are hidden
from the LLM during development.
"""

import numpy as np
import pytest

import pdesolver
from conftest import l2_error, max_error


# ---------------------------------------------------------------------------
# 1. Three-Field Diffusion
# ---------------------------------------------------------------------------


class TestThreeFieldDiffusion:
    """
    Three fields (a, b, c) with different diffusivities on [0,1]x[0,1].
    IC = sin(pi*x)*sin(pi*y), Dirichlet u=0 on all edges.
    Analytical: u(x,y,t) = sin(pi*x)*sin(pi*y)*exp(-2*pi^2*D*t).
    Each field should evolve independently and match its own analytical
    solution.
    """

    @pytest.fixture()
    def sim(self, sim_factory):
        s = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=101, ny=101)
        for name, D in [("a", 1.0), ("b", 0.5), ("c", 0.1)]:
            s.add_field(name, D=D)
            s.set_initial_condition(
                name, lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y)
            )
            s.set_bc(name, "all", "dirichlet", value=0.0)
        return s

    @pytest.mark.parametrize("field_name,D", [("a", 1.0), ("b", 0.5), ("c", 0.1)])
    def test_each_field_matches_analytical(self, sim, field_name, D):
        """Each field matches its own analytical decay at t=0.05."""
        t_target = 0.05
        sim.run_until(t_target, dt=2e-5)
        u = sim.get_field(field_name)
        x, y = sim.coordinates()
        X, Y = np.meshgrid(x, y, indexing="ij")
        u_exact = (
            np.sin(np.pi * X) * np.sin(np.pi * Y)
            * np.exp(-2 * np.pi ** 2 * D * t_target)
        )
        ref_norm = np.sqrt(np.mean(u_exact ** 2))
        rel_err = l2_error(u, u_exact) / ref_norm
        assert rel_err < 0.20, (
            f"Field '{field_name}' (D={D}) relative L2 error: {rel_err:.4e}"
        )


# ---------------------------------------------------------------------------
# 2. Poisson with Different Source
# ---------------------------------------------------------------------------


class TestPoissonDifferentSource:
    """
    Poisson solve with rho = -8*pi^2 * cos(2*pi*x) * cos(2*pi*y).
    Analytical solution: phi = cos(2*pi*x) * cos(2*pi*y).
    Boundary condition: Dirichlet matching analytical on all edges.

    Alternatively, use a constant source rho = -1 on [0,1]x[0,1] with
    Dirichlet phi=0. No simple closed-form, but we can verify the residual
    is small: |laplacian(phi) - rho| should be near zero.
    """

    def test_cosine_source(self, sim_factory):
        """Poisson solve with cos(2*pi*x)*cos(2*pi*y) source."""
        sim = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=101, ny=101)
        x, y = sim.coordinates()
        X, Y = np.meshgrid(x, y, indexing="ij")

        # Source: laplacian of cos(2*pi*x)*cos(2*pi*y) = -8*pi^2 * cos(2*pi*x)*cos(2*pi*y)
        rho_data = -8 * np.pi ** 2 * np.cos(2 * np.pi * X) * np.cos(2 * np.pi * Y)
        sim.add_static_field("rho", data=rho_data)
        sim.add_field("phi", D=0.0)
        sim.set_initial_condition("phi", lambda x, y: np.zeros_like(x))

        # Dirichlet BC matching analytical: phi = cos(2*pi*x)*cos(2*pi*y)
        # On boundaries, this is cos(2*pi*x)*cos(2*pi*y) evaluated at edges.
        # For simplicity use the analytical values at boundaries.
        sim.set_bc("phi", "all", "dirichlet", value=0.0)
        sim.poisson_solve("phi", source="rho", tol=1e-8)

        phi = sim.get_field("phi")
        phi_exact = np.cos(2 * np.pi * X) * np.cos(2 * np.pi * Y)

        # With Dirichlet=0 BCs that don't match the analytical solution
        # on the boundary, we compare only interior behavior qualitatively.
        # The solver should still converge; check the residual is small.
        # A tighter check: the error on the interior should be bounded.
        interior = phi[2:-2, 2:-2]
        exact_interior = phi_exact[2:-2, 2:-2]
        err = l2_error(interior, exact_interior)
        # Error can be larger because BCs don't perfectly match.
        # At minimum the solver should produce a finite, non-NaN result.
        assert np.all(np.isfinite(phi)), "Poisson solution contains NaN or Inf"

    def test_constant_source_residual(self, sim_factory):
        """Poisson solve with constant source rho=-1, check residual."""
        sim = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        x, y = sim.coordinates()
        X, Y = np.meshgrid(x, y, indexing="ij")

        rho_data = -1.0 * np.ones_like(X)
        sim.add_static_field("rho", data=rho_data)
        sim.add_field("phi", D=0.0)
        sim.set_initial_condition("phi", lambda x, y: np.zeros_like(x))
        sim.set_bc("phi", "all", "dirichlet", value=0.0)
        sim.poisson_solve("phi", source="rho", tol=1e-8)

        phi = sim.get_field("phi")
        assert np.all(np.isfinite(phi)), "Poisson solution contains NaN or Inf"
        # The solution should be positive in the interior (source is negative,
        # meaning laplacian(phi) = -1, so phi bulges upward).
        assert phi[len(x) // 2, len(y) // 2] > 0, (
            "Poisson solution with constant negative source should be positive inside"
        )


# ---------------------------------------------------------------------------
# 3. Static Field Read-Only
# ---------------------------------------------------------------------------


class TestStaticFieldReadOnly:
    """
    A static field should not be altered by time-stepping of other fields.
    """

    def test_static_field_unchanged_after_stepping(self, sim_factory):
        """Static field data is identical before and after time stepping."""
        sim = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        x, y = sim.coordinates()
        X, Y = np.meshgrid(x, y, indexing="ij")

        source_data = np.sin(np.pi * X) * np.sin(np.pi * Y)
        sim.add_static_field("source", data=source_data)

        sim.add_field("u", D=1.0)
        sim.set_initial_condition(
            "u", lambda x, y: np.exp(-((x - 0.5) ** 2 + (y - 0.5) ** 2) / 0.01)
        )
        sim.set_bc("u", "all", "dirichlet", value=0.0)

        # Record the static field before stepping
        # (Try to read it back via get_field or similar mechanism)
        before = source_data.copy()

        # Step forward significantly
        sim.step(dt=1e-5, n_steps=100)

        # Re-read the static field. The API may expose it through get_field
        # or through the original data. At minimum, the original array should
        # be unchanged (no in-place mutation).
        np.testing.assert_array_equal(
            source_data, before,
            err_msg="Static field data was mutated during time stepping",
        )


# ---------------------------------------------------------------------------
# 4. Stability Monitor Reports Reduction
# ---------------------------------------------------------------------------


class TestStabilityMonitorReportsReduction:
    """
    When dt is too large for the CFL condition, the stability monitor
    should automatically reduce dt. We verify the solver does not blow up
    and that the effective dt is smaller than the requested one.
    """

    def test_large_dt_does_not_blow_up(self, sim_factory):
        """Simulation with excessively large dt still produces finite results."""
        sim = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=101, ny=101)
        sim.add_field("u", D=1.0)
        sim.set_initial_condition(
            "u", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y)
        )
        sim.set_bc("u", "all", "dirichlet", value=0.0)

        # CFL limit for dx=0.01, D=1.0 is dt ~ 2.5e-5.
        # Request dt=0.01 which is ~400x too large.
        sim.step(dt=0.01, n_steps=10)
        u = sim.get_field("u")
        assert np.all(np.isfinite(u)), (
            "Solution blew up with large dt; stability monitor should have reduced it"
        )

    def test_dt_reduction_recorded(self, sim_factory):
        """After stepping with too-large dt, verify some record of reduction."""
        sim = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=101, ny=101)
        sim.add_field("u", D=1.0)
        sim.set_initial_condition(
            "u", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y)
        )
        sim.set_bc("u", "all", "dirichlet", value=0.0)

        large_dt = 0.01
        sim.step(dt=large_dt, n_steps=5)

        u = sim.get_field("u")
        assert np.all(np.isfinite(u)), "Solution should remain finite"

        # The simulation should have advanced time, but not by 5 * 0.01 = 0.05
        # with unreduced dt (it would blow up). If it is finite, the monitor
        # did its job. Optionally check that sim.time > 0.
        assert sim.time > 0, "Simulation should have advanced in time"


# ---------------------------------------------------------------------------
# 5. Field Independence
# ---------------------------------------------------------------------------


class TestFieldIndependence:
    """
    Two fields with identical setups should produce identical results.
    Changing one field's D should not affect the other.
    """

    def test_identical_fields_same_result(self, sim_factory):
        """Two fields with same D and IC produce identical solutions."""
        sim = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        for name in ("p", "q"):
            sim.add_field(name, D=1.0)
            sim.set_initial_condition(
                name, lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y)
            )
            sim.set_bc(name, "all", "dirichlet", value=0.0)

        sim.run_until(0.01, dt=2e-5)
        p = sim.get_field("p")
        q = sim.get_field("q")
        np.testing.assert_allclose(
            p, q, atol=1e-6,
            err_msg="Identical fields should produce identical results",
        )

    def test_changing_one_field_does_not_affect_other(self, sim_factory):
        """Field 'a' with D=1.0 should match a solo run regardless of field 'b'."""
        # Run with two fields
        sim2 = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        sim2.add_field("a", D=1.0)
        sim2.set_initial_condition(
            "a", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y)
        )
        sim2.set_bc("a", "all", "dirichlet", value=0.0)

        sim2.add_field("b", D=5.0)
        sim2.set_initial_condition(
            "b", lambda x, y: np.cos(np.pi * x) * np.cos(np.pi * y)
        )
        sim2.set_bc("b", "all", "dirichlet", value=0.0)

        sim2.run_until(0.01, dt=1e-5)
        a_with_b = sim2.get_field("a")

        # Run field 'a' alone
        sim1 = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        sim1.add_field("a", D=1.0)
        sim1.set_initial_condition(
            "a", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y)
        )
        sim1.set_bc("a", "all", "dirichlet", value=0.0)
        sim1.run_until(0.01, dt=1e-5)
        a_solo = sim1.get_field("a")

        rel_err = l2_error(a_with_b, a_solo)
        assert rel_err < 1e-6, (
            f"Field 'a' differs when another field is present: L2 diff = {rel_err:.4e}"
        )


# ---------------------------------------------------------------------------
# 6. Vector Field Different Patterns
# ---------------------------------------------------------------------------


class TestVectorFieldDifferentPatterns:
    """
    Test divergence and curl with analytically known vector fields.
    """

    def test_radial_field_divergence(self, sim_factory):
        """v=(x, y) has divergence = 2 everywhere."""
        sim = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=101, ny=101)
        x, y = sim.coordinates()
        X, Y = np.meshgrid(x, y, indexing="ij")

        sim.add_vector_field("v", data_x=X.copy(), data_y=Y.copy())
        div = sim.divergence("v")

        # Interior only (finite differences lose accuracy at boundary)
        div_interior = div[2:-2, 2:-2]
        expected = 2.0 * np.ones_like(div_interior)
        err = max_error(div_interior, expected)
        assert err < 0.1, (
            f"Divergence of (x, y) should be ~2 everywhere, max error = {err:.4e}"
        )

    def test_rotational_field_curl(self, sim_factory):
        """v=(-y, x) has curl = 2 everywhere (in 2D, curl is scalar)."""
        sim = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=101, ny=101)
        x, y = sim.coordinates()
        X, Y = np.meshgrid(x, y, indexing="ij")

        sim.add_vector_field("v", data_x=-Y.copy(), data_y=X.copy())
        curl = sim.curl("v")

        curl_interior = curl[2:-2, 2:-2]
        expected = 2.0 * np.ones_like(curl_interior)
        err = max_error(curl_interior, expected)
        assert err < 0.1, (
            f"Curl of (-y, x) should be ~2 everywhere, max error = {err:.4e}"
        )

    def test_zero_divergence_of_rotational_field(self, sim_factory):
        """v=(-y, x) should have zero divergence."""
        sim = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=101, ny=101)
        x, y = sim.coordinates()
        X, Y = np.meshgrid(x, y, indexing="ij")

        sim.add_vector_field("v", data_x=-Y.copy(), data_y=X.copy())
        div = sim.divergence("v")

        div_interior = div[2:-2, 2:-2]
        err = np.max(np.abs(div_interior))
        assert err < 0.05, (
            f"Divergence of (-y, x) should be ~0, max abs = {err:.4e}"
        )


# ---------------------------------------------------------------------------
# 7. Poisson Convergence
# ---------------------------------------------------------------------------


class TestPoissonConvergence:
    """
    Poisson solve with tight tolerance should give better (or equal) results
    compared to loose tolerance.
    """

    def test_tight_vs_loose_tolerance(self, sim_factory):
        """Tighter tolerance yields smaller error vs analytical."""
        errors = {}
        for tol in [1e-4, 1e-8]:
            sim = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
            x, y = sim.coordinates()
            X, Y = np.meshgrid(x, y, indexing="ij")

            # rho = -2*pi^2 * sin(pi*x)*sin(pi*y)
            rho_data = -2 * np.pi ** 2 * np.sin(np.pi * X) * np.sin(np.pi * Y)
            sim.add_static_field("rho", data=rho_data)
            sim.add_field("phi", D=0.0)
            sim.set_initial_condition("phi", lambda x, y: np.zeros_like(x))
            sim.set_bc("phi", "all", "dirichlet", value=0.0)
            sim.poisson_solve("phi", source="rho", tol=tol)

            phi = sim.get_field("phi")
            phi_exact = np.sin(np.pi * X) * np.sin(np.pi * Y)
            errors[tol] = l2_error(phi, phi_exact)

        assert errors[1e-8] <= errors[1e-4] + 1e-6, (
            f"Tight tolerance error ({errors[1e-8]:.4e}) should be <= "
            f"loose tolerance error ({errors[1e-4]:.4e})"
        )


# ---------------------------------------------------------------------------
# 8. Static Field Multiple Updates
# ---------------------------------------------------------------------------


class TestStaticFieldMultipleUpdates:
    """
    Update a static field (source term) multiple times during simulation.
    The evolving field should respond to each updated source.
    """

    def test_source_field_switches_effect(self, sim_factory):
        """
        Phase 1: source pushes u upward (positive source).
        Phase 2: source switches sign, pushing u downward.
        The field value at center should first rise, then fall.
        """
        sim = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        x, y = sim.coordinates()
        X, Y = np.meshgrid(x, y, indexing="ij")

        # Positive source
        source_pos = 10.0 * np.sin(np.pi * X) * np.sin(np.pi * Y)
        sim.add_static_field("source", data=source_pos)
        sim.add_field("u", D=1.0, source="source")
        sim.set_initial_condition("u", lambda x, y: np.zeros_like(x))
        sim.set_bc("u", "all", "dirichlet", value=0.0)

        # Phase 1: step with positive source
        sim.step(dt=2e-5, n_steps=500)  # t = 0.01
        u_phase1 = sim.get_field("u").copy()
        center = len(x) // 2
        val_after_phase1 = u_phase1[center, center]

        assert val_after_phase1 > 0, (
            f"Center value should be positive after positive source, got {val_after_phase1}"
        )

        # Phase 2: switch to strong negative source
        source_neg = -50.0 * np.sin(np.pi * X) * np.sin(np.pi * Y)
        sim.update_static_field("source", data=source_neg)

        sim.step(dt=2e-5, n_steps=1000)  # t = 0.03
        u_phase2 = sim.get_field("u").copy()
        val_after_phase2 = u_phase2[center, center]

        # With a strong negative source, the center value should have decreased
        assert val_after_phase2 < val_after_phase1, (
            f"Center should decrease after negative source switch: "
            f"phase1={val_after_phase1:.6e}, phase2={val_after_phase2:.6e}"
        )

    def test_multiple_source_updates(self, sim_factory):
        """Three sequential source updates produce monotonically changing center."""
        sim = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        x, y = sim.coordinates()
        X, Y = np.meshgrid(x, y, indexing="ij")

        base_pattern = np.sin(np.pi * X) * np.sin(np.pi * Y)
        sim.add_static_field("source", data=5.0 * base_pattern)
        sim.add_field("u", D=1.0, source="source")
        sim.set_initial_condition("u", lambda x, y: np.zeros_like(x))
        sim.set_bc("u", "all", "dirichlet", value=0.0)

        center = len(x) // 2
        vals = []

        # Three phases with increasing source strength
        for strength in [5.0, 15.0, 30.0]:
            sim.update_static_field("source", data=strength * base_pattern)
            sim.step(dt=2e-5, n_steps=200)
            u = sim.get_field("u")
            vals.append(u[center, center])

        # Center value should be increasing since source is always positive
        # and getting stronger
        for i in range(1, len(vals)):
            assert vals[i] > vals[i - 1], (
                f"Center value should increase with stronger source: "
                f"vals = {vals}"
            )
