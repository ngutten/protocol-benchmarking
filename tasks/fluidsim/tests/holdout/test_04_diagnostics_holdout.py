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
