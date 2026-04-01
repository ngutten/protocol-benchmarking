"""
Training tests for Stage 1: Diffusion equation solver.

Tests cover the basic heat/diffusion equation (du/dt = D * laplacian(u))
with various boundary conditions, conservation properties, and grid
convergence.
"""

import numpy as np
import pytest

import pdesolver
from conftest import l2_error, load_ref, max_error


# ---------------------------------------------------------------------------
# 1. API Availability
# ---------------------------------------------------------------------------


class TestAPIAvailability:
    """Verify that the public API surface exists and does not raise on basic use."""

    def test_import(self):
        """pdesolver can be imported."""
        import pdesolver  # noqa: F811

    def test_create_simulation(self):
        """Simulation can be instantiated with domain and grid parameters."""
        sim = pdesolver.Simulation(
            x_range=(0, 1), y_range=(0, 1), nx=11, ny=11,
        )
        assert sim is not None

    def test_add_field(self):
        """A diffusion field can be added."""
        sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=11, ny=11)
        sim.add_field("u", D=1.0)

    def test_set_initial_condition(self):
        """An initial condition can be set via a callable."""
        sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=11, ny=11)
        sim.add_field("u", D=1.0)
        sim.set_initial_condition("u", lambda x, y: np.zeros_like(x))

    def test_set_bc_dirichlet(self):
        """Dirichlet boundary condition can be applied."""
        sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=11, ny=11)
        sim.add_field("u", D=1.0)
        sim.set_bc("u", "all", "dirichlet", value=0.0)

    def test_set_bc_neumann(self):
        """Neumann boundary condition can be applied."""
        sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=11, ny=11)
        sim.add_field("u", D=1.0)
        sim.set_bc("u", "all", "neumann", flux=0.0)

    def test_set_bc_robin(self):
        """Robin boundary condition can be applied."""
        sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=11, ny=11)
        sim.add_field("u", D=1.0)
        sim.set_bc("u", "all", "robin", a=1.0, b=0.5, g=0.0)

    def test_set_bc_periodic(self):
        """Periodic boundary condition can be applied."""
        sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=11, ny=11)
        sim.add_field("u", D=1.0)
        sim.set_bc("u", "all", "periodic")

    def test_step(self):
        """A single time step executes without error."""
        sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=11, ny=11)
        sim.add_field("u", D=1.0)
        sim.set_initial_condition("u", lambda x, y: np.zeros_like(x))
        sim.set_bc("u", "all", "dirichlet", value=0.0)
        sim.step(dt=0.001)

    def test_step_multiple(self):
        """Multiple steps via n_steps parameter."""
        sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=11, ny=11)
        sim.add_field("u", D=1.0)
        sim.set_initial_condition("u", lambda x, y: np.zeros_like(x))
        sim.set_bc("u", "all", "dirichlet", value=0.0)
        sim.step(dt=0.001, n_steps=10)

    def test_run_until(self):
        """run_until advances to the target time."""
        sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=11, ny=11)
        sim.add_field("u", D=1.0)
        sim.set_initial_condition("u", lambda x, y: np.zeros_like(x))
        sim.set_bc("u", "all", "dirichlet", value=0.0)
        sim.run_until(0.01, dt=0.001)
        assert sim.time == pytest.approx(0.01, abs=1e-6)

    def test_get_field(self):
        """get_field returns a 2D numpy array."""
        sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=11, ny=11)
        sim.add_field("u", D=1.0)
        sim.set_initial_condition("u", lambda x, y: np.ones_like(x))
        sim.set_bc("u", "all", "dirichlet", value=0.0)
        u = sim.get_field("u")
        assert isinstance(u, np.ndarray)
        assert u.ndim == 2

    def test_coordinates(self):
        """coordinates() returns 2D meshgrid arrays."""
        sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=11, ny=11)
        x, y = sim.coordinates()
        assert isinstance(x, np.ndarray)
        assert isinstance(y, np.ndarray)
        assert x.ndim == 1
        assert y.ndim == 1
        assert len(x) == 11
        assert len(y) == 11

    def test_time_starts_at_zero(self):
        """Simulation time starts at zero."""
        sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=11, ny=11)
        assert sim.time == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 2. Gaussian Blob Diffusion  (REF-1.1)
