"""Shared fixtures for PlotCurve tests."""
import json
import os
import subprocess
import tempfile

import pytest


ENGINE_CMD = os.environ.get("PLOTCURVE_ENGINE_CMD", os.environ.get("MINIDB_ENGINE_CMD", "python3 plotcurve.py"))


class PlotCurveEngine:
    """Subprocess wrapper for plotcurve.py."""

    def __init__(self, cmd, cwd=None):
        self.cmd = cmd
        self.cwd = cwd
        self._tmpdir = tempfile.mkdtemp(prefix="plotcurve_test_")

    def run(self, request: dict = None) -> dict:
        """Send a JSON request and return the JSON response."""
        if request is None:
            request = {}

        # Default output to a temp file so tests don't litter
        if "output" not in request:
            request["output"] = os.path.join(self._tmpdir, "test_plot.png")

        input_str = json.dumps(request) + "\n"
        result = subprocess.run(
            self.cmd, shell=True, input=input_str,
            capture_output=True, text=True, cwd=self.cwd, timeout=30,
        )
        stdout = result.stdout.strip()
        if not stdout:
            raise RuntimeError(
                f"plotcurve produced no output. stderr: {result.stderr}"
            )
        return json.loads(stdout)

    def run_ok(self, request: dict = None) -> dict:
        """Run and assert success."""
        resp = self.run(request)
        assert "error" not in resp, f"Unexpected error: {resp['error']}"
        assert resp.get("ok") is True
        return resp

    def run_error(self, request: dict = None, match: str = None) -> str:
        """Run and assert error. Returns the error string."""
        resp = self.run(request)
        assert "error" in resp, f"Expected error but got: {resp}"
        if match:
            assert match.lower() in resp["error"].lower(), \
                f"Error '{resp['error']}' does not contain '{match}'"
        return resp["error"]

    @property
    def last_output_path(self):
        return os.path.join(self._tmpdir, "test_plot.png")


@pytest.fixture
def engine():
    """Fresh PlotCurve engine instance."""
    e = PlotCurveEngine(ENGINE_CMD)
    yield e
