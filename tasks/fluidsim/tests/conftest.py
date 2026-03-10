"""
Shared fixtures for FluidSim benchmark tests.

The engine fixture starts the FluidSim engine as a subprocess and communicates
via stdin/stdout JSON protocol. Tests are language-agnostic.
"""
import subprocess
import json
import os
import time
import pytest


ENGINE_CMD_ENV = "FLUIDSIM_ENGINE_CMD"
DEFAULT_ENGINE_CMD = "python3 fluidsim.py"


class FluidSimEngine:
    """Client wrapper for a FluidSim engine subprocess."""

    def __init__(self, cmd):
        self.proc = subprocess.Popen(
            cmd, shell=True,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        time.sleep(0.1)
        if self.proc.poll() is not None:
            stderr = self.proc.stderr.read()
            raise RuntimeError(f"Engine failed to start: {stderr}")

    def send(self, command):
        """Send a JSON command dict and return parsed JSON response."""
        if isinstance(command, dict):
            line = json.dumps(command)
        else:
            line = command
        assert self.proc.poll() is None, "Engine process has exited"
        self.proc.stdin.write(line.strip() + "\n")
        self.proc.stdin.flush()
        resp_line = self.proc.stdout.readline()
        if not resp_line:
            stderr = self.proc.stderr.read()
            raise RuntimeError(f"Engine produced no output. stderr: {stderr}")
        return json.loads(resp_line)

    def execute(self, command):
        """Send a command, assert no error, return response."""
        resp = self.send(command)
        assert "error" not in resp, f"Unexpected error: {resp}"
        return resp

    def expect_error(self, command, substring=None):
        """Send a command and assert it returns an error."""
        resp = self.send(command)
        assert "error" in resp, f"Expected error, got: {resp}"
        if substring:
            assert substring.lower() in resp["error"].lower(), \
                f"Expected '{substring}' in error, got: {resp['error']}"
        return resp["error"]

    def create(self, nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01, force=None):
        """Create a simulation with common defaults."""
        cmd = {
            "command": "create",
            "grid": {"nx": nx, "ny": ny, "lx": lx, "ly": ly},
            "fluid": {"viscosity": viscosity},
        }
        if force is not None:
            cmd["force"] = force
        return self.execute(cmd)

    def set_boundary(self, boundary, bc_type, value=None, **kwargs):
        """Set a boundary condition."""
        cmd = {"command": "set_boundary", "boundary": boundary, "type": bc_type}
        if value is not None:
            cmd["value"] = value
        cmd.update(kwargs)
        return self.execute(cmd)

    def solve_steady(self, tolerance=1e-6, max_iterations=10000):
        """Solve to steady state."""
        return self.execute({
            "command": "solve_steady",
            "tolerance": tolerance,
            "max_iterations": max_iterations,
        })

    def step(self, dt, steps=1):
        """Advance time by given number of steps."""
        return self.execute({
            "command": "step",
            "dt": dt,
            "steps": steps,
        })

    def get_field(self, field):
        """Get a full 2D field."""
        return self.execute({"command": "get_field", "field": field})

    def get_value(self, field, point):
        """Get interpolated value at a point."""
        return self.execute({
            "command": "get_value",
            "field": field,
            "point": point,
        })

    def get_profile(self, field, line, position, n_points=50):
        """Get field values along a line."""
        return self.execute({
            "command": "get_profile",
            "field": field,
            "line": line,
            "position": position,
            "n_points": n_points,
        })

    def status(self):
        """Get simulation status."""
        return self.execute({"command": "status"})

    def reset(self):
        """Reset simulation state."""
        return self.execute({"command": "reset"})

    def load_config(self, path):
        """Load a JSON configuration file."""
        return self.execute({"command": "load_config", "path": path})

    def add_obstacle(self, obs_type, **params):
        """Add an obstacle to the domain."""
        cmd = {"command": "add_obstacle", "type": obs_type}
        cmd.update(params)
        return self.execute(cmd)

    def set_solver(self, solver_type, **params):
        """Set the solver type and parameters."""
        cmd = {"command": "set_solver", "type": solver_type}
        cmd.update(params)
        return self.execute(cmd)

    def get_diagnostics(self):
        """Get current diagnostic values."""
        return self.execute({"command": "get_diagnostics"})

    def get_diagnostic_history(self, diagnostic):
        """Get time history of a diagnostic."""
        return self.execute({
            "command": "get_diagnostic_history",
            "diagnostic": diagnostic,
        })

    def close(self):
        if self.proc.poll() is None:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)


@pytest.fixture
def engine():
    """Start a fresh FluidSim engine for each test."""
    cmd = os.environ.get(ENGINE_CMD_ENV, DEFAULT_ENGINE_CMD)
    eng = FluidSimEngine(cmd)
    yield eng
    eng.close()


@pytest.fixture
def stokes_engine(engine):
    """Engine with a standard Stokes flow setup (no-slip walls, no body force)."""
    engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
    engine.set_boundary("top", "no_slip")
    engine.set_boundary("bottom", "no_slip")
    engine.set_boundary("left", "no_slip")
    engine.set_boundary("right", "no_slip")
    return engine


@pytest.fixture
def cavity_engine(engine):
    """Engine set up for lid-driven cavity flow."""
    engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
    engine.set_boundary("top", "velocity", value=[1.0, 0.0])
    engine.set_boundary("bottom", "no_slip")
    engine.set_boundary("left", "no_slip")
    engine.set_boundary("right", "no_slip")
    return engine
