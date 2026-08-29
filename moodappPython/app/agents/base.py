from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from ..core.contracts import AgentContext

RequestT = TypeVar("RequestT")
ResponseT = TypeVar("ResponseT")


class BaseAgent(ABC, Generic[RequestT, ResponseT]):
    """所有业务智能体必须遵循的统一生命周期接口。"""

    name: str
    version: str = "1.0.0"

    @abstractmethod
    async def run(self, request: RequestT, context: AgentContext) -> ResponseT:
        raise NotImplementedError

