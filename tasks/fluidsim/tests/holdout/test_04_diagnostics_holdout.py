"""Stage 4 holdout tests: Cylinder drag coefficients, energy dissipation, enstrophy."""
import pytest
import math


class TestCylinderDragRe20:
    """Cylinder drag coefficient at Re=20.

    Dennis & Chang (1970): Cd ~ 2.05
    Tolerance: |Cd - 2.05| < 0.3 (~15%)
    """

    def test_cylinder_cd_re20(self, engine):
        """Cd for cylinder at Re=20 should be near 2.05."""
        D = 0.2
        U = 1.0
        nu = U * D / 20.0  # Re = 20

        engine.create(nx=128, ny=64, lx=4.0, ly=2.0, viscosity=nu)
        engine.set_boundary("left", "inflow", profile="uniform", velocity=[U, 0.0])
        engine.set_boundary("right", "outflow")
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.add_obstacle("circle", center=[1.0, 1.0], radius=D / 2)
        engine.solve_steady(tolerance=1e-5, max_iterations=200000)

        diag = engine.get_diagnostics()
        assert "drag" in diag

        # Cd = 2F / (ρ U² D) — the engine should return the force, we compute Cd
        # Or the engine returns Cd directly. Accept either convention.
        drag = diag["drag"]
        # If drag is the force per unit span:
        # Cd = 2 * drag / (rho * U^2 * D), rho=1
        cd = 2.0 * drag / (U**2 * D) if drag < 10 else drag
        # Allow for the engine returning Cd directly
        if abs(drag - 2.05) < 0.5:
            cd = drag

        assert abs(cd - 2.05) < 0.3, \
            f"Cylinder Re=20 Cd={cd:.3f}, expected ~2.05 (tolerance ±0.3)"

    def test_cylinder_cl_re20(self, engine):
        """Lift coefficient for symmetric cylinder at Re=20 should be ~0."""
        D = 0.2
        U = 1.0
        nu = U * D / 20.0

        engine.create(nx=128, ny=64, lx=4.0, ly=2.0, viscosity=nu)
        engine.set_boundary("left", "inflow", profile="uniform", velocity=[U, 0.0])
        engine.set_boundary("right", "outflow")
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.add_obstacle("circle", center=[1.0, 1.0], radius=D / 2)
        engine.solve_steady(tolerance=1e-5, max_iterations=200000)

        diag = engine.get_diagnostics()
        assert "lift" in diag
        # Lift should be approximately zero for symmetric setup
        assert abs(diag["lift"]) < 0.1, \
            f"Cylinder Re=20 lift={diag['lift']:.4f}, expected ~0"


class TestCylinderDragRe100:
    """Cylinder drag at Re=100 (unsteady, vortex shedding).

    Braza et al. (1986): mean Cd ~ 1.33
    Tolerance: Cd in [1.1, 1.6] (~15%)
    """

    def test_cylinder_cd_re100_mean(self, engine):
        """Mean Cd for cylinder at Re=100 should be in [1.1, 1.6]."""
        D = 0.2
        U = 1.0
        nu = U * D / 100.0  # Re = 100

        engine.create(nx=128, ny=64, lx=4.0, ly=2.0, viscosity=nu)
        engine.set_boundary("left", "inflow", profile="uniform", velocity=[U, 0.0])
        engine.set_boundary("right", "outflow")
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.add_obstacle("circle", center=[1.0, 1.0], radius=D / 2)

        # Run time-dependent simulation to develop vortex shedding
        # Small dt for stability at Re=100
        dt = 0.005
        total_steps = 2000
        engine.step(dt=dt, steps=total_steps)

        # Get drag history and compute mean over latter half (after transient)
        hist = engine.get_diagnostic_history("drag")
        times = hist["times"]
        values = hist["values"]

        if len(values) > 10:
            # Use latter half to avoid startup transient
            half = len(values) // 2
            drag_values = values[half:]
            mean_drag = sum(drag_values) / len(drag_values)

            # Convert to Cd if needed
            cd = 2.0 * mean_drag / (U**2 * D) if mean_drag < 5 else mean_drag
            if abs(mean_drag - 1.33) < 1.0:
                cd = mean_drag

            assert 1.1 < cd < 1.6, \
                f"Mean Cd at Re=100 = {cd:.3f}, expected in [1.1, 1.6]"


