"""
Shared fixtures for MiniDB benchmark tests.

The engine fixture starts the MiniDB engine as a subprocess and communicates
via stdin/stdout JSON protocol. Tests are language-agnostic.
"""
import subprocess
import json
import os
import time
import pytest


ENGINE_CMD_ENV = "MINIDB_ENGINE_CMD"
DEFAULT_ENGINE_CMD = "python3 minidb.py"


class MiniDBEngine:
    """Client wrapper for a MiniDB engine subprocess."""

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
        """Send a command and return parsed JSON response."""
        assert self.proc.poll() is None, "Engine process has exited"
        self.proc.stdin.write(command.strip() + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            stderr = self.proc.stderr.read()
            raise RuntimeError(f"Engine produced no output. stderr: {stderr}")
        return json.loads(line)

    def execute(self, command):
        """Send a command, assert no error, return response."""
        resp = self.send(command)
        assert "error" not in resp, f"Unexpected error: {resp}"
        return resp

    def query(self, sql):
        """Send a SELECT query, return (columns, rows) tuple."""
        resp = self.execute(sql)
        return resp["columns"], resp["rows"]

    def query_rows(self, sql):
        """Send a SELECT query, return just the rows."""
        _, rows = self.query(sql)
        return rows

    def query_scalar(self, sql):
        """Send a query expected to return a single value."""
        cols, rows = self.query(sql)
        assert len(rows) == 1 and len(rows[0]) == 1, \
            f"Expected scalar, got {len(rows)} rows x {len(cols)} cols"
        return rows[0][0]

    def expect_error(self, command, substring=None):
        """Send a command and assert it returns an error."""
        resp = self.send(command)
        assert "error" in resp, f"Expected error, got: {resp}"
        if substring:
            assert substring.lower() in resp["error"].lower(), \
                f"Expected substring in error, got: {resp}"
        return resp["error"]

    def close(self):
        if self.proc.poll() is None:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)


@pytest.fixture
def engine():
    """Start a fresh MiniDB engine for each test."""
    cmd = os.environ.get(ENGINE_CMD_ENV, DEFAULT_ENGINE_CMD)
    eng = MiniDBEngine(cmd)
    yield eng
    eng.close()


@pytest.fixture
def populated_engine(engine):
    """Engine with a standard test table pre-populated with mixed types."""
    engine.execute("CREATE TABLE mixed (id, name, value, flag, data)")
    engine.execute("INSERT INTO mixed VALUES (1, 'alice', 100, true, null)")
    engine.execute("INSERT INTO mixed VALUES (2, 'bob', 200.5, false, 'extra')")
    engine.execute("INSERT INTO mixed VALUES (3, 'carol', '300', true, null)")
    engine.execute("INSERT INTO mixed VALUES (4, 'dave', null, null, 42)")
    engine.execute("INSERT INTO mixed VALUES (5, 'eve', true, 'yes', 0)")
    return engine
