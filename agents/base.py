import logging
from abc import ABC, abstractmethod
from typing import Any

from context.memory import SharedContext

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base class for all vendor pipeline agents.

    Every agent receives a shared MCP context for reading/writing state
    and exposes a standard run() interface.
    """

    name: str = "BaseAgent"

    def __init__(self, context: SharedContext) -> None:
        self.context = context

    @abstractmethod
    def run(self, data: Any) -> Any:
        ...

    def log_to_context(self, key: str, item: Any) -> None:
        self.context.append(key, item)

    def read_context(self, key: str) -> Any:
        return self.context.read(key)

    def info(self, msg: str) -> None:
        logger.info("[%s] %s", self.name, msg)

    def warn(self, msg: str) -> None:
        logger.warning("[%s] %s", self.name, msg)
