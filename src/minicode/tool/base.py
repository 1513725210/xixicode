"""Tool 抽象基类 + ToolResult + ToolContext。

参考 MiniCode tool.ts 的设计：
- ToolContext: 执行上下文（cwd, permissions）
- ToolResult: 执行结果（ok, output, awaitUser, backgroundTask）
- Tool: 抽象基类，每个 Tool 定义 name/description/parameters/risk_level + execute 方法
"""

from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import Literal, Any

RiskLevel = Literal["safe", "medium", "high"]


@dataclass
class ToolContext:
    """Tool 执行上下文 — 参考 MiniCode 的 ToolContext。

    Attributes:
        cwd: 当前工作目录
        dry_run: 只读模式，不执行写操作
    """

    cwd: str = "."
    dry_run: bool = False


@dataclass
class BackgroundTask:
    """后台任务描述 — 参考 MiniCode 的 BackgroundTaskResult。

    Attributes:
        task_id: 任务唯一标识
        type: 任务类型（如 local_bash）
        command: 执行的命令
        pid: 进程 ID
        status: 运行状态
        started_at: 启动时间戳
    """

    task_id: str
    type: str = "local_bash"
    command: str = ""
    pid: int = -1
    status: str = "running"
    started_at: float = 0.0


class ToolResult:
    """Tool 执行结果。

    参考 MiniCode 的 ToolResult 扩展：
    - ok: 是否执行成功（兼容旧字段 success）
    - output: 人类可读的输出文本
    - error: 失败时的错误信息
    - artifacts: 产生的文件变更列表
    - awaitUser: True 表示需要暂停等待用户回复（ask_user 专用）
    - backgroundTask: 后台任务描述（run_command --bg 专用）
    """

    __slots__ = ("ok", "output", "error", "artifacts", "awaitUser", "backgroundTask")

    def __init__(
        self,
        ok: bool = True,
        output: str = "",
        error: str | None = None,
        artifacts: list[dict] | None = None,
        awaitUser: bool = False,
        backgroundTask: BackgroundTask | None = None,
        *,
        # 兼容旧代码：接受 success 关键字，映射到 ok
        success: bool | None = None,
    ):
        self.ok = success if success is not None else ok
        self.output = output
        self.error = error
        self.artifacts = artifacts if artifacts is not None else []
        self.awaitUser = awaitUser
        self.backgroundTask = backgroundTask

    @property
    def success(self) -> bool:
        """兼容旧接口 — 等价于 ok。"""
        return self.ok

    @success.setter
    def success(self, value: bool) -> None:
        self.ok = value


class Tool(ABC):
    """Tool 抽象基类。

    每个 Tool 必须定义：name, description, parameters (JSON Schema),
    risk_level，并实现 execute 方法。

    参考 MiniCode 的 ToolDefinition — execute 接收 **params + context。
    """

    name: str
    description: str
    parameters: dict[str, Any] = {}
    risk_level: RiskLevel = "safe"

    @abstractmethod
    async def execute(self, **params) -> ToolResult:
        """执行工具。高风险操作会触发 Security Layer 审批。

        子类可额外接收 context: ToolContext 参数。
        """
        ...

    def to_dict(self) -> dict:
        """返回 LLM 可读的工具描述（用于注入 prompt）。"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "risk_level": self.risk_level,
        }