# ---------------------------------------------------------------------------


class TestGaussianBlobDiffusion:
    """
    A Gaussian blob centred at (5, 5) diffuses on [0,10]x[0,10] with
    Dirichlet u=0 boundaries and D=1.0.
    """

    @pytest.fixture(scope="class")
    def snapshots(self):
        """Run one simulation to t=0.5 and capture snapshots along the way."""
        s = pdesolver.Simulation(x_range=(0, 10), y_range=(0, 10), nx=101, ny=101)
        s.add_field("u", D=1.0)
        s.set_initial_condition(
            "u", lambda x, y: np.exp(-((x - 5) ** 2 + (y - 5) ** 2) / 0.5)
        )
        s.set_bc("u", "all", "dirichlet", value=0.0)

        results = {}
        for t in [0.1, 0.3, 0.5]:
            s.run_until(t, dt=0.001)
            results[t] = s.get_field("u").copy()
        return results

    @pytest.fixture(scope="class")
    def ref(self):
        return load_ref("ref_1_1")

    @pytest.mark.parametrize("t_target,key", [
        (0.1, "u_t0.1"),
        (0.3, "u_t0.3"),
        (0.5, "u_t0.5"),
    ])
    def test_snapshot(self, snapshots, ref, t_target, key):
        """Solution at t={t_target} matches reference within 15% relative L2."""
        u = snapshots[t_target]
        u_ref = ref[key]
        ref_norm = np.sqrt(np.mean(u_ref ** 2))
        rel_err = l2_error(u, u_ref) / ref_norm
        assert rel_err < 0.15, (
            f"Relative L2 error at t={t_target}: {rel_err:.4e} (limit 15%)"
        )


# ---------------------------------------------------------------------------
# 3. Steady-State Laplace  (REF-1.2)
# ---------------------------------------------------------------------------


class TestSteadyStateLaplace:
    """
    Laplace equation on [0,1]x[0,1]: IC=0, top edge u=1, other edges u=0.
    Runs until convergence.
    """

    @pytest.fixture(scope="class")
    def snapshots(self):
        """Run one simulation to t=5.0 and capture snapshots along the way."""
        s = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=101, ny=101)
        s.add_field("u", D=1.0)
        s.set_initial_condition("u", lambda x, y: np.zeros_like(x))
        s.set_bc("u", "top", "dirichlet", value=1.0)
        s.set_bc("u", "bottom", "dirichlet", value=0.0)
        s.set_bc("u", "left", "dirichlet", value=0.0)
        s.set_bc("u", "right", "dirichlet", value=0.0)

        results = {}
        for t in [0.5, 1.0, 5.0]:
            s.run_until(t, dt=2e-5)
            results[t] = s.get_field("u").copy()
        return results

    @pytest.fixture(scope="class")
    def ref(self):
        return load_ref("ref_1_2")

    @pytest.mark.parametrize("t_target,key", [
        (0.5, "u_t0.5"),
        (1.0, "u_t1.0"),
    ])
    def test_transient_snapshot(self, snapshots, ref, t_target, key):
        """Transient snapshots match reference within 15% relative L2."""
        u = snapshots[t_target]
        u_ref = ref[key]
        ref_norm = np.sqrt(np.mean(u_ref ** 2))
        rel_err = l2_error(u, u_ref) / ref_norm
        assert rel_err < 0.15, (
            f"Relative L2 error at t={t_target}: {rel_err:.4e}"
        )

    def test_converged_solution(self, snapshots, ref):
        """Converged solution matches reference within 15%."""
        u = snapshots[5.0]
        u_ref = ref["u_converged"]
        ref_norm = np.sqrt(np.mean(u_ref ** 2))
        rel_err = l2_error(u, u_ref) / ref_norm
        assert rel_err < 0.15, (
            f"Relative L2 error for converged solution: {rel_err:.4e}"
        )

    def test_matches_analytical(self, snapshots, ref):
        """Converged solution matches analytical series solution within 20%."""
        u = snapshots[5.0]
        u_analytical = ref["u_analytical"]
        ref_norm = np.sqrt(np.mean(u_analytical ** 2))
        rel_err = l2_error(u, u_analytical) / ref_norm
        assert rel_err < 0.20, (
            f"Relative L2 error vs analytical: {rel_err:.4e}"
        )


