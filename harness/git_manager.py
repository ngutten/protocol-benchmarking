"""Git operations for the benchmark harness."""
import subprocess
import os


class GitManager:
    """Manages git operations for a benchmark workspace."""

    def __init__(self, work_dir):
        self.work_dir = work_dir

    def _run(self, *args):
        result = subprocess.run(
            ["git"] + list(args),
            capture_output=True, text=True, cwd=self.work_dir,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout.strip()

    def init(self):
        """Initialize a new git repo."""
        self._run("init")
        self._run("config", "user.email", "benchmark@minidb.test")
        self._run("config", "user.name", "Benchmark Harness")

    def commit_all(self, message):
        """Stage all changes and commit."""
        self._run("add", "-A")
        try:
            self._run("commit", "--allow-empty", "-m", message)
        except RuntimeError:
            pass  # nothing to commit
        return self._run("rev-parse", "HEAD")

    def tag(self, name):
        self._run("tag", name)

    def branch(self, name):
        self._run("checkout", "-b", name)

    def checkout(self, ref):
        self._run("checkout", ref)

    def merge(self, branch, no_commit=False):
        """Merge a branch. Returns (success, num_conflicts)."""
        cmd = ["merge", branch]
        if no_commit:
            cmd.append("--no-commit")
        result = subprocess.run(
            ["git"] + cmd,
            capture_output=True, text=True, cwd=self.work_dir,
        )
        if result.returncode == 0:
            return True, 0
        # Count conflicts
        status = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            capture_output=True, text=True, cwd=self.work_dir,
        )
        conflicts = len([l for l in status.stdout.splitlines() if l.strip()])
        return False, conflicts

    def log_oneline(self, n=20):
        return self._run("log", "--oneline", f"-{n}")

    def diff_stat(self, ref1, ref2):
        return self._run("diff", "--stat", ref1, ref2)

    def current_branch(self):
        return self._run("rev-parse", "--abbrev-ref", "HEAD")

    def current_commit(self):
        return self._run("rev-parse", "HEAD")

    def tag_exists(self, name):
        """Check if a tag exists."""
        try:
            self._run("rev-parse", f"refs/tags/{name}")
            return True
        except RuntimeError:
            return False

    def list_tags(self, pattern=None):
        """List tags, optionally filtered by glob pattern."""
        if pattern:
            output = self._run("tag", "-l", pattern)
        else:
            output = self._run("tag", "-l")
        return [t for t in output.splitlines() if t.strip()]

    def checkout_tag(self, tag_name, new_branch=None):
        """Checkout a tag, optionally creating a new branch."""
        if new_branch:
            self._run("checkout", tag_name, "-b", new_branch)
        else:
            self._run("checkout", tag_name)
