"""AgentEvent — MiniCode 事件总线核心类型。

Agent 是 User 和 Tool 之间的唯一网关。
Agent 通过事件总线选择性暴露内部状态。
Tool 不知道 User 的存在，User 不知道 Tool 的存在。
"""

from dataclasses import dataclass, field
from typing import Literal
from datetime import datetime

EventType = Literal[
    "thinking",       # Agent 在推理中
    "tool_call",      # 即将调用 Tool
    "tool_result",    # Tool 返回结果
    "progress",       # 进度更新
    "need_approval",  # 暂停等待用户批准
    "reflection",     # 反思总结
    "done",           # 任务完成
]

EVENT_ICONS: dict[EventType, str] = {
    "thinking":       "~",
    "tool_call":      ">",
    "tool_result":    " ",
    "progress":       ".",
    "need_approval":  "!",
    "reflection":     "*",
    "done":           "+",
}


@dataclass
class AgentEvent:
    """Agent 内部事件 — 由 Query Loop 产生，CLI 层消费并渲染。

    Attributes:
        type: 事件类型，决定渲染方式
        message: 人类可读的一行摘要
        detail: 额外结构化数据（如 diff、文件路径、审批选项）
        timestamp: Unix 时间戳，用于排序和 trace
    """

    type: EventType
    message: str
    detail: dict | None = field(default=None)
    timestamp: float = field(
        default_factory=lambda: datetime.now().timestamp()
    )

    @property
    def icon(self) -> str:
        """事件对应的渲染图标."""
        return EVENT_ICONS.get(self.type, " ")