# ---------------------------------------------------------------------------
# 4. Robin Cooling  (REF-1.3)
# ---------------------------------------------------------------------------


class TestRobinCooling:
    """
    Uniform IC=1 cools via Robin BC (a=1, b=0.5, g=0) on [0,1]x[0,1].
    """

    @pytest.fixture(scope="class")
    def snapshots(self):
        """Run one simulation to t=0.1 and capture snapshots along the way."""
        s = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=101, ny=101)
        s.add_field("u", D=1.0)
        s.set_initial_condition("u", lambda x, y: np.ones_like(x))
        s.set_bc("u", "all", "robin", a=1.0, b=0.5, g=0.0)

        results = {}
        for t in [0.01, 0.05, 0.1]:
            s.run_until(t, dt=2e-5)
            results[t] = s.get_field("u").copy()
        return results

    @pytest.fixture(scope="class")
    def ref(self):
        return load_ref("ref_1_3")

    @pytest.mark.parametrize("t_target,key", [
        (0.01, "u_t0.01"),
        (0.05, "u_t0.05"),
        (0.1, "u_t0.1"),
    ])
    def test_snapshot(self, snapshots, ref, t_target, key):
        """Robin cooling snapshot at t={t_target} matches reference."""
        u = snapshots[t_target]
        u_ref = ref[key]
        ref_norm = np.sqrt(np.mean(u_ref ** 2))
        if ref_norm < 0.01:
            # Absolute comparison when reference is near zero
            assert l2_error(u, u_ref) < 0.01
        else:
            rel_err = l2_error(u, u_ref) / ref_norm
            assert rel_err < 0.15, (
                f"Relative L2 error at t={t_target}: {rel_err:.4e}"
            )


# ---------------------------------------------------------------------------
# 5. Periodic Sinusoidal  (REF-1.4)
# ---------------------------------------------------------------------------


class TestPeriodicSinusoidal:
    """
    IC = sin(x) + 0.5*cos(2y) on [0, 2pi]x[0, 2pi] with periodic BCs
    and D=0.1. Analytical solution is known because each Fourier mode
    decays independently.
    """

    @pytest.fixture(scope="class")
    def snapshots(self):
        """Run one simulation to t=2.0 and capture snapshots along the way."""
        L = 2 * np.pi
        s = pdesolver.Simulation(x_range=(0, L), y_range=(0, L), nx=101, ny=101)
        s.add_field("u", D=0.1)
        s.set_initial_condition(
            "u", lambda x, y: np.sin(x) + 0.5 * np.cos(2 * y)
        )
        s.set_bc("u", "all", "periodic")

        results = {}
        for t in [0.5, 1.0, 2.0]:
            s.run_until(t, dt=0.003)
            results[t] = s.get_field("u").copy()
        return results

    @pytest.fixture(scope="class")
    def ref(self):
        return load_ref("ref_1_4")

    @pytest.mark.parametrize("t_target,ref_key,ana_key", [
        (0.5, "u_t0.5", "u_analytical_t0.5"),
        (1.0, "u_t1.0", "u_analytical_t1.0"),
        (2.0, "u_t2.0", "u_analytical_t2.0"),
    ])
    def test_snapshot_vs_reference(self, snapshots, ref, t_target, ref_key, ana_key):
        """Periodic solution matches reference at t={t_target}."""
        u = snapshots[t_target]
        u_ref = ref[ref_key]
        ref_norm = np.sqrt(np.mean(u_ref ** 2))
        if ref_norm < 0.01:
            assert l2_error(u, u_ref) < 0.01
        else:
            rel_err = l2_error(u, u_ref) / ref_norm
            assert rel_err < 0.15, (
                f"Relative L2 error at t={t_target}: {rel_err:.4e}"
            )

    @pytest.mark.parametrize("t_target,ana_key", [
        (0.5, "u_analytical_t0.5"),
        (1.0, "u_analytical_t1.0"),
        (2.0, "u_analytical_t2.0"),
    ])
    def test_snapshot_vs_analytical(self, snapshots, ref, t_target, ana_key):
        """Periodic solution matches analytical at t={t_target}."""
        u = snapshots[t_target]
        u_ana = ref[ana_key]
        ref_norm = np.sqrt(np.mean(u_ana ** 2))
        if ref_norm < 0.01:
            assert l2_error(u, u_ana) < 0.01
        else:
            rel_err = l2_error(u, u_ana) / ref_norm
            assert rel_err < 0.20, (
                f"Relative L2 error vs analytical at t={t_target}: {rel_err:.4e}"
            )


