"""Shared test fixtures for the MUD benchmark.

Stage 1 drives `mud.py` over stdin/stdout with a plain-text line protocol
terminated by the `> ` prompt. Stages 2 and 3 spawn `mudserver.py` and
connect test clients over TCP using the same prompt-terminated protocol.

Engine commands are configurable via environment variables so the benchmark
harness can point tests at workspace-specific paths:
  ENGINE_CMD        — Stage 1: the mud.py command. Default "python3 mud.py".
  SERVER_CMD        — Stage 2+: the mudserver.py command. Default
                      "python3 mudserver.py". Tests append --port N.
"""
import os
import socket
import subprocess
import threading
import time
import pytest


DEFAULT_ENGINE_CMD = "python3 mud.py"
DEFAULT_SERVER_CMD = "python3 mudserver.py"
PROMPT = "> "


class MUDSession:
    """Wraps a single-player mud.py subprocess.

    Reads bytes from the child's stdout into a buffer on a background thread
    and exposes `cmd(text)` which sends a line and blocks until the buffer
    ends with the `> ` prompt. Returns the response body (everything between
    the previous prompt and this one).
    """

    def __init__(self, cmd, startup_timeout=5.0):
        self.cmd_line = cmd
        self.proc = subprocess.Popen(
            cmd, shell=True,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self._buf = bytearray()
        self._cv = threading.Condition()
        self._done = False
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        try:
            self.welcome = self._read_until_prompt(timeout=startup_timeout)
        except TimeoutError:
            self.close()
            raise

    def _read_loop(self):
        while True:
            try:
                chunk = self.proc.stdout.read(1)
            except Exception:
                with self._cv:
                    self._done = True
                    self._cv.notify_all()
                return
            if not chunk:
                with self._cv:
                    self._done = True
                    self._cv.notify_all()
                return
            with self._cv:
                self._buf.extend(chunk)
                # Only notify when the prompt is visible to avoid waking the
                # consumer on every byte (negligible at human typing speed,
                # measurable at benchmark volume).
                if bytes(self._buf[-2:]) == PROMPT.encode():
                    self._cv.notify_all()

    def _read_until_prompt(self, timeout=3.0):
        marker = PROMPT.encode()
        deadline = time.time() + timeout
        with self._cv:
            while True:
                if self._buf.endswith(marker):
                    out = bytes(self._buf[:-len(marker)]).decode("utf-8", errors="replace")
                    self._buf.clear()
                    return out
                if self._done:
                    leftover = bytes(self._buf).decode("utf-8", errors="replace")
                    stderr = self._read_stderr()
                    raise RuntimeError(
                        f"Process exited before prompt. Buffer: {leftover!r}  stderr: {stderr!r}"
                    )
                remaining = deadline - time.time()
                if remaining <= 0:
                    leftover = bytes(self._buf).decode("utf-8", errors="replace")
                    raise TimeoutError(
                        f"Timed out waiting for prompt. Buffer: {leftover!r}"
                    )
                self._cv.wait(timeout=remaining)

    def _read_stderr(self):
        try:
            return self.proc.stderr.read().decode("utf-8", errors="replace")
        except Exception:
            return ""

    def cmd(self, text, timeout=3.0):
        """Send one command line and return the response body (no prompt)."""
        assert self.proc.poll() is None, "Engine process has exited"
        line = (text + "\n").encode("utf-8")
        self.proc.stdin.write(line)
        self.proc.stdin.flush()
        return self._read_until_prompt(timeout=timeout)

    def quit(self, timeout=2.0):
        """Send `quit` and read the final `Goodbye.` line.

        Unlike regular commands, `quit` ends the session and does NOT
        emit a trailing prompt. Returns the accumulated bytes written by
        the engine before it terminated.
        """
        assert self.proc.poll() is None, "Engine process has exited"
        self.proc.stdin.write(b"quit\n")
        self.proc.stdin.flush()
        deadline = time.time() + timeout
        with self._cv:
            while not self._done and time.time() < deadline:
                remaining = max(0.01, deadline - time.time())
                self._cv.wait(timeout=remaining)
            out = bytes(self._buf).decode("utf-8", errors="replace")
            self._buf.clear()
            return out

    def close(self):
        if self.proc.poll() is None:
            try:
                self.proc.stdin.close()
            except Exception:
                pass
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=1)