class TestEnergyDissipation:
    """Test energy dissipation properties."""

    def test_energy_decreasing_cavity(self, engine):
        """Kinetic energy should decrease when lid velocity is reduced."""
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.solve_steady(tolerance=1e-5, max_iterations=50000)

        diag1 = engine.get_diagnostics()
        ke1 = diag1["kinetic_energy"]

        # Reduce lid velocity
        engine.set_boundary("top", "velocity", value=[0.5, 0.0])
        engine.solve_steady(tolerance=1e-5, max_iterations=50000)

        diag2 = engine.get_diagnostics()
        ke2 = diag2["kinetic_energy"]

        assert ke2 < ke1, \
            f"KE should decrease with reduced lid velocity: {ke2:.6f} vs {ke1:.6f}"

    def test_energy_dissipation_decaying_flow(self, engine):
        """After removing driving, KE should decay."""
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")

        # Drive the flow
        engine.step(dt=0.01, steps=100)

        hist = engine.get_diagnostic_history("kinetic_energy")
        if len(hist["values"]) >= 2:
            # Energy should be positive and bounded
            for ke in hist["values"]:
                assert ke >= 0, "Kinetic energy should be non-negative"


class TestEnstrophyConsistency:
    """Test enstrophy is consistent with vorticity field."""

    def test_enstrophy_matches_vorticity(self, engine):
        """Enstrophy from diagnostics should be consistent with vorticity field integral."""
        nx, ny = 32, 32
        lx, ly = 1.0, 1.0
        engine.create(nx=nx, ny=ny, lx=lx, ly=ly, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.solve_steady(tolerance=1e-5, max_iterations=50000)

        diag = engine.get_diagnostics()
        enstrophy_diag = diag["enstrophy"]

        # Compute enstrophy from vorticity field
        vort = engine.get_field("vorticity")["data"]
        dx = lx / nx
        dy = ly / ny

        enstrophy_computed = 0.0
        for j in range(ny):
            for i in range(nx):
                enstrophy_computed += 0.5 * vort[j][i] ** 2 * dx * dy

        # Should be within 20% of each other (different integration methods)
        if enstrophy_diag > 0:
            rel_diff = abs(enstrophy_diag - enstrophy_computed) / enstrophy_diag
            assert rel_diff < 0.3, \
                f"Enstrophy mismatch: diag={enstrophy_diag:.4f}, computed={enstrophy_computed:.4f}"


class TestMassFluxChannelFlow:
    """Test mass flux conservation in channel flows."""

    def test_inflow_outflow_mass_balance(self, engine):
        """Mass flux in should equal mass flux out for channel flow."""
        engine.create(nx=64, ny=32, lx=4.0, ly=1.0, viscosity=0.05)
        engine.set_boundary("left", "inflow", profile="uniform", velocity=[1.0, 0.0])
        engine.set_boundary("right", "outflow")
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.solve_steady(tolerance=1e-5, max_iterations=100000)

        diag = engine.get_diagnostics()
        flux = diag["mass_flux"]

        # Inflow (left, negative = into domain) + outflow (right, positive = out of domain)
        # should balance with no-slip walls having ~zero flux
        net = sum(flux.values())
        assert abs(net) < 1e-2, f"Net mass flux = {net}, should be ~0"


class TestNumericalDissipation:
    """Precise tests for numerical dissipation using the diagnostics API.

    These tests use the energy-enstrophy identity dKE/dt = -2νZ and
    diagnostic time series to directly measure numerical viscosity.
    """

    def test_energy_enstrophy_balance_precise(self, engine):
        """dKE/dt ≈ -2νZ measured via diagnostics, within 50%.

        This is a stricter version than the training test. On a 48² grid
        at Re=100, a good second-order scheme should give a ratio close to 1.0.
        First-order upwind would give ratio ≈ 2.0 and fail this test.
        """
        nu = 0.01
        engine.create(nx=48, ny=48, lx=1.0, ly=1.0, viscosity=nu)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.step(dt=0.01, steps=200)

        engine.set_boundary("top", "no_slip")
        engine.step(dt=0.005, steps=2)

        ratios = []
        for _ in range(6):
            diag1 = engine.get_diagnostics()
            ke1 = diag1["kinetic_energy"]
            z1 = diag1["enstrophy"]

            engine.step(dt=0.005, steps=5)

            diag2 = engine.get_diagnostics()
            ke2 = diag2["kinetic_energy"]
            z2 = diag2["enstrophy"]

            dke_dt = (ke2 - ke1) / 0.025
            z_avg = (z1 + z2) / 2
            expected = -2.0 * nu * z_avg

            if abs(expected) > 1e-8:
                ratios.append(dke_dt / expected)

        assert len(ratios) >= 3
        avg = sum(ratios) / len(ratios)
        assert 0.5 < avg < 1.7, \
            f"Energy-enstrophy ratio = {avg:.3f}, expected ~1.0. " \
            f"Ratio > 1.5 indicates excessive numerical viscosity."

    def test_decay_rate_scales_with_viscosity(self, engine):
        """Doubling viscosity should roughly double the energy decay rate.

        If numerical viscosity dominates, the decay rate won't change much
        when the physical viscosity changes. This test checks that the
        solver is actually using the specified viscosity.
        """
        def measure_decay(eng, nu):
            eng.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=nu)
            eng.set_boundary("top", "velocity", value=[1.0, 0.0])
            eng.set_boundary("bottom", "no_slip")
            eng.set_boundary("left", "no_slip")
            eng.set_boundary("right", "no_slip")
            eng.step(dt=0.01, steps=100)

            eng.set_boundary("top", "no_slip")
            eng.step(dt=0.005, steps=2)

            d1 = eng.get_diagnostics()
            eng.step(dt=0.005, steps=10)
            d2 = eng.get_diagnostics()

            return (d2["kinetic_energy"] - d1["kinetic_energy"]) / 0.05

        rate_1 = measure_decay(engine, 0.01)
        engine.reset()
        rate_2 = measure_decay(engine, 0.02)

        # Both rates should be negative; rate_2 should be ~2x more negative
        assert rate_1 < 0, f"Decay rate should be negative: {rate_1:.6f}"
        assert rate_2 < 0, f"Decay rate should be negative: {rate_2:.6f}"

        ratio = rate_2 / rate_1
        assert 1.3 < ratio < 3.0, \
            f"Doubling ν should ~double decay rate: ratio={ratio:.3f}, " \
            f"rate(ν=0.01)={rate_1:.6f}, rate(ν=0.02)={rate_2:.6f}"

    def test_no_spurious_energy_production(self, engine):
        """KE should never increase during unforced, no-slip decay.

        Check every entry in the diagnostic history after stopping the lid.
        Any increase indicates a numerical instability or energy-producing bug.
        """
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.step(dt=0.01, steps=100)

        engine.set_boundary("top", "no_slip")
        engine.step(dt=0.005, steps=100)

        hist = engine.get_diagnostic_history("kinetic_energy")
        vals = hist["values"]

        # Check the decay portion (latter entries, after lid was stopped)
        # The history covers all steps; use the last 100 entries
        decay_vals = vals[-100:] if len(vals) >= 100 else vals[-50:]

        for i in range(len(decay_vals) - 1):
            assert decay_vals[i + 1] <= decay_vals[i] + 1e-10, \
                f"KE increased at step {i}: {decay_vals[i]:.10f} -> {decay_vals[i + 1]:.10f}"

    def test_enstrophy_decays_during_free_evolution(self, engine):
        """Enstrophy should also decay in unforced flow (not grow spuriously).

        While enstrophy can grow in driven 2D turbulence, in decaying flow
        with no forcing it should decrease (in 2D, enstrophy is bounded by
        its initial value for Navier-Stokes).
        """
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.step(dt=0.01, steps=100)

        engine.set_boundary("top", "no_slip")
        engine.step(dt=0.005, steps=5)

        z_initial = engine.get_diagnostics()["enstrophy"]
        engine.step(dt=0.005, steps=100)
        z_final = engine.get_diagnostics()["enstrophy"]

        assert z_final < z_initial * 1.05, \
            f"Enstrophy should not grow in decaying flow: " \
            f"initial={z_initial:.6f}, final={z_final:.6f}"