# ---------------------------------------------------------------------------
# 6. Time-Dependent Dirichlet  (REF-1.5)
# ---------------------------------------------------------------------------


class TestTimeDependentDirichlet:
    """
    IC=0 on [0,1]x[0,1]. Left edge has g(y,t)=sin(2*pi*t), other edges u=0.
    """

    @pytest.fixture(scope="class")
    def snapshots(self):
        """Run one simulation to t=0.5 and capture snapshots along the way."""
        s = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=101, ny=101)
        s.add_field("u", D=1.0)
        s.set_initial_condition("u", lambda x, y: np.zeros_like(x))
        s.set_bc("u", "left", "dirichlet", value=lambda s, t: np.sin(2 * np.pi * t) * np.ones_like(s))
        s.set_bc("u", "right", "dirichlet", value=0.0)
        s.set_bc("u", "top", "dirichlet", value=0.0)
        s.set_bc("u", "bottom", "dirichlet", value=0.0)

        results = {}
        for t in [0.1, 0.25, 0.5]:
            s.run_until(t, dt=2e-5)
            results[t] = s.get_field("u").copy()
        return results

    @pytest.fixture(scope="class")
    def ref(self):
        return load_ref("ref_1_5")

    @pytest.mark.parametrize("t_target,key", [
        (0.1, "u_t0.1"),
        (0.25, "u_t0.25"),
        (0.5, "u_t0.5"),
    ])
    def test_snapshot(self, snapshots, ref, t_target, key):
        """Time-dependent Dirichlet solution matches reference."""
        u = snapshots[t_target]
        u_ref = ref[key]
        ref_norm = np.sqrt(np.mean(u_ref ** 2))
        if ref_norm < 0.01:
            assert l2_error(u, u_ref) < 0.01
        else:
            rel_err = l2_error(u, u_ref) / ref_norm
            assert rel_err < 0.15, (
                f"Relative L2 error at t={t_target}: {rel_err:.4e}"
            )

    @pytest.mark.parametrize("t_target,bnd_key", [
        (0.1, "left_boundary_t0.1"),
        (0.25, "left_boundary_t0.25"),
        (0.5, "left_boundary_t0.5"),
    ])
    def test_left_boundary_values(self, snapshots, ref, t_target, bnd_key):
        """Left boundary matches the prescribed time-dependent values."""
        u = snapshots[t_target]
        # Left boundary is the first row in ij convention: u[0, :]
        left_col = u[0, :]
        left_ref = ref[bnd_key]
        err = max_error(left_col, left_ref)
        assert err < 0.15, (
            f"Left boundary max error at t={t_target}: {err:.4e}"
        )


# ---------------------------------------------------------------------------
# 7. Neumann Conservation  (PROP-1.1)
# ---------------------------------------------------------------------------


