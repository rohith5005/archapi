from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set


@dataclass
class TaskNode:
    name: str
    depends_on: List[str] = field(default_factory=list)
    status: str = "pending"


@dataclass
class TaskDAG:
    nodes: Dict[str, TaskNode] = field(default_factory=dict)

    def add_task(self, name: str, depends_on: List[str] = None) -> None:
        self.nodes[name] = TaskNode(name=name, depends_on=depends_on or [])

    def ready_tasks(self) -> List[str]:
        ready: List[str] = []
        completed = {
            name
            for name, node in self.nodes.items()
            if node.status == "completed"
        }

        for name, node in self.nodes.items():
            if node.status != "pending":
                continue

            if all(dep in completed for dep in node.depends_on):
                ready.append(name)

        return ready

    def mark_completed(self, name: str) -> None:
        self.nodes[name].status = "completed"

    def mark_failed_and_block_dependents(self, name: str) -> List[str]:
        self.nodes[name].status = "failed"

        blocked: List[str] = []
        for node_name, node in self.nodes.items():
            if self._depends_on(node_name, name):
                if node.status == "pending":
                    node.status = "blocked"
                    blocked.append(node_name)

        return blocked

    def _depends_on(self, node_name: str, dependency: str) -> bool:
        visited: Set[str] = set()

        def visit(current: str) -> bool:
            if current in visited:
                return False
            visited.add(current)

            node = self.nodes[current]
            if dependency in node.depends_on:
                return True

            return any(visit(dep) for dep in node.depends_on if dep in self.nodes)

        return visit(node_name)

    @classmethod
    def default_api_dag(cls) -> "TaskDAG":
        dag = cls()
        dag.add_task("detect_models")
        dag.add_task("detect_route_style")
        dag.add_task("detect_auth_style")
        dag.add_task("detect_service_style")
        dag.add_task("generate_schema", ["detect_models"])
        dag.add_task("generate_route", ["detect_route_style", "detect_auth_style"])
        dag.add_task("generate_service", ["detect_models", "detect_service_style"])
        dag.add_task("generate_controller", ["generate_schema", "generate_route", "generate_service"])
        dag.add_task("generate_test", ["generate_controller", "generate_route"])
        return dag
