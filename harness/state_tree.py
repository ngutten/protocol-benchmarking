"""Experiment state tree — tracks completed stages as a DAG of codebase states.

Each node represents a completed stage on a specific codebase state, recording
the git tag, protocol used, parent node, and associated metrics log.  Nodes
form a DAG that enables forking (running stage B from a codebase where stage A
was completed with a different protocol) and tree-aware differential analysis.

The tree is persisted as ``experiment_tree.json`` in the log directory.
"""
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class TreeNode:
    """A single node in the experiment state tree."""
    node_id: str
    git_tag: str
    stage_id: str
    protocol: str
    parent: Optional[str]  # parent node_id or None for roots
    run_id: str
    metrics_log: str  # filename of the metrics log JSON
    stage_index: int
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TreeNode":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class StateTree:
    """Manages the experiment state tree stored as experiment_tree.json."""

    def __init__(self, log_dir: str):
        self.log_dir = Path(log_dir)
        self.tree_path = self.log_dir / "experiment_tree.json"
        self.nodes: Dict[str, TreeNode] = {}
        self._next_id = 1
        self.load()

    def load(self):
        """Load tree from disk, or start empty."""
        if self.tree_path.exists():
            with open(self.tree_path) as f:
                data = json.load(f)
            for nid, ndata in data.get("nodes", {}).items():
                self.nodes[nid] = TreeNode.from_dict(ndata)
            # Set next ID counter past existing nodes
            if self.nodes:
                max_num = max(
                    int(nid.split("_")[1]) for nid in self.nodes
                    if nid.startswith("node_") and nid.split("_")[1].isdigit()
                )
                self._next_id = max_num + 1

    def save(self):
        """Persist tree to disk."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        data = {"nodes": {nid: n.to_dict() for nid, n in self.nodes.items()}}
        with open(self.tree_path, "w") as f:
            json.dump(data, f, indent=2)

    def _make_id(self) -> str:
        nid = f"node_{self._next_id:03d}"
        self._next_id += 1
        return nid

    def add_node(
        self,
        git_tag: str,
        stage_id: str,
        protocol: str,
        parent: Optional[str],
        run_id: str,
        metrics_log: str,
        stage_index: int,
    ) -> TreeNode:
        """Add a new node to the tree and persist."""
        node_id = self._make_id()
        node = TreeNode(
            node_id=node_id,
            git_tag=git_tag,
            stage_id=stage_id,
            protocol=protocol,
            parent=parent,
            run_id=run_id,
            metrics_log=metrics_log,
            stage_index=stage_index,
            timestamp=datetime.now().isoformat(),
        )
        self.nodes[node_id] = node
        self.save()
        return node

    def find_node(self, stage_id: str, protocol: str) -> Optional[TreeNode]:
        """Find a node by stage_id and protocol. Returns most recent match."""
        matches = [
            n for n in self.nodes.values()
            if n.stage_id == stage_id and n.protocol == protocol
        ]
        if not matches:
            return None
        return max(matches, key=lambda n: n.timestamp)

    def find_by_tag(self, git_tag: str) -> Optional[TreeNode]:
        """Find a node by its git tag."""
        for n in self.nodes.values():
            if n.git_tag == git_tag:
                return n
        return None

    def find_by_id(self, node_id: str) -> Optional[TreeNode]:
        """Find a node by its ID."""
        return self.nodes.get(node_id)

    def get_path(self, node_id: str) -> List[TreeNode]:
        """Get the full path from root to the given node."""
        path = []
        current = self.nodes.get(node_id)
        while current:
            path.append(current)
            current = self.nodes.get(current.parent) if current.parent else None
        path.reverse()
        return path

    def get_children(self, node_id: str) -> List[TreeNode]:
        """Get all direct children of a node."""
        return [n for n in self.nodes.values() if n.parent == node_id]

    def get_roots(self) -> List[TreeNode]:
        """Get all root nodes (no parent)."""
        return [n for n in self.nodes.values() if n.parent is None]

    def find_fork_point(self, stage_id: str, protocol: str) -> Optional[TreeNode]:
        """Find the best node to fork from for running stage_id with protocol.

        Looks for a completed node whose stage is the predecessor of stage_id
        (i.e., the node represents the codebase state just before stage_id
        would be run). Returns None if no suitable fork point exists.
        """
        # Find all nodes that could serve as a starting point
        # (any node where stage_index < the target stage, completed with any protocol)
        candidates = []
        for n in self.nodes.values():
            # A node is a fork candidate if running stage_id from it makes sense
            # This is heuristic — callers usually specify an explicit node
            candidates.append(n)
        return max(candidates, key=lambda n: n.stage_index) if candidates else None

    def get_paths_for_comparison(
        self, stage_id: str, protocol_a: str, protocol_b: str
    ) -> tuple:
        """Find two paths through the tree for differential comparison.

        Returns (path_a, path_b) where path_a ends at stage_id under protocol_a
        and path_b ends at stage_id under protocol_b, or (None, None).
        """
        node_a = self.find_node(stage_id, protocol_a)
        node_b = self.find_node(stage_id, protocol_b)
        if not node_a or not node_b:
            return None, None
        return self.get_path(node_a.node_id), self.get_path(node_b.node_id)

    def list_available_comparisons(self) -> List[dict]:
        """List all computable differential comparisons from existing data.

        Returns a list of dicts describing possible comparisons:
        {stage_id, protocols: [p1, p2, ...], diff_type}
        """
        # Group nodes by stage_id
        by_stage = {}
        for n in self.nodes.values():
            by_stage.setdefault(n.stage_id, set()).add(n.protocol)

        comparisons = []
        for stage_id, protocols in by_stage.items():
            if len(protocols) >= 2:
                comparisons.append({
                    "stage_id": stage_id,
                    "protocols": sorted(protocols),
                    "diff_type": "sequential",
                })
        return comparisons

    def list_missing_comparisons(self, pipeline_stages: List[str], protocols: List[str]) -> List[dict]:
        """List comparisons that are needed but not yet computable.

        Given a set of pipeline stages and protocols to compare, identifies
        which stage/protocol combinations are missing from the tree.
        """
        missing = []
        for stage_id in pipeline_stages:
            for protocol in protocols:
                if not self.find_node(stage_id, protocol):
                    missing.append({
                        "stage_id": stage_id,
                        "protocol": protocol,
                        "action": "run",
                    })
        return missing

    def to_dict(self) -> dict:
        """Export the full tree as a dict (for API responses)."""
        return {
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
        }