class TestNeumannConservation:
    """
    With zero-flux (Neumann) BCs the total integral of u must be conserved.
    IC = sin(2*pi*x)*cos(pi*y) + 1.5 on [0,1]x[0,1], D=1.0.
    """

    @pytest.fixture(scope="class")
    def snapshots(self):
        """Run one simulation to t=0.1 and capture integral snapshots."""
        s = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=101, ny=101)
        s.add_field("u", D=1.0)
        s.set_initial_condition(
            "u",
            lambda x, y: np.sin(2 * np.pi * x) * np.cos(np.pi * y) + 1.5,
        )
        s.set_bc("u", "all", "neumann", flux=0.0)

        x, y = s.coordinates()
        dx = x[1] - x[0]
        dy = y[1] - y[0]

        def _integral(sim):
            u = sim.get_field("u")
            return np.trapezoid(np.trapezoid(u, dx=dx, axis=0), dx=dy)

        times = [0.0, 0.01, 0.05, 0.1]
        integrals = {}
        integrals[0.0] = _integral(s)
        for t in times[1:]:
            s.run_until(t, dt=2e-5)
            integrals[t] = _integral(s)
        return integrals

    @pytest.fixture(scope="class")
    def ref(self):
        return load_ref("prop_1_1")

    def test_integral_conserved(self, snapshots):
        """Total integral is conserved at t=0, 0.01, 0.05, 0.1."""
        times = [0.0, 0.01, 0.05, 0.1]
        initial_integral = snapshots[0.0]

        # All integrals should be close to the initial value
        for t in times:
            integral = snapshots[t]
            rel_diff = abs(integral - initial_integral) / abs(initial_integral)
            assert rel_diff < 0.01, (
                f"Integral not conserved at t={t}: "
                f"initial={initial_integral:.8e}, current={integral:.8e}, "
                f"relative diff={rel_diff:.4e}"
            )

    def test_integral_matches_reference(self, snapshots, ref):
        """Computed integrals match reference values."""
        times_keys = [
            (0.0, "integral_t0.0"),
            (0.01, "integral_t0.01"),
            (0.05, "integral_t0.05"),
            (0.1, "integral_t0.1"),
        ]
        for t, key in times_keys:
            integral = snapshots[t]
            ref_val = float(ref[key].flat[0])
            rel_diff = abs(integral - ref_val) / abs(ref_val)
            assert rel_diff < 0.15, (
                f"Integral mismatch at t={t}: "
                f"computed={integral:.8e}, reference={ref_val:.8e}"
            )


# ---------------------------------------------------------------------------
# 8. Energy Dissipation  (PROP-1.2)
# ---------------------------------------------------------------------------


class TestEnergyDissipation:
    """
    For the diffusion equation with Dirichlet BCs, the L2 energy
    integral(u^2 dA) must be strictly decreasing over time.
    Uses the same setup as the Gaussian blob (REF-1.1).
    """

    @pytest.fixture(scope="class")
    def snapshots(self):
        """Run one simulation to t=0.5 and capture energy at each snapshot."""
        s = pdesolver.Simulation(x_range=(0, 10), y_range=(0, 10), nx=101, ny=101)
        s.add_field("u", D=1.0)
        s.set_initial_condition(
            "u", lambda x, y: np.exp(-((x - 5) ** 2 + (y - 5) ** 2) / 0.5)
        )
        s.set_bc("u", "all", "dirichlet", value=0.0)

        x, y = s.coordinates()
        dx = x[1] - x[0]
        dy = y[1] - y[0]

        def _energy(sim):
            u = sim.get_field("u")
            return np.trapezoid(np.trapezoid(u ** 2, dx=dx, axis=0), dx=dy)

        times = [0.0, 0.05, 0.1, 0.2, 0.3, 0.5]
        energies = {}
        energies[0.0] = _energy(s)
        for t in times[1:]:
            s.run_until(t, dt=0.001)
            energies[t] = _energy(s)
        return energies

    @pytest.fixture(scope="class")
    def ref(self):
        return load_ref("prop_1_2")

    def test_energy_strictly_decreasing(self, snapshots):
        """L2 energy is strictly decreasing at sampled times."""
        times = [0.0, 0.05, 0.1, 0.2, 0.3, 0.5]
        for i in range(1, len(times)):
            assert snapshots[times[i]] < snapshots[times[i - 1]], (
                f"Energy not decreasing between t={times[i-1]} and t={times[i]}: "
                f"{snapshots[times[i-1]]:.8e} -> {snapshots[times[i]]:.8e}"
            )

    def test_energy_matches_reference(self, snapshots, ref):
        """Energy values match reference data."""
        times_keys = [
            (0.0, "energy_t0.0"),
            (0.05, "energy_t0.05"),
            (0.1, "energy_t0.1"),
            (0.2, "energy_t0.2"),
            (0.3, "energy_t0.3"),
            (0.5, "energy_t0.5"),
        ]
        for t, key in times_keys:
            energy = snapshots[t]
            ref_val = float(ref[key].flat[0])
            if ref_val > 1e-12:
                rel_err = abs(energy - ref_val) / ref_val
                assert rel_err < 0.15, (
                    f"Energy mismatch at t={t}: "
                    f"computed={energy:.8e}, reference={ref_val:.8e}, "
                    f"rel_err={rel_err:.4e}"
                )

    def test_monotone_flag(self, ref):
        """Reference data confirms monotone decreasing energy."""
        assert bool(ref["monotone"].flat[0]) is True


