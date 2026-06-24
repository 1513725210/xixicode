"""Memory Retriever — 语义检索 + 元数据过滤。

V1: 基于关键词的检索（由 MemoryManager.search() 提供）。
V2: 升级到 sqlite-vec 向量检索（内积相似度）。

本模块提供 V2 接口占位，目前委托给 MemoryManager 的 V1 关键词搜索。
"""

from minicode.memory.manager import MemoryManager


class MemoryRetriever:
    """记忆检索器。

    V1: 委托给 MemoryManager 的关键词匹配。
    V2: 接入 sqlite-vec 进行向量语义检索。

    检索策略：
    - User Memory → 全量注入（数据量小）
    - Knowledge Memory → 语义检索 Top 5
    - Procedural Memory → 语义检索 Top 3
    """

    def __init__(self, manager: MemoryManager | None = None):
        """
        Args:
            manager: MemoryManager 实例。为 None 时自动创建。
        """
        self._manager = manager or MemoryManager()

    def search(
        self,
        query: str,
        memory_type: str | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        """检索相关记忆。

        Args:
            query: 搜索查询
            memory_type: 可选，只返回指定类型的记忆
            top_k: 返回数量上限

        Returns:
            list[dict]: 匹配的记忆条目，每个含 name, type, description, body
        """
        results = self._manager.search(query)

        # 类型过滤
        if memory_type:
            results = [r for r in results if r.get("type") == memory_type]

        return results[:top_k]

    def search_user_memory(self) -> list[dict]:
        """获取所有 User Memory（全量注入）。

        Returns:
            list[dict]: 所有 user 类型的记忆
        """
        # V1: 遍历 MEMORY.md 索引找到所有 user 类型
        index = self._manager.read_index()
        results = []
        for slug, desc in index.items():
            if "user:" in desc:
                mem = self._manager.read(slug)
                if mem:
                    results.append(mem)
        return results

    def search_knowledge(self, query: str, top_k: int = 5) -> list[dict]:
        """检索 Knowledge Memory。

        Args:
            query: 搜索查询
            top_k: 返回数量

        Returns:
            list[dict]: 匹配的知识记忆
        """
        return self.search(query, memory_type="knowledge", top_k=top_k)

    def search_procedural(self, query: str, top_k: int = 3) -> list[dict]:
        """检索 Procedural Memory。

        Args:
            query: 搜索查询
            top_k: 返回数量

        Returns:
            list[dict]: 匹配的经验记忆
        """
        return self.search(query, memory_type="procedural", top_k=top_k)

    @property
    def manager(self) -> MemoryManager:
        """底层 MemoryManager 实例。"""
        return self._manager
