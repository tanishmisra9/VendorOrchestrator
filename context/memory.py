import uuid
from typing import Any, Optional

from .schema import RunContext


class SharedContext:
    """MCP-style shared context store for coordinating agents.

    Each pipeline run gets its own RunContext. Agents read/write through
    this class, which ensures all context mutations are centralized.
    """

    def __init__(self) -> None:
        self._runs: dict[str, RunContext] = {}
        self._current_run_id: Optional[str] = None

    def new_run(self, run_id: Optional[str] = None) -> str:
        run_id = run_id or uuid.uuid4().hex[:12]
        self._runs[run_id] = RunContext(run_id=run_id)
        self._current_run_id = run_id
        return run_id

    @property
    def current_run(self) -> RunContext:
        if self._current_run_id is None or self._current_run_id not in self._runs:
            raise RuntimeError("No active run. Call new_run() first.")
        return self._runs[self._current_run_id]

    def read(self, key: str) -> Any:
        return getattr(self.current_run, key)

    def write(self, key: str, value: Any) -> None:
        if not hasattr(self.current_run, key):
            raise KeyError(f"Unknown context key: {key}")
        setattr(self.current_run, key, value)

    def append(self, key: str, item: Any) -> None:
        """Append an item to a list-type context field."""
        current = self.read(key)
        if not isinstance(current, list):
            raise TypeError(f"Context key '{key}' is not a list.")
        current.append(item)

    def get_full_state(self) -> dict:
        return self.current_run.model_dump()

    def reset(self, run_id: Optional[str] = None) -> None:
        """Reset a specific run or the current run."""
        rid = run_id or self._current_run_id
        if rid and rid in self._runs:
            self._runs[rid] = RunContext(run_id=rid)

    def get_run(self, run_id: str) -> RunContext:
        if run_id not in self._runs:
            raise KeyError(f"Run '{run_id}' not found.")
        return self._runs[run_id]

    def list_runs(self) -> list[str]:
        return list(self._runs.keys())
