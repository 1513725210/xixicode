"""Memory Store — 持久化记忆存储。

FileMemoryStore: 基于 Markdown+YAML 的文件持久化（V1 生产用）
MockMemoryStore: 内存列表（测试保留）
"""

import time
from dataclasses import dataclass, field
from typing import Literal

from minicode.memory.manager import MemoryManager


MemoryType = Literal["user", "episodic", "procedural", "knowledge"]


@dataclass
class MemoryEntry:
    """一条记忆记录。"""
    id: str
    type: MemoryType
    content: str
    metadata: dict = field(default_factory=dict)
    timestamp: float = 0.0


class FileMemoryStore:
    """基于文件的持久化记忆存储。

    使用 MemoryManager 管理 .minicode/memory/ 目录。
    search() 用关键词匹配，V2 升级到语义检索。
    """

    def __init__(self, memory_dir: str | None = None):
        self._manager = MemoryManager(memory_dir)
        self._id_counter = 0

    async def search(self, query: str, top_k: int = 3) -> list[MemoryEntry]:
        """关键词检索相关记忆。

        Args:
            query: 搜索关键词
            top_k: 返回数量上限

        Returns:
            list[MemoryEntry]: 匹配的记忆条目
        """
        results = self._manager.search(query)
        entries = []
        for r in results[:top_k]:
            entries.append(MemoryEntry(
                id=r.get("filename", ""),
                type=r.get("type", "knowledge"),
                content=f"{r['name']}: {r['body'][:200]}",
                metadata={"name": r["name"], "description": r.get("description", "")},
            ))
        return entries

    async def add_episodic(
        self, task: str, step: str, tool: str, result: str
    ) -> MemoryEntry:
        """添加一条 Episodic Memory（持久化）。"""
        body = f"Task: {task}\nStep: {step}\nTool: {tool}\nResult: {result}"
        name = f"session-{task[:30]}"
        self._manager.write(name, "episodic", step[:80], body)
        self._id_counter += 1
        return MemoryEntry(
            id=f"ep-{self._id_counter}",
            type="episodic",
            content=body[:200],
            metadata={"task": task, "step": step, "tool": tool},
        )

    async def add_procedural(self, lesson: str) -> MemoryEntry:
        """添加一条 Procedural Memory（持久化）。"""
        name = f"lesson-{lesson[:40]}"
        self._manager.write(name, "procedural", lesson[:80], lesson)
        self._id_counter += 1
        return MemoryEntry(
            id=f"proc-{self._id_counter}",
            type="procedural",
            content=lesson,
        )

    @property
    def count(self) -> int:
        index = self._manager.read_index()
        return len(index)


class MockMemoryStore:
    """Mock 记忆存储 — 测试保留。

    所有操作在内存列表中完成，不持久化。
    """

    def __init__(self):
        self._memories: list[MemoryEntry] = []
        self._id_counter = 0

    async def search(self, query: str, top_k: int = 3) -> list[MemoryEntry]:
        return self._memories[-top_k:] if self._memories else []

    async def add_episodic(
        self, task: str, step: str, tool: str, result: str
    ) -> MemoryEntry:
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