# ---------------------------------------------------------------------------
# 9. Grid Convergence  (REF-1.6)
# ---------------------------------------------------------------------------


class TestGridConvergence:
    """
    IC = sin(pi*x)*sin(pi*y) on [0,1]x[0,1], Dirichlet u=0 on all edges,
    D=1.0. Analytical solution: sin(pi*x)*sin(pi*y)*exp(-2*pi^2*D*t).
    Compare coarse (51x51) vs fine (101x101) grids at t=0.05: error
    should decrease by roughly 4x (second-order spatial convergence).
    """

    @staticmethod
    def _run_convergence(nx, ny, dt):
        s = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=nx, ny=ny)
        s.add_field("u", D=1.0)
        s.set_initial_condition(
            "u", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y)
        )
        s.set_bc("u", "all", "dirichlet", value=0.0)
        s.run_until(0.05, dt=dt)
        u = s.get_field("u")
        x, y = s.coordinates()
        X, Y = np.meshgrid(x, y, indexing="ij")
        u_analytical = (
            np.sin(np.pi * X) * np.sin(np.pi * Y)
            * np.exp(-2 * np.pi ** 2 * 1.0 * 0.05)
        )
        return l2_error(u, u_analytical)

    def test_coarse_grid(self, ref_data):
        """Coarse grid (51x51) error matches reference."""
        ref = ref_data("ref_1_6a")
        err = self._run_convergence(51, 51, dt=1e-5)
        ref_err = float(ref["l2_error"].flat[0])
        # Allow 3x tolerance to account for different stencil implementations
        assert err < ref_err * 3.0, (
            f"Coarse grid error {err:.4e} exceeds 3x reference {ref_err:.4e}"
        )

    def test_fine_grid(self, ref_data):
        """Fine grid (101x101) error matches reference."""
        ref = ref_data("ref_1_6b")
        err = self._run_convergence(101, 101, dt=1e-5)
        ref_err = float(ref["l2_error"].flat[0])
        assert err < ref_err * 3.0, (
            f"Fine grid error {err:.4e} exceeds 3x reference {ref_err:.4e}"
        )

    def test_convergence_rate(self):
        """Doubling resolution reduces L2 error by approximately 4x (2nd order)."""
        err_coarse = self._run_convergence(51, 51, dt=1e-5)
        err_fine = self._run_convergence(101, 101, dt=1e-5)
        ratio = err_coarse / err_fine
        # Expect ratio ~4 for second-order scheme; accept 2.0-20.0
        # (ratio can exceed 4 when temporal error contributes at coarse resolution)
        assert 2.0 < ratio < 20.0, (
            f"Convergence ratio {ratio:.2f} outside expected range [2.0, 20.0]. "
            f"Coarse error: {err_coarse:.4e}, Fine error: {err_fine:.4e}"
        )