@pytest.fixture
def session():
    """Fresh mud.py session per test."""
    cmd = os.environ.get("ENGINE_CMD", DEFAULT_ENGINE_CMD)
    s = MUDSession(cmd)
    yield s
    s.close()


def lines(response):
    """Split a response body into non-empty lines (trailing \\n stripped)."""
    return [ln for ln in response.split("\n") if ln != ""]


# ----------------------------------------------------------------------
# Stage 2+ TCP support
# ----------------------------------------------------------------------


def _free_port():
    """Pick an unused localhost port. Small race window."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class MUDClient:
    """TCP client for a Stage 2+ mudserver.

    Uses the same prompt-terminated line protocol as Stage 1. A background
    reader thread pulls bytes off the socket into a buffer; the buffer is
    searched for the `> ` prompt to delimit responses.

    Broadcasts: the server can push unsolicited prompt-terminated messages
    onto a client's socket whenever another player acts nearby. If a
    broadcast arrives between tests' cmd() calls, its bytes land in the
    buffer and look just like any other response. To avoid accidentally
    consuming a broadcast as a command's response, cmd() drains any
    non-empty buffer state FIRST and stashes it in `self.pending` for the
    test to inspect. drain(settle=...) explicitly waits for unsolicited
    messages and returns them.
    """

    def __init__(self, host, port, connect_timeout=3.0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(connect_timeout)
        deadline = time.time() + connect_timeout
        while True:
            try:
                self.sock.connect((host, port))
                break
            except (ConnectionRefusedError, OSError):
                if time.time() > deadline:
                    raise
                time.sleep(0.02)
        self.sock.settimeout(None)
        self._buf = bytearray()
        self._cv = threading.Condition()
        self._done = False
        self.pending = []  # broadcasts collected incidentally by cmd()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self):
        while True:
            try:
                chunk = self.sock.recv(4096)
            except (OSError, ValueError):
                chunk = b""
            if not chunk:
                with self._cv:
                    self._done = True
                    self._cv.notify_all()
                return
            with self._cv:
                self._buf.extend(chunk)
                if bytes(self._buf[-2:]) == PROMPT.encode():
                    self._cv.notify_all()

    def _read_until_prompt(self, timeout=3.0):
        marker = PROMPT.encode()
        deadline = time.time() + timeout
        with self._cv:
            while True:
                if self._buf.endswith(marker):
                    out = bytes(self._buf[:-len(marker)]).decode("utf-8", errors="replace")
                    self._buf.clear()
                    return out
                if self._done:
                    leftover = bytes(self._buf).decode("utf-8", errors="replace")
                    raise RuntimeError(f"Socket closed before prompt. Buffer: {leftover!r}")
                remaining = deadline - time.time()
                if remaining <= 0:
                    leftover = bytes(self._buf).decode("utf-8", errors="replace")
                    raise TimeoutError(f"Timed out waiting for prompt. Buffer: {leftover!r}")
                self._cv.wait(timeout=remaining)

    def cmd(self, text, timeout=3.0):
        """Send one command; return its response body (not any preceding
        broadcasts, which are stashed in self.pending).
        """
        # Stash any buffered bytes before sending so they're not folded
        # into our response. They're most likely broadcasts we hadn't
        # drained explicitly.
        with self._cv:
            if self._buf:
                self.pending.append(
                    bytes(self._buf).decode("utf-8", errors="replace")
                )
                self._buf.clear()
        self.sock.sendall((text + "\n").encode("utf-8"))
        return self._read_until_prompt(timeout=timeout)

    def login(self, name, timeout=3.0):
        """Send `login <name>` and return the server's response."""
        return self.cmd(f"login {name}", timeout=timeout)

    def quit(self, timeout=2.0):
        """Send `quit` and read the final `Goodbye.` line.

        Unlike regular commands, `quit` ends the session and does NOT
        emit a trailing prompt. Returns the accumulated bytes received
        before the socket closed.
        """
        self.sock.sendall(b"quit\n")
        deadline = time.time() + timeout
        with self._cv:
            while not self._done and time.time() < deadline:
                remaining = max(0.01, deadline - time.time())
                self._cv.wait(timeout=remaining)
            out = bytes(self._buf).decode("utf-8", errors="replace")
            self._buf.clear()
            return out

    def drain(self, settle=0.1):
        """Return everything currently buffered, waiting up to `settle` for
        broadcasts still in flight. Call after an action on another client
        is expected to broadcast to this one.
        """
        time.sleep(settle)
        with self._cv:
            out = bytes(self._buf).decode("utf-8", errors="replace")
            self._buf.clear()
            return out

    def close(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


class MUDServer:
    """Handle for a running mudserver.py subprocess on a known port."""

    def __init__(self, cmd, port, extra_args=""):
        self.cmd_line = cmd
        self.port = port
        full_cmd = f"{cmd} --port {port}"
        if extra_args:
            full_cmd = f"{full_cmd} {extra_args}"
        self.proc = subprocess.Popen(
            full_cmd, shell=True,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        # Wait for the server to accept connections.
        deadline = time.time() + 5.0
        while True:
            try:
                s = socket.socket()
                s.settimeout(0.3)
                s.connect(("127.0.0.1", port))
                s.close()
                break
            except (ConnectionRefusedError, OSError, socket.timeout):
                if time.time() > deadline:
                    err = b""
                    try:
                        err = self.proc.stderr.read(4096)
                    except Exception:
                        pass
                    raise RuntimeError(
                        f"mudserver failed to start on port {port}. "
                        f"stderr: {err.decode('utf-8', errors='replace')!r}"
                    )
                time.sleep(0.05)
        self._clients = []

    def connect(self, name=None):
        """Open a new TCP client. If `name` is given, perform the login
        handshake and return (client, login_response). Otherwise return
        the client without logging in.
        """
        c = MUDClient("127.0.0.1", self.port)
        self._clients.append(c)
        if name is not None:
            resp = c.login(name)
            return c, resp
        return c

    def close(self):
        for c in self._clients:
            c.close()
        self._clients.clear()
        if self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=1)


@pytest.fixture
def server():
    """Fresh mudserver.py on a free port per test."""
    cmd = os.environ.get("SERVER_CMD", DEFAULT_SERVER_CMD)
    port = _free_port()
    srv = MUDServer(cmd, port)
    yield srv
    srv.close()


def _clean_graffiti():
    """Remove a leftover graffiti.json (relative to the test runner's
    cwd, which is also the server subprocess's cwd). Stage 3 tests must
    start with no persisted state.
    """
    for fname in ("graffiti.json", "graffiti.json.tmp"):
        try:
            os.remove(fname)
        except FileNotFoundError:
            pass


@pytest.fixture
def stage3_server():
    """Fresh mudserver.py with NPCs enabled and a small tick interval.

    Cleans any stale `graffiti.json` from prior runs before starting.
    Tick is set to 0.3s so NPC behavior is observable in tests within
    a reasonable wall-clock window.
    """
    cmd = os.environ.get("SERVER_CMD", DEFAULT_SERVER_CMD)
    _clean_graffiti()
    port = _free_port()
    srv = MUDServer(cmd, port, extra_args="--tick-seconds 0.3")
    yield srv
    srv.close()
    _clean_graffiti()


@pytest.fixture
def stage3_server_quiet():
    """Fresh mudserver.py with the NPC tick effectively disabled.

    Use this for stage 3 tests that exercise non-NPC features (chat,
    graffiti, descriptions) and don't want broadcast-vs-response races
    with the ghost. Tick is set to 60 s, larger than any test's runtime.
    """
    cmd = os.environ.get("SERVER_CMD", DEFAULT_SERVER_CMD)
    _clean_graffiti()
    port = _free_port()
    srv = MUDServer(cmd, port, extra_args="--tick-seconds 60")
    yield srv
    srv.close()
    _clean_graffiti()