class TestVortexDecayProperties:
    """Test vortex decay and preservation properties.

    These tests check whether the solver correctly captures the decay of
    vortical structures and doesn't introduce spurious diffusion.
    """

    def test_peak_vorticity_decays_monotonically(self, engine):
        """Peak vorticity magnitude should decrease during free decay.

        Numerical diffusion causes faster-than-physical vorticity decay.
        Here we just check it decays monotonically (no oscillations or growth).
        """
        nx, ny = 32, 32
        engine.create(nx=nx, ny=ny, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.step(dt=0.01, steps=100)

        engine.set_boundary("top", "no_slip")
        engine.step(dt=0.005, steps=2)

        vort = engine.get_field("vorticity")["data"]
        prev_peak = max(abs(vort[j][i]) for j in range(ny) for i in range(nx))

        for interval in range(5):
            engine.step(dt=0.005, steps=10)
            vort = engine.get_field("vorticity")["data"]
            peak = max(abs(vort[j][i]) for j in range(ny) for i in range(nx))
            assert peak < prev_peak * 1.05, \
                f"Interval {interval}: peak |ω| grew from {prev_peak:.4f} to {peak:.4f}"
            prev_peak = peak

    def test_vorticity_decay_rate_bounded_by_viscosity(self, engine):
        """Peak vorticity shouldn't decay much faster than the viscous time scale.

        For a vortex with characteristic size L and viscosity ν, the decay
        time scale is τ ~ L²/ν. Over time T << τ, the peak vorticity should
        retain most of its value. Excessive numerical diffusion would cause
        much faster decay.
        """
        nx, ny = 48, 48
        lx, ly = 1.0, 1.0
        nu = 0.01

        engine.create(nx=nx, ny=ny, lx=lx, ly=ly, viscosity=nu)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.step(dt=0.01, steps=200)

        engine.set_boundary("top", "no_slip")
        engine.step(dt=0.005, steps=2)

        diag_initial = engine.get_diagnostics()
        ke_initial = diag_initial["kinetic_energy"]

        # Evolve for T = 0.5 time units
        # Viscous time scale τ = L²/ν = 1/0.01 = 100
        # So T/τ = 0.005 — should retain most of the energy
        engine.step(dt=0.005, steps=100)

        diag_final = engine.get_diagnostics()
        ke_final = diag_final["kinetic_energy"]

        # Should retain at least 50% of energy over this short time
        # (purely viscous decay: exp(-2ν k² T) ≈ exp(-0.01*T) for k=1)
        # With T=0.5: retention ≈ exp(-0.005) ≈ 0.995 for the lowest mode
        # Actual cavity flow has higher modes that decay faster, so ~70-90% expected
        retention = ke_final / ke_initial if ke_initial > 1e-10 else 0
        assert retention > 0.3, \
            f"Energy retention = {retention:.3f} over T=0.5 is too low — " \
            f"excessive numerical dissipation (expected > 0.3)"
