"""Mock MemoryStore — 模拟长期记忆存储。

V1 第一阶段：Memory 操作用 Mock。
后续接入 SQLite + sqlite-vec 实现真实向量检索。
"""

from dataclasses import dataclass, field
from typing import Literal


MemoryType = Literal["user", "episodic", "procedural", "knowledge"]


@dataclass
class MemoryEntry:
    """一条记忆记录。"""
    id: str
    type: MemoryType
    content: str
    metadata: dict = field(default_factory=dict)
    timestamp: float = 0.0


class MockMemoryStore:
    """Mock 记忆存储。

    所有操作在内存列表中完成，不持久化。
    """

    def __init__(self):
        self._memories: list[MemoryEntry] = []
        self._id_counter = 0

    async def search(self, query: str, top_k: int = 3) -> list[MemoryEntry]:
        """语义检索相关记忆（Mock: 返回最近添加的）。"""
        return self._memories[-top_k:] if self._memories else []

    async def add_episodic(
        self, task: str, step: str, tool: str, result: str
    ) -> MemoryEntry:
        """添加一条 Episodic Memory。"""
        entry = MemoryEntry(
            id=f"ep-{self._id_counter}",
            type="episodic",
            content=f"Task: {task} | Step: {step} | Tool: {tool} | Result: {result}",
            metadata={"task": task, "step": step, "tool": tool},
        )
        self._id_counter += 1
        self._memories.append(entry)
        return entry

    async def add_procedural(self, lesson: str) -> MemoryEntry:
        """添加一条 Procedural Memory。"""
        entry = MemoryEntry(
            id=f"proc-{self._id_counter}",
            type="procedural",
            content=lesson,
        )
        self._id_counter += 1
        self._memories.append(entry)
        return entry

    @property
    def count(self) -> int:
        return len(self._memories)
