"""Tool 抽象基类 + ToolResult。

Tool 是唯一能产生文件系统副作用的原子操作。
所有 Tool 通过 Agent → Tool 调用，User 不直接接触 Tool。
"""

from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import Literal

RiskLevel = Literal["safe", "medium", "high"]


@dataclass
class ToolResult:
    """Tool 执行结果。

    Attributes:
        success: 是否执行成功
        output: 人类可读的输出摘要
        error: 失败时的错误信息
        artifacts: 产生的文件变更列表
    """

    success: bool
    output: str = ""
    error: str | None = None
    artifacts: list[dict] = field(default_factory=list)


class Tool(ABC):
    """Tool 抽象基类。

    每个 Tool 必须定义：name, description, parameters (JSON Schema),
    risk_level，并实现 execute 方法。
    """

    name: str
    description: str
    parameters: dict = {}
    risk_level: RiskLevel = "safe"

    @abstractmethod
    async def execute(self, **params) -> ToolResult:
        """执行工具。高风险操作会触发 Security Layer 审批。"""
        ...
