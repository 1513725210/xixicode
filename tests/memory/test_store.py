"""MockMemoryStore 单元测试。"""

import asyncio
import pytest

from minicode.memory.store import MockMemoryStore, MemoryEntry


class TestMockMemoryStore:
    @pytest.fixture
    def store(self):
        return MockMemoryStore()

    def test_starts_empty(self, store):
        assert store.count == 0

    def test_search_empty_returns_empty(self, store):
        result = asyncio.run(store.search("anything"))
        assert result == []

    def test_add_and_search(self, store):
        asyncio.run(store.add_episodic("修复 NPE", "定位代码", "grep", "found"))
        asyncio.run(store.add_episodic("重构", "改名", "edit_file", "ok"))
        result = asyncio.run(store.search("修复", top_k=3))
        assert len(result) == 2

    def test_search_respects_top_k(self, store):
        for i in range(5):
            asyncio.run(store.add_episodic(f"task {i}", f"step {i}", "tool", "ok"))
        result = asyncio.run(store.search("task", top_k=3))
        assert len(result) == 3

    def test_returns_most_recent(self, store):
        """Mock 返回最近添加的条目。"""
        asyncio.run(store.add_episodic("first", "s1", "t1", "r1"))
        asyncio.run(store.add_episodic("second", "s2", "t2", "r2"))
        result = asyncio.run(store.search("any", top_k=1))
        assert "second" in result[0].content

    def test_add_procedural(self, store):
        entry = asyncio.run(store.add_procedural("NPE → 先检查 null"))
        assert entry.type == "procedural"
        assert "NPE" in entry.content
        assert store.count == 1

    def test_episodic_entry_format(self, store):
        entry = asyncio.run(
            store.add_episodic("修复 NPE", "阅读源码", "read_file", "200 行读取成功")
        )
        assert entry.type == "episodic"
        assert "修复 NPE" in entry.content
        assert "read_file" in entry.content
